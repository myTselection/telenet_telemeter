import logging
import json
from pathlib import Path

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.core import HomeAssistant
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
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

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


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up this component using YAML."""
    _LOGGER.info(STARTUP)
    if config.get(DOMAIN) is None:
        # We get here if the integration is set up using config flow
        return True

    try:
        await hass.config_entries.async_forward_entry(config, Platform.SENSOR)
        _LOGGER.info("Successfully added sensor from the integration")
    except ValueError:
        pass

    hass.async_create_task(
        await hass.config_entries.flow.async_init(
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
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    _LOGGER.info(f"{DOMAIN} register_services")
    internet = config_entry.data.get("internet")
    if internet: 
        register_services(hass, config_entry)
    return True


async def async_remove_entry(hass, config_entry):
    try:
        for platform in PLATFORMS:
            await hass.config_entries.async_forward_entry_unload(config_entry, platform)
            _LOGGER.info("Successfully removed sensor from the integration")
    except ValueError:
        pass


def register_services(hass, config_entry):
        
    async def handle_reboot_internet(call):
        """Handle the service call."""
        
        config = config_entry.data
        username = config.get("username")
        password = config.get("password")
        session = TelenetSession()
        if not(session):
            session = TelenetSession()

        if session:
            await hass.async_add_executor_job(lambda: session.login(username, password))
        _LOGGER.debug(f"{NAME} reboot_internet login completed")
        v2 = await hass.async_add_executor_job(lambda: session.apiVersion2())
        if not v2:
            return
        internetProductDetails = await hass.async_add_executor_job(lambda: session.productSubscriptions("INTERNET"))
        assert internetProductDetails is not None
        internetProductIdentifier = internetProductDetails[0].get('identifier')
        assert internetProductIdentifier is not None

        modemDetails = await hass.async_add_executor_job(lambda: session.modemdetails(internetProductIdentifier))
        modemMac = modemDetails.get('mac')
        assert modemMac is not None
        assert len(modemMac) > 0
        await hass.async_add_executor_job(lambda: session.reboot(modemMac))

    hass.services.async_register(DOMAIN, 'reboot_internet', handle_reboot_internet)
    _LOGGER.info(f"async_register done")
