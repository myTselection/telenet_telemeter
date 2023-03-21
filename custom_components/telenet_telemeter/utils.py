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
        _LOGGER.error("username was not set")
    else:
        return True
    if not config.get("password"):
        _LOGGER.error("password was not set")
    else:
        return True
    if not config.get("internet"):
        _LOGGER.error("internet bool was not set")
    else:
        return True
    if not config.get("mobile"):
        _LOGGER.error("mobile bool was not set")
    else:
        return True
        
    if config.get("internet") and config.get("mobile"):
        return True
    else:
        _LOGGER.error("At least one of internet or mobile is to be set")

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
        _LOGGER.debug("userdetails result status code:" + str(response.status_code))
        if (response.status_code == 200):
            # Return if already authenticated
            return
        
        assert response.status_code == 401
        state, nonce = response.text.split(",", maxsplit=2)

        # Log in
        response = self.s.get(f'https://login.prd.telenet.be/openid/oauth/authorize?client_id=ocapi&response_type=code&claims={{"id_token":{{"http://telenet.be/claims/roles":null,"http://telenet.be/claims/licenses":null}}}}&lang=nl&state={state}&nonce={nonce}&prompt=login',timeout=10)
            #no action
        _LOGGER.debug("login result status code: " + str(response.status_code))
        
        response = self.s.post("https://login.prd.telenet.be/openid/login.do",data={"j_username": username,"j_password": password,"rememberme": True,},timeout=10)
        _LOGGER.debug("login post result status code: " + str(response.status_code))
        assert response.status_code == 200

        self.s.headers["X-TOKEN-XSRF"] = self.s.cookies.get("TOKEN-XSRF")

        response = self.s.get(
            "https://api.prd.telenet.be/ocapi/oauth/userdetails",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
            timeout=10,
        )
        _LOGGER.debug("get userdetails result status code: " + str(response.status_code))
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
        _LOGGER.debug("telemeter result status code: " + str(response.status_code))
        _LOGGER.debug("telemeter result " + response.text)
        if response.status_code == 200:
            # return next(Telemeter.from_json(response.json()))
            return response.json()

    def telemeter_product_details(self, url):
        response = self.s.get(
            url,
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
        )
        assert response.status_code == 200
        # _LOGGER.info("telemeter_product_details result " + response.text)
        # json_string = response.text.replace("'",'"').replace("True","true").replace("False","false")
        # _LOGGER.info("telemeter_product_details json_string " + json_string)
        # return json.loads(json_string)
        return response.json()
        
    def mobile(self):
        response = self.s.get(
            "https://api.prd.telenet.be/ocapi/public/?p=mobileusage",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
            timeout=10,
        )
        _LOGGER.info("mobile result status code: " + str(response.status_code))
        _LOGGER.info("mobile result " + response.text)
        if response.status_code == 200:
            return response.json()
        
    def planInfo(self):
        response = self.s.get(
            "https://api.prd.telenet.be/ocapi/public/api/product-service/v1/product-subscriptions?producttypes=PLAN",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
            timeout=10,
        )
        _LOGGER.debug("planInfo result status code: " + str(response.status_code))
        _LOGGER.debug("planInfo result " + response.text)
        assert response.status_code == 200
        # return next(Telemeter.from_json(response.json()))
        return response.json()
    
    def billCycles(self, productType, productIdentifier):
        response = self.s.get(
            f"https://api.prd.telenet.be/ocapi/public/api/billing-service/v1/account/products/{productIdentifier}/billcycle-details?producttype={productType}&count=3",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
            timeout=10,
        )
        _LOGGER.debug("billCycles url: " + str(response.url))
        _LOGGER.debug("billCycles result status code: " + str(response.status_code))
        _LOGGER.debug("billCycles result " + response.text)
        assert response.status_code == 200
        # return next(Telemeter.from_json(response.json()))
        return response.json()
    
    def productUsage(self, productType, productIdentifier,startDate, endDate):
        response = self.s.get(
            f"https://api.prd.telenet.be/ocapi/public/api/product-service/v1/products/{productType}/{productIdentifier}/usage?fromDate={startDate}&toDate={endDate}",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
            timeout=10,
        )
        _LOGGER.debug("productUsage result status code: " + str(response.status_code))
        _LOGGER.debug("productUsage result " + response.text)
        assert response.status_code == 200
        # return next(Telemeter.from_json(response.json()))
        return response.json()

    def productSubscriptions(self, productType):
        response = self.s.get(
            f"https://api.prd.telenet.be/ocapi/public/api/product-service/v1/product-subscriptions?producttypes={productType}",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
            timeout=10,
        )
        _LOGGER.debug("productSubscriptions result status code: " + str(response.status_code))
        _LOGGER.debug("productSubscriptions result " + response.text)
        assert response.status_code == 200
        return response.json()

    def mobileUsage(self, productIdentifier):
        response = self.s.get(
            f"https://api.prd.telenet.be/ocapi/public/api/mobile-service/v3/mobilesubscriptions/{productIdentifier}/usages",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
            timeout=10,
        )
        _LOGGER.debug("mobileUsage result status code: " + str(response.status_code))
        _LOGGER.debug("mobileUsage result " + response.text)
        assert response.status_code == 200
        return response.json()
    