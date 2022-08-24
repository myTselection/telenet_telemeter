import json
import logging
import pprint
from collections import defaultdict
from datetime import date, datetime, timedelta

import voluptuous as vol
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


def check_settings(config, hass):
    if not any(config.get(i) for i in ["username"]):
        _LOGGER.debug("username was not set")
    else:
        return True
    if not config.get("password"):
        _LOGGER.debug("password was not set")
    else:
        return True

    raise vol.Invalid("Missing settings to setup the sensor.")
