"""Shared data coordinator for the Telenet Telemeter integration."""
import logging
import re
from datetime import datetime, timedelta, timezone

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import NAME, PROVIDER_TELENET
from .utils import TelenetSession

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=240)
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _format_last_update(dt_str):
    """Format ISO datetime string to '08:00 on 27 May'."""
    if not dt_str:
        return None
    try:
        match = re.match(r'\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})', str(dt_str))
        if match:
            month, day, hour, minute = match.groups()
            return f"{hour}:{minute} on {int(day)} {_MONTHS[int(month)-1]}"
    except Exception:
        pass
    return str(dt_str)


def get_desired_internet_product(products, desired_product_type):
    _LOGGER.debug(f'products: {products}, {desired_product_type}')
    bundle_product = next((product for product in products if product.get('productType','').lower() == desired_product_type), None)
    if desired_product_type == 'bundle' and bundle_product and not bundle_product.get('products'):
        bundle_product = None
    _LOGGER.debug(f'desired_product: {bundle_product}, {desired_product_type}')

    if not bundle_product:
        return next((product for product in products if product.get('productType','').lower() == 'internet'), products[0])

    _LOGGER.debug(f'return desired_product: {bundle_product}, {desired_product_type}')
    return bundle_product


def _parse_mobile_line_usage(product_subscription, mobileusage, oob=None):
    """Parse one v2 mobile line payload into cached entity fields."""
    identifier = product_subscription.get('identifier') or product_subscription.get('msisdn')
    parsed = {
        'identifier': identifier,
        'label': product_subscription.get('label', ''),
        'last_update': None,
        'total_volume_data': None,
        'total_volume_text': None,
        'total_volume_voice': None,
        'remaining_volume_data': None,
        'remaining_volume_text': None,
        'remaining_volume_voice': None,
        'used_percentage_data': None,
        'used_percentage_text': None,
        'used_percentage_voice': None,
        'state': None,
        'period_end_date': None,
        'product': product_subscription.get('label', ''),
        'number': identifier,
        'active': product_subscription.get('status'),
        'outofbundle': None,
        'mobileinternetonly': product_subscription.get('isDataOnly', False),
        'bundle_total_volume_data': None,
        'bundle_used_percentage_data': None,
        'bundle_remaining_volume_data': None,
        'bundle_total_volume_text': None,
        'bundle_total_volume_voice': None,
        'usage_gb': None,
        'max_data_gb': None,
        'data_unlimited': None,
        'period_days_left': None,
        'has_voice': False,
        'voice_used_minutes': None,
        'voice_max_minutes': None,
        'voice_unlimited': False,
        'last_update_formatted': None,
        'oob_total_eur': None,
        'oob_details': None,
    }

    if mobileusage is None:
        return parsed

    subscription = (mobileusage.get('usage') or {}).get('subscription', {})
    breakdown = subscription.get('breakdown', {})
    bars_summary = breakdown.get('barsSummary', {})
    bars = bars_summary.get('bars', [])
    tiles = breakdown.get('tiles', [])

    plan_name = subscription.get('planName', {})
    parsed['label'] = parsed['product'] = (
        plan_name.get('nl') or plan_name.get('en') or parsed['label']
    )
    parsed['active'] = mobileusage.get('lineStatus') or parsed['active']

    next_billing = subscription.get('nextBillingDate')
    parsed['period_end_date'] = next_billing
    if next_billing:
        try:
            end_dt = datetime.fromisoformat(next_billing.replace('Z', '+00:00'))
            parsed['period_days_left'] = round(
                (end_dt - datetime.now(timezone.utc)).total_seconds() / 86400,
                1,
            )
        except Exception:
            parsed['period_days_left'] = None

    parsed['last_update'] = subscription.get('lastUpdated')
    parsed['last_update_formatted'] = _format_last_update(parsed['last_update'])

    data_bar = next((b for b in bars if b.get('category') == 'DATA'), None)
    if data_bar:
        consumed = data_bar.get('consumed', 0) or 0
        remaining = data_bar.get('remaining', 0) or 0
        total = data_bar.get('total', 0) or 0
        unit = data_bar.get('unit', 'GB')
        parsed['usage_gb'] = round(consumed, 2)
        parsed['max_data_gb'] = round(total, 2) if total else None
        parsed['data_unlimited'] = data_bar.get('lineType') == 'UNLIMITED'
        parsed['used_percentage_data'] = round(data_bar.get('consumedPercentage', 0) or 0, 1)
        parsed['total_volume_data'] = f"{consumed} {unit}"
        parsed['remaining_volume_data'] = f"{remaining} {unit}"
    elif bars_summary.get('totalConsumed') is not None:
        parsed['usage_gb'] = round(bars_summary.get('totalConsumed', 0) or 0, 2)
        parsed['max_data_gb'] = round(bars_summary.get('totalAllocated', 0) or 0, 2)

    parsed['has_voice'] = not product_subscription.get('isDataOnly', False)
    call_tile = next((t for t in tiles if t.get('category') == 'CALL'), None)
    if call_tile:
        parsed['voice_used_minutes'] = round(call_tile.get('consumed', 0) or 0, 1)
        parsed['voice_unlimited'] = call_tile.get('lineType') == 'UNLIMITED'
        total_voice = call_tile.get('total', 0) or 0
        parsed['voice_max_minutes'] = round(total_voice, 0) if total_voice > 0 else None
        parsed['total_volume_voice'] = f"{parsed['voice_used_minutes']} minutes"
    elif parsed['has_voice']:
        parsed['voice_used_minutes'] = None

    sms_tile = next((t for t in tiles if t.get('category') == 'SMS'), None)
    if sms_tile:
        parsed['total_volume_text'] = str(sms_tile.get('consumed', 0))

    parsed['state'] = parsed['used_percentage_data']

    if oob is not None:
        parsed['oob_total_eur'] = oob.get('usedUnits', '0')
        parsed['oob_details'] = {
            d.get('type'): d.get('value')
            for d in (oob.get('details') or [])
            if d.get('type')
        }

    return parsed


def _mobile_attribute_cache(parsed):
    """Return the subset used by v2 mobile sub-sensors."""
    return {
        'usage_gb': parsed.get('usage_gb'),
        'used_percentage_data': parsed.get('used_percentage_data'),
        'period_days_left': parsed.get('period_days_left'),
        'max_data_gb': parsed.get('max_data_gb'),
        'data_unlimited': parsed.get('data_unlimited'),
        'has_voice': parsed.get('has_voice'),
        'voice_used_minutes': parsed.get('voice_used_minutes'),
        'voice_max_minutes': parsed.get('voice_max_minutes'),
        'voice_unlimited': parsed.get('voice_unlimited'),
        'last_update_formatted': parsed.get('last_update_formatted'),
    }


class ComponentData:
    """Fetch and cache Telenet data behind a Home Assistant coordinator."""

    def __init__(self, username, password, internet, mobile, client, hass, provider=PROVIDER_TELENET):
        self._username = username
        self._password = password
        self._internet = internet
        self._mobile = mobile
        self._client = client
        self._provider = provider
        self._session = TelenetSession(provider=provider)
        self._telemeter = None
        self._mobilemeter = None
        self._producturl = None
        self._product_details = None
        self._inbox_messages = None
        self._v2 = None
        self._mobile_parsed = {}
        self._mobile_line_usage = {}
        self._hass = hass
        coordinator_name = "mobile" if mobile else "internet"
        self.coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=f"{NAME} {coordinator_name} {username}",
            update_method=self._async_update_data,
            update_interval=MIN_TIME_BETWEEN_UPDATES,
        )

    async def _async_update_data(self):
        try:
            await self._forced_update()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with {NAME}: {err}") from err

        return {
            "telemeter": self._telemeter,
            "mobilemeter": self._mobilemeter,
            "product_details": self._product_details,
            "inbox_messages": self._inbox_messages,
            "mobile_parsed": self._mobile_parsed,
            "mobile_line_usage": self._mobile_line_usage,
        }

    async def _forced_update(self):
        _LOGGER.info("Fetching init stuff for " + NAME)
        if not self._session:
            self._session = TelenetSession(provider=self._provider)

        if self._session:
            await self._hass.async_add_executor_job(lambda: self._session.login(self._username, self._password))
            _LOGGER.debug("ComponentData init login completed")
            if self._v2 is None:
                self._v2 = await self._hass.async_add_executor_job(lambda: self._session.apiVersion2())
                _LOGGER.info(f"Telenet API Version 2? : {self._v2}")

            if self._internet:
                if not self._v2:
                    self._telemeter = await self._hass.async_add_executor_job(lambda: self._session.telemeter())
                    self._telemeter['productIdentifier'] = self._telemeter.get('internetusage')[0].get('businessidentifier')
                else:
                    planInfo = await self._hass.async_add_executor_job(lambda: self._session.planInfo())
                    productIdentifier = ""
                    _LOGGER.debug(f"planInfo: {planInfo}")
                    desired_product = get_desired_internet_product(planInfo, 'bundle')
                    productIdentifier = desired_product.get('identifier')
                    _LOGGER.debug(f"productIdentifier internet: {productIdentifier}")
                    if desired_product.get('productType','').lower() == "bundle":
                        product = next((product for product in desired_product.get('products') if product.get('productType','').lower() == 'internet'), desired_product.get('identifier'))
                        productIdentifier = product.get('identifier')
                        _LOGGER.debug(f"productIdentifier bundle: {productIdentifier}")
                    else:
                        productIdentifier = desired_product.get('identifier')
                        _LOGGER.debug(f"productIdentifier internet: {productIdentifier}")
                    billcycles = await self._hass.async_add_executor_job(lambda: self._session.billCycles("internet", productIdentifier))
                    startDate = billcycles.get('billCycles')[0].get("startDate")
                    endDate = billcycles.get('billCycles')[0].get("endDate")
                    self._telemeter = await self._hass.async_add_executor_job(lambda: self._session.productUsage("internet", productIdentifier, startDate,endDate))
                    self._telemeter['startDate'] = startDate
                    self._telemeter['endDate'] = endDate
                    self._telemeter['productIdentifier'] = productIdentifier
                    self._telemeter['productLabel'] = desired_product.get('label', '').split('/')[0].strip()
                    dailyUsage = await self._hass.async_add_executor_job(lambda: self._session.productDailyUsage("internet", productIdentifier, startDate,endDate))
                    self._telemeter['internetUsage'] = dailyUsage.get('internetUsage')

                    internetProductIdentifier = None
                    modemMac = None
                    wifiEnabled = None
                    wifreeEnabled = None
                    try:
                        internetProductDetails = await self._hass.async_add_executor_job(lambda: self._session.productSubscriptions("INTERNET"))
                        _LOGGER.debug(f"internetProductDetails: {internetProductDetails}")

                        desired_product = get_desired_internet_product(internetProductDetails, 'internet')
                        internetProductIdentifier = desired_product.get('identifier')
                        _LOGGER.debug(f"internetProductIdentifier: {internetProductIdentifier}")

                        modemDetails = await self._hass.async_add_executor_job(lambda: self._session.modemdetails(internetProductIdentifier))
                        modemMac = modemDetails.get('mac')

                        wifiDetails = await self._hass.async_add_executor_job(lambda: self._session.wifidetails(internetProductIdentifier, modemMac))
                        wifiEnabled = wifiDetails.get('wirelessEnabled')
                        wifreeEnabled = wifiDetails.get('homeSpotEnabled')
                    except Exception:
                        _LOGGER.error('Failure in fetching wifi details')
                    self._telemeter['wifidetails'] = {'internetProductIdentifier': internetProductIdentifier, 'modemMac': modemMac, 'wifiEnabled': wifiEnabled, 'wifreeEnabled': wifreeEnabled}

                if not self._v2:
                    self._producturl = self._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('specurl')
                    _LOGGER.debug(f"ComponentData init telemeter data: {self._telemeter}")
                else:
                    self._producturl = self._telemeter.get('internet').get('specurl')
                _LOGGER.debug(f"ComponentData init telemeter data: {self._telemeter}")
                assert self._producturl is not None
                self._product_details = await self._hass.async_add_executor_job(lambda: self._session.telemeter_product_details(self._producturl))
                assert self._product_details is not None
                _LOGGER.debug(f"ComponentData init telemeter productdetails: {self._product_details}")
            try:
                self._inbox_messages = await self._hass.async_add_executor_job(lambda: self._session.inboxMessages())
                _LOGGER.debug(f"ComponentData init inbox messages: {self._inbox_messages}")
            except Exception as e:
                _LOGGER.warning(f"Failed to fetch inbox messages: {e}")
                self._inbox_messages = None

            if self._mobile:
                self._mobile_parsed = {}
                self._mobile_line_usage = {}
                if not self._v2:
                    self._mobilemeter = await self._hass.async_add_executor_job(lambda: self._session.mobile())
                else:
                    lines = await self._hass.async_add_executor_job(lambda: self._session.mobileLines())
                    enriched = []
                    for line in lines:
                        msisdn = line.get('msisdn')
                        line_data = {
                            'identifier': msisdn,
                            'msisdn': msisdn,
                            'label': '',
                            'isDataOnly': line.get('isDataOnly', False),
                            'status': line.get('status'),
                        }
                        usage = await self._hass.async_add_executor_job(lambda m=msisdn: self._session.mobileLineUsage(m))
                        oob = None
                        try:
                            oob = await self._hass.async_add_executor_job(lambda m=msisdn: self._session.mobileOutOfBundle(m))
                        except Exception as e:
                            _LOGGER.debug(f"OOB fetch failed for {msisdn}: {e}")

                        parsed = _parse_mobile_line_usage(line_data, usage, oob)
                        line_data['label'] = parsed.get('label') or ''
                        enriched.append(line_data)
                        self._mobile_line_usage[msisdn] = parsed
                        self._mobile_parsed[msisdn] = _mobile_attribute_cache(parsed)
                    self._mobilemeter = enriched
                assert self._mobilemeter is not None
                _LOGGER.debug(f"ComponentData init mobilemeter data: {self._mobilemeter}")

    async def _update(self):
        await self.coordinator.async_request_refresh()

    async def update(self):
        await self._update()

    async def async_config_entry_first_refresh(self):
        await self.coordinator.async_config_entry_first_refresh()

    def clear_session(self):
        self._session = None

    @property
    def unique_id(self):
        return f"{NAME} {self._username}"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self.unique_id


class TelenetCoordinatorEntity(CoordinatorEntity):
    """Base entity that updates its local fields from ComponentData."""

    def __init__(self, data, hass):
        super().__init__(data.coordinator)
        self._data = data
        self._hass = hass

    @property
    def should_poll(self):
        return False

    def _update_from_data(self):
        """Update local fields from the coordinator cache."""

    async def async_update(self):
        await self._data.update()
        self._update_from_data()

    def _handle_coordinator_update(self):
        self._update_from_data()
        self.async_write_ha_state()
