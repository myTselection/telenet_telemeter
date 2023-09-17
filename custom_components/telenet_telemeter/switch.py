"""Support for Wifi switches"""
import logging

from homeassistant.helpers.entity import ToggleEntity
from homeassistant.const import CONF_USERNAME

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Old way."""


async def async_setup_entry(hass, config_entry, async_add_entities):

    switches = []
    account = config_entry.data.get(CONF_USERNAME)
    audiData = hass.data[DOMAIN][account]

    switch = ComponentSwitch()
    switches.append(switch)

    async_add_entities(switches)


class ComponentSwitch():
    """Representation of a Audi switch."""

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._instrument.state

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._instrument.turn_on()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._instrument.turn_off()
