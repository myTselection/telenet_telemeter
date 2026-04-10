"""Adds config flow for component."""
import logging
from collections import OrderedDict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
    CONF_RESOURCES,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME
)

from . import DOMAIN, NAME
from .utils import (check_settings)
from .const import PROVIDERS, PROVIDER_TELENET

_LOGGER = logging.getLogger(__name__)


def create_schema(entry, option=False):
    """Create a default schema based on if a option or if settings
    is already filled out.
    """

    if option:
        default_username = entry.data.get(CONF_USERNAME, "")
        default_password = entry.data.get(CONF_PASSWORD, "")
        default_internet = entry.data.get("internet", True)
        default_mobile = entry.data.get("mobile", True)
        default_provider = entry.data.get("provider", PROVIDER_TELENET)
    else:
        default_username = ""
        default_password = ""
        default_internet = True
        default_mobile = True
        default_provider = PROVIDER_TELENET

    data_schema = OrderedDict()
    data_schema[
        vol.Required("provider", default=default_provider, description="Provider")
    ] = vol.In(PROVIDERS)
    data_schema[
        vol.Required(CONF_USERNAME, description="Email")
    ] = str
    data_schema[
        vol.Required(CONF_PASSWORD, description="Password")
    ] = str
    data_schema[
        vol.Optional("internet", default=default_internet, description="Track internet usage?")
    ] = bool
    data_schema[
        vol.Optional("mobile", default=default_mobile, description="Track mobile usage?")
    ] = bool

    return data_schema


class Mixin:
    async def test_setup(self, user_input):
        client = async_get_clientsession(self.hass)

        try:
            check_settings(user_input, self.hass)
        except ValueError:
            self._errors["base"] = "no_valid_settings"
            return False

        if user_input.get("username"):
            username = user_input.get(CONF_USERNAME)
        else:
            self._errors["base"] = "missing username"

        if user_input.get("password"):
            password = user_input.get(CONF_PASSWORD)
        else:
            self._errors["base"] = "missing password"

        # Use explicit None check so False (unchecked) is valid
        internet = user_input.get("internet")
        if internet is None:
            self._errors["base"] = "missing internet"

        mobile = user_input.get("mobile")
        if mobile is None:
            self._errors["base"] = "missing mobile"

        return len(self._errors) == 0


class ComponentFlowHandler(Mixin, config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for component."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""

        if user_input is not None:
            await self.test_setup(user_input)
            if self._errors:
                return await self._show_config_form(user_input)
            provider = user_input.get("provider", PROVIDER_TELENET)
            return self.async_create_entry(title=f'{NAME} {provider} {user_input.get("username","")}', data=user_input)

        return await self._show_config_form(user_input)

    async def _show_config_form(self, user_input):
        """Show the configuration form to edit location data."""
        data_schema = create_schema(user_input)
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(data_schema), errors=self._errors
        )

    async def async_step_import(self, user_input):
        """Import a config entry."""
        return self.async_create_entry(title="configuration.yaml", data={})


class ComponentOptionsHandler(config_entries.OptionsFlow, Mixin):
    """Options flow handler."""

    def __init__(self, config_entry):
        self.config_entry = config_entry
        self.options = dict(config_entry.options)
        self._errors = {}

    async def async_step_init(self, user_input=None):
        return self.async_show_form(
            step_id="edit",
            data_schema=vol.Schema(create_schema(self.config_entry, option=True)),
            errors=self._errors,
        )

    async def async_step_edit(self, user_input):
        if user_input is not None:
            ok = await self.test_setup(user_input)
            if ok:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=user_input
                )
                return self.async_create_entry(title="", data={})
            else:
                self._errors["base"] = "missing data options handler"
                return self.async_show_form(
                    step_id="edit",
                    data_schema=vol.Schema(
                        create_schema(self.config_entry, option=True)
                    ),
                    errors=self._errors,
                )
