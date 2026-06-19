import logging
import json
from pathlib import Path

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .coordinator import ComponentData
from .utils import TelenetSession
from .const import PROVIDER_TELENET, PROVIDER_NAMES

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
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(config_entry.entry_id, None)
    return unload_ok


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up component as config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = await _async_setup_coordinators(
        hass,
        config_entry,
    )
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    _LOGGER.info(f"{DOMAIN} register_services")
    internet = config_entry.data.get("internet")
    if internet: 
        register_services(hass, config_entry)
    return True


async def _async_setup_coordinators(hass: HomeAssistant, config_entry: ConfigEntry):
    config = config_entry.data
    username = config.get("username")
    password = config.get("password")
    internet = config.get("internet")
    mobile = config.get("mobile")
    provider = config.get("provider", PROVIDER_TELENET)
    client = async_get_clientsession(hass)
    data_by_type = {}

    if internet:
        internet_data = ComponentData(
            username,
            password,
            True,
            False,
            client,
            hass,
            provider,
        )
        await internet_data.async_config_entry_first_refresh()
        data_by_type["internet"] = internet_data

    if mobile:
        mobile_data = ComponentData(
            username,
            password,
            False,
            True,
            client,
            hass,
            provider,
        )
        await mobile_data.async_config_entry_first_refresh()
        data_by_type["mobile"] = mobile_data

    return data_by_type


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
        provider = config.get("provider", PROVIDER_TELENET)
        session = TelenetSession(provider=provider)

        await hass.async_add_executor_job(lambda: session.login(username, password))
        provider_name = PROVIDER_NAMES.get(provider, NAME)
        _LOGGER.debug(f"{provider_name} reboot_internet login completed")
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
