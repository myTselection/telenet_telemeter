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

from .const import PROVIDER_TELENET, PROVIDER_BASE, PROVIDER_CONFIG

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
    def __init__(self, provider=PROVIDER_TELENET):
        self.provider = provider
        self.cfg = PROVIDER_CONFIG.get(provider, PROVIDER_CONFIG[PROVIDER_TELENET])
        self.api_url = self.cfg["api_url"]
        self.secure_url = self.cfg["secure_url"]

        self.s = requests.Session()
        self.s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64; rv:137.0) Gecko/20100101 Firefox/137.0"
        self.s.headers["x-alt-referer"] = self.cfg["alt_referer"]
        self.s.headers["X-Requested-With"] = "XMLHttpRequest"
        self.s.headers["Origin"] = self.cfg["origin"]
        self.s.headers["Referrer"] = self.cfg["referrer"]

    def callTelenet(self, url, caller = "Not set", expectedStatusCode = 200, data = None, printResponse = False, method : HttpMethod  = HttpMethod.GET, allowRedirects = True):
        response = None
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
            status = response.status_code if response is not None else "N/A"
            _LOGGER.error(f"[{caller}]: Failed to call [{method}]({url}). Statuscode was {status}. Exception was {getattr(e, 'message', repr(e))}")
        return response

    
    @sleep_and_retry
    @limits(calls=1, period=5)
    def login(self, username, password):
        _LOGGER.info(f"Trying to login to My {self.provider}")

        # Check maintenance — skip for BASE if endpoint doesn't exist
        try:
            maintenance = self.callTelenet(url=self.cfg["maintenance_url"], caller="login").json()
            assert not maintenance["enabled"]
        except (KeyError, AssertionError):
            _LOGGER.debug(f"[login] Maintenance check skipped for {self.provider}")
        except Exception as e:
            _LOGGER.warning(f"[login] Maintenance check failed for {self.provider}: {e}")

        response = self.callTelenet(url=f"{self.api_url}/ocapi/oauth/userdetails", caller="login", expectedStatusCode=None)
        if response.status_code == 200:
            # Return if already authenticated
            return
        assert response.status_code == 401
        _LOGGER.debug(f"Login response to split state, nonce: {response.text} - ({response.status_code}) - {response.headers}")
        _state, _nonce = response.text.split(",", maxsplit=2)

        # Fetch the initial state token
        # BASE returns 200 directly (follows redirect internally), Telenet returns 302
        state_token_response = self.callTelenet(
            url=self.cfg["authorization_url"],
            caller="login",
            expectedStatusCode=None,
            allowRedirects=True
        )
        _LOGGER.debug(f"Authorization URL status: {state_token_response.status_code}")
        assert state_token_response.status_code in [200, 302], f"Unexpected status {state_token_response.status_code}"
        _LOGGER.debug(f"State token response: ({state_token_response.status_code}) - {state_token_response.headers}")

        state_token_matcher = re.search('"stateToken":"(.*)","helpLinks"', state_token_response.text) 
        state_token_encoded = state_token_matcher.group(1)
        state_token_decoded = state_token_encoded.encode('latin1').decode('unicode_escape')
        _LOGGER.debug(f"Initial state token {state_token_decoded}")
        
        introspection_response = self.callTelenet(
            url=f"{self.secure_url}/idp/idx/introspect",
            method=HttpMethod.POST,
            data=json.dumps({"stateToken": state_token_decoded}),
            caller="login"
        )
        state_handle = introspection_response.json()['stateHandle']

        self.callTelenet(url=f"{self.secure_url}/auth/services/devicefingerprint", caller="login")
        self.callTelenet(url=f"{self.secure_url}/api/v1/internal/device/nonce", method=HttpMethod.POST, caller="login")
        identify_response = self.callTelenet(
            url=f"{self.secure_url}/idp/idx/identify", 
            data=json.dumps({'identifier': username, 'stateHandle': state_handle}),
            method=HttpMethod.POST,
            caller="login"
        )
        state_handle = identify_response.json()['stateHandle']

        password_id = None
        for auth in identify_response.json()["authenticators"]["value"]:
            if auth.get("type") == "password":
                password_id = auth.get("id")
                break

        challenge_response = self.callTelenet(
            url=f"{self.secure_url}/idp/idx/challenge",
            data=json.dumps({
                "authenticator": {"id": password_id},
                "stateHandle": state_handle
            }),
            method=HttpMethod.POST,
            caller="login"
        )
        state_handle = challenge_response.json()['stateHandle']

        answer_response = self.callTelenet(
            url=f"{self.secure_url}/idp/idx/challenge/answer",
            data=json.dumps({
                "credentials": {"passcode": password},
                "stateHandle": state_handle
            }),
            method=HttpMethod.POST,
            caller="login"
        )
        _LOGGER.debug(f"Answer response: {answer_response.text}")

        self.callTelenet(url=answer_response.json()["success"]["href"], caller="login")


    def userdetails(self):
        response = self.callTelenet(f"{self.api_url}/ocapi/oauth/userdetails", "userdetails", None)
        return response.json()
    
    def customerdetails(self):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/customer-service/v1/customers", "customerdetails")
        return response.json()

    def telemeter(self):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/?p=internetusage,internetusagereminder", "telemeter")
        return response.json()

    def telemeter_product_details(self, url):
        response = self.callTelenet(url, "telemeter_product_details")
        return response.json()

    def modemdetails(self, productIdentifier):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/resource-service/v1/modems?productIdentifier={productIdentifier}", "modemdetails")
        return response.json()
    
    def wifidetails(self, productIdentifier, modemMac):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/resource-service/v1/modems/{modemMac}/wireless-settings?withmetadata=true&withwirelessservice=true&productidentifier={productIdentifier}", "wifidetails")
        return response.json()
    
    def wifiStatus(self, productIdentifier, modemMac):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/resource-service/v1/modems/{modemMac}/wireless-status?productidentifier={productIdentifier}", "wifiStatus")
        return response.json()
    
    def urldetails(self, url):
        response = self.callTelenet(url, "urldetails")
        return response.json()
    
    def switchWifi(self, wirelessEnabled: bool, productIdentifier: bool, modemMac, locationId):
        if wirelessEnabled:
            data = {"cos": "WSO_SHARING"}
        else:
            data = {"cos": "WSO_OFF"}
        self.callTelenet(f"{self.api_url}/ocapi/public/api/resource-service/v1/modems/{modemMac}/wireless-status", "patchwifi", 200, data, True, HttpMethod.PATCH)
        return
    
    def reboot(self, modemMac):
        self.callTelenet(f"{self.api_url}/ocapi/public/api/resource-service/v1/modems/{modemMac}/reboot", "modem_general reboot", 200, None, True, HttpMethod.POST)
        return
    
    def mobile(self):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/?p=mobileusage", "mobile")
        return response.json()
        
    def planInfo(self):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/product-service/v1/product-subscriptions?producttypes=PLAN", "planInfo")
        return response.json()
    
    def billCycles(self, productType, productIdentifier):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/billing-service/v1/account/products/{productIdentifier}/billcycle-details?producttype={productType}&count=3", "billCycles")
        return response.json()
    
    def productUsage(self, productType, productIdentifier, startDate, endDate):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/product-service/v1/products/{productType}/{productIdentifier}/usage?fromDate={startDate}&toDate={endDate}", "productUsage")
        return response.json()
    
    def productDailyUsage(self, productType, productIdentifier, startDate, endDate):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/product-service/v1/products/{productType}/{productIdentifier}/dailyusage?billcycle=CURRENT&fromDate={startDate}&toDate={endDate}", "productUsage")
        return response.json()

    def productSubscriptions(self, productType):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/product-service/v1/product-subscriptions?producttypes={productType}", "productSubscriptions")
        return response.json()

    def productService(self, productIdentifier, productType):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/product-service/v1/products/{productIdentifier}?producttype={productType.lower()}", "productService")
        return response.json()

    def _call_with_retry(self, url, caller, retries=3, backoff=10):
        """Call an endpoint, retrying on 429 with exponential-ish backoff.
        Stops immediately on Cloudflare block (HTML body on 429)."""
        import time
        for attempt in range(retries):
            response = self.callTelenet(url, caller, expectedStatusCode=None)
            if response.status_code == 200:
                return response
            if response.status_code == 429:
                content_type = response.headers.get("Content-Type", "")
                if "text/html" in content_type:
                    _LOGGER.warning(f"[{caller}] Cloudflare block (not retrying) — run less frequently to avoid bot detection")
                    return response
                if attempt < retries - 1:
                    wait = int(response.headers.get("Retry-After", backoff * (attempt + 1)))
                    wait = wait if wait > 0 else backoff * (attempt + 1)
                    _LOGGER.warning(f"[{caller}] 429 rate-limited, retrying in {wait}s (attempt {attempt + 1}/{retries})")
                    time.sleep(wait)
            else:
                _LOGGER.warning(f"[{caller}] Unexpected status {response.status_code}")
                return response
        return response

    def mobileUsage(self, productIdentifier):
        response = self._call_with_retry(
            f"{self.api_url}/ocapi/public/api/mobile-service/v3/mobilesubscriptions/{productIdentifier}/usages",
            "mobileUsage"
        )
        if response is not None and response.status_code == 200:
            return response.json()
        return None

    def mobileBundleUsage(self, bundleIdentifier, lineIdentifier=None):
        if lineIdentifier is not None:
            url = f"{self.api_url}/ocapi/public/api/mobile-service/v3/mobilesubscriptions/{bundleIdentifier}/usages?type=bundle&lineIdentifier={lineIdentifier}"
            caller = "mobileBundleUsage lineIdentifier"
        else:
            url = f"{self.api_url}/ocapi/public/api/mobile-service/v3/mobilesubscriptions/{bundleIdentifier}/usages?type=bundle"
            caller = "mobileBundleUsage bundle"
        response = self._call_with_retry(url, caller)
        if response is not None and response.status_code == 200:
            return response.json()
        return None

    def mobileLines(self):
        """List all mobile lines: [{msisdn, isDataOnly, status, name}]"""
        response = self.callTelenet(
            f"{self.api_url}/ocapi/public/api/customer-web-billing-mobile-line-selector/v1/mobile-lines",
            "mobileLines"
        )
        if response is not None and response.status_code == 200:
            return response.json()
        return []

    def mobileLineUsage(self, msisdn):
        """Usage for one mobile line via the customer-web-billing API."""
        response = self._call_with_retry(
            f"{self.api_url}/ocapi/public/api/customer-web-billing-mobile-usage/v1/mobile-lines/{msisdn}/usage",
            "mobileLineUsage"
        )
        if response is not None and response.status_code == 200:
            return response.json()
        return None

    def inboxMessages(self):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/telenet-app-inbox-messages-cs/v1/inbox/messages", "inboxMessages", expectedStatusCode=None)
        if response is not None and response.status_code == 200:
            return response.json()
        return None

    def inboxCount(self):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/telenet-app-inbox-messages-cs/v1/inbox", "inboxCount", expectedStatusCode=None)
        if response.status_code == 200:
            return response.json()
        return None

    def apiVersion2(self):
        response = self.callTelenet(f"{self.api_url}/ocapi/public/api/product-service/v1/product-subscriptions?producttypes=PLAN", "apiVersion2", None)
        if response.status_code == 200:
            return True
        return False
