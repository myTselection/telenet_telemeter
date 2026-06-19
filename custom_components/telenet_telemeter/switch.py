"""Support for Wifi switches"""
import logging

from homeassistant.components.switch import SwitchEntity

from . import DOMAIN, NAME
from .coordinator import TelenetCoordinatorEntity, get_desired_internet_product
from .utils import TelenetSession
from .const import PROVIDER_TELENET

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Old way."""


async def async_setup_entry(hass, config_entry, async_add_entities):
    config = config_entry.data
    data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {}).get("internet")
    if data is None:
        _LOGGER.debug("No internet coordinator available, skipping wifi switch")
        return

    controller = ComponentSwitch(hass, config, data)
    wifiSwitch = WifiSwitch(data, controller)
    wifiSwitch._update_from_data()
    if wifiSwitch._identifier is None:
        _LOGGER.debug("No wifi identifier available, skipping wifi switch")
        return

    async_add_entities([wifiSwitch])

async def async_remove_entry(hass, config_entry):
    _LOGGER.info("async_remove_entry " + NAME)
    try:
        await hass.config_entries.async_forward_entry_unload(config_entry, "switch")
        _LOGGER.info("Successfully removed switch from the integration")
    except ValueError:
        pass


class ComponentSwitch():
    def __init__(self, hass, config, data=None):
        self._hass = hass
        self._username = config.get('username')
        self._password = config.get('password')
        self._provider = config.get('provider', PROVIDER_TELENET)
        self._data = data
        self._wifiState = None
        self._session = TelenetSession(provider=self._provider)
        self._identifier = self._cached_internet_identifier()

    def _cached_wifi_details(self):
        if not self._data or not self._data._telemeter:
            return {}
        return self._data._telemeter.get('wifidetails') or {}

    def _cached_internet_identifier(self):
        details = self._cached_wifi_details()
        if details.get('internetProductIdentifier'):
            return details.get('internetProductIdentifier')
        if self._data and self._data._telemeter:
            return self._data._telemeter.get('productIdentifier')
        return None


    async def handle_switch_wireless(self, enableWifi):
        await self._hass.async_add_executor_job(lambda: self._session.login(self._username, self._password))
        v2 = await self._hass.async_add_executor_job(lambda: self._session.apiVersion2())
        if not v2:
            return

        wifiDetails = self._cached_wifi_details()
        internetProductIdentifier = wifiDetails.get('internetProductIdentifier')
        modemMac = wifiDetails.get('modemMac')
        if not internetProductIdentifier or not modemMac:
            internetProductDetails = await self._hass.async_add_executor_job(lambda: self._session.productSubscriptions("INTERNET"))
            bundle = get_desired_internet_product(internetProductDetails, "internet")
            internetProductIdentifier = bundle.get('identifier')
            modemDetails = await self._hass.async_add_executor_job(lambda: self._session.modemdetails(internetProductIdentifier))
            modemMac = modemDetails.get('mac')
        self._identifier = internetProductIdentifier

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

        self._wifiState = enableWifi
        if self._data and self._data._telemeter:
            cached_details = self._data._telemeter.setdefault('wifidetails', {})
            cached_details['wifiEnabled'] = enableWifi
            await self._data.coordinator.async_request_refresh()
        return
    
    @property
    def unique_id(self):
        return f"{NAME} {self._username}"

    @property
    def name(self) -> str:
        return self.unique_id
    
    async def turn_on_wifi(self):
        await self.handle_switch_wireless(True)
    
    async def turn_off_wifi(self):
        await self.handle_switch_wireless(False)

class WifiSwitch(TelenetCoordinatorEntity, SwitchEntity):
    def __init__(self, data, controller):
        super().__init__(data, controller._hass)
        self._data = data
        self._controller = controller
        self._identifier = None
        self._wifiState = None

    def _update_from_data(self):
        telemeter = self._data._telemeter or {}
        wifiDetails = telemeter.get('wifidetails') or {}
        self._identifier = (
            wifiDetails.get('internetProductIdentifier')
            or telemeter.get('productIdentifier')
        )
        self._wifiState = wifiDetails.get('wifiEnabled')

    @property
    def name(self) -> str:
        return self.unique_id
    
    @property
    def icon(self) -> str:
        return "mdi:wifi-lock"
        
    @property
    def unique_id(self) -> str:
        return (
            f"{NAME} Wifi {self._identifier}"
        )
    
    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(NAME, self._data.unique_id)},
            "name": self._data.name,
            "manufacturer": NAME,
        }

    @property
    def is_on(self):
        return self._wifiState
    
    async def async_turn_on(self, **kwargs):
        await self._controller.turn_on_wifi()
        self._update_from_data()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._controller.turn_off_wifi()
        self._update_from_data()
        self.async_write_ha_state()
