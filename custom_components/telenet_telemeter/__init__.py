import logging
import json
from pathlib import Path

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Config, HomeAssistant
from homeassistant.const import Platform
from .utils import TelenetSession
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
    CONF_RESOURCES,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME
)

manifestfile = Path(__file__).parent / 'manifest.json'
with open(manifestfile, 'r') as json_file:
    manifest_data = json.load(json_file)
    
DOMAIN = manifest_data.get("domain")
NAME = manifest_data.get("name")
VERSION = manifest_data.get("version")
ISSUEURL = manifest_data.get("issue_tracker")
PLATFORMS = [Platform.SENSOR]

STARTUP = """
-------------------------------------------------------------------
{name}
Version: {version}
This is a custom component
If you have any issues with this you need to open an issue here:
{issueurl}
-------------------------------------------------------------------
""".format(
    name=NAME, version=VERSION, issueurl=ISSUEURL
)


_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up this component using YAML."""
    _LOGGER.info(STARTUP)
    if config.get(DOMAIN) is None:
        # We get her if the integration is set up using config flow
        return True

    try:
        await hass.config_entries.async_forward_entry(config, Platform.SENSOR)
        _LOGGER.info("Successfully added sensor from the integration")
    except ValueError:
        pass

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data={}
        )
    )
    return True

async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry):
    await hass.config_entries.async_reload(config_entry.entry_id)

async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Reload integration when options changed"""
    await hass.config_entries.async_reload(config_entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    # if unload_ok:
        # hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up component as config entry."""
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(config_entry, Platform.SENSOR)
    )
    _LOGGER.info(f"{DOMAIN} register_services")
    register_services(hass, config_entry)
    return True


async def async_remove_entry(hass, config_entry):
    try:
        await hass.config_entries.async_forward_entry_unload(config_entry, Platform.SENSOR)
        _LOGGER.info("Successfully removed sensor from the integration")
    except ValueError:
        pass


def register_services(hass, config_entry):
    
    async def handle_switch_wireless(enableWifi, enableWifree):
        """Handle the service call."""
        
        config = config_entry.data
        username = config.get("username")
        password = config.get("password")
        internet = config.get("internet")
        if not internet:
            return
        session = TelenetSession()
        await hass.async_add_executor_job(lambda: session.login(username, password))
        v2 = await hass.async_add_executor_job(lambda: session.apiVersion2())
        if not v2:
            return
        
        # customerDetails = await hass.async_add_executor_job(lambda: session.customerdetails())
        # customerLocationId = customerDetails.get('customerLocations')[0].get('id')
        
        internetProductDetails = await hass.async_add_executor_job(lambda: session.productSubscriptions("INTERNET"))
        internetProductIdentifier = internetProductDetails[0].get('identifier')

        modemDetails = await hass.async_add_executor_job(lambda: session.modemdetails(internetProductIdentifier))
        modemMac = modemDetails.get('mac')

        productServiceDetails = await hass.async_add_executor_job(lambda: session.productService(internetProductIdentifier, "INTERNET"))
        customerLocationId = productServiceDetails.get('locationId')
        
        for lineLevelProduct in productServiceDetails.get('lineLevelProducts',[]):
            if lineLevelProduct.get('specurl'):
                 urlDetails = await hass.async_add_executor_job(lambda: session.urldetails(lineLevelProduct.get('specurl')))

        for option in productServiceDetails.get('options',[]):
            if option.get('specurl'):
                 urlDetails = await hass.async_add_executor_job(lambda: session.urldetails(option.get('specurl')))

        wifiDetails = await hass.async_add_executor_job(lambda: session.wifidetails(internetProductIdentifier, modemMac))
        # wifiEnabled = wifiDetails.get('wirelessEnabled')
        wifiEnabled = wifiDetails.get("wirelessInterfaces")[0].get('active')
        wifreeEnabled = wifiDetails.get('homeSpotEnabled')

        if enableWifi is None:
            enableWifi = wifiEnabled
        if enableWifi == "Yes":
            enableWifi = True
        else:
            enableWifi = False
        if enableWifree is None:
            enableWifree = wifreeEnabled

        # if wifiEnabled and enableWifi and wifreeEnabled == enableWifree:
        #     _LOGGER.debug(f"no wifi change required: wifiEnabled: {wifiEnabled}, enableWifi: {enableWifi}, wifreeEnabled: {wifreeEnabled}, enableWifree: {enableWifree}")
        #     return
        # else:
        _LOGGER.debug(f"wifi change required: wifiEnabled: {wifiEnabled}, enableWifi: {enableWifi}, wifreeEnabled: {wifreeEnabled}, enableWifree: {enableWifree}")

    
        await hass.async_add_executor_job(lambda: session.switchWifi(enableWifree, enableWifi, internetProductIdentifier, modemMac, customerLocationId))

        _LOGGER.debug(f"{NAME} handle_switch_wifi switch executed, old state: wifiEnabled: {wifiEnabled}, wifreeEnabled: {wifreeEnabled}, new state: enableWifi: {enableWifi}, enableWifree: {enableWifree}")
        return
        
    async def handle_switch_wifi(call):
        """Handle the service call."""
        
        enable = call.data.get('enable')
        if not(enable in ["Yes","No"]):
            return
        _LOGGER.debug(f"handle_switch_wifi: enable : {enable}")
        await handle_switch_wireless(enable, None)
        return
        
    async def handle_switch_wifree(call):
        """Handle the service call."""
        enable = call.data.get('enable')
        if not(enable in ["Yes","No"]):
            return
        _LOGGER.debug(f"handle_switch_wifree: enable : {enable}")
        await handle_switch_wireless(None, enable)
        return


    hass.services.async_register(DOMAIN, 'switch_wifi', handle_switch_wifi)
    hass.services.async_register(DOMAIN, 'switch_wifree', handle_switch_wifree)
    _LOGGER.info(f"async_register done")