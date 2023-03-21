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
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "TelemeterPython/3"
        self.s.headers["x-alt-referer"] = "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice"

    def callTelenet(self, url, caller = "Not set", data = None, expectedStatusCode = "200", printResponse = False):
        if data == None:
            _LOGGER.debug(f"[{caller}] Calling GET {url}")
            response = self.s.get(url,timeout=10)
        else:
            _LOGGER.debug(f"[{caller}] Calling POST {url}")
            response = self.s.post(url,data,timeout=10)
        _LOGGER.debug(f"[{caller}] http status code = {response.status_code} (expecting {expectedStatusCode})")
        if printResponse:
            _LOGGER.debug(f"[{caller}] Response:\n{response.text}")
        if expectedStatusCode != None:
            assert response.status_code == expectedStatusCode
        
        return response

    def login(self, username, password):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/oauth/userdetails","login", None, None)
        if response.status_code == 200:
            # Return if already authenticated
            return
        assert response.status_code == 401
        # Fetch state & nonce
        state, nonce = response.text.split(",", maxsplit=2)
        # Log in
        self.callTelenet(f'https://login.prd.telenet.be/openid/oauth/authorize?client_id=ocapi&response_type=code&claims={{"id_token":{{"http://telenet.be/claims/roles":null,"http://telenet.be/claims/licenses":null}}}}&lang=nl&state={state}&nonce={nonce}&prompt=login',"login", None, None)
        self.callTelenet("https://login.prd.telenet.be/openid/login.do","login",{"j_username": username,"j_password": password,"rememberme": True}, 200)
        self.s.headers["X-TOKEN-XSRF"] = self.s.cookies.get("TOKEN-XSRF")
        self.callTelenet("https://api.prd.telenet.be/ocapi/oauth/userdetails","login", None, 200)

    def userdetails(self):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/oauth/userdetails","userdetails", None, 200)
        return response.json()

    def telemeter(self):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/public/?p=internetusage,internetusagereminder","telemeter", None, 200)
        return response.json()

    def telemeter_product_details(self, url):
        response = self.callTelenet(url,"telemeter_product_details",None, 200)
        return response.json()
        
    def mobile(self):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/public/?p=mobileusage","mobile", None, 200)
        return response.json()
        
    def planInfo(self):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/public/api/product-service/v1/product-subscriptions?producttypes=PLAN","planInfo", None, 200)
        return response.json()
    
    def billCycles(self, productType, productIdentifier):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/billing-service/v1/account/products/{productIdentifier}/billcycle-details?producttype={productType}&count=3","billCycles", None, 200)
        return response.json()
    
    def productUsage(self, productType, productIdentifier,startDate, endDate):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/product-service/v1/products/{productType}/{productIdentifier}/usage?fromDate={startDate}&toDate={endDate}","productUsage", None, 200)
        return response.json()

    def productSubscriptions(self, productType):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/product-service/v1/product-subscriptions?producttypes={productType}","productSubscriptions", None, 200)
        return response.json()

    def mobileUsage(self, productIdentifier):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/mobile-service/v3/mobilesubscriptions/{productIdentifier}/usages","mobileUsage", None, 200)
        return response.json()

    def mobileBundleUsage(self, bundleIdentifier, lineIdentifier = None):
        if lineIdentifier != None:
            response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/mobile-service/v3/mobilesubscriptions/{bundleIdentifier}/usages?type=bundle&lineIdentifier={lineIdentifier}","mobileBundleUsage lineIdentifier", None, 200)
        else:
            response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/mobile-service/v3/mobilesubscriptions/{bundleIdentifier}/usages?type=bundle","mobileBundleUsage bundle", None, 200)
        return response.json()
