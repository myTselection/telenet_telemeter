import logging
from datetime import datetime, timedelta, time

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity

from . import DOMAIN, NAME
from .coordinator import (
    ComponentData,
    TelenetCoordinatorEntity,
    _format_last_update,
)
from .utils import check_settings
from .const import PROVIDER_TELENET

_LOGGER = logging.getLogger(__name__)
_TELENET_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.0%z"
_TELENET_DATETIME_FORMAT_V2 = "%Y-%m-%d"
_TELENET_DATETIME_FORMAT_MOBILE = "%Y-%m-%dT%H:%M:%S%z"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required("username"): cv.string,
        vol.Required("password"): cv.string,
        vol.Optional("internet", default=True): cv.boolean,
        vol.Optional("mobile", default=True): cv.boolean,
    }
)

PARALLEL_UPDATES = 1


def _entity_name(*parts) -> str:
    return " ".join(str(part).strip() for part in parts if part is not None and str(part).strip())


def _suggested_object_id(*parts) -> str:
    return _entity_name(*parts)


def _mobile_subscription_identifier(product_subscription):
    return product_subscription.get('identifier') or product_subscription.get('msisdn')


def _internet_identifier(data):
    return (data._telemeter or {}).get('productIdentifier')


async def dry_setup(hass, config_entry, async_add_devices, data_by_type=None):
    config = config_entry
    username = config.get("username")
    password = config.get("password")
    internet = config.get("internet")
    mobile = config.get("mobile")
    provider = config.get("provider", PROVIDER_TELENET)
    data_by_type = data_by_type or {}

    check_settings(config, hass)
    sensors = []
    data_internet = None

    if internet:
        data_internet = data_by_type.get("internet")
        if data_internet is None:
            data_internet = ComponentData(
                username,
                password,
                internet,
                False,
                async_get_clientsession(hass),
                hass,
                provider
            )
            await data_internet.async_config_entry_first_refresh()
        assert data_internet._telemeter is not None
        sensor = SensorInternet(data_internet, hass)
        sensor._update_from_data()
        sensors.append(sensor)
        binarysensor = SensorPeak(data_internet, hass)
        binarysensor._update_from_data()
        sensors.append(binarysensor)
        announcements = SensorAnnouncements(data_internet, hass)
        announcements._update_from_data()
        sensors.append(announcements)
    if mobile:
        data_mobile = data_by_type.get("mobile")
        if data_mobile is None:
            data_mobile = ComponentData(
                username,
                password,
                False,
                mobile,
                async_get_clientsession(hass),
                hass,
                provider
            )
            await data_mobile.async_config_entry_first_refresh()
        assert data_mobile._mobilemeter is not None
        if not data_mobile._v2:
            mobileusage = data_mobile._mobilemeter.get('mobileusage')
            for idxproduct, product in enumerate(mobileusage):
                _LOGGER.debug("enumarate mobileusage elements idx:" + str(idxproduct) + ", product: "+ str(product) + " " +  NAME)
                if product.get('sharedusage'):
                    _LOGGER.info("shared mobileusage element " +  NAME)
                    sensor = ComponentMobileShared(data_mobile, idxproduct, hass)
                    sensor._update_from_data()
                    sensors.append(sensor)
                if product.get('unassigned'):
                    _LOGGER.info("unassigned mobileusage element " +  NAME)
                    for idxunsubs, subscription in enumerate(product.get('unassigned').get('mobilesubscriptions')):
                        _LOGGER.debug("enumarate unassigned subsc elements idx:" + str(idxunsubs) + ", subscription: "+ str(subscription) + " " +  NAME)
                        sensor = SensorMobileUnassigned(data_mobile, idxproduct, idxunsubs, hass)
                        sensor._update_from_data()
                        sensors.append(sensor)
                if product.get('profiles'):
                    _LOGGER.info("assigned mobileusage element " +  NAME)
                    for idxunprofile, profile in enumerate(product.get('profiles')):
                        _LOGGER.debug("enumarate assigned profiles elements idx:" + str(idxunprofile) + ", profile: "+ str(profile) + " " +  NAME)
                        for idxunsubs, subscription in enumerate(product.get('profiles')[idxunprofile].get('mobilesubscriptions')):
                            _LOGGER.debug("enumarate assigned subsc elements idx:" + str(idxunsubs) + ", subscription: "+ str(subscription) + " " +  NAME)
                            sensor = SensorMobileAssigned(data_mobile, idxproduct, idxunprofile, idxunsubs, hass)
                            sensor._update_from_data()
                            sensors.append(sensor)
        else:
            for productSubscription in data_mobile._mobilemeter:
                _LOGGER.debug("Mobile productSubscription " +  productSubscription.get("identifier") + " [" +  productSubscription.get("label") + "]")
                sensor = SensorMobile(data_mobile, productSubscription, hass)
                sensor._update_from_data()
                sensors.append(sensor)
                # Sub-sensors: each exposes one metric as a separate HA entity
                sub_defs = [
                    ("period_days_left",      "days left",    "days", "mdi:calendar-clock"),
                    ("max_data_gb",           "max data",     "GB",   "mdi:database"),
                    ("used_percentage_data",  "usage %",      "%",    "mdi:percent"),
                    ("voice_used_minutes",    "voice used",   "min",  "mdi:phone-outgoing"),
                    ("last_update_formatted", "last update",  None,   "mdi:clock-outline"),
                ]
                for field, suffix, unit, icon in sub_defs:
                    sub = SensorMobileAttribute(data_mobile, productSubscription, hass, field, suffix, unit, icon)
                    sensors.append(sub)
        if not data_internet:
            announcements = SensorAnnouncements(data_mobile, hass)
            announcements._update_from_data()
            sensors.append(announcements)
    async_add_devices(sensors)


async def async_setup_platform(
    hass, config_entry, async_add_devices, discovery_info=None
):
    """Setup sensor platform for the ui"""
    _LOGGER.info("async_setup_platform " + NAME)
    await dry_setup(hass, config_entry, async_add_devices)
    return True


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Setup sensor platform for the ui"""
    _LOGGER.info("async_setup_entry " + NAME)
    config = config_entry.data
    data_by_type = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    await dry_setup(hass, config, async_add_devices, data_by_type)
    return True


async def async_remove_entry(hass, config_entry):
    _LOGGER.info("async_remove_entry " + NAME)
    try:
        await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
        _LOGGER.info("Successfully removed sensor from the integration")
    except ValueError:
        pass


class SensorInternet(TelenetCoordinatorEntity, Entity):
    def __init__(self, data, hass):
        super().__init__(data, hass)
        self._last_update = None
        self._used_percentage = None
        self._period_start_date = None
        self._period_end_date = None
        tz_info = None
        self._period_length = None
        self._period_left = None
        self._period_used = None
        self._total_volume = None
        self._included_volume = None
        self._extended_volume = None
        self._wifree_usage = None
        self._includedvolume_usage = None
        self._extendedvolume_usage = None
        self._period_used_percentage = None
        self._product = None
        self._download_speed = None
        self._upload_speed = None
        self._peak_usage = None
        self._offpeak_usage = None
        self._total_downloaded_gb = None
        self._squeezed = False
        self._modemMac = None
        self._wifiEnabled = None
        self._wifreeEnabled = None
        self._usage_gb = None

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._usage_gb

    def _update_from_data(self):
        if not self._data._v2:
            self._last_update =  self._data._telemeter.get('internetusage')[0].get('lastupdated')
            self._product = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('producttype') 
            self._period_start_date = datetime.strptime(self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('periodstart'), _TELENET_DATETIME_FORMAT)
            self._period_end_date = datetime.strptime(self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('periodend'), _TELENET_DATETIME_FORMAT)
            self._period_end_date = self._period_end_date + timedelta(days=1)
            tz_info = self._period_end_date.tzinfo
            self._extended_volume = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('extendedvolume').get('volume')
        else:
            self._last_update =  self._data._telemeter.get('internet').get('totalUsage').get('lastUsageDate')
            self._product =  self._data._product_details.get('product').get('labelkey','N/A')
            self._period_start_date =   datetime.strptime(self._data._telemeter.get('startDate'), _TELENET_DATETIME_FORMAT_V2)
            self._period_end_date =  datetime.strptime(self._data._telemeter.get('endDate'), _TELENET_DATETIME_FORMAT_V2)
            self._period_end_date = self._period_end_date + timedelta(days=1)
            tz_info = self._period_end_date.tzinfo
            self._extended_volume =  0
            wifiDetails = self._data._telemeter.get('wifidetails')
            self._modemMac = wifiDetails.get('modemMac')
            self._wifiEnabled = wifiDetails.get('wifiEnabled')
            self._wifreeEnabled = wifiDetails.get('wifreeEnabled')
        _LOGGER.debug(f"SensorInternet _last_update: {self._last_update}")
        _LOGGER.debug(f"SensorInternet _product: {self._product}")
        _LOGGER.debug(f"SensorInternet _period_start_date: {self._period_start_date}")
        _LOGGER.debug(f"SensorInternet _period_end_date: {self._period_end_date}")
        _LOGGER.debug(f"SensorInternet tz_info: {tz_info}")

        self._period_length = (self._period_end_date - self._period_start_date).total_seconds()
        seconds_completed = (datetime.now(tz_info) - self._period_start_date).total_seconds()
        self._period_left = round(((self._period_end_date - datetime.now(tz_info)).total_seconds())/86400,2)
        self._period_used = seconds_completed
        _LOGGER.debug(f"SensorInternet end date: {self._period_end_date} - now {datetime.now(tz_info)} = perdiod_left {self._period_left}, self._period_length {self._period_length}")
        self._period_used_percentage = round(100 * (self._period_used / self._period_length),1)

        for servicetype in self._data._product_details.get('product').get('services'):
            if servicetype.get('servicetype') == 'FIXED_INTERNET':
                for productdetails in servicetype.get('specifications'):
                    _LOGGER.debug(f"SensorInternet productdetails: {productdetails}")
                    if productdetails.get('labelkey') == "spec.fixedinternet.speed.download":
                        self._download_speed = f"{productdetails.get('value')} {productdetails.get('unit')}"
                    if productdetails.get('labelkey') == "spec.fixedinternet.speed.upload":
                        self._upload_speed = f"{productdetails.get('value')} {productdetails.get('unit')}"
                break
        
        if type(self._data._product_details.get('product').get('characteristics').get('service_category_limit')) == dict:
            self._included_volume = int((self._data._product_details.get('product').get('characteristics').get('service_category_limit').get('value'))) * 1024 * 1024
        elif type(self._data._product_details.get('product').get('characteristics').get('elementarycharacteristics')) == list:
            for elem in self._data._product_details.get('product').get('characteristics').get('elementarycharacteristics'):
                if elem.get("key") == "internet_usage_limit":
                    self._included_volume = int(elem.get('value')) * 1024 * 1024
                    break
        else:
            if not self._data._v2:
                self._included_volume = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('includedvolume')
            else:
                self._included_volume = self._data._telemeter.get('internet').get('allocatedUsage').get('units') * 1024 * 1024
        self._total_volume = (self._included_volume + self._extended_volume) / 1024 / 1024
        
        if (not self._data._v2 and self._data._telemeter and self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('peak') is None) or (self._data._v2 and self._data._telemeter and self._data._telemeter.get('internet').get('category') == 'CAP'):
            if not self._data._v2:
                self._wifree_usage = 0
                self._includedvolume_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('includedvolume')
                self._extendedvolume_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('extendedvolume')
            else:
                self._wifree_usage = 0
                self._includedvolume_usage = self._data._telemeter.get('internet').get('totalUsage').get('units', 0)
                self._extendedvolume_usage = self._data._telemeter.get('internet').get('extendedUsage').get('volume', 0)

            self._used_percentage = 0
            if ( self._included_volume + self._extended_volume) != 0:
                if not self._data._v2:
                    self._used_percentage = round(100 * ((self._includedvolume_usage + self._extendedvolume_usage ) / ( self._included_volume + self._extended_volume)),2)
                else:
                    self._used_percentage = round(100 * ((self._includedvolume_usage + self._extendedvolume_usage ) / ( (self._included_volume/1024/1024) + self._extended_volume)),2)
            else:
                if self._data._v2: 
                    if self._data._telemeter.get('internet').get('usedPercentage') != None:
                        self._used_percentage = float(self._data._telemeter.get('internet').get('usedPercentage',0))
            
            if self._used_percentage >= 100:
                self._squeezed = True
            else:
                self._squeezed = False
            
        else:
            if not self._data._v2:
                self._wifree_usage = 0
                self._peak_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('peak')
                self._offpeak_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('offpeak')
                self._squeezed = bool(self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('squeezed'))
                self._extendedvolume_usage = 0
            else:
                self._wifree_usage = 0
                self._peak_usage = round(self._data._telemeter.get('internetUsage')[0].get('totalUsage').get('peak', 0) or 0, 2)
                self._includedvolume_usage = self._peak_usage
                self._extendedvolume_usage = 0
                self._offpeak_usage = round(self._data._telemeter.get('internetUsage')[0].get('totalUsage').get('offPeak', 0) or 0, 2)
                self._total_downloaded_gb = round(self._peak_usage + self._offpeak_usage, 2)
            self._used_percentage = 0
            if ( self._included_volume + self._extended_volume) != 0:
                if not self._data._v2:
                    self._used_percentage = round(100 * ((self._peak_usage + self._wifree_usage) / ( self._included_volume + self._extended_volume)),2)
                else:
                    self._used_percentage = round(100 * ((self._peak_usage + self._wifree_usage) / ( (self._included_volume/1024/1024) + self._extended_volume)),2)
            else:
                if self._data._v2: 
                    if self._data._telemeter.get('internet').get('usedPercentage') != None:
                        self._used_percentage = float(self._data._telemeter.get('internet').get('usedPercentage',0))
                    
            if not self._data._telemeter and self._used_percentage >= 100:
                self._squeezed = True
            else:
                self._squeezed = False
            _LOGGER.debug(f"SensorInternet _wifree_usage: {self._wifree_usage}")
            _LOGGER.debug(f"SensorInternet _peak_usage: {self._peak_usage}")
            _LOGGER.debug(f"SensorInternet _offpeak_usage: {self._offpeak_usage}")
            _LOGGER.debug(f"SensorInternet _included_volume: {self._included_volume}")
            _LOGGER.debug(f"SensorInternet _extended_volume: {self._extended_volume}")
            _LOGGER.debug(f"SensorInternet _used_percentage: {self._used_percentage}")
            _LOGGER.debug(f"SensorInternet _squeezed: {self._squeezed}")

        # usage_gb = authoritative FUP/CAP counter from productUsage (only peak counts).
        # total_downloaded_gb = peak + offPeak (raw bytes, already set for v2 TURBO/FUP).
        if self._peak_usage is not None and self._offpeak_usage is not None:
            if self._data._v2:
                fup_units = (self._data._telemeter.get('internet') or {}).get('totalUsage', {}).get('units')
                self._usage_gb = round(fup_units, 2) if fup_units is not None else round(self._peak_usage, 2)
            else:
                self._usage_gb = round((self._peak_usage or 0) + (self._offpeak_usage or 0), 2)
        elif self._total_volume and self._used_percentage is not None:
            self._usage_gb = round(self._used_percentage / 100 * self._total_volume, 2)

    async def async_will_remove_from_hass(self):
        """Clean up after entity before removal."""
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()

    @property
    def icon(self) -> str:
        return "mdi:check-network-outline"
        
    @property
    def unique_id(self) -> str:
        label = self._data._telemeter.get('productLabel', '')
        pid = self._data._telemeter.get('productIdentifier')
        return f"Telenet internet {label} {pid}".strip()

    @property
    def name(self) -> str:
        return _entity_name("internet", _internet_identifier(self._data))

    @property
    def suggested_object_id(self) -> str:
        return _suggested_object_id("internet", _internet_identifier(self._data))

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_ATTRIBUTION: NAME,
            "last update": self._last_update,
            "last_update_formatted": _format_last_update(self._last_update),
            "used_percentage": self._used_percentage,
            "usage_gb": self._usage_gb,
            "peak_usage_gb": self._peak_usage,
            "offpeak_usage_gb": self._offpeak_usage,
            "total_downloaded_gb": self._total_downloaded_gb,
            "period_next_start": str(self._period_end_date)[:10] if self._period_end_date else None,
            "included_volume": self._included_volume,
            "extended_volume": self._extended_volume,
            "total_volume": self._total_volume,
            "wifree_usage": self._wifree_usage,
            "includedvolume_usage": self._includedvolume_usage,
            "extendedvolume_usage": self._extendedvolume_usage,
            "peak_usage": self._peak_usage,
            "offpeak_usage": self._offpeak_usage,
            "squeezed": self._squeezed,
            "period_start": self._period_start_date,
            "period_end": self._period_end_date,
            "period_days_left": self._period_left,
            "period_used_percentage": self._period_used_percentage,
            "product": self._product,
            "download_speed": self._download_speed,
            "upload_speed": self._upload_speed,
            "modemMac": self._modemMac,
            "wifiEnabled": self._wifiEnabled,
            "wifreeEnabled": self._wifreeEnabled
        }

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(NAME, self._data.unique_id)},
            "name": self._data.name,
            "manufacturer": NAME,
        }

    @property
    def unit(self) -> int:
        return int

    @property
    def unit_of_measurement(self) -> str:
        return "GB"

    @property
    def friendly_name(self) -> str:
        return self.name


class SensorPeak(TelenetCoordinatorEntity, BinarySensorEntity):
    def __init__(self, data, hass):
        super().__init__(data, hass)
        self._last_update = None
        self._product = None
        self._peak = None
        self._servicecategory = None
        self._download_speed = None
        self._upload_speed = None
        self._used_percentage = None
        self._peak_usage = None
        self._offpeak_usage = None
        self._wifree_usage = None
        self._included_volume = None
        self._extended_volume = None
        self._total_volume = None
        self._squeezed = False

    @property
    def is_on(self):
        return self._peak

    def _update_from_data(self):
        if not self._data._v2:
            self._last_update =  self._data._telemeter.get('internetusage')[0].get('lastupdated')
            self._product = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('producttype')  
            self._extended_volume = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('extendedvolume').get('volume') 
        else:
            self._last_update =  self._data._telemeter.get('internet').get('totalUsage').get('lastUsageDate')
            self._product =  self._data._product_details.get('product').get('labelkey','N/A')      
            self._extended_volume =  0
        self._servicecategory = self._data._product_details.get('product').get('characteristics').get('service_category')

        for servicetype in self._data._product_details.get('product').get('services'):
            if servicetype.get('servicetype') == 'FIXED_INTERNET':
                for productdetails in servicetype.get('specifications'):
                    _LOGGER.debug(f"SensorInternet productdetails: {productdetails}")
                    if productdetails.get('labelkey') == "spec.fixedinternet.speed.download":
                        self._download_speed = f"{productdetails.get('value')} {productdetails.get('unit')}"
                    if productdetails.get('labelkey') == "spec.fixedinternet.speed.upload":
                        self._upload_speed = f"{productdetails.get('value')} {productdetails.get('unit')}"
                break
            
        if type(self._data._product_details.get('product').get('characteristics').get('service_category_limit')) == dict:
            self._included_volume = int((self._data._product_details.get('product').get('characteristics').get('service_category_limit').get('value'))) * 1024 * 1024
        elif type(self._data._product_details.get('product').get('characteristics').get('elementarycharacteristics')) == list:
            for elem in self._data._product_details.get('product').get('characteristics').get('elementarycharacteristics'):
                if elem.get("key") == "internet_usage_limit":
                    self._included_volume = int(elem.get('value')) * 1024 * 1024
                    break
        else:
            if not self._data._v2:
                self._included_volume = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('includedvolume')
            else:
                self._included_volume = self._data._telemeter.get('internet').get('allocatedUsage').get('units') * 1024 * 1024
        self._total_volume = (self._included_volume + self._extended_volume) / 1024 / 1024
                
        if (not self._data._v2 and self._data._telemeter and self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('peak') is None) or (self._data._v2 and self._data._telemeter and self._data._telemeter.get('internet').get('category') == 'CAP'):
            if not self._data._v2:
                self._wifree_usage = 0
                self._includedvolume_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('includedvolume')
                self._extendedvolume_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('extendedvolume')
            else:
                self._wifree_usage = 0
                self._includedvolume_usage = self._data._telemeter.get('internet').get('totalUsage').get('units')
                self._extendedvolume_usage = self._data._telemeter.get('internet').get('extendedUsage').get('volume')
            
            self._used_percentage = 0
            if ( self._included_volume + self._extended_volume) != 0:
                self._used_percentage = round(100 * ((self._includedvolume_usage + self._extendedvolume_usage ) / ( self._included_volume + self._extended_volume)),1)
            else:
                if self._data._v2: 
                    if self._data._telemeter.get('internet').get('usedPercentage') != None:
                        self._used_percentage = float(self._data._telemeter.get('internet').get('usedPercentage'))
                    
            if self._used_percentage >= 100:
                self._download_speed = f"1 Mbps"
                self._upload_speed = f"256 Kbps"
                self._squeezed = True
            else:
                self._squeezed = False
            now = datetime.now().time()
            start_time = time(10, 0, 0)
            end_time = time(23, 59, 59)
            if start_time <= now <= end_time:
                self._peak = True
            else:
                self._peak = False
            _LOGGER.debug(f"SensorPeak _wifree_usage: {self._wifree_usage}")
            _LOGGER.debug(f"SensorPeak _includedvolume_usage: {self._includedvolume_usage}")
            _LOGGER.debug(f"SensorPeak _extendedvolume_usage: {self._extendedvolume_usage}")
            _LOGGER.debug(f"SensorPeak _download_speed: {self._download_speed}")
            _LOGGER.debug(f"SensorPeak _upload_speed: {self._upload_speed}")
            _LOGGER.debug(f"SensorPeak _squeezed: {self._squeezed}")
            _LOGGER.debug(f"SensorPeak _peak: {self._peak}")
            
        else:
            if not self._data._v2:
                self._wifree_usage = 0
                self._peak_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('peak')
                self._offpeak_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('offpeak')
                self._squeezed = bool(self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('squeezed'))
            else:
                self._wifree_usage = 0
                self._peak_usage = round(self._data._telemeter.get('internetUsage')[0].get('totalUsage').get('peak', 0) or 0, 1)
                self._includedvolume_usage = self._peak_usage
                self._offpeak_usage = round(self._data._telemeter.get('internetUsage')[0].get('totalUsage').get('offPeak', 0) or 0, 1)
            
            self._used_percentage = 0
            if ( self._included_volume + self._extended_volume) != 0:
                self._used_percentage = round(100 * ((self._peak_usage + self._wifree_usage) / ( self._included_volume + self._extended_volume)),1)
            else:
                if self._data._v2:
                    if self._data._telemeter.get('internet').get('usedPercentage') != None:
                        self._used_percentage = float(self._data._telemeter.get('internet').get('usedPercentage'))
            if not self._data._telemeter and self._used_percentage >= 100:
                self._squeezed = True
            else:
                self._squeezed = False
            
            if self._used_percentage >= 100:
                self._download_speed = f"10 Mbps"
                self._upload_speed = f"1 Mbps"

            now = datetime.now().time()
            start_time = time(17, 0, 0)
            end_time = time(23, 59, 59)
            if start_time <= now <= end_time:
                self._peak = True
            else:
                self._peak = False
            
        
    async def async_will_remove_from_hass(self):
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()

    @property
    def icon(self) -> str:
        return "mdi:check-network-outline"
        
    @property
    def unique_id(self) -> str:
        label = self._data._telemeter.get('productLabel', '')
        pid = self._data._telemeter.get('productIdentifier')
        return f"Telenet peak {label} {pid}".strip()

    @property
    def name(self) -> str:
        return _entity_name("peak", _internet_identifier(self._data))

    @property
    def suggested_object_id(self) -> str:
        return _suggested_object_id("peak", _internet_identifier(self._data))

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_ATTRIBUTION: NAME,
            "last update": self._last_update,
            "used_percentage": self._used_percentage,
            "peak": self._peak,
            "wifree_usage": self._wifree_usage,
            "peak_usage": self._peak_usage, 
            "offpeak_usage": self._offpeak_usage,
            "squeezed": self._squeezed,
            "servicecategory": self._servicecategory,
            "download_speed": self._download_speed,
            "upload_speed": self._upload_speed
        }

    @property
    def friendly_name(self) -> str:
        return self.name

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(NAME, self._data.unique_id)},
            "name": self._data.name,
            "manufacturer": NAME,
        }


class ComponentMobileShared(TelenetCoordinatorEntity, Entity):
    def __init__(self, data, productid, hass):
        super().__init__(data, hass)
        self._productid = productid
        self._last_update = None
        self._total_volume_data = None
        self._total_volume_text = None
        self._total_volume_voice = None
        self._remaining_volume_data = None
        self._remaining_volume_text = None
        self._remaining_volume_voice = None
        self._used_percentage_data = None
        self._used_percentage_text = None
        self._used_percentage_voice = None
        self._period_end_date = None
        self._outofbundle = None
        tz_info = None
        self._product = None

    @property
    def state(self):
        return self._used_percentage_data

    def _update_from_data(self):
        _LOGGER.debug(f"mobilemeter ComponentMobileShared productid: {self._productid}")
        
        if not self._data._v2:
            mobileusage = self._data._mobilemeter.get('mobileusage')
            productdetails = mobileusage[self._productid]
            
            self._last_update =  productdetails.get('lastupdated')
            self._product = productdetails.get('label')
            self._period_end_date = productdetails.get('nextbillingdate')
            original_datetime = datetime.strptime(self._period_end_date, _TELENET_DATETIME_FORMAT_MOBILE)
            new_datetime = original_datetime + timedelta(days=1)
            self._period_end_date = new_datetime.strftime(_TELENET_DATETIME_FORMAT_MOBILE)
            sharedusage = productdetails.get('sharedusage')
            
            if sharedusage:
                if sharedusage.get('included'):
                    if sharedusage.get('included').get('data'):
                        self._total_volume_data = f"{sharedusage.get('included').get('data').get('startunits')} {sharedusage.get('included').get('data').get('unittype')}"
                        self._used_percentage_data = sharedusage.get('included').get('data').get('usedpercentage')
                        self._remaining_volume_data = f"{sharedusage.get('included').get('data').get('remainingunits')} {sharedusage.get('included').get('data').get('unittype')}"
                        
                    if sharedusage.get('included').get('text'):
                        self._total_volume_text = f"{sharedusage.get('included').get('text').get('startunits')} {sharedusage.get('included').get('text').get('unittype')}"
                        self._used_percentage_text = sharedusage.get('included').get('text').get('remainingunits') + ' ' + sharedusage.get('included').get('text').get('unittype')
                        self._remaining_volume_text = f"{sharedusage.get('included').get('text').get('remainingunits')} {sharedusage.get('included').get('data').get('unittype')}"
                        
                    if sharedusage.get('included').get('voice'):
                        self._total_volume_voice = f"{sharedusage.get('included').get('voice').get('startunits')} {sharedusage.get('included').get('voice').get('unittype')}"
                        self._used_percentage_voice = sharedusage.get('included').get('voice').get('usedpercentage')
                        self._remaining_volume_voice = f"{sharedusage.get('included').get('voice').get('remainingunits')} {sharedusage.get('included').get('voice').get('unittype')}"
                    
                if sharedusage.get('outofbundle'):
                    self._outofbundle = f"{sharedusage.get('outofbundle').get('usedunits')} {sharedusage.get('outofbundle').get('unittype')}"

        
    async def async_will_remove_from_hass(self):
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()

    @property
    def icon(self) -> str:
        return "mdi:check-network-outline"
        
    @property
    def unique_id(self) -> str:
        return f"{NAME} mobile shared {self._productid}"

    @property
    def name(self) -> str:
        return _entity_name("mobile shared", self._productid)

    @property
    def suggested_object_id(self) -> str:
        return _suggested_object_id("mobile shared", self._productid)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_ATTRIBUTION: NAME,
            "last update": self._last_update,
            "used_percentage_data": self._used_percentage_data,
            "used_percentage_text": self._used_percentage_text,
            "used_percentage_voice": self._used_percentage_voice,
            "total_volume_data": self._total_volume_data,
            "total_volume_text": self._total_volume_text,
            "total_volume_voice": self._total_volume_voice,
            "remaining_volume_data": self._remaining_volume_data,
            "remaining_volume_text": self._remaining_volume_text,
            "remaining_volume_voice": self._remaining_volume_voice,
            "period_end": self._period_end_date,
            "product": self._product,
            "outofbundle" : self._outofbundle,
            "mobile_json": self._data._mobilemeter
        }

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(NAME, self._data.unique_id)},
            "name": self._data.name,
            "manufacturer": NAME,
        }

    @property
    def unit(self) -> int:
        return int

    @property
    def unit_of_measurement(self) -> str:
        return "%"

    @property
    def friendly_name(self) -> str:
        return self.name
        
class SensorMobileUnassigned(TelenetCoordinatorEntity, Entity):
    def __init__(self, data, productid, subsid, hass):
        super().__init__(data, hass)
        self._productid = productid
        self._subsid = subsid
        self._last_update = None
        self._total_volume_data = None
        self._total_volume_text = None
        self._total_volume_voice = None
        self._remaining_volume_data = None
        self._remaining_volume_text = None
        self._remaining_volume_voice = None
        self._used_percentage_data = None
        self._used_percentage_text = None
        self._used_percentage_voice = None
        self._period_end_date = None
        self._product = None
        self._number = None
        self._active = None
        self._outofbundle = None
        self._mobileinternetonly = None  

    @property
    def state(self):
        return self._used_percentage_data

    def _update_from_data(self):
        _LOGGER.debug(f"mobilemeter ComponentMobileShared subsid: {self._subsid}")
        
        mobileusage = self._data._mobilemeter.get('mobileusage')
        productdetails = mobileusage[self._productid]
        
        self._last_update =  productdetails.get('lastupdated')
        self._product = productdetails.get('label')
        self._period_end_date = productdetails.get('nextbillingdate')
        original_datetime = datetime.strptime(self._period_end_date, _TELENET_DATETIME_FORMAT_MOBILE)
        new_datetime = original_datetime + timedelta(days=1)
        self._period_end_date = new_datetime.strftime(_TELENET_DATETIME_FORMAT_MOBILE)
        unassignesub = productdetails.get('unassigned').get('mobilesubscriptions')[self._subsid]
        
        if unassignesub:
            if unassignesub.get('included'):
                if unassignesub.get('included').get('data'):
                    self._total_volume_data = f"{unassignesub.get('included').get('data').get('startunits')} {unassignesub.get('included').get('data').get('unittype')}"
                    self._used_percentage_data = unassignesub.get('included').get('data').get('usedpercentage')
                    self._remaining_volume_data = f"{unassignesub.get('included').get('data').get('remainingunits')} {unassignesub.get('included').get('data').get('unittype')}"
                    
                if unassignesub.get('included').get('text'):
                    self._total_volume_text = f"{unassignesub.get('included').get('text').get('startunits')} {unassignesub.get('included').get('text').get('unittype')}"
                    self._used_percentage_text = unassignesub.get('included').get('text').get('usedpercentage')
                    self._remaining_volume_text = f"{unassignesub.get('included').get('text').get('remainingunits')} {unassignesub.get('included').get('text').get('unittype')}"
                    
                if unassignesub.get('included').get('voice'):
                    self._total_volume_voice = f"{unassignesub.get('included').get('voice').get('startunits')} {unassignesub.get('included').get('voice').get('unittype')}"
                    self._used_percentage_voice = unassignesub.get('included').get('voice').get('usedpercentage')
                    self._remaining_volume_voice = f"{unassignesub.get('included').get('voice').get('remainingunits')} {unassignesub.get('included').get('voice').get('unittype')}"
                
            self._number = unassignesub.get('mobile')
            self._active = unassignesub.get('activationstate')
            if unassignesub.get('outofbundle'): 
                self._outofbundle = f"{unassignesub.get('outofbundle').get('usedunits')} {unassignesub.get('outofbundle').get('unittype')}"
            self._mobileinternetonly = unassignesub.get('mobileinternetonly')               
                
    async def async_will_remove_from_hass(self):
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()

    @property
    def icon(self) -> str:
        return "mdi:check-network-outline"
        
    @property
    def unique_id(self) -> str:
        return (
            f"{NAME} mobile {self._data._mobilemeter.get('mobileusage')[self._productid].get('unassigned').get('mobilesubscriptions')[self._subsid].get('mobile')}"
        )

    @property
    def name(self) -> str:
        return _entity_name(
            "mobile",
            self._data._mobilemeter.get('mobileusage')[self._productid].get('unassigned').get('mobilesubscriptions')[self._subsid].get('mobile')
        )

    @property
    def suggested_object_id(self) -> str:
        return _suggested_object_id(
            "mobile",
            self._data._mobilemeter.get('mobileusage')[self._productid].get('unassigned').get('mobilesubscriptions')[self._subsid].get('mobile')
        )

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_ATTRIBUTION: NAME,
            "last update": self._last_update,
            "used_percentage_data": self._used_percentage_data,
            "used_percentage_text": self._used_percentage_text,
            "used_percentage_voice": self._used_percentage_voice,
            "total_volume_data": self._total_volume_data,
            "total_volume_text": self._total_volume_text,
            "total_volume_voice": self._total_volume_voice,
            "remaining_volume_data": self._remaining_volume_data,
            "remaining_volume_text": self._remaining_volume_text,
            "remaining_volume_voice": self._remaining_volume_voice,
            "period_end": self._period_end_date,
            "product": self._product,
            "mobile_json": self._data._mobilemeter,
            "number" : self._number,
            "active" : self._active,
            "outofbundle" : self._outofbundle,
            "mobileinternetonly" :  self._mobileinternetonly
        }

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(NAME, self._data.unique_id)},
            "name": self._data.name,
            "manufacturer": NAME,
        }

    @property
    def unit(self) -> int:
        return int

    @property
    def unit_of_measurement(self) -> str:
        return "%"

    @property
    def friendly_name(self) -> str:
        return self.name
        
class SensorMobileAssigned(TelenetCoordinatorEntity, Entity):
    def __init__(self, data, productid, profileid, subsid, hass):
        super().__init__(data, hass)
        self._productid = productid
        self._profileid = profileid
        self._subsid = subsid
        self._last_update = None
        self._total_volume_data = None
        self._total_volume_text = None
        self._total_volume_voice = None
        self._remaining_volume_data = None
        self._remaining_volume_text = None
        self._remaining_volume_voice = None
        self._remaining_volume = None
        self._remaining_volume_text = None
        self._remaining_volume_voice = None
        self._used_percentage_data = None
        self._used_percentage_text = None
        self._used_percentage_voice = None
        self._period_end_date = None
        self._product = None
        self._number = None
        self._active = None
        self._outofbundle = None
        self._mobileinternetonly = None  
        self._firstname = None
        self._lastname = None
        self._role = None

    @property
    def state(self):
        return self._used_percentage_data

    def _update_from_data(self):
        _LOGGER.debug(f"mobilemeter ComponentMobileShared subsid: {self._subsid}")
        
        mobileusage = self._data._mobilemeter.get('mobileusage')
        productdetails = mobileusage[self._productid]
        
        self._last_update =  productdetails.get('lastupdated')
        self._product = productdetails.get('label')
        self._period_end_date = productdetails.get('nextbillingdate')
        original_datetime = datetime.strptime(self._period_end_date, _TELENET_DATETIME_FORMAT_MOBILE)
        new_datetime = original_datetime + timedelta(days=1)
        self._period_end_date = new_datetime.strftime(_TELENET_DATETIME_FORMAT_MOBILE)
        profile = productdetails.get('profiles')[self._profileid]
        
        if profile:
            assignesub = profile.get('mobilesubscriptions')[self._subsid]
            if assignesub:
                if assignesub.get('included'):
                    if assignesub.get('included').get('data'):
                        self._total_volume_data = f"{assignesub.get('included').get('data').get('startunits')} {assignesub.get('included').get('data').get('unittype')}"
                        self._used_percentage_data = assignesub.get('included').get('data').get('usedpercentage')
                        self._remaining_volume_data = f"{assignesub.get('included').get('data').get('remainingunits')} {assignesub.get('included').get('data').get('unittype')}"
                    
                    if assignesub.get('included').get('text'):
                        self._total_volume_text = f"{assignesub.get('included').get('text').get('startunits')} {assignesub.get('included').get('text').get('unittype')}"
                        self._used_percentage_text = assignesub.get('included').get('text').get('usedpercentage')
                        self._remaining_volume_text = f"{assignesub.get('included').get('text').get('remainingunits')} {assignesub.get('included').get('text').get('unittype')}"
                    
                    if assignesub.get('included').get('voice'):
                        self._total_volume_voice = f"{assignesub.get('included').get('voice').get('startunits')} {assignesub.get('included').get('voice').get('unittype')}"             
                        self._used_percentage_voice = assignesub.get('included').get('voice').get('usedpercentage')
                        self._remaining_volume_voice = f"{assignesub.get('included').get('voice').get('remainingunits')} {assignesub.get('included').get('voice').get('unittype')}"
                    
                self._number = assignesub.get('mobile')
                self._active = assignesub.get('activationstate')
                if assignesub.get('outofbundle'):
                    self._outofbundle = f"{assignesub.get('outofbundle').get('usedunits')} {assignesub.get('outofbundle').get('unittype')}"
                self._mobileinternetonly = assignesub.get('mobileinternetonly')    
                self._firstname = profile.get('firstname')
                self._lastname = profile.get('lastname')
                self._role = profile.get('role')                
                
    async def async_will_remove_from_hass(self):
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()

    @property
    def icon(self) -> str:
        return "mdi:check-network-outline"
        
    @property
    def unique_id(self) -> str:
        return (
            f"{NAME} mobile {self._data._mobilemeter.get('mobileusage')[self._productid].get('profiles')[self._profileid].get('mobilesubscriptions')[self._subsid].get('mobile')}"
        )

    @property
    def name(self) -> str:
        return _entity_name(
            "mobile",
            self._data._mobilemeter.get('mobileusage')[self._productid].get('profiles')[self._profileid].get('mobilesubscriptions')[self._subsid].get('mobile')
        )

    @property
    def suggested_object_id(self) -> str:
        return _suggested_object_id(
            "mobile",
            self._data._mobilemeter.get('mobileusage')[self._productid].get('profiles')[self._profileid].get('mobilesubscriptions')[self._subsid].get('mobile')
        )

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_ATTRIBUTION: NAME,
            "last update": self._last_update,
            "used_percentage_data": self._used_percentage_data,
            "used_percentage_text": self._used_percentage_text,
            "used_percentage_voice": self._used_percentage_voice,
            "total_volume_data": self._total_volume_data,
            "total_volume_text": self._total_volume_text,
            "total_volume_voice": self._total_volume_voice,
            "remaining_volume_data": self._remaining_volume_data,
            "remaining_volume_text": self._remaining_volume_text,
            "remaining_volume_voice": self._remaining_volume_voice,
            "period_end": self._period_end_date,
            "product": self._product,
            "mobile_json": self._data._mobilemeter,
            "number" : self._number,
            "active" : self._active,
            "outofbundle" : self._outofbundle,
            "mobileinternetonly" :  self._mobileinternetonly,
            "firstname": self._firstname,
            "lastnam": self._lastname,
            "role": self._role
        }

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(NAME, self._data.unique_id)},
            "name": self._data.name,
            "manufacturer": NAME,
        }

    @property
    def unit(self) -> int:
        return int

    @property
    def unit_of_measurement(self) -> str:
        return "%"

    @property
    def friendly_name(self) -> str:
        return self.name
  
class SensorMobile(TelenetCoordinatorEntity, Entity):
    def __init__(self, data, productSubscription, hass):
        super().__init__(data, hass)
        self._productSubscription = productSubscription
        self._last_update = None
        self._total_volume_data = None
        self._total_volume_text = None
        self._total_volume_voice = None
        self._remaining_volume_data = None
        self._remaining_volume_text = None
        self._remaining_volume_voice = None
        self._used_percentage_data = None
        self._used_percentage_text = None
        self._used_percentage_voice = None
        self._state = None
        self._period_end_date = None
        self._product = None
        self._label = None
        self._identifier = None
        self._activation_date = None
        self._number = None
        self._active = None
        self._outofbundle = None
        self._mobileinternetonly = None
        self._bundle_total_volume_data = None
        self._bundle_used_percentage_data = None
        self._bundle_remaining_volume_data = None
        self._bundle_total_volume_text = None
        self._bundle_total_volume_voice = None
        self._usage_gb = None
        self._max_data_gb = None
        self._data_unlimited = None
        self._period_days_left = None
        self._has_voice = False
        self._voice_used_minutes = None
        self._voice_max_minutes = None
        self._voice_unlimited = False
        self._last_update_formatted = None
        self._oob_total_eur = None
        self._oob_details = None

    @property
    def state(self):
        return self._usage_gb if self._usage_gb is not None else self._state

    @staticmethod
    def _parse_usage_gb(volume_str):
        """Parse '40.61 GB' / '7780 MB' to a float in GB, or None."""
        if not volume_str:
            return None
        try:
            parts = str(volume_str).strip().split()
            val = float(parts[0].replace(',', '.'))
            unit = parts[1].upper() if len(parts) > 1 else "GB"
            if unit == "KB":
                return round(val / 1024 / 1024, 2)
            if unit == "MB":
                return round(val / 1024, 2)
            return round(val, 2)
        except (ValueError, IndexError):
            return None

    def _update_from_data(self):
        self._identifier = self._productSubscription.get('identifier') or self._productSubscription.get('msisdn')
        _LOGGER.debug(f"Mobile sensor sync: {self._identifier}")

        parsed = self._data._mobile_line_usage.get(self._identifier)
        if parsed is None:
            _LOGGER.warning(f"No cached mobile usage for {self._identifier}, keeping previous state")
            return

        self._label = parsed.get('label')
        self._last_update = parsed.get('last_update')
        self._total_volume_data = parsed.get('total_volume_data')
        self._total_volume_text = parsed.get('total_volume_text')
        self._total_volume_voice = parsed.get('total_volume_voice')
        self._remaining_volume_data = parsed.get('remaining_volume_data')
        self._remaining_volume_text = parsed.get('remaining_volume_text')
        self._remaining_volume_voice = parsed.get('remaining_volume_voice')
        self._used_percentage_data = parsed.get('used_percentage_data')
        self._used_percentage_text = parsed.get('used_percentage_text')
        self._used_percentage_voice = parsed.get('used_percentage_voice')
        self._state = parsed.get('state')
        self._period_end_date = parsed.get('period_end_date')
        self._product = parsed.get('product')
        self._number = parsed.get('number')
        self._active = parsed.get('active')
        self._outofbundle = parsed.get('outofbundle')
        self._mobileinternetonly = parsed.get('mobileinternetonly')
        self._bundle_total_volume_data = parsed.get('bundle_total_volume_data')
        self._bundle_used_percentage_data = parsed.get('bundle_used_percentage_data')
        self._bundle_remaining_volume_data = parsed.get('bundle_remaining_volume_data')
        self._bundle_total_volume_text = parsed.get('bundle_total_volume_text')
        self._bundle_total_volume_voice = parsed.get('bundle_total_volume_voice')
        self._usage_gb = parsed.get('usage_gb')
        self._max_data_gb = parsed.get('max_data_gb')
        self._data_unlimited = parsed.get('data_unlimited')
        self._period_days_left = parsed.get('period_days_left')
        self._has_voice = parsed.get('has_voice')
        self._voice_used_minutes = parsed.get('voice_used_minutes')
        self._voice_max_minutes = parsed.get('voice_max_minutes')
        self._voice_unlimited = parsed.get('voice_unlimited')
        self._last_update_formatted = parsed.get('last_update_formatted')
        self._oob_total_eur = parsed.get('oob_total_eur')
        self._oob_details = parsed.get('oob_details')

    async def async_will_remove_from_hass(self):
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()

    @property
    def icon(self) -> str:
        return "mdi:cellphone-information"

    @property
    def unique_id(self) -> str:
        label = str(self._productSubscription.get('label', '')).split('/')[0].strip()
        pid = _mobile_subscription_identifier(self._productSubscription)
        return f"Telenet mobile {label} {pid}".strip()

    @property
    def name(self) -> str:
        return _entity_name("mobile", _mobile_subscription_identifier(self._productSubscription))

    @property
    def suggested_object_id(self) -> str:
        return _suggested_object_id("mobile", _mobile_subscription_identifier(self._productSubscription))

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_ATTRIBUTION: NAME,
            "label": self._label,
            "last update": self._last_update,
            "used_percentage_data": self._used_percentage_data,
            "used_percentage_text": self._used_percentage_text,
            "used_percentage_voice": self._used_percentage_voice,
            "total_volume_data": self._total_volume_data,
            "total_volume_text": self._total_volume_text,
            "total_volume_voice": self._total_volume_voice,
            "remaining_volume_data": self._remaining_volume_data,
            "remaining_volume_text": self._remaining_volume_text,
            "remaining_volume_voice": self._remaining_volume_voice,
            "period_end": self._period_end_date,
            "product": self._product,
            "mobile_json": self._data._mobilemeter,
            "number" : self._number,
            "active" : self._active,
            "outofbundle" : self._outofbundle,
            "mobileinternetonly" : self._mobileinternetonly,
            "bundle_total_volume_data" : self._bundle_total_volume_data,
            "bundle_used_percentage_data" : self._bundle_used_percentage_data,
            "bundle_remaining_volume_data" : self._bundle_remaining_volume_data,
            "bundle_total_volume_text" : self._bundle_total_volume_text,
            "bundle_total_volume_voice" : self._bundle_total_volume_voice,
            "usage_gb": self._usage_gb,
            "period_days_left": self._period_days_left,
            "max_data_gb": self._max_data_gb,
            "data_unlimited": self._data_unlimited,
            "has_voice": self._has_voice,
            "voice_used_minutes": self._voice_used_minutes,
            "voice_max_minutes": self._voice_max_minutes,
            "voice_unlimited": self._voice_unlimited,
            "last_update_formatted": self._last_update_formatted,
            "outofbundle_eur": self._oob_total_eur,
            "outofbundle_details": self._oob_details,
        }

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(NAME, self._data.unique_id)},
            "name": self._data.name,
            "manufacturer": NAME,
        }

    @property
    def unit(self) -> int:
        return int

    @property
    def unit_of_measurement(self) -> str:
        return "GB"

    @property
    def friendly_name(self) -> str:
        return self.name


class SensorMobileAttribute(TelenetCoordinatorEntity, Entity):
    """Exposes one parsed field from SensorMobile as a separate HA entity.

    Reads from ComponentData._mobile_parsed which is populated by the coordinator.
    No additional API calls are made.
    """

    def __init__(self, data, productSubscription, hass, field, name_suffix, unit, icon):
        super().__init__(data, hass)
        self._productSubscription = productSubscription
        self._field = field
        self._name_suffix = name_suffix
        self._unit = unit
        self._icon_str = icon

    @property
    def _identifier(self):
        return _mobile_subscription_identifier(self._productSubscription)

    @property
    def state(self):
        return (self._data._mobile_parsed.get(self._identifier) or {}).get(self._field)

    async def async_will_remove_from_hass(self):
        self._data.clear_session()

    @property
    def icon(self) -> str:
        return self._icon_str

    @property
    def unique_id(self) -> str:
        label = str(self._productSubscription.get('label', '')).split('/')[0].strip()
        pid = _mobile_subscription_identifier(self._productSubscription)
        return f"Telenet mobile {label} {pid} {self._name_suffix}".strip()

    @property
    def name(self) -> str:
        return _entity_name("mobile", _mobile_subscription_identifier(self._productSubscription), self._name_suffix)

    @property
    def suggested_object_id(self) -> str:
        return _suggested_object_id("mobile", _mobile_subscription_identifier(self._productSubscription), self._name_suffix)

    @property
    def unit_of_measurement(self):
        return self._unit

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(NAME, self._data.unique_id)},
            "name": self._data.name,
            "manufacturer": NAME,
        }

    @property
    def friendly_name(self) -> str:
        return self.name


class SensorAnnouncements(TelenetCoordinatorEntity, Entity):
    def __init__(self, data, hass):
        super().__init__(data, hass)
        self._last_update = None
        self._unread_count = None
        self._messages = None

    @property
    def state(self):
        return self._unread_count

    def _update_from_data(self):
        self._last_update = datetime.now().isoformat()
        inbox = self._data._inbox_messages
        if inbox is None:
            self._unread_count = None
            self._messages = None
            return

        messages = inbox if isinstance(inbox, list) else inbox.get("messages", [])
        if messages is None:
            messages = []

        self._messages = [
            {
                "messageId": m.get("messageId") or m.get("id"),
                "title": m.get("title"),
                "body": m.get("body") or m.get("content"),
                "type": m.get("type"),
                "createdAt": m.get("createdAt") or m.get("publishedAt"),
                "read": m.get("read", False),
            }
            for m in messages
        ]
        self._unread_count = sum(1 for m in self._messages if not m.get("read"))

    async def async_will_remove_from_hass(self):
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()

    @property
    def icon(self) -> str:
        return "mdi:bell-outline"

    @property
    def unique_id(self) -> str:
        return f"Telenet announcements {self._data._username}"

    @property
    def name(self) -> str:
        return _entity_name("announcements")

    @property
    def suggested_object_id(self) -> str:
        return _suggested_object_id("announcements")

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_ATTRIBUTION: NAME,
            "last_update": self._last_update,
            "unread_count": self._unread_count,
            "messages": self._messages,
        }

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(NAME, self._data.unique_id)},
            "name": self._data.name,
            "manufacturer": NAME,
        }

    @property
    def friendly_name(self) -> str:
        return self.name
