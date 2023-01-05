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


def _kibibyte_to_gibibyte(kib):
    return kib / (2 ** 20)
    
class UsageDay(BaseModel):
    """Represents a day of internet usage"""

    date: datetime
    peak_usage: int
    offpeak_usage: int
    total_usage: int

    def __str__(self):
        date_str = self.date.strftime("%Y-%m-%d")
        if self.peak_usage or self.offpeak_usage:
            peak_usage_gib = _kibibyte_to_gibibyte(self.peak_usage)
            offpeak_usage_gib = _kibibyte_to_gibibyte(self.offpeak_usage)
            return (
                f"{date_str}: {peak_usage_gib:4.2f} GiB\t{offpeak_usage_gib:4.2f} GiB"
            )
        else:
            usage_gib = _kibibyte_to_gibibyte(self.total_usage)
            return f"{date_str}: {usage_gib:4.2f} GiB"



class TelenetProductUsage(BaseModel):
    product_type: str
    squeezed: bool
    period_start: datetime
    period_end: datetime

    included_volume: int
    peak_usage: int
    offpeak_usage: int
    total_usage: int
    daily_usage: List[UsageDay]

    @classmethod
    def from_json(cls, data: dict):
        logger.debug(f"Parsing telemeter json: {json.dumps(data, indent=4)}")
        days = [
            UsageDay(
                date=datetime.strptime(x["date"], TELENET_DATETIME_FORMAT),
                peak_usage=x.get("peak", 0),
                offpeak_usage=x.get("offpeak", 0),
                total_usage=x.get("included", 0),
            )
            for x in data["totalusage"]["dailyusages"]
        ]

        peak_usage = data["totalusage"].get("peak", 0)
        offpeak_usage = data["totalusage"].get("offpeak", 0)

        included_usage = data["totalusage"].get("includedvolume", 0)
        extended_usage = data["totalusage"].get("extendedvolume", 0)

        total_usage = peak_usage + offpeak_usage + included_usage + extended_usage

        return cls(
            product_type=data["producttype"],
            squeezed=data["squeezed"],
            period_start=datetime.strptime(
                data["periodstart"], TELENET_DATETIME_FORMAT
            ),
            period_end=datetime.strptime(data["periodend"], TELENET_DATETIME_FORMAT),
            included_volume=data["includedvolume"],
            peak_usage=peak_usage,
            offpeak_usage=offpeak_usage,
            total_usage=total_usage,
            daily_usage=days,
        )

    def __str__(self):
        if self.peak_usage or self.offpeak_usage:
            peak_usage_gib = _kibibyte_to_gibibyte(self.peak_usage)
            offpeak_usage_gib = _kibibyte_to_gibibyte(self.offpeak_usage)
            return f"Usage for {self.product_type}: {peak_usage_gib:4.2f} GiB peak usage, {offpeak_usage_gib:4.2f} GiB offpeak usage"
        else:
            usage_gib = _kibibyte_to_gibibyte(self.total_usage)
            included_gib = _kibibyte_to_gibibyte(self.included_volume)
            return f"Usage for {self.product_type}: {usage_gib:4.2f} GiB of {included_gib:4.2f} GiB"



class Telemeter(BaseModel):
    period_start: datetime
    period_end: datetime
    products: List[TelenetProductUsage]

    @classmethod
    def from_json(cls, data: dict):
        for period in data["internetusage"][0]["availableperiods"]:
            # '2021-02-19T00:00:00.0+01:00'
            start = datetime.strptime(period["start"], TELENET_DATETIME_FORMAT)
            end = datetime.strptime(period["end"], TELENET_DATETIME_FORMAT)
            products = [TelenetProductUsage.from_json(x) for x in period["usages"]]
            yield cls(period_start=start, period_end=end, products=products)

    def __str__(self):
        s = f"Telemeter for {self.period_start} to {self.period_end}"
        for product in self.products:
            s += f"\n\t {product}"
        return s

class TelenetSession(object):
    def __init__(self, client):
        self.s = client
        # self.s.headers["User-Agent"] = "TelemeterPython/3"

    async def login(self, username, password, hass):
        # Get OAuth2 state / nonce
        headers = {"x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice"}

        response = await self.s.get("https://api.prd.telenet.be/ocapi/oauth/userdetails", headers=headers,timeout=10)
        if (await response.status == 200):
            # Return if already authenticated
            return
        
        assert await response.status == 401
        data = await response.text()
        state, nonce = data.text.split(",", maxsplit=2)

        # Log in
        response = await self.s.get(f'https://login.prd.telenet.be/openid/oauth/authorize?client_id=ocapi&response_type=code&claims={{"id_token":{{"http://telenet.be/claims/roles":null,"http://telenet.be/claims/licenses":null}}}}&lang=nl&state={state}&nonce={nonce}&prompt=login',timeout=10)
            #no action
        
        response = await self.s.post("https://login.prd.telenet.be/openid/login.do",data={"j_username": username,"j_password": password,"rememberme": True,},timeout=10)
        assert await response.status == 200

        self.s.headers["X-TOKEN-XSRF"] = await self.s.cookies.get("TOKEN-XSRF")

        r = await self.s.get(
            "https://api.prd.telenet.be/ocapi/oauth/userdetails",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
            timeout=10,
        )
        assert await r.status == 200

    async def userdetails(self, hass):
        r = await self.s.get(
            "https://api.prd.telenet.be/ocapi/oauth/userdetails",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
        )
        assert await r.status == 200
        return await r.json()

    async def telemeter(self, hass):
        r = await self.s.get(
            "https://api.prd.telenet.be/ocapi/public/?p=internetusage,internetusagereminder",
            headers={
                "x-alt-referer": "https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice",
            },
            timeout=10,
        )
        assert await r.status_code == 200
        # return next(Telemeter.from_json(r.json()))
        return await r.json()
