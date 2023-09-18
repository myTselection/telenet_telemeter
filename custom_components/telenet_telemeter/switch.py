"""Support for Wifi switches"""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_USERNAME
from homeassistant.util import Throttle

from . import DOMAIN, NAME
from .utils import *

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=15)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Old way."""


async def async_setup_entry(hass, config_entry, async_add_entities):
    config = config_entry.data
    
    switches = []

    data = ComponentSwitch(hass, config)
    wifiSwitch = WifiSwitch(data)
    switches.append(wifiSwitch)
    wifreeSwitch = WifreeSwitch(data)
    switches.append(wifreeSwitch)

    async_add_entities(switches)

async def async_remove_entry(hass, config_entry):
    _LOGGER.info("async_remove_entry " + NAME)
    try:
        await hass.config_entries.async_forward_entry_unload(config_entry, "switch")
        _LOGGER.info("Successfully removed switch from the integration")
    except ValueError:
        pass
        

class ComponentSwitch():
    """Representation of a Audi switch."""
    def __init__(self, hass, config):
        self._hass = hass
        self._username = config.get('username')
        self._password = config.get('password')
        self._wifiState = False
        self._wifreeState = False
        self._session = TelenetSession()

    async def handle_switch_wireless(self, enableWifi, enableWifree):
        """Handle the service call."""
        
        if not(self._session):
            self._session = TelenetSession()
        await self._hass.async_add_executor_job(lambda: self._session.login(self._username, self._password))
        v2 = await self._hass.async_add_executor_job(lambda: self._session.apiVersion2())
        if not v2:
            return
        
        # customerDetails = await hass.async_add_executor_job(lambda: session.customerdetails())
        # customerLocationId = customerDetails.get('customerLocations')[0].get('id')
        
        internetProductDetails = await self._hass.async_add_executor_job(lambda: self._session.productSubscriptions("INTERNET"))
        internetProductIdentifier = internetProductDetails[0].get('identifier')

        modemDetails = await self._hass.async_add_executor_job(lambda: self._session.modemdetails(internetProductIdentifier))
        modemMac = modemDetails.get('mac')

        productServiceDetails = await self._hass.async_add_executor_job(lambda: self._session.productService(internetProductIdentifier, "INTERNET"))
        customerLocationId = productServiceDetails.get('locationId')
        
        for lineLevelProduct in productServiceDetails.get('lineLevelProducts',[]):
            if lineLevelProduct.get('specurl'):
                urlDetails = await self._hass.async_add_executor_job(lambda: self._session.urldetails(lineLevelProduct.get('specurl')))

        for option in productServiceDetails.get('options',[]):
            if option.get('specurl'):
                urlDetails = await self._hass.async_add_executor_job(lambda: self._session.urldetails(option.get('specurl')))

        wifiDetails = await self._hass.async_add_executor_job(lambda: self._session.wifidetails(internetProductIdentifier, modemMac))
        # wifiEnabled = wifiDetails.get('wirelessEnabled')
        wifiEnabled = wifiDetails.get("wirelessInterfaces")[0].get('active')
        wifreeEnabled = wifiDetails.get('homeSpotEnabled')
        _LOGGER.debug(f"wifidetails switch handle: {wifiDetails}")

        if enableWifi is None:
            enableWifi = wifiEnabled
        if enableWifi == True or enableWifi == "Yes":
            enableWifi = True
        else:
            enableWifi = False
        if enableWifree is None:
            enableWifree = wifreeEnabled
        elif enableWifree:
            enableWifree = "Yes"
        else:
            enableWifree = "No"


        # if wifiEnabled and enableWifi and wifreeEnabled == enableWifree:
        #     _LOGGER.debug(f"no wifi change required: wifiEnabled: {wifiEnabled}, enableWifi: {enableWifi}, wifreeEnabled: {wifreeEnabled}, enableWifree: {enableWifree}")
        #     return
        # else:
        _LOGGER.debug(f"wifi change required: wifiEnabled: {wifiEnabled}, enableWifi: {enableWifi}, wifreeEnabled: {wifreeEnabled}, enableWifree: {enableWifree}")

    
        await self._hass.async_add_executor_job(lambda: self._session.switchWifi(enableWifree, enableWifi, internetProductIdentifier, modemMac, customerLocationId))

        _LOGGER.debug(f"{NAME} handle_switch_wifi switch executed, old state: wifiEnabled: {wifiEnabled}, wifreeEnabled: {wifreeEnabled}, new state: enableWifi: {enableWifi}, enableWifree: {enableWifree}")
        
        
        wifiDetails = await self._hass.async_add_executor_job(lambda: self._session.wifidetails(internetProductIdentifier, modemMac))
        # wifiEnabled = wifiDetails.get('wirelessEnabled')
        self._wifiState = enableWifi
        self._wifreeState = (enableWifree == "Yes")
        self._update_required = True
        return
    
    
    async def force_update(self):
        """Handle the service call."""
        
        if not(self._session):
            self._session = TelenetSession()
        await self._hass.async_add_executor_job(lambda: self._session.login(self._username, self._password))
        v2 = await self._hass.async_add_executor_job(lambda: self._session.apiVersion2())
        if not v2:
            return
        
        # customerDetails = await hass.async_add_executor_job(lambda: session.customerdetails())
        # customerLocationId = customerDetails.get('customerLocations')[0].get('id')
        
        internetProductDetails = await self._hass.async_add_executor_job(lambda: self._session.productSubscriptions("INTERNET"))
        internetProductIdentifier = internetProductDetails[0].get('identifier')

        modemDetails = await self._hass.async_add_executor_job(lambda: self._session.modemdetails(internetProductIdentifier))
        modemMac = modemDetails.get('mac')

        productServiceDetails = await self._hass.async_add_executor_job(lambda: self._session.productService(internetProductIdentifier, "INTERNET"))
        customerLocationId = productServiceDetails.get('locationId')
        
        for lineLevelProduct in productServiceDetails.get('lineLevelProducts',[]):
            if lineLevelProduct.get('specurl'):
                urlDetails = await self._hass.async_add_executor_job(lambda: self._session.urldetails(lineLevelProduct.get('specurl')))

        for option in productServiceDetails.get('options',[]):
            if option.get('specurl'):
                urlDetails = await self._hass.async_add_executor_job(lambda: self._session.urldetails(option.get('specurl')))
        
        wifiDetails = await self._hass.async_add_executor_job(lambda: self._session.wifidetails(internetProductIdentifier, modemMac))
        # wifiEnabled = wifiDetails.get('wirelessEnabled')
        _LOGGER.debug(f"wifidetails switch update: {wifiDetails}")
        self._wifiState = bool(wifiDetails.get("wirelessInterfaces")[0].get('active'))
        self._wifreeState = (wifiDetails.get('homeSpotEnabled') == "Yes")
        return                
    
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def _update(self):
        await self.force_update()

    async def update(self):
        if self._update_required:
            # no throttle if update is required
            await self.force_update()
        else:
            await self._update()

    async def turn_on_wifi(self):
        # response = await self.handle_switch_wireless(True, None)
        # return response.get("wifiEnabled")
        await self.handle_switch_wireless(True, None)
    
    async def turn_off_wifi(self):
        # response = await self.handle_switch_wireless(False, None)
        # return response.get("wifiEnabled")
        await self.handle_switch_wireless(False, None)

    async def turn_on_wifree(self):
        # response = await self.handle_switch_wireless(None, True)
        # return response.get("wifreeEnabled")
        await self.handle_switch_wireless(None, True)
    
    async def turn_off_wifree(self):
        # response = await self.handle_switch_wireless(None, False)
        # return response.get("wifreeEnabled")
        await self.handle_switch_wireless(None, False)

class WifiSwitch(SwitchEntity):
    """Representation of a Audi switch."""
    def __init__(self, data):
        self._data = data

    @property
    def name(self) -> str:
        return self.unique_id
    
    @property
    def icon(self) -> str:
        """Shows the correct icon for container."""
        return "mdi:wifi-lock"
        
    @property
    def unique_id(self) -> str:
        """Return the name of the sensor."""
        return (
            f"{NAME} Wifi"
        )
    
    @property
    def device_info(self) -> dict:
        """I can't remember why this was needed :D"""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": DOMAIN,
        }

    async def async_update(self):
        await self._data.update()
    
    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._data._wifiState
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._data.turn_on_wifi()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._data.turn_off_wifi()

class WifreeSwitch(SwitchEntity):
    """Representation of a Audi switch."""
    def __init__(self, data):
        self._data = data

    @property
    def name(self) -> str:
        return self.unique_id
    
    @property
    def icon(self) -> str:
        """Shows the correct icon for container."""
        return "mdi:wifi-star"
        
    @property
    def unique_id(self) -> str:
        """Return the name of the sensor."""
        return (
            f"{NAME} Wi-free"
        )
    
    @property
    def device_info(self) -> dict:
        """I can't remember why this was needed :D"""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": DOMAIN,
        }

    async def async_update(self):
        await self._data.update()

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._data._wifreeState

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._data.turn_on_wifree()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._data.turn_off_wifree()