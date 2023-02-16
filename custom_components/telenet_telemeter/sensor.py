import logging
import asyncio
from datetime import date, datetime, timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

from . import DOMAIN, NAME
from .utils import *

_LOGGER = logging.getLogger(__name__)
_TELENET_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.0%z"


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required("username"): cv.string,
        vol.Required("password"): cv.string,
        vol.Optional("internet", default=True): cv.boolean,
        vol.Optional("mobile", default=True): cv.boolean,
    }
)

MIN_TIME_BETWEEN_UPDATES = timedelta(hours=1)


async def dry_setup(hass, config_entry, async_add_devices):
    config = config_entry
    username = config.get("username")
    password = config.get("password")
    internet = config.get("internet")
    mobile = config.get("mobile")

    check_settings(config, hass)
    sensors = []
    
    if internet:
        data_internet = ComponentData(
            username,
            password,
            internet,
            False,
            async_get_clientsession(hass),
            hass
        )
        await data_internet._forced_update()
        assert data_internet._telemeter is not None
        sensor = SensorInternet(data_internet, hass)
        sensors.append(sensor)
    if mobile:
        data_mobile = ComponentData(
            username,
            password,
            False,
            mobile,
            async_get_clientsession(hass),
            hass
        )
        await data_mobile._forced_update()
        assert data_mobile._mobilemeter is not None
        # createa mobile sensor for each mobile subscription
        # for mobilenr in data_mobile._mobilemeter
        mobileusage = data_mobile._mobilemeter.get('mobileusage')
        for idxproduct, product in enumerate(mobileusage):
            _LOGGER.debug("enumarate mobileusage elements idx:" + str(idxproduct) + ", product: "+ str(product) + " " +  NAME)
            #shared sensor
            if product.get('sharedusage'):
                _LOGGER.info("shared mobileusage element " +  NAME)
                sensor = ComponentMobileShared(data_mobile, idxproduct, hass)
                sensors.append(sensor)
            #unassigned sensor
            if product.get('unassigned'):
                _LOGGER.info("unassined mobileusage element " +  NAME)
                for idxunsubs, subscription in enumerate(product.get('unassigned').get('mobilesubscriptions')):
                    _LOGGER.debug("enumarate unassigned subsc elements idx:" + str(idxunsubs) + ", subscription: "+ str(subscription) + " " +  NAME)
                    #unassigned sensor
                    sensor = SensorMobileUnassigned(data_mobile, idxproduct, idxunsubs, hass)
                    sensors.append(sensor)
            #assigned sensor
            if product.get('profiles'):
                _LOGGER.info("assined mobileusage element " +  NAME)
                for idxunprofile, profile in enumerate(product.get('profiles')):
                    _LOGGER.debug("enumarate assigned profiles elements idx:" + str(idxunprofile) + ", profile: "+ str(profile) + " " +  NAME)
                    for idxunsubs, subscription in enumerate(product.get('profiles')[idxunprofile].get('mobilesubscriptions')):
                        _LOGGER.debug("enumarate assigned subsc elements idx:" + str(idxunsubs) + ", subscription: "+ str(subscription) + " " +  NAME)
                        #assigned sensor
                        sensor = SensorMobileAssigned(data_mobile, idxproduct, idxunprofile, idxunsubs, hass)
                        sensors.append(sensor)
    async_add_devices(sensors)


async def async_setup_platform(
    hass, config_entry, async_add_devices, discovery_info=None
):
    """Setup sensor platform for the ui"""
    _LOGGER.info("async_setup_platform " + NAME)
    await dry_setup(hass, config_entry, async_add_devices)
    return True


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Setup sensor platform for the ui"""
    _LOGGER.info("async_setup_entry " + NAME)
    config = config_entry.data
    await dry_setup(hass, config, async_add_devices)
    return True


async def async_remove_entry(hass, config_entry):
    _LOGGER.info("async_remove_entry " + NAME)
    try:
        await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
        _LOGGER.info("Successfully removed sensor from the integration")
    except ValueError:
        pass
        

class ComponentData:
    def __init__(self, username, password, internet, mobile, client, hass):
        self._username = username
        self._password = password
        self._internet = internet
        self._mobile = mobile
        self._client = client
        self._session = TelenetSession()
        self._telemeter = None
        self._mobilemeter = None
        self._producturl = None
        self._product_details = None
        self._hass = hass
        
    # same as update, but without throttle to make sure init is always executed
    async def _forced_update(self):
        _LOGGER.info("Fetching intit stuff for " + NAME)
        if not(self._session):
            self._session = TelenetSession()

        if self._session:
            await self._hass.async_add_executor_job(lambda: self._session.login(self._username, self._password))
            _LOGGER.debug("init login completed")
            if self._internet:
                self._telemeter = await self._hass.async_add_executor_job(lambda: self._session.telemeter())
                # mock data
                # self._telemeter = 
                assert self._telemeter is not None
                _LOGGER.debug(f"init telemeter data: {self._telemeter}")
                self._producturl = self._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('specurl') 
                assert self._producturl is not None
                self._product_details = await self._hass.async_add_executor_job(lambda: self._session.telemeter_product_details(self._producturl))
                # mock data
                # self._product_details = {"product":{"productid":627,"labelkey":"internet.line.fmc.wigo35gb","visible":True,"family":"FMC_RMD","producttype":"PRODUCT","weight":2,"apps":[{"labelkey":"support"}],"services":[{"labelkey":"surf.fixedinternet.wigo","servicetype":"FIXED_INTERNET","experience":{"experiencetype":"SURF","weight":10},"weight":0,"specifications":[{"labelkey":"spec.fixedinternet.wifree","value":"1","visible":False,"weight":7},{"labelkey":"spec.fixedinternet.speed.download","value":"300","unit":"Mbps","visible":True,"weight":1},{"labelkey":"spec.fixedinternet.volume.download.fup","value":"FUP","visible":True,"weight":3},{"labelkey":"spec.fixedinternet.mailbox.volume","value":"5","unit":"GB","visible":True,"weight":5},{"labelkey":"spec.fixedinternet.mailbox.included","value":"10","visible":True,"weight":4},{"labelkey":"spec.fixedinternet.speed.upload","value":"20","unit":"Mbps","visible":True,"weight":2}]}],"characteristics":{"alert_threshold_marker":{"unit":"GB","value":"750"},"detailed_scale":{"unit":"GB","value":"25"},"productsegment":"RMD","service_category":"FUP","productgroup":"FMC","initial_threshold_2":{"unit":"GB","value":"1050"},"initial_threshold_1":{"unit":"GB","value":"225"},"alert_threshold":{"unit":"GB","value":"525"},"service_category_limit":{"unit":"GB","value":"750"}},"localizedcontent":[{"locale":"nl","name":"All-Internet 300","logo":"https://www2.telenet.be/content/dam/www-telenet-be/img/self-service/products/internet-line-fmc-wigo35gb.png"},{"locale":"fr","name":"All-Internet 300","logo":"https://www2.telenet.be/content/dam/www-telenet-be/img/self-service/products/internet-line-fmc-wigo35gb.png"},{"locale":"en","name":"All-Internet 300","logo":"https://www2.telenet.be/content/dam/www-telenet-be/img/self-service/products/internet-line-fmc-wigo35gb.png"}]}}
                assert self._product_details is not None
                _LOGGER.debug(f"init telemeter productdetails: {self._product_details}")
            if self._mobile:
                self._mobilemeter = await self._hass.async_add_executor_job(lambda: self._session.mobile())
                # mock data
                # self._mobilemeter = {"mobileusage":[{"label":"O2","specurl":"https://api.prd.telenet.be/omapi/public/product/36860","identifier":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","nextbillingdate":"2023-02-20T00:00:00.0+01:00","lastupdated":"2023-01-23T07:59:08.1+01:00","address":{"street":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","postalcode":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","municipality":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","country":"Belgi\u00eb","housenr":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","addressid":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},"unassigned":{"mobilesubscriptions":[{"mobile":"1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","sim":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","pin":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","puk":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","activationstate":"active","graceuntil":"2022-01-14T00:00:00.0+01:00","blockstatus":"OPEN","paused": "False","mobileinternetonly": "True"}],"aggregatedusage":{"included":{"data":{"startunits":600.0,"start":"600","remainingunits":600.0,"remaining":"600,00","usedunits":0.0,"used":"0,00","usedpercentage":0,"unittype":"GB","unlimited": "True","scaledusedpercentage":0}},"outofbundle":{"usedunits":0.0,"unittype":"EUR"}}},"profiles":[{"pid":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","role":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","firstname":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","lastname":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","paused": "False","mobilesubscriptions":[{"mobile":"2xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","sim":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","pin":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","puk":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","activationstate":"active","included":{"data":{"startunits":500.0,"start":"500","remainingunits":499.99,"remaining":"499,99","usedunits":0.01,"used":"0,01","usedpercentage":0,"unittype":"GB","unlimited": "True"},"text":{"startunits":30000.0,"remainingunits":30000.0,"usedunits":0.0,"usedpercentage":0,"unittype":"number","unlimited": "True","scaledusedpercentage":0},"voice":{"startunits":180000,"remainingunits":180000,"usedunits":0,"usedpercentage":0,"unittype":"seconds","unlimited": "True","scaledusedpercentage":0}},"options":[],"outofbundle":{"usedunits":0.0,"unittype":"EUR"},"paused": "False","mobileinternetonly": "False"}],"aggregatedusage":{"included":{"data":{"startunits":600.0,"start":"600","remainingunits":599.99,"remaining":"599,99","usedunits":0.01,"used":"0,01","usedpercentage":0,"unittype":"GB","unlimited": "True","scaledusedpercentage":0}},"outofbundle":{"usedunits":0.0,"unittype":"EUR"}}},{"pid":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","role":"manager","firstname":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","lastname":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","nickname":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","paused": "False","mobilesubscriptions":[{"mobile":"3xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","sim":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","pin":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","puk":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","activationstate":"active","included":{"data":{"startunits":500.0,"start":"500","remainingunits":499.82,"remaining":"499,82","usedunits":0.18,"used":"0,18","usedpercentage":0,"unittype":"GB","unlimited": "True"},"text":{"startunits":30000.0,"remainingunits":30000.0,"usedunits":0.0,"usedpercentage":0,"unittype":"number","unlimited": "True","scaledusedpercentage":0},"voice":{"startunits":180000,"remainingunits":180000,"usedunits":0,"usedpercentage":0,"unittype":"seconds","unlimited": "True","scaledusedpercentage":0}},"options":[],"outofbundle":{"usedunits":0.0,"unittype":"EUR"},"paused": "False","mobileinternetonly": "False"}],"aggregatedusage":{"included":{"data":{"startunits":600.0,"start":"600","remainingunits":599.82,"remaining":"599,82","usedunits":0.18,"used":"0,18","usedpercentage":0,"unittype":"GB","unlimited": "True","scaledusedpercentage":0}},"outofbundle":{"usedunits":0.0,"unittype":"EUR"}}}],"sharedusage":{"outofbundle":{"usedunits":0.0,"unittype":"EUR"},"included":{"data":{"startunits":600.0,"start":"600","remainingunits":599.7,"remaining":"599,7","usedunits":0.3,"used":"0,3","usedpercentage":0,"unittype":"GB","unlimited": "True"}},"options":[]},"freeride":{"active": "False"},"totalusage":{"included":{"data":{"startunits":600.0,"start":"600","remainingunits":599.7,"remaining":"599,7","usedunits":0.3,"used":"0,3","usedpercentage":0,"unittype":"GB"}}}}]}
                # self._mobilemeter = {'mobileusage': [{'label': 'O1', 'specurl': 'https://api.prd.telenet.be/omapi/public/product/42797', 'identifier': 'O1_46172164', 'nextbillingdate': '2023-01-26T00:00:00.0+01:00', 'lastupdated': '2023-01-21T10:50:01.7+01:00', 'address': {'street': '', 'postalcode': '', 'municipality': '', 'country': '', 'housenr': '', 'addressid': ''}, 'unassigned': {'mobilesubscriptions': []}, 'profiles': [{'pid': '16517642', 'role': 'manager', 'firstname': '', 'lastname': '', 'nickname': '', 'paused': False, 'mobilesubscriptions': [{'mobile': '0477777777', 'sim': '', 'pin': '', 'puk': '', 'activationstate': 'active', 'included': {'data': {'startunits': 300.0, 'start': '300', 'remainingunits': 272.9, 'remaining': '272,90', 'usedunits': 27.1, 'used': '27,10', 'usedpercentage': 9, 'unittype': 'GB', 'unlimited': True}, 'text': {'startunits': 30000.0, 'remainingunits': 29990.0, 'usedunits': 10.0, 'usedpercentage': 0, 'unittype': 'number', 'unlimited': True, 'scaledusedpercentage': 1}, 'voice': {'startunits': 180000, 'remainingunits': 174503, 'usedunits': 5497, 'usedpercentage': 3, 'unittype': 'seconds', 'unlimited': True, 'scaledusedpercentage': 36}}, 'options': [], 'outofbundle': {'usedunits': 0.0, 'unittype': 'EUR'}, 'paused': False, 'mobileinternetonly': False}, {'mobile': '0488888888', 'sim': '', 'pin': '', 'puk': '', 'activationstate': 'active', 'included': {'data': {'startunits': 300.0, 'start': '300', 'remainingunits': 290.21, 'remaining': '290,21', 'usedunits': 9.79, 'used': '9,79', 'usedpercentage': 3, 'unittype': 'GB', 'unlimited': True}}, 'options': [], 'outofbundle': {'usedunits': 0.0, 'unittype': 'EUR'}, 'paused': False, 'mobileinternetonly': True}], 'aggregatedusage': {'included': {'data': {'startunits': 300.0, 'start': '300', 'remainingunits': 263.11, 'remaining': '263,11', 'usedunits': 36.89, 'used': '36,89', 'usedpercentage': 12, 'unittype': 'GB', 'unlimited': True, 'scaledusedpercentage': 12}}, 'outofbundle': {'usedunits': 0.0, 'unittype': 'EUR'}}}], 'sharedusage': {'outofbundle': {'usedunits': 0.0, 'unittype': 'EUR'}, 'included': {'data': {'startunits': 300.0, 'start': '300', 'remainingunits': 263.1, 'remaining': '263,1', 'usedunits': 36.9, 'used': '36,9', 'usedpercentage': 12, 'unittype': 'GB', 'unlimited': True}}, 'options': []}, 'freeride': {'active': False}, 'totalusage': {'included': {'data': {'startunits': 300.0, 'start': '300', 'remainingunits': 263.1, 'remaining': '263,1', 'usedunits': 36.9, 'used': '36,9', 'usedpercentage': 12, 'unittype': 'GB'}}}}]}
                _LOGGER.debug(f"init mobilemeter data: {self._mobilemeter}")
                
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def _update(self):
        await self._forced_update()

    async def update(self):
        await self._update()
    
    def clear_session(self):
        self._session : None



class SensorInternet(Entity):
    def __init__(self, data, hass):
        self._data = data
        self._hass = hass
        self._last_update = None
        self._used_percentage = 0
        self._period_start_date = None
        self._period_end_date = None
        tz_info = None
        self._period_length = 0
        self._period_left = 0
        self._period_used = 0
        self._total_volume = 0
        self._included_volume = 0
        self._extended_volume = 0
        self._wifree_usage = 0
        self._includedvolume_usage = 0
        self._extendedvolume_usage = 0
        self._period_used_percentage = 0
        self._product = None
        self._download_speed = 0
        self._upload_speed = 0
        self._peak_usage = 0
        self._offpeak_usage = 0

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._used_percentage

    async def async_update(self):
        await self._data.update()
        self._last_update =  self._data._telemeter.get('internetusage')[0].get('lastupdated')
        self._product = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('producttype') 
        self._period_start_date = datetime.strptime(self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('periodstart'), _TELENET_DATETIME_FORMAT)
        self._period_end_date = datetime.strptime(self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('periodend'), _TELENET_DATETIME_FORMAT)
        tz_info = self._period_end_date.tzinfo
        self._period_length = (self._period_end_date - self._period_start_date).days
        self._period_left = (self._period_end_date - datetime.now(tz_info)).days + 1
        _LOGGER.debug(f"telemeter end date: {self._period_end_date} - now {datetime.now(tz_info)} = perdiod_left {self._period_left}, self._period_length {self._period_length}")
        self._period_used = self._period_length - self._period_left
        self._period_used_percentage = round(100 * (self._period_used / self._period_length),1)
        
        #original way to get included volume, but now getting out of product details to get FUP limits
        # self._included_volume = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('includedvolume')
        self._included_volume = int((self._data._product_details.get('product').get('characteristics').get('service_category_limit').get('value'))) * 1024 * 1024
        self._extended_volume = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('extendedvolume').get('volume')
        
        self._total_volume = (self._included_volume + self._extended_volume) / 1024 / 1024
        
        _LOGGER.debug(f"specifications: {self._data._product_details.get('product').get('services')[0].get('specifications')}")
        for productdetails in self._data._product_details.get('product').get('services')[0].get('specifications'):
            _LOGGER.debug(f"productdetails: {productdetails}")
            if productdetails.get('labelkey') == "spec.fixedinternet.speed.download":
                self._download_speed = f"{productdetails.get('value')} {productdetails.get('unit')}"
            if productdetails.get('labelkey') == "spec.fixedinternet.speed.upload":
                self._upload_speed = f"{productdetails.get('value')} {productdetails.get('unit')}"
        
        if self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('peak') is None:
            #https://www2.telenet.be/content/www-telenet-be/nl/klantenservice/wat-is-de-telemeter
            self._wifree_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('wifree')
            self._includedvolume_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('includedvolume')
            self._extendedvolume_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('extendedvolume')
            
            self._used_percentage = round(100 * ((self._includedvolume_usage + self._extendedvolume_usage + self._wifree_usage) / ( self._included_volume + self._extended_volume)),1)
            
        else:
            #when peak indication is available, only use peak + wifree in total used counter, as offpeak is not attributed
            self._wifree_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('wifree')
            self._peak_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('peak')
            self._offpeak_usage = self._data._telemeter.get('internetusage')[0].get('availableperiods')[0].get('usages')[0].get('totalusage').get('offpeak')
            
            self._used_percentage = round(100 * ((self._peak_usage + self._wifree_usage) / ( self._included_volume + self._extended_volume)),1)

            
        
    async def async_will_remove_from_hass(self):
        """Clean up after entity before removal."""
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()


    @property
    def icon(self) -> str:
        """Shows the correct icon for container."""
        return "mdi:check-network-outline"
        #alternative: 
        #return "mdi:wifi_tethering_error"
        
    @property
    def unique_id(self) -> str:
        """Return the name of the sensor."""
        return (
            NAME
        )

    @property
    def name(self) -> str:
        return self.unique_id

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return {
            ATTR_ATTRIBUTION: NAME,
            "last update": self._last_update,
            "used_percentage": self._used_percentage,
            "included_volume": self._included_volume,
            "extended_volume": self._extended_volume,
            "total_volume": self._total_volume,
            "wifree_usage": self._wifree_usage,
            "includedvolume_usage": self._includedvolume_usage,
            "extendedvolume_usage": self._extendedvolume_usage,
            "peak_usage": self._peak_usage, 
            "offpeak_usage": self._offpeak_usage,
            "period_start": self._period_start_date,
            "period_end": self._period_end_date,
            "period_days_left": self._period_left,
            "period_used_percentage": self._period_used_percentage,
            "product": self._product,
            "download_speed": self._download_speed,
            "upload_speed": self._upload_speed,
            "telemeter_json": self._data._telemeter
        }

    @property
    def device_info(self) -> dict:
        """I can't remember why this was needed :D"""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": DOMAIN,
        }

    @property
    def unit(self) -> int:
        """Unit"""
        return int

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement this sensor expresses itself in."""
        return "%"

    @property
    def friendly_name(self) -> str:
        return self.unique_id
        
        
        
        

class ComponentMobileShared(Entity):
    def __init__(self, data, productid, hass):
        self._data = data
        self._productid = productid
        self._hass = hass
        self._last_update = None
        self._total_volume_data = None
        self._total_volume_text = None
        self._total_volume_voice = None
        self._remaining_volume_data = None
        self._remaining_volume_text = None
        self._remaining_volume_voice = None
        self._used_percentage_data = None
        self._used_percentage_text = None
        self._used_percentage_voice = None
        self._period_end_date = None
        self._outofbundle = None
        tz_info = None
        self._product = None

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._used_percentage_data

    async def async_update(self):
        await self._data.update()
        _LOGGER.debug(f"mobilemeter ComponentMobileShared productid: {self._productid}")
        
        mobileusage = self._data._mobilemeter.get('mobileusage')
        productdetails = mobileusage[self._productid]
        
        self._last_update =  productdetails.get('lastupdated')
        self._product = productdetails.get('label')
        self._period_end_date = productdetails.get('nextbillingdate')
        # get shared sensor
        sharedusage = productdetails.get('sharedusage')
        
        #todo: add checks on empty elements
        if sharedusage:
            if sharedusage.get('included'):
                if sharedusage.get('included').get('data'):
                    self._total_volume_data = f"{sharedusage.get('included').get('data').get('startunits')} {sharedusage.get('included').get('data').get('unittype')}"
                    self._used_percentage_data = sharedusage.get('included').get('data').get('usedpercentage')
                    self._remaining_volume_data = f"{sharedusage.get('included').get('data').get('remainingunits')} {sharedusage.get('included').get('data').get('unittype')}"
                    
                if sharedusage.get('included').get('text'):
                    self._total_volume_text = f"{sharedusage.get('included').get('text').get('startunits')} {sharedusage.get('included').get('text').get('unittype')}"
                    self._used_percentage_text = sharedusage.get('included').get('text').get('remainingunits') + ' ' + sharedusage.get('included').get('text').get('unittype')
                    self._remaining_volume_text = f"{sharedusage.get('included').get('text').get('remainingunits')} {sharedusage.get('included').get('data').get('unittype')}"
                    
                if sharedusage.get('included').get('voice'):
                    self._total_volume_voice = f"{sharedusage.get('included').get('voice').get('startunits')} {sharedusage.get('included').get('voice').get('unittype')}"
                    self._used_percentage_voice = sharedusage.get('included').get('voice').get('usedpercentage')
                    self._remaining_volume_voice = f"{sharedusage.get('included').get('voice').get('remainingunits')} {sharedusage.get('included').get('voice').get('unittype')}"
                
            if sharedusage.get('outofbundle'):
                self._outofbundle = f"{sharedusage.get('outofbundle').get('usedunits')} {sharedusage.get('outofbundle').get('unittype')}"
        
    async def async_will_remove_from_hass(self):
        """Clean up after entity before removal."""
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()


    @property
    def icon(self) -> str:
        """Shows the correct icon for container."""
        return "mdi:check-network-outline"
        #alternative: 
        #return "mdi:wifi_tethering_error"
        
    @property
    def unique_id(self) -> str:
        """Return the name of the sensor."""
        return (
            f"{NAME} mobile shared"
        )

    @property
    def name(self) -> str:
        return self.unique_id

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return {
            ATTR_ATTRIBUTION: NAME,
            "last update": self._last_update,
            "used_percentage_data": self._used_percentage_data,
            "used_percentage_text": self._used_percentage_text,
            "used_percentage_voice": self._used_percentage_voice,
            "total_volume_data": self._total_volume_data,
            "total_volume_text": self._total_volume_text,
            "total_volume_voice": self._total_volume_voice,
            "remaining_volume_data": self._remaining_volume_data,
            "remaining_volume_text": self._remaining_volume_text,
            "remaining_volume_voice": self._remaining_volume_voice,
            "period_end": self._period_end_date,
            "product": self._product,
            "outofbundle" : self._outofbundle,
            "mobile_json": self._data._mobilemeter
        }

    @property
    def device_info(self) -> dict:
        """I can't remember why this was needed :D"""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": DOMAIN,
        }

    @property
    def unit(self) -> int:
        """Unit"""
        return int

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement this sensor expresses itself in."""
        return "%"

    @property
    def friendly_name(self) -> str:
        return self.unique_id
        
class SensorMobileUnassigned(Entity):
    def __init__(self, data, productid, subsid, hass):
        self._data = data
        self._productid = productid
        self._subsid = subsid
        self._hass = hass
        self._last_update = None
        self._total_volume_data = None
        self._total_volume_text = None
        self._total_volume_voice = None
        self._remaining_volume_data = None
        self._remaining_volume_text = None
        self._remaining_volume_voice = None
        self._used_percentage_data = None
        self._used_percentage_text = None
        self._used_percentage_voice = None
        self._period_end_date = None
        self._product = None
        self._number = None
        self._active = None
        self._outofbundle = None
        self._mobileinternetonly = None  

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._used_percentage_data

    async def async_update(self):
        await self._data.update()
        _LOGGER.debug(f"mobilemeter ComponentMobileShared subsid: {self._subsid}")
        
        mobileusage = self._data._mobilemeter.get('mobileusage')
        productdetails = mobileusage[self._productid]
        
        self._last_update =  productdetails.get('lastupdated')
        self._product = productdetails.get('label')
        self._period_end_date = productdetails.get('nextbillingdate')
        # get shared sensor
        unassignesub = productdetails.get('unassigned').get('mobilesubscriptions')[self._subsid]
        
        #todo: add checks on empty elements
        if unassignesub:
            if unassignesub.get('included'):
                if unassignesub.get('included').get('data'):
                    self._total_volume_data = f"{unassignesub.get('included').get('data').get('startunits')} {unassignesub.get('included').get('data').get('unittype')}"
                    self._used_percentage_data = unassignesub.get('included').get('data').get('usedpercentage')
                    self._remaining_volume_data = f"{unassignesub.get('included').get('data').get('remainingunits')} {unassignesub.get('included').get('data').get('unittype')}"
                    
                if unassignesub.get('included').get('text'):
                    self._total_volume_text = f"{unassignesub.get('included').get('text').get('startunits')} {unassignesub.get('included').get('text').get('unittype')}"
                    self._used_percentage_text = unassignesub.get('included').get('text').get('usedpercentage')
                    self._remaining_volume_text = f"{unassignesub.get('included').get('text').get('remainingunits')} {unassignesub.get('included').get('text').get('unittype')}"
                    
                if unassignesub.get('included').get('voice'):
                    self._total_volume_voice = f"{unassignesub.get('included').get('voice').get('startunits')} {unassignesub.get('included').get('voice').get('unittype')}"
                    self._used_percentage_voice = unassignesub.get('included').get('voice').get('usedpercentage')
                    self._remaining_volume_voice = f"{unassignesub.get('included').get('voice').get('remainingunits')} {unassignesub.get('included').get('voice').get('unittype')}"
                
            self._number = unassignesub.get('mobile')
            self._active = unassignesub.get('activationstate')
            if unassignesub.get('outofbundle'): 
                self._outofbundle = f"{unassignesub.get('outofbundle').get('usedunits')} {unassignesub.get('outofbundle').get('unittype')}"
            self._mobileinternetonly = unassignesub.get('mobileinternetonly')               
                
            
        
    async def async_will_remove_from_hass(self):
        """Clean up after entity before removal."""
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()


    @property
    def icon(self) -> str:
        """Shows the correct icon for container."""
        return "mdi:check-network-outline"
        #alternative: 
        #return "mdi:wifi_tethering_error"
        
    @property
    def unique_id(self) -> str:
        """Return the name of the sensor."""
        return (
            f"{NAME} mobile {self._data._mobilemeter.get('mobileusage')[self._productid].get('unassigned').get('mobilesubscriptions')[self._subsid].get('mobile')}"
        )

    @property
    def name(self) -> str:
        return self.unique_id

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return {
            ATTR_ATTRIBUTION: NAME,
            "last update": self._last_update,
            "used_percentage_data": self._used_percentage_data,
            "used_percentage_text": self._used_percentage_text,
            "used_percentage_voice": self._used_percentage_voice,
            "total_volume_data": self._total_volume_data,
            "total_volume_text": self._total_volume_text,
            "total_volume_voice": self._total_volume_voice,
            "remaining_volume_data": self._remaining_volume_data,
            "remaining_volume_text": self._remaining_volume_text,
            "remaining_volume_voice": self._remaining_volume_voice,
            "period_end": self._period_end_date,
            "product": self._product,
            "mobile_json": self._data._mobilemeter,
            "number" : self._number,
            "active" : self._active,
            "outofbundle" : self._outofbundle,
            "mobileinternetonly" :  self._mobileinternetonly
        }

    @property
    def device_info(self) -> dict:
        """I can't remember why this was needed :D"""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": DOMAIN,
        }

    @property
    def unit(self) -> int:
        """Unit"""
        return int

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement this sensor expresses itself in."""
        return "%"

    @property
    def friendly_name(self) -> str:
        return self.unique_id
        
class SensorMobileAssigned(Entity):
    def __init__(self, data, productid, profileid, subsid, hass):
        self._data = data
        self._productid = productid
        self._profileid = profileid
        self._subsid = subsid
        self._hass = hass
        self._last_update = None
        self._total_volume_data = None
        self._total_volume_text = None
        self._total_volume_voice = None
        self._remaining_volume_data = None
        self._remaining_volume_text = None
        self._remaining_volume_voice = None
        self._remaining_volume = None
        self._remaining_volume_text = None
        self._remaining_volume_voice = None
        self._used_percentage_data = None
        self._used_percentage_text = None
        self._used_percentage_voice = None
        self._period_end_date = None
        self._product = None
        self._number = None
        self._active = None
        self._outofbundle = None
        self._mobileinternetonly = None  
        self._firstname = None
        self._lastname = None
        self._role = None

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._used_percentage_data

    async def async_update(self):
        await self._data.update()
        _LOGGER.debug(f"mobilemeter ComponentMobileShared subsid: {self._subsid}")
        
        mobileusage = self._data._mobilemeter.get('mobileusage')
        productdetails = mobileusage[self._productid]
        
        self._last_update =  productdetails.get('lastupdated')
        self._product = productdetails.get('label')
        self._period_end_date = productdetails.get('nextbillingdate')
        # get shared sensor
        profile = productdetails.get('profiles')[self._profileid]
        
        #todo: add checks on empty elements
        if profile:
            
            assignesub = profile.get('mobilesubscriptions')[self._subsid]
            if assignesub:
                if assignesub.get('included'):
                    if assignesub.get('included').get('data'):
                        self._total_volume_data = f"{assignesub.get('included').get('data').get('startunits')} {assignesub.get('included').get('data').get('unittype')}"
                        self._used_percentage_data = assignesub.get('included').get('data').get('usedpercentage')
                        self._remaining_volume_data = f"{assignesub.get('included').get('data').get('remainingunits')} {assignesub.get('included').get('data').get('unittype')}"
                    
                    if assignesub.get('included').get('text'):
                        self._total_volume_text = f"{assignesub.get('included').get('text').get('startunits')} {assignesub.get('included').get('text').get('unittype')}"
                        self._used_percentage_text = assignesub.get('included').get('text').get('usedpercentage')
                        self._remaining_volume_text = f"{assignesub.get('included').get('text').get('remainingunits')} {assignesub.get('included').get('text').get('unittype')}"
                    
                    if assignesub.get('included').get('voice'):
                        self._total_volume_voice = f"{assignesub.get('included').get('voice').get('startunits')} {assignesub.get('included').get('voice').get('unittype')}"             
                        self._used_percentage_voice = assignesub.get('included').get('voice').get('usedpercentage')
                        self._remaining_volume_voice = f"{assignesub.get('included').get('voice').get('remainingunits')} {assignesub.get('included').get('voice').get('unittype')}"
                    
                self._number = assignesub.get('mobile')
                self._active = assignesub.get('activationstate')
                if assignesub.get('outofbundle'):
                    self._outofbundle = f"{assignesub.get('outofbundle').get('usedunits')} {assignesub.get('outofbundle').get('unittype')}"
                self._mobileinternetonly = assignesub.get('mobileinternetonly')    

                self._firstname = profile.get('firstname')
                self._lastname = profile.get('lastname')
                self._role = profile.get('role')                
                
            
        
    async def async_will_remove_from_hass(self):
        """Clean up after entity before removal."""
        _LOGGER.info("async_will_remove_from_hass " + NAME)
        self._data.clear_session()


    @property
    def icon(self) -> str:
        """Shows the correct icon for container."""
        return "mdi:check-network-outline"
        #alternative: 
        #return "mdi:wifi_tethering_error"
        
    @property
    def unique_id(self) -> str:
        """Return the name of the sensor."""
        return (
            f"{NAME} mobile {self._data._mobilemeter.get('mobileusage')[self._productid].get('profiles')[self._profileid].get('mobilesubscriptions')[self._subsid].get('mobile')}"
        )

    @property
    def name(self) -> str:
        return self.unique_id

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return {
            ATTR_ATTRIBUTION: NAME,
            "last update": self._last_update,
            "used_percentage_data": self._used_percentage_data,
            "used_percentage_text": self._used_percentage_text,
            "used_percentage_voice": self._used_percentage_voice,
            "total_volume_data": self._total_volume_data,
            "total_volume_text": self._total_volume_text,
            "total_volume_voice": self._total_volume_voice,
            "remaining_volume_data": self._remaining_volume_data,
            "remaining_volume_text": self._remaining_volume_text,
            "remaining_volume_voice": self._remaining_volume_voice,
            "period_end": self._period_end_date,
            "product": self._product,
            "mobile_json": self._data._mobilemeter,
            "number" : self._number,
            "active" : self._active,
            "outofbundle" : self._outofbundle,
            "mobileinternetonly" :  self._mobileinternetonly,
            "firstname": self._firstname,
            "lastnam": self._lastname,
            "role": self._role
        }

    @property
    def device_info(self) -> dict:
        """I can't remember why this was needed :D"""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": DOMAIN,
        }

    @property
    def unit(self) -> int:
        """Unit"""
        return int

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement this sensor expresses itself in."""
        return "%"

    @property
    def friendly_name(self) -> str:
        return self.unique_id
  
