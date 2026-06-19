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


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _as_list(value):
    return value if isinstance(value, list) else []


def _list_item(value, index):
    values = _as_list(value)
    return _as_dict(values[index]) if 0 <= index < len(values) else {}


def _safe_float(value, default=0):
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _empty_product_details():
    return {"product": {"services": [], "characteristics": {}}}


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
    products = [_as_dict(product) for product in _as_list(products) if _as_dict(product)]
    _LOGGER.debug(f'products: {products}, {desired_product_type}')
    if not products:
        return {}
    bundle_product = next((product for product in products if product.get('productType','').lower() == desired_product_type), None)
    if desired_product_type == 'bundle' and bundle_product and not bundle_product.get('products'):
        bundle_product = None
    _LOGGER.debug(f'desired_product: {bundle_product}, {desired_product_type}')

    if not bundle_product:
        return next((product for product in products if product.get('productType','').lower() == 'internet'), _list_item(products, 0))

    _LOGGER.debug(f'return desired_product: {bundle_product}, {desired_product_type}')
    return bundle_product


def _internet_identifier_from_product(product):
    product = _as_dict(product)
    identifier = product.get('identifier')
    if product.get('productType','').lower() != "bundle":
        return identifier

    internet_product = next(
        (
            _as_dict(child)
            for child in _as_list(product.get('products'))
            if _as_dict(child).get('productType','').lower() == 'internet'
        ),
        {},
    )
    return internet_product.get('identifier') or identifier


def _parse_mobile_line_usage(product_subscription, mobileusage, oob=None):
    """Parse one v2 mobile line payload into cached entity fields."""
    product_subscription = _as_dict(product_subscription)
    mobileusage = _as_dict(mobileusage)
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
        'used_percentage_data': 0,
        'used_percentage_text': 0,
        'used_percentage_voice': 0,
        'state': 0,
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
        'usage_gb': 0,
        'max_data_gb': 0,
        'data_unlimited': None,
        'period_days_left': 0,
        'has_voice': False,
        'voice_used_minutes': 0,
        'voice_max_minutes': None,
        'voice_unlimited': False,
        'last_update_formatted': None,
        'oob_total_eur': 0,
        'oob_details': None,
    }

    if not mobileusage:
        return parsed

    subscription = _as_dict(_as_dict(mobileusage.get('usage')).get('subscription'))
    breakdown = _as_dict(subscription.get('breakdown'))
    bars_summary = _as_dict(breakdown.get('barsSummary'))
    bars = _as_list(bars_summary.get('bars'))
    tiles = _as_list(breakdown.get('tiles'))

    plan_name = _as_dict(subscription.get('planName'))
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
            parsed['period_days_left'] = 0

    parsed['last_update'] = subscription.get('lastUpdated')
    parsed['last_update_formatted'] = _format_last_update(parsed['last_update'])

    data_bar = next((_as_dict(b) for b in bars if _as_dict(b).get('category') == 'DATA'), None)
    if data_bar:
        consumed = _safe_float(data_bar.get('consumed'))
        remaining = _safe_float(data_bar.get('remaining'))
        total = _safe_float(data_bar.get('total'))
        unit = data_bar.get('unit', 'GB')
        parsed['usage_gb'] = round(consumed, 2)
        parsed['max_data_gb'] = round(total, 2)
        parsed['data_unlimited'] = data_bar.get('lineType') == 'UNLIMITED'
        parsed['used_percentage_data'] = round(_safe_float(data_bar.get('consumedPercentage')), 1)
        parsed['total_volume_data'] = f"{consumed} {unit}"
        parsed['remaining_volume_data'] = f"{remaining} {unit}"
    elif bars_summary.get('totalConsumed') is not None:
        parsed['usage_gb'] = round(_safe_float(bars_summary.get('totalConsumed')), 2)
        parsed['max_data_gb'] = round(_safe_float(bars_summary.get('totalAllocated')), 2)

    parsed['has_voice'] = not product_subscription.get('isDataOnly', False)
    call_tile = next((_as_dict(t) for t in tiles if _as_dict(t).get('category') == 'CALL'), None)
    if call_tile:
        parsed['voice_used_minutes'] = round(_safe_float(call_tile.get('consumed')), 1)
        parsed['voice_unlimited'] = call_tile.get('lineType') == 'UNLIMITED'
        total_voice = _safe_float(call_tile.get('total'))
        parsed['voice_max_minutes'] = round(total_voice, 0) if total_voice > 0 else None
        parsed['total_volume_voice'] = f"{parsed['voice_used_minutes']} minutes"
    elif parsed['has_voice']:
        parsed['voice_used_minutes'] = 0

    sms_tile = next((_as_dict(t) for t in tiles if _as_dict(t).get('category') == 'SMS'), None)
    if sms_tile:
        parsed['total_volume_text'] = str(sms_tile.get('consumed', 0))

    parsed['state'] = parsed['used_percentage_data']

    oob = _as_dict(oob)
    if oob:
        parsed['oob_total_eur'] = _safe_float(oob.get('usedUnits'))
        parsed['oob_details'] = {
            _as_dict(d).get('type'): _as_dict(d).get('value')
            for d in _as_list(oob.get('details'))
            if _as_dict(d).get('type')
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
                    self._telemeter = _as_dict(await self._hass.async_add_executor_job(lambda: self._session.telemeter()))
                    self._telemeter['productIdentifier'] = _list_item(self._telemeter.get('internetusage'), 0).get('businessidentifier')
                else:
                    planInfo = _as_list(await self._hass.async_add_executor_job(lambda: self._session.planInfo()))
                    productIdentifier = None
                    _LOGGER.debug(f"planInfo: {planInfo}")
                    desired_product = get_desired_internet_product(planInfo, 'bundle')
                    productIdentifier = desired_product.get('identifier')
                    _LOGGER.debug(f"productIdentifier internet: {productIdentifier}")
                    if desired_product.get('productType','').lower() == "bundle":
                        productIdentifier = _internet_identifier_from_product(desired_product)
                        _LOGGER.debug(f"productIdentifier bundle: {productIdentifier}")
                    else:
                        productIdentifier = desired_product.get('identifier')
                        _LOGGER.debug(f"productIdentifier internet: {productIdentifier}")
                    billcycles = _as_dict(await self._hass.async_add_executor_job(lambda: self._session.billCycles("internet", productIdentifier))) if productIdentifier else {}
                    current_billcycle = _list_item(billcycles.get('billCycles'), 0)
                    startDate = current_billcycle.get("startDate")
                    endDate = current_billcycle.get("endDate")
                    if productIdentifier and startDate and endDate:
                        self._telemeter = _as_dict(await self._hass.async_add_executor_job(lambda: self._session.productUsage("internet", productIdentifier, startDate,endDate)))
                    else:
                        self._telemeter = {}
                    self._telemeter['internet'] = _as_dict(self._telemeter.get('internet'))
                    self._telemeter['internet'].setdefault('totalUsage', {'units': 0})
                    self._telemeter['internet'].setdefault('allocatedUsage', {'units': 0})
                    self._telemeter['internet'].setdefault('extendedUsage', {'volume': 0})
                    self._telemeter['startDate'] = startDate
                    self._telemeter['endDate'] = endDate
                    self._telemeter['productIdentifier'] = productIdentifier
                    self._telemeter['productLabel'] = desired_product.get('label', '').split('/')[0].strip()
                    dailyUsage = _as_dict(await self._hass.async_add_executor_job(lambda: self._session.productDailyUsage("internet", productIdentifier, startDate,endDate))) if productIdentifier and startDate and endDate else {}
                    self._telemeter['internetUsage'] = _as_list(dailyUsage.get('internetUsage'))

                    internetProductIdentifier = None
                    modemMac = None
                    wifiEnabled = None
                    wifreeEnabled = None
                    try:
                        internetProductDetails = _as_list(await self._hass.async_add_executor_job(lambda: self._session.productSubscriptions("INTERNET")))
                        _LOGGER.debug(f"internetProductDetails: {internetProductDetails}")

                        desired_product = get_desired_internet_product(internetProductDetails, 'internet')
                        internetProductIdentifier = desired_product.get('identifier')
                        _LOGGER.debug(f"internetProductIdentifier: {internetProductIdentifier}")

                        modemDetails = _as_dict(await self._hass.async_add_executor_job(lambda: self._session.modemdetails(internetProductIdentifier))) if internetProductIdentifier else {}
                        modemMac = modemDetails.get('mac')

                        wifiDetails = _as_dict(await self._hass.async_add_executor_job(lambda: self._session.wifidetails(internetProductIdentifier, modemMac))) if internetProductIdentifier and modemMac else {}
                        wifiEnabled = wifiDetails.get('wirelessEnabled')
                        wifreeEnabled = wifiDetails.get('homeSpotEnabled')
                    except Exception:
                        _LOGGER.error('Failure in fetching wifi details')
                    self._telemeter['wifidetails'] = {'internetProductIdentifier': internetProductIdentifier, 'modemMac': modemMac, 'wifiEnabled': wifiEnabled, 'wifreeEnabled': wifreeEnabled}

                if not self._v2:
                    internet_usage = _list_item(_list_item(_list_item(self._telemeter.get('internetusage'), 0).get('availableperiods'), 0).get('usages'), 0)
                    self._producturl = internet_usage.get('specurl')
                    _LOGGER.debug(f"ComponentData init telemeter data: {self._telemeter}")
                else:
                    self._producturl = _as_dict(self._telemeter.get('internet')).get('specurl')
                _LOGGER.debug(f"ComponentData init telemeter data: {self._telemeter}")
                self._product_details = (
                    _as_dict(await self._hass.async_add_executor_job(lambda: self._session.telemeter_product_details(self._producturl)))
                    if self._producturl
                    else _empty_product_details()
                )
                if not self._product_details:
                    self._product_details = _empty_product_details()
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
                    self._mobilemeter = _as_dict(await self._hass.async_add_executor_job(lambda: self._session.mobile()))
                    self._mobilemeter.setdefault('mobileusage', [])
                else:
                    lines = _as_list(await self._hass.async_add_executor_job(lambda: self._session.mobileLines()))
                    enriched = []
                    for line in lines:
                        line = _as_dict(line)
                        msisdn = line.get('msisdn')
                        if not msisdn:
                            continue
                        line_data = {
                            'identifier': msisdn,
                            'msisdn': msisdn,
                            'label': '',
                            'isDataOnly': line.get('isDataOnly', False),
                            'status': line.get('status'),
                        }
                        usage = _as_dict(await self._hass.async_add_executor_job(lambda m=msisdn: self._session.mobileLineUsage(m)))
                        oob = None
                        try:
                            oob = _as_dict(await self._hass.async_add_executor_job(lambda m=msisdn: self._session.mobileOutOfBundle(m)))
                        except Exception as e:
                            _LOGGER.debug(f"OOB fetch failed for {msisdn}: {e}")

                        parsed = _parse_mobile_line_usage(line_data, usage, oob)
                        line_data['label'] = parsed.get('label') or ''
                        enriched.append(line_data)
                        self._mobile_line_usage[msisdn] = parsed
                        self._mobile_parsed[msisdn] = _mobile_attribute_cache(parsed)
                    self._mobilemeter = enriched
                if self._mobilemeter is None:
                    self._mobilemeter = [] if self._v2 else {"mobileusage": []}
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
        return NAME


class TelenetCoordinatorEntity(CoordinatorEntity):
    """Base entity that updates its local fields from ComponentData."""

    _attr_has_entity_name = True

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
