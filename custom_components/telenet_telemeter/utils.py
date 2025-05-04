import json
import logging
import pprint
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import List
import requests
from pydantic import BaseModel
from enum import Enum
import re
import urllib.parse
from ratelimit import limits, sleep_and_retry

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
        self.s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64; rv:137.0) Gecko/20100101 Firefox/137.0"
        self.s.headers["x-alt-referer"] = "https://www2.telenet.be/residential/nl/mijn-telenet/"
        self.s.headers["X-Requested-With"] = "XMLHttpRequest"
        self.s.headers["Origin"] = "https://www2.telenet.be"
        self.s.headers["Referrer"] = "https://www2.telenet.be"

    def callTelenet(self, url, caller = "Not set", expectedStatusCode = 200, data = None, printResponse = False, method : HttpMethod  = HttpMethod.GET, allowRedirects = True):
        try:
            if method == HttpMethod.GET:
                _LOGGER.debug(f"[{caller}] Calling GET {url}")
                response = self.s.get(url,timeout=30, allow_redirects=allowRedirects)
            elif method == HttpMethod.POST:
                self.s.headers["Content-Type"] = "application/json;charset=UTF-8"
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
        except Exception as e:
            _LOGGER.error(f"[{caller}]: Failed to call [{method}]({url}). Statuscode was {response.status_code}. Exception was {getattr(e, 'message', repr(e))}")
        return response

    
    @sleep_and_retry
    @limits(calls=1, period=5)
    def login(self, username, password):
        _LOGGER.info("Trying to login to My Telenet")
        assert not self.callTelenet(url="https://api.prd.telenet.be/omapi/public/publicconfigs/maintenance_ocapi", caller="login").json()["enabled"]

        response = self.callTelenet(url="https://api.prd.telenet.be/ocapi/oauth/userdetails", caller="login", expectedStatusCode=None)
        if response.status_code == 200:
            # Return if already authenticated
            return
        assert response.status_code == 401
        # Fetch state & nonce
        _LOGGER.debug(f"Loging response to split state, nonce: {response.text} - ({response.status_code}) - {response.headers}")
        state, nonce = response.text.split(",", maxsplit=2)

        # Fetch the initial state token
        state_token_response = self.callTelenet(
            url="https://api.prd.telenet.be/ocapi/login/authorization/telenet_be?lang=nl&style_hint=care&targetUrl=https://www2.telenet.be/residential/nl/mytelenet/",
            caller="login",
            expectedStatusCode=302,
            allowRedirects=True
        )
        _LOGGER.debug(f"State token response:  ({state_token_response.status_code}) - {state_token_response.headers}")

        # If allowRedirects=False, the follow up request needs to be manually executed based on location of response header
        # #get location url out of response header
        # authorizeUrl = state_token_response.headers.get("location")
        # _LOGGER.debug(f"authorizeUrl: {authorizeUrl}")
        

        # #  https://secure.telenet.be/oauth2/default/v1/authorize?client_id=***********&response_type=code&redirect_uri=https://api.prd.telenet.be/ocapi/login/callback/telenet_be&state=*************&nonce=*******&scope=openid%20profile%20licenses%20telenet.scopes%20offline_access&claims=%7B%22id_token%22:%7B%22http://telenet.be/claims/roles%22:null%7D%7D&code_challenge=**********&code_challenge_method=S256
        # state_token_response = self.callTelenet(
        #     # url="https://api.prd.telenet.be/ocapi/login/authorization/telenet_be?client_id=telenet_be&response_type=code&claims={\"id_token\":{\"http://telenet.be/claims/roles\":null,\"http://telenet.be/claims/licenses\":null}}&lang=nl&nonce=" + nonce + "&state=" + state + "&prompt=none",
        #     url=authorizeUrl,
        #     caller="login"
        # )
        

        state_token_matcher = re.search('"stateToken":"(.*)","helpLinks"', state_token_response.text) 
        state_token_encoded = state_token_matcher.group(1)
        state_token_decoded = state_token_encoded.encode('latin1').decode('unicode_escape')
        _LOGGER.debug(f"Initial state token {state_token_decoded}")
        
        introspection_response = self.callTelenet(
            url="https://secure.telenet.be/idp/idx/introspect",
            method=HttpMethod.POST,
            data=json.dumps({"stateToken": state_token_decoded}),
            caller="login"
        )
        state_handle = introspection_response.json()['stateHandle']

        self.callTelenet(url="https://secure.telenet.be/auth/services/devicefingerprint", caller="login")
        self.callTelenet(url="https://secure.telenet.be/api/v1/internal/device/nonce", method=HttpMethod.POST, caller="login")
        identify_response = self.callTelenet(
            url="https://secure.telenet.be/idp/idx/identify", 
            data=json.dumps({'identifier': username, 'stateHandle': state_handle}),
            method=HttpMethod.POST,
            caller="login"
        )
        state_handle = identify_response.json()['stateHandle']
        # authenticator = identify_response.json()['authenticators']['value'][0]['id']
        # fetch the authenticator id linked to password login, this isn't always the first
        password_id = None
        for auth in identify_response.json()["authenticators"]["value"]:
            if auth.get("type") == "password":
                password_id = auth.get("id")
                break

        challenge_response = self.callTelenet(
            url="https://secure.telenet.be/idp/idx/challenge",
            data=json.dumps({
                "authenticator":
                    {
                        "id":password_id
                    },
                    "stateHandle":state_handle
                }
            ),
            method=HttpMethod.POST,
            caller="login"
        )
        state_handle = challenge_response.json()['stateHandle']

        answer_response = self.callTelenet(
            url="https://secure.telenet.be/idp/idx/challenge/answer",
            data=json.dumps({
                "credentials":
                    {
                        "passcode":password
                    },
                    "stateHandle":state_handle
                }
            ),
            method=HttpMethod.POST,
            caller="login"
        )
        _LOGGER.debug(f"Answer response: {answer_response.text}")

        self.callTelenet(url=answer_response.json()["success"]["href"], caller="login")


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
    
    def wifiStatus(self, productIdentifier, modemMac):
        response = self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems/{modemMac}/wireless-status?productidentifier={productIdentifier}","wifiStatus")
        return response.json()
    
    def urldetails(self, url):
        response = self.callTelenet(url,"urldetails")
        return response.json()
    
    def switchWifi(self,  wirelessEnabled: bool, productIdentifier: bool, modemMac, locationId):
        # data = {"productIdentifier":productIdentifier,"homeSpotEnabled":homeSpotEnabled,"wirelessEnabled":"Yes","locationId":locationId,"patchOperations":[{"op":"replace","path":"/wirelessInterfaces/2.4GHZ/ssids/PRIMARY/active","value":wirelessEnabled},{"op":"replace","path":"/wirelessInterfaces/5GHZ/ssids/PRIMARY/active","value":wirelessEnabled}]}
        if wirelessEnabled:
            data = {"cos": "WSO_SHARING"}
        else:
            data = {"cos":"WSO_OFF"}
        # self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems/{modemMac}/wireless-settings","optionswifi", 200, None, True, HttpMethod.OPTIONS)
        # self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems/{modemMac}/wireless-settings","patchwifi", 200, data, True, HttpMethod.PATCH)
        self.callTelenet(f"https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems/{modemMac}/wireless-status","patchwifi", 200, data, True, HttpMethod.PATCH)
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
