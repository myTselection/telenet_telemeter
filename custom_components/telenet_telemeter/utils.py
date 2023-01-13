import json
import logging
import pprint
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import List
import requests
from pydantic import BaseModel

import voluptuous as vol
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

TELENET_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.0%z"

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


class TelenetSession(object):
    def __init__(self):
        # self.s = client
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "TelemeterPython/3"

    def login(self, username, password):
        # Get OAuth2 state / nonce
        headers = {"x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice"}

        response = self.s.get("https://api.prd.telenet.be/ocapi/oauth/userdetails", headers=headers,timeout=10)
        _LOGGER.info("userdetails restult " + str(response.status_code))
        if (response.status_code == 200):
            # Return if already authenticated
            return
        
        assert response.status_code == 401
        state, nonce = response.text.split(",", maxsplit=2)

        # Log in
        response = self.s.get(f'https://login.prd.telenet.be/openid/oauth/authorize?client_id=ocapi&response_type=code&claims={{"id_token":{{"http://telenet.be/claims/roles":null,"http://telenet.be/claims/licenses":null}}}}&lang=nl&state={state}&nonce={nonce}&prompt=login',timeout=10)
            #no action
        _LOGGER.info("login result status code: " + str(response.status_code))
        
        response = self.s.post("https://login.prd.telenet.be/openid/login.do",data={"j_username": username,"j_password": password,"rememberme": True,},timeout=10)
        _LOGGER.info("post result status code: " + str(response.status_code))
        assert response.status_code == 200

        self.s.headers["X-TOKEN-XSRF"] = self.s.cookies.get("TOKEN-XSRF")

        response = self.s.get(
            "https://api.prd.telenet.be/ocapi/oauth/userdetails",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
            timeout=10,
        )
        _LOGGER.info("get userdetails result status code: " + str(response.status_code))
        assert response.status_code == 200

    def userdetails(self):
        response = self.s.get(
            "https://api.prd.telenet.be/ocapi/oauth/userdetails",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
        )
        assert response.status_code == 200
        return response.json()

    def telemeter(self):
        response = self.s.get(
            "https://api.prd.telenet.be/ocapi/public/?p=internetusage,internetusagereminder",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
            timeout=10,
        )
        _LOGGER.info("telemeter result status code: " + str(response.status_code))
        _LOGGER.info("telemeter result " + response.text)
        assert response.status_code == 200
        # return next(Telemeter.from_json(response.json()))
        return response.json()
