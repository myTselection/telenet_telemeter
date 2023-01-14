import logging
import asyncio
from datetime import date, datetime, timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

from . import DOMAIN, NAME
from .utils import *

_LOGGER = logging.getLogger(__name__)
_TELENET_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.0%z"


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional("username", default=""): cv.string,
        vol.Optional("password", default=""): cv.string,
        vol.Optional("internet", default=True): cv.boolean,
        vol.Optional("mobile", default=True): cv.boolean,
    }
)

#TODO check if needed
MIN_TIME_BETWEEN_UPDATES = timedelta(hours=2)


async def dry_setup(hass, config_entry, async_add_devices):
    config = config_entry
    username = config.get("username")
    password = config.get("password")
    internet = config.get("internet")
    mobile = config.get("mobile")

    check_settings(config, hass)
    sensors = []
    
    if internet:
        data_internet = ComponentData(
            username,
            password,
            internet,
            False,
            async_get_clientsession(hass),
            hass
        )
        await data_internet._init()
        sensor = ComponentInternet(data_internet, hass)
        sensors.append(sensor)
    if mobile:
        data_mobile = ComponentData(
            username,
            password,
            False,
            mobile,
            async_get_clientsession(hass),
            hass
        )
        await data_mobile._init()
        sensor = ComponentMobile(data_mobile, hass)
        sensors.append(sensor)
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
    await dry_setup(hass, config, async_add_devices)
    return True


async def async_remove_entry(hass, config_entry):
    _LOGGER.info("async_remove_entry " + NAME)
    try:
        await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
        _LOGGER.info("Successfully removed sensor from the integration")
    except ValueError:
        pass
        

class ComponentData:
    def __init__(self, username, password, internet, mobile, client, hass):
        self._username = username
        self._password = password
        self._internet = internet
        self._mobile = mobile
        self._client = client
        self._data = {}
        self._last_update = None
        self._friendly_name = None
        self._session = TelenetSession()
        self._telemeter = None
        self._mobilemeter = None
        self._hass = hass
        
    # same as update, but without throttle to make sure init is always executed
    async def _init(self):
        _LOGGER.info("Fetching intit stuff for " + NAME)
        if not(self._session):
            self._session = TelenetSession()

        if self._session:
            await self._hass.async_add_executor_job(lambda: self._session.login(self._username, self._password))
            _LOGGER.info("init login completed")
            if self._internet:
                self._telemeter = await self._hass.async_add_executor_job(lambda: self._session.telemeter())
                _LOGGER.debug(f"init telemeter data: {self._telemeter}")
            if self._mobile:
                self._mobilemeter = await self._hass.async_add_executor_job(lambda: self._session.mobile())
                _LOGGER.debug(f"init mobilemeter data: {self._mobilemeter}")
                
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def _update(self):
        _LOGGER.info("Fetching stuff for " + NAME)
        if not(self._session):
            self._session = TelenetSession()

        if self._session:
            await self._hass.async_add_executor_job(lambda: self._session.login(self._username, self._password))
            _LOGGER.info("login completed")
            if self._internet:
                self._telemeter = await self._hass.async_add_executor_job(lambda: self._session.telemeter())
                _LOGGER.debug(f"telemeter data: {self._telemeter}")
            if self._mobile:
                self._mobilemeter = await self._hass.async_add_executor_job(lambda: self._session.mobile())
                _LOGGER.debug(f"mobilemeter data: {self._mobilemeter}")

    async def update(self):
        await self._update()
    
    def clear_session():
        self._session : None



class ComponentInternet(Entity):
    def __init__(self, data, hass):
        self._data = data
        self._hass = hass
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
        self._peak_usage = None
        self._offpeak_usage = None

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._used_percentage

    async def async_update(self):
        await self._data.update()
        self._last_update =  self._data._telemeter.get('internetusage')[0].get('lastupdated')
        self._product = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('producttype') 
        self._period_start_date = datetime.strptime(self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('periodstart'), _TELENET_DATETIME_FORMAT)
        self._period_end_date = datetime.strptime(self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('periodend'), _TELENET_DATETIME_FORMAT)
        tz_info = self._period_end_date.tzinfo
        self._period_length = (self._period_end_date - self._period_start_date).days
        self._period_left = (self._period_end_date - datetime.now(tz_info)).days + 2
        _LOGGER.info(f"telemeter end date: {self._period_end_date} - now {datetime.now(tz_info)} = perdiod_left {self._period_left}")
        self._period_used = self._period_length - self._period_left
        self._period_used_percentage = round(100 * (self._period_used / self._period_length),2)
        
        self._total_volume = (self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('includedvolume') + self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('extendedvolume').get('volume')) / 1024 / 1024
        
        self._included_volume = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('includedvolume')
        self._extended_volume = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('extendedvolume').get('volume')
        
        if self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('peak') is None:
            #https://www2.telenet.be/content/www-telenet-be/nl/klantenservice/wat-is-de-telemeter
            self._wifree_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('wifree')
            self._includedvolume_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('includedvolume')
            self._extendedvolume_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('extendedvolume')
            
            self._used_percentage = round(100 * ((self._includedvolume_usage + self._extendedvolume_usage + self._wifree_usage) / ( self._included_volume + self._extended_volume)),2)
            
        else:
            #when peak indication is available, only use peak + wifree in total used counter, as offpeak is not attributed
            self._wifree_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('wifree')
            self._peak_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('peak')
            self._offpeak_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('offpeak')
            
            self._used_percentage = round(100 * ((self._peak_usage + self._wifree_usage) / ( self._included_volume + self._extended_volume)),2)

            
        
    async def async_will_remove_from_hass(self):
        """Clean up after entity before removal."""
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()


    @property
    def icon(self) -> str:
        """Shows the correct icon for container."""
        return "mdi:check-network-outline"
        #alternative: 
        #return "mdi:wifi_tethering_error"
        
    @property
    def unique_id(self) -> str:
        """Return the name of the sensor."""
        return (
            NAME + "_internet"
        )

    @property
    def name(self) -> str:
        return self.unique_id

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return {
            ATTR_ATTRIBUTION: NAME,
            "last update": self._last_update,
            "used_percentage": self._used_percentage,
            "included_volume": self._included_volume,
            "extended_volume": self._extended_volume,
            "total_volume": self._total_volume,
            "wifree_usage": self._wifree_usage,
            "includedvolume_usage": self._includedvolume_usage,
            "extendedvolume_usage": self._extendedvolume_usage,
            "peak_usage": self._peak_usage, 
            "offpeak_usage": self._offpeak_usage,
            "period_start": self._period_start_date,
            "period_end": self._period_end_date,
            "period_days_left": self._period_left,
            "period_used_percentage": self._period_used_percentage,
            "product": self._product,
            "telemeter_json": self._data._telemeter
        }

    @property
    def device_info(self) -> dict:
        """I can't remember why this was needed :D"""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": DOMAIN,
        }

    @property
    def unit(self) -> int:
        """Unit"""
        return int

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement this sensor expresses itself in."""
        return "%"

    @property
    def friendly_name(self) -> str:
        return self.unique_id
        

class ComponentMobile(Entity):
    def __init__(self, data, hass):
        self._data = data
        self._hass = hass
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
        self._peak_usage = None
        self._offpeak_usage = None

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._used_percentage

    async def async_update(self):
        await self._data.update()
        # self._last_update =  self._data._telemeter.get('internetusage')[0].get('lastupdated')
        # self._product = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('producttype') 
        # self._period_start_date = datetime.strptime(self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('periodstart'), _TELENET_DATETIME_FORMAT)
        # self._period_end_date = datetime.strptime(self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('periodend'), _TELENET_DATETIME_FORMAT)
        # tz_info = self._period_end_date.tzinfo
        # self._period_length = (self._period_end_date - self._period_start_date).days
        # self._period_left = (self._period_end_date - datetime.now(tz_info)).days + 2
        # _LOGGER.info(f"telemeter end date: {self._period_end_date} - now {datetime.now(tz_info)} = perdiod_left {self._period_left}")
        # self._period_used = self._period_length - self._period_left
        # self._period_used_percentage = round(100 * (self._period_used / self._period_length),2)
        
        # self._total_volume = (self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('includedvolume') + self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('extendedvolume').get('volume')) / 1024 / 1024
        
        # self._included_volume = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('includedvolume')
        # self._extended_volume = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('extendedvolume').get('volume')
        
        # if self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('peak') is None:
            # #https://www2.telenet.be/content/www-telenet-be/nl/klantenservice/wat-is-de-telemeter
            # self._wifree_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('wifree')
            # self._includedvolume_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('includedvolume')
            # self._extendedvolume_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('extendedvolume')
            
            # self._used_percentage = round(100 * ((self._includedvolume_usage + self._extendedvolume_usage + self._wifree_usage) / ( self._included_volume + self._extended_volume)),2)
            
        # else:
            # #when peak indication is available, only use peak + wifree in total used counter, as offpeak is not attributed
            # self._wifree_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('wifree')
            # self._peak_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('peak')
            # self._offpeak_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('offpeak')
            
            # self._used_percentage = round(100 * ((self._peak_usage + self._wifree_usage) / ( self._included_volume + self._extended_volume)),2)
            # self._last_update =  self._data._mobilemeter.get('product')[0].get('lastupdated')
        mobileproduct = self._data._mobilemeter.get('product')
        if mobileproduct:
            mobileproduct = mobileproduct[0].get('label')
        _LOGGER.info(f"mobilemeter product: {mobileproduct}")
        # mobileproduct = self._data._mobilemeter.get('product')[0].get('label')
            
        
    async def async_will_remove_from_hass(self):
        """Clean up after entity before removal."""
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()


    @property
    def icon(self) -> str:
        """Shows the correct icon for container."""
        return "mdi:check-network-outline"
        #alternative: 
        #return "mdi:wifi_tethering_error"
        
    @property
    def unique_id(self) -> str:
        """Return the name of the sensor."""
        return (
            NAME + "_mobile"
        )

    @property
    def name(self) -> str:
        return self.unique_id

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return {
            ATTR_ATTRIBUTION: NAME,
            "last update": self._last_update,
            "used_percentage": self._used_percentage,
            "included_volume": self._included_volume,
            "extended_volume": self._extended_volume,
            "total_volume": self._total_volume,
            "wifree_usage": self._wifree_usage,
            "includedvolume_usage": self._includedvolume_usage,
            "extendedvolume_usage": self._extendedvolume_usage,
            "peak_usage": self._peak_usage, 
            "offpeak_usage": self._offpeak_usage,
            "period_start": self._period_start_date,
            "period_end": self._period_end_date,
            "period_days_left": self._period_left,
            "period_used_percentage": self._period_used_percentage,
            "product": self._product,
            "telemeter_json": self._data._telemeter,
            "mobile_json": self._data._mobilemeter
        }

    @property
    def device_info(self) -> dict:
        """I can't remember why this was needed :D"""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": DOMAIN,
        }

    @property
    def unit(self) -> int:
        """Unit"""
        return int

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement this sensor expresses itself in."""
        return "%"

    @property
    def friendly_name(self) -> str:
        return self.unique_id
        
