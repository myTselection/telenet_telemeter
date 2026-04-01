"""Support for Wifi switches"""
import logging
from datetime import timedelta

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_USERNAME
from homeassistant.util import Throttle

from . import DOMAIN, NAME
from .utils import *
from .const import PROVIDER_TELENET

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=240)
PARALLEL_UPDATES = 1

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Old way."""


async def async_setup_entry(hass, config_entry, async_add_entities):
    config = config_entry.data
    
    switches = []

    data = ComponentSwitch(hass, config)
    
    await data.force_update()
    assert data._identifier is not None
    wifiSwitch = WifiSwitch(data)
    switches.append(wifiSwitch)

    async_add_entities(switches)

async def async_remove_entry(hass, config_entry):
    _LOGGER.info("async_remove_entry " + NAME)
    try:
        await hass.config_entries.async_forward_entry_unload(config_entry, "switch")
        _LOGGER.info("Successfully removed switch from the integration")
    except ValueError:
        pass


def get_desired_internet_product(products, desired_product_type):
    bundle_product = next((product for product in products if product.get('productType').lower() == desired_product_type), None)
    _LOGGER.debug(f'desired_product: {bundle_product}, {desired_product_type}')
    
    if not bundle_product:
        return next((product for product in products if product.get('productType').lower() == 'internet'), products[0])
    
    return bundle_product      

class ComponentSwitch():
    def __init__(self, hass, config):
        self._hass = hass
        self._username = config.get('username')
        self._password = config.get('password')
        self._provider = config.get('provider', PROVIDER_TELENET)
        self._wifiState = None
        self._session = TelenetSession(provider=self._provider)
        self._update_required = True
        self._identifier = None


    async def handle_switch_wireless(self, enableWifi):
        if not(self._session):
            self._session = TelenetSession(provider=self._provider)
        await self._hass.async_add_executor_job(lambda: self._session.login(self._username, self._password))
        v2 = await self._hass.async_add_executor_job(lambda: self._session.apiVersion2())
        if not v2:
            return
        
        internetProductDetails = await self._hass.async_add_executor_job(lambda: self._session.productSubscriptions("INTERNET"))
        bundle = get_desired_internet_product(internetProductDetails, "internet")
        internetProductIdentifier = bundle.get('identifier')
        self._identifier = internetProductIdentifier

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

        wifiStatus = await self._hass.async_add_executor_job(lambda: self._session.wifiStatus(internetProductIdentifier, modemMac))
        _LOGGER.debug(f"wifiStatus switch handle: {wifiStatus}")
        wifiEnabled = wifiStatus.get('cos') == 'WSO_SHARING'

        if enableWifi is None:
            enableWifi = wifiEnabled

        _LOGGER.debug(f"wifi change required: wifiEnabled: {wifiEnabled}, enableWifi: {enableWifi}")

        await self._hass.async_add_executor_job(lambda: self._session.switchWifi(enableWifi, internetProductIdentifier, modemMac, customerLocationId))

        _LOGGER.debug(f"{NAME} handle_switch_wifi switch executed, old state: wifiEnabled: {wifiEnabled}, new state: enableWifi: {enableWifi}")
        
        wifiDetails = await self._hass.async_add_executor_job(lambda: self._session.wifidetails(internetProductIdentifier, modemMac))
        self._wifiState = enableWifi
        self._update_required = True
        return
    
    @property
    def unique_id(self):
        return f"{NAME} {self._username}"

    @property
    def name(self) -> str:
        return self.unique_id
    
    async def force_update(self):
        if not(self._session):
            self._session = TelenetSession(provider=self._provider)
        await self._hass.async_add_executor_job(lambda: self._session.login(self._username, self._password))
        v2 = await self._hass.async_add_executor_job(lambda: self._session.apiVersion2())
        if not v2:
            return
        
        internetProductDetails = await self._hass.async_add_executor_job(lambda: self._session.productSubscriptions("INTERNET"))
        bundle = get_desired_internet_product(internetProductDetails, "internet")
        internetProductIdentifier = bundle.get('identifier')
        self._identifier = internetProductIdentifier

        modemDetails = await self._hass.async_add_executor_job(lambda: self._session.modemdetails(internetProductIdentifier))
        modemMac = modemDetails.get('mac')

        productServiceDetails = await self._hass.async_add_executor_job(lambda: self._session.productService(internetProductIdentifier, "INTERNET"))
        
        wifiStatus = await self._hass.async_add_executor_job(lambda: self._session.wifiStatus(internetProductIdentifier, modemMac))
        _LOGGER.debug(f"wifiStatus switch handle: {wifiStatus}")
        wifiEnabled = wifiStatus.get('cos') == 'WSO_SHARING'
        self._wifiState = wifiEnabled
        self._update_required = False
        return                
    
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def _update(self):
        await self.force_update()

    async def update(self):
        if self._update_required:
            await self.force_update()
        else:
            await self._update()

    async def turn_on_wifi(self):
        await self.handle_switch_wireless(True)
    
    async def turn_off_wifi(self):
        await self.handle_switch_wireless(False)

class WifiSwitch(SwitchEntity):
    def __init__(self, data):
        self._data = data

    @property
    def name(self) -> str:
        return self.unique_id
    
    @property
    def icon(self) -> str:
        return "mdi:wifi-lock"
        
    @property
    def unique_id(self) -> str:
        return (
            f"{NAME} Wifi {self._data._identifier}"
        )
    
    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(NAME, self._data.unique_id)},
            "name": self._data.name,
            "manufacturer": NAME,
        }

    async def async_update(self):
        await self._data.update()
    
    @property
    def is_on(self):
        return self._data._wifiState
    
    async def async_turn_on(self, **kwargs):
        await self._data.turn_on_wifi()

    async def async_turn_off(self, **kwargs):
        await self._data.turn_off_wifi()
