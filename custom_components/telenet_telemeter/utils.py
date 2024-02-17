import json
import logging
import pprint
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import List
import requests
from pydantic import BaseModel
from enum import Enum

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

class HttpMethod(Enum):
    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    PATCH = 'PATCH'
    DELETE = 'DELETE'
    HEAD = 'HEAD'
    OPTIONS = 'OPTIONS'
    

class TelenetSession(object):
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        # self.s.headers["x-alt-referer"] = "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice"
        self.s.headers["x-alt-referer"] = "https://www2.telenet.be/residential/nl/mijn-telenet"

    def callTelenet(self, url, caller = "Not set", expectedStatusCode = 200, data = None, printResponse = False, method : HttpMethod  = HttpMethod.GET):
        if method == HttpMethod.GET:
            _LOGGER.debug(f"[{caller}] Calling GET {url}")
            response = self.s.get(url,timeout=30)
        elif method == HttpMethod.POST:
            # self.s.headers["Content-Type"] = "application/json;charset=UTF-8"
            _LOGGER.debug(f"[{caller}] Calling POST {url} with data {data}")
            response = self.s.post(url,data,timeout=30)
        elif method == HttpMethod.PATCH:
            self.s.headers["Content-Type"] = "application/json;charset=UTF-8"
            _LOGGER.debug(f"[{caller}] Calling PATCH {url} with data: {data}")
            response = self.s.patch(url,json=data,timeout=60)
        elif method == HttpMethod.OPTIONS:
            self.s.headers["Content-Type"] = "application/json;charset=UTF-8"
            _LOGGER.debug(f"[{caller}] Calling OPTIONS {url} with data: {data}")
            response = self.s.options(url,timeout=60)
        _LOGGER.debug(f"[{caller}] http status code = {response.status_code} (expecting {expectedStatusCode})")
        if printResponse:
            _LOGGER.debug(f"[{caller}] Response: {response.text}")
        if expectedStatusCode != None:
            assert response.status_code == expectedStatusCode
        
        return response

    def login(self, username, password):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/oauth/userdetails","login", None)
        if response.status_code == 200:
            # Return if already authenticated
            return
        assert response.status_code == 401
        # Fetch state & nonce
        _LOGGER.debug(f"loging response to split state, nonce: {response.text}")
        state, nonce = response.text.split(",", maxsplit=2)
        # Log in
        self.callTelenet(f'https://login.prd.telenet.be/openid/oauth/authorize?client_id=ocapi&response_type=code&claims={{"id_token":{{"http://telenet.be/claims/roles":null,"http://telenet.be/claims/licenses":null}}}}&lang=nl&state={state}&nonce={nonce}&prompt=login',"login", None)
        self.callTelenet("https://login.prd.telenet.be/openid/login.do","login", 200, {"j_username": username,"j_password": password,"rememberme": True}, False, HttpMethod.POST)
        self.s.headers["X-TOKEN-XSRF"] = self.s.cookies.get("TOKEN-XSRF")
        self.callTelenet("https://api.prd.telenet.be/ocapi/oauth/userdetails","login")

    def userdetails(self):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/oauth/userdetails","userdetails", None)
        return response.json()
    
    def customerdetails(self):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/public/api/customer-service/v1/customers","customerdetails")
        return response.json()

    def telemeter(self):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/public/?p=internetusage,internetusagereminder","telemeter")
        return response.json()

    def telemeter_product_details(self, url):
        response = self.callTelenet(url,"telemeter_product_details")
        return response.json()

    def modemdetails(self, productIdentifier):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems?productIdentifier={productIdentifier}","modemdetails")
        return response.json()
    
    def wifidetails(self, productIdentifier, modemMac):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems/{modemMac}/wireless-settings?withmetadata=true&withwirelessservice=true&productidentifier={productIdentifier}","wifidetails")
        return response.json()
    
    def urldetails(self, url):
        response = self.callTelenet(url,"urldetails")
        return response.json()
    
    def switchWifi(self, homeSpotEnabled, wirelessEnabled: bool, productIdentifier: bool, modemMac, locationId):
        if homeSpotEnabled:
            homeSpotEnabled = "Yes"
        else:
            homeSpotEnabled = "No"
        
        data = {"productIdentifier":productIdentifier,"homeSpotEnabled":homeSpotEnabled,"wirelessEnabled":"Yes","locationId":locationId,"patchOperations":[{"op":"replace","path":"/wirelessInterfaces/2.4GHZ/ssids/PRIMARY/active","value":wirelessEnabled},{"op":"replace","path":"/wirelessInterfaces/5GHZ/ssids/PRIMARY/active","value":wirelessEnabled}]}
        self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems/{modemMac}/wireless-settings","optionswifi", 200, None, True, HttpMethod.OPTIONS)
        self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems/{modemMac}/wireless-settings","patchwifi", 200, data, True, HttpMethod.PATCH)
        return
    
    def reboot(self, modemMac):
        self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems/{modemMac}/reboot","modem_general reboot", 200, None, True, HttpMethod.POST)
        return
    
    def mobile(self):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/public/?p=mobileusage","mobile")
        return response.json()
        
    def planInfo(self):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/public/api/product-service/v1/product-subscriptions?producttypes=PLAN","planInfo")
        return response.json()
    
    def billCycles(self, productType, productIdentifier):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/billing-service/v1/account/products/{productIdentifier}/billcycle-details?producttype={productType}&count=3","billCycles")
        return response.json()
    
    def productUsage(self, productType, productIdentifier,startDate, endDate):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/product-service/v1/products/{productType}/{productIdentifier}/usage?fromDate={startDate}&toDate={endDate}","productUsage")
        return response.json()
    
    def productDailyUsage(self, productType, productIdentifier,startDate, endDate):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/product-service/v1/products/{productType}/{productIdentifier}/dailyusage?billcycle=CURRENT&fromDate={startDate}&toDate={endDate}","productUsage")
        return response.json()

    def productSubscriptions(self, productType):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/product-service/v1/product-subscriptions?producttypes={productType}","productSubscriptions")
        return response.json()

    def productService(self, productIdentifier, productType):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/product-service/v1/products/{productIdentifier}?producttype={productType.lower()}","productService")
        return response.json()

    def mobileUsage(self, productIdentifier):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/mobile-service/v3/mobilesubscriptions/{productIdentifier}/usages","mobileUsage")
        return response.json()

    def mobileBundleUsage(self, bundleIdentifier, lineIdentifier = None):
        if lineIdentifier != None:
            response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/mobile-service/v3/mobilesubscriptions/{bundleIdentifier}/usages?type=bundle&lineIdentifier={lineIdentifier}","mobileBundleUsage lineIdentifier")
        else:
            response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/mobile-service/v3/mobilesubscriptions/{bundleIdentifier}/usages?type=bundle","mobileBundleUsage bundle")
        return response.json()

    def apiVersion2(self):
        response = self.callTelenet("https://api.prd.telenet.be/ocapi/public/api/product-service/v1/product-subscriptions?producttypes=PLAN","apiVersion2", None)
        if response.status_code == 200:
            return True
        return False
