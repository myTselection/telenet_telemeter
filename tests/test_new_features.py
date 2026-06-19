"""Unit tests for inbox messages, usage_gb, and SensorAnnouncements."""
import asyncio
import json
import sys
import types as _types
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub homeassistant before any project imports
# ---------------------------------------------------------------------------

def _make_module(name, **attrs):
    m = _types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m

class _AutoMockModule(_types.ModuleType):
    """Module stub: any attribute access returns a MagicMock."""
    def __getattr__(self, name):
        v = MagicMock()
        setattr(self, name, v)
        return v

def _make_mock_module(name):
    m = _AutoMockModule(name)
    sys.modules[name] = m
    return m

try:
    import ratelimit  # noqa: F401
except ImportError:
    _make_module(
        "ratelimit",
        limits=lambda *args, **kwargs: (lambda f: f),
        sleep_and_retry=lambda f: f,
    )

# Stub every homeassistant sub-module that the package imports.
for _mod_name in [
    "homeassistant", "homeassistant.config_entries", "homeassistant.core",
    "homeassistant.helpers", "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.config_validation", "homeassistant.helpers.entity",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.typing", "homeassistant.components",
    "homeassistant.components.sensor", "homeassistant.components.binary_sensor",
    "homeassistant.components.switch",
    "homeassistant.const", "homeassistant.util",
    "voluptuous",
]:
    _make_mock_module(_mod_name)

# Provide the specific values that sensor.py and utils.py actually USE
# (attribute access, not just import-name binding).
sys.modules["homeassistant.const"].ATTR_ATTRIBUTION = "attribution"
sys.modules["homeassistant.helpers.config_validation"].string = str
sys.modules["homeassistant.helpers.config_validation"].boolean = bool
sys.modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = lambda h: None
sys.modules["homeassistant.helpers.entity"].Entity = object
class _CoordinatorEntity:
    def __init__(self, coordinator=None):
        self.coordinator = coordinator
    def async_write_ha_state(self):
        pass
class _DataUpdateCoordinator:
    def __init__(self, *args, **kwargs):
        self.update_method = kwargs.get("update_method")
        self.data = None
    async def async_config_entry_first_refresh(self):
        if self.update_method:
            self.data = await self.update_method()
    async def async_request_refresh(self):
        if self.update_method:
            self.data = await self.update_method()
sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = _CoordinatorEntity
sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = _DataUpdateCoordinator
sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed = Exception
sys.modules["homeassistant.components.binary_sensor"].BinarySensorEntity = object
sys.modules["homeassistant.components.binary_sensor"].DEVICE_CLASSES = []
sys.modules["homeassistant.components.switch"].SwitchEntity = object
sys.modules["homeassistant.util"].Throttle = lambda d: (lambda f: f)
_ps_mod = sys.modules["homeassistant.components.sensor"]
_ps_mock = MagicMock()
_ps_mock.extend = MagicMock(return_value=MagicMock())
_ps_mod.PLATFORM_SCHEMA = _ps_mock
sys.modules["voluptuous"].Invalid = Exception

sys.path.insert(0, ".")

from custom_components.telenet_telemeter.utils import TelenetSession  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code, body):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = body
    r.text = json.dumps(body)
    return r


def _make_component_data(inbox=None, v2=True, telemeter=None, product_details=None):
    """Return a minimal ComponentData-like mock."""
    data = MagicMock()
    data._inbox_messages = inbox
    data._v2 = v2
    data._telemeter = telemeter or {}
    data._product_details = product_details or {}
    data._username = "test@example.com"
    data.unique_id = "Telenet Telemeter test@example.com"
    data.name = "Telenet Telemeter"
    data._mobile_line_usage = {}
    data._mobile_parsed = {}
    # update() is a no-op coroutine
    async def noop_update():
        pass
    data.update = noop_update
    return data


# ---------------------------------------------------------------------------
# TelenetSession.inboxMessages / inboxCount
# ---------------------------------------------------------------------------

class TestTelenetSessionInbox(unittest.TestCase):

    def _make_session(self):
        session = TelenetSession.__new__(TelenetSession)
        session.provider = "Telenet"
        session.api_url = "https://api.prd.telenet.be"
        return session

    def test_inbox_messages_returns_json_on_200(self):
        session = self._make_session()
        payload = {"messages": [{"messageId": "abc", "title": "Hi", "read": False}]}
        with patch.object(session, "callTelenet", return_value=_mock_response(200, payload)):
            result = session.inboxMessages()
        self.assertEqual(result, payload)

    def test_inbox_messages_returns_none_on_non_200(self):
        session = self._make_session()
        with patch.object(session, "callTelenet", return_value=_mock_response(401, {})):
            result = session.inboxMessages()
        self.assertIsNone(result)

    def test_inbox_messages_returns_none_on_403(self):
        session = self._make_session()
        with patch.object(session, "callTelenet", return_value=_mock_response(403, {})):
            result = session.inboxMessages()
        self.assertIsNone(result)

    def test_inbox_count_returns_json_on_200(self):
        session = self._make_session()
        payload = {"unreadMessagesCount": 3}
        with patch.object(session, "callTelenet", return_value=_mock_response(200, payload)):
            result = session.inboxCount()
        self.assertEqual(result, payload)
        self.assertEqual(result["unreadMessagesCount"], 3)

    def test_inbox_count_returns_none_on_non_200(self):
        session = self._make_session()
        with patch.object(session, "callTelenet", return_value=_mock_response(404, {})):
            result = session.inboxCount()
        self.assertIsNone(result)

    def test_inbox_messages_uses_correct_url(self):
        session = self._make_session()
        with patch.object(session, "callTelenet", return_value=_mock_response(200, {})) as mock_call:
            session.inboxMessages()
        url = mock_call.call_args[0][0]
        self.assertIn("telenet-app-inbox-messages-cs/v1/inbox/messages", url)

    def test_inbox_count_uses_correct_url(self):
        session = self._make_session()
        with patch.object(session, "callTelenet", return_value=_mock_response(200, {})) as mock_call:
            session.inboxCount()
        url = mock_call.call_args[0][0]
        self.assertIn("telenet-app-inbox-messages-cs/v1/inbox", url)
        self.assertNotIn("/messages", url)


# ---------------------------------------------------------------------------
# SensorAnnouncements
# ---------------------------------------------------------------------------

try:
    import custom_components.telenet_telemeter.coordinator as _coord_mod
    import custom_components.telenet_telemeter.sensor as _sensor_mod
    import custom_components.telenet_telemeter.switch as _switch_mod
    SensorAnnouncements = _sensor_mod.SensorAnnouncements
    SensorPeak = _sensor_mod.SensorPeak
    SensorInternet = _sensor_mod.SensorInternet
    ComponentMobileShared = _sensor_mod.ComponentMobileShared
    SensorMobile = _sensor_mod.SensorMobile
    SensorMobileAttribute = _sensor_mod.SensorMobileAttribute
    WifiSwitch = _switch_mod.WifiSwitch
    get_desired_internet_product = _coord_mod.get_desired_internet_product
    _internet_identifier_from_product = _coord_mod._internet_identifier_from_product
    _parse_mobile_line_usage = _coord_mod._parse_mobile_line_usage
    _SENSOR_AVAILABLE = True
except Exception:
    _SENSOR_AVAILABLE = False


@unittest.skipUnless(_SENSOR_AVAILABLE, "sensor module could not be imported without HA")
class TestSensorAnnouncements(unittest.TestCase):

    def _run(self, coro):
        return asyncio.run(coro)

    def test_state_is_none_when_inbox_unavailable(self):
        data = _make_component_data(inbox=None)
        sensor = SensorAnnouncements(data, None)
        self._run(sensor.async_update())
        self.assertIsNone(sensor.state)
        self.assertIsNone(sensor._messages)

    def test_state_zero_when_all_messages_read(self):
        inbox = {"messages": [
            {"messageId": "1", "title": "Hello", "read": True, "createdAt": "2026-01-01T10:00:00"},
            {"messageId": "2", "title": "World", "read": True, "createdAt": "2026-01-02T10:00:00"},
        ]}
        data = _make_component_data(inbox=inbox)
        sensor = SensorAnnouncements(data, None)
        self._run(sensor.async_update())
        self.assertEqual(sensor.state, 0)
        self.assertEqual(len(sensor._messages), 2)

    def test_unread_count_correct(self):
        inbox = {"messages": [
            {"messageId": "1", "title": "Unread A", "read": False},
            {"messageId": "2", "title": "Read B",   "read": True},
            {"messageId": "3", "title": "Unread C", "read": False},
        ]}
        data = _make_component_data(inbox=inbox)
        sensor = SensorAnnouncements(data, None)
        self._run(sensor.async_update())
        self.assertEqual(sensor.state, 2)

    def test_empty_messages_list(self):
        data = _make_component_data(inbox={"messages": []})
        sensor = SensorAnnouncements(data, None)
        self._run(sensor.async_update())
        self.assertEqual(sensor.state, 0)
        self.assertEqual(sensor._messages, [])

    def test_inbox_as_plain_list(self):
        """Some API versions may return a bare list instead of a dict."""
        inbox = [
            {"messageId": "x", "title": "Notice", "read": False},
        ]
        data = _make_component_data(inbox=inbox)
        sensor = SensorAnnouncements(data, None)
        self._run(sensor.async_update())
        self.assertEqual(sensor.state, 1)

    def test_message_fields_mapped_correctly(self):
        inbox = {"messages": [{
            "messageId": "abc123",
            "title": "Important update",
            "body": "Your plan changes next month.",
            "type": "INFO",
            "createdAt": "2026-05-01T09:00:00",
            "read": False,
        }]}
        data = _make_component_data(inbox=inbox)
        sensor = SensorAnnouncements(data, None)
        self._run(sensor.async_update())
        msg = sensor._messages[0]
        self.assertEqual(msg["messageId"], "abc123")
        self.assertEqual(msg["title"], "Important update")
        self.assertEqual(msg["body"], "Your plan changes next month.")
        self.assertEqual(msg["type"], "INFO")
        self.assertEqual(msg["createdAt"], "2026-05-01T09:00:00")
        self.assertFalse(msg["read"])

    def test_fallback_id_field(self):
        """messageId should fall back to id if messageId is absent."""
        inbox = {"messages": [{"id": "fallback-id", "title": "Hi", "read": False}]}
        data = _make_component_data(inbox=inbox)
        sensor = SensorAnnouncements(data, None)
        self._run(sensor.async_update())
        self.assertEqual(sensor._messages[0]["messageId"], "fallback-id")

    def test_fallback_body_to_content(self):
        """body should fall back to content field."""
        inbox = {"messages": [{"messageId": "1", "content": "Text here", "read": True}]}
        data = _make_component_data(inbox=inbox)
        sensor = SensorAnnouncements(data, None)
        self._run(sensor.async_update())
        self.assertEqual(sensor._messages[0]["body"], "Text here")

    def test_extra_state_attributes_keys(self):
        data = _make_component_data(inbox={"messages": []})
        sensor = SensorAnnouncements(data, None)
        self._run(sensor.async_update())
        attrs = sensor.extra_state_attributes
        self.assertIn("last_update", attrs)
        self.assertIn("unread_count", attrs)
        self.assertIn("messages", attrs)

    def test_unique_id_contains_username(self):
        data = _make_component_data()
        sensor = SensorAnnouncements(data, None)
        self.assertIn("test@example.com", sensor.unique_id)

    def test_icon(self):
        data = _make_component_data()
        sensor = SensorAnnouncements(data, None)
        self.assertEqual(sensor.icon, "mdi:bell-outline")


@unittest.skipUnless(_SENSOR_AVAILABLE, "sensor module could not be imported without HA")
class TestEntityNames(unittest.TestCase):

    def _make_telemeter_data(self):
        return _make_component_data(
            telemeter={
                "productIdentifier": "W12345678",
                "productLabel": "All-Internet",
                "wifidetails": {
                    "internetProductIdentifier": "W12345678",
                    "wifiEnabled": True,
                },
            }
        )

    def test_internet_name_uses_old_short_shape(self):
        sensor = SensorInternet(self._make_telemeter_data(), None)
        self.assertTrue(sensor._attr_has_entity_name)
        self.assertEqual(sensor.name, "internet W12345678")
        self.assertEqual(sensor.suggested_object_id, "internet W12345678")
        self.assertEqual(sensor.device_info["name"], "Telenet Telemeter")
        self.assertNotIn("test@example.com", sensor.name)
        self.assertNotIn("All-Internet", sensor.name)

    def test_peak_name_uses_old_short_shape(self):
        sensor = SensorPeak(self._make_telemeter_data(), None)
        self.assertEqual(sensor.name, "peak W12345678")
        self.assertEqual(sensor.suggested_object_id, "peak W12345678")

    def test_mobile_names_use_identifier_without_label_or_username(self):
        product = {"identifier": "M12345678", "label": "Mobile Plan / Extra"}
        sensor = SensorMobile(_make_component_data(), product, None)
        attr = SensorMobileAttribute(_make_component_data(), product, None, "period_days_left", "days left", "days", "mdi:calendar")
        self.assertEqual(sensor.name, "mobile M12345678")
        self.assertEqual(sensor.suggested_object_id, "mobile M12345678")
        self.assertEqual(attr.name, "mobile M12345678 days left")
        self.assertEqual(attr.suggested_object_id, "mobile M12345678 days left")
        self.assertNotIn("test@example.com", sensor.name)
        self.assertNotIn("Mobile Plan", sensor.name)

    def test_shared_mobile_and_announcements_names_are_short(self):
        shared = ComponentMobileShared(_make_component_data(), 0, None)
        announcements = SensorAnnouncements(_make_component_data(), None)
        self.assertEqual(shared.name, "mobile shared 0")
        self.assertEqual(shared.suggested_object_id, "mobile shared 0")
        self.assertEqual(announcements.name, "announcements")
        self.assertEqual(announcements.suggested_object_id, "announcements")

    def test_wifi_switch_name_uses_identifier_without_account_prefix(self):
        data = self._make_telemeter_data()
        switch = WifiSwitch(data, SimpleNamespace(_hass=None))
        switch._update_from_data()
        self.assertTrue(switch._attr_has_entity_name)
        self.assertEqual(switch.name, "Wifi W12345678")
        self.assertEqual(switch.suggested_object_id, "Wifi W12345678")
        self.assertEqual(switch.device_info["name"], "Telenet Telemeter")


@unittest.skipUnless(_SENSOR_AVAILABLE, "sensor module could not be imported without HA")
class TestEmptyDataDefaults(unittest.TestCase):

    def test_internet_empty_v2_payload_defaults_to_zero(self):
        data = _make_component_data(v2=True, telemeter={}, product_details={})
        sensor = SensorInternet(data, None)
        sensor._update_from_data()
        attrs = sensor.extra_state_attributes
        self.assertEqual(sensor.state, 0)
        self.assertEqual(attrs["usage_gb"], 0)
        self.assertEqual(attrs["used_percentage"], 0)
        self.assertEqual(attrs["period_days_left"], 0)
        self.assertEqual(attrs["total_volume"], 0)

    def test_internet_zero_total_volume_uses_percentage_fallback(self):
        data = _make_component_data(
            v2=True,
            telemeter={
                "internet": {
                    "category": "CAP",
                    "totalUsage": {"units": 5},
                    "allocatedUsage": {"units": 0},
                    "extendedUsage": {"volume": 0},
                    "usedPercentage": 80,
                },
                "internetUsage": [],
            },
            product_details={},
        )
        sensor = SensorInternet(data, None)
        sensor._update_from_data()
        attrs = sensor.extra_state_attributes
        self.assertEqual(sensor.state, 5)
        self.assertEqual(attrs["used_percentage"], 80)
        self.assertEqual(attrs["total_volume"], 0)

    def test_legacy_cap_usage_uses_included_and_extended_counters(self):
        mib = 1024 * 1024
        data = _make_component_data(
            v2=False,
            telemeter={
                "internetusage": [
                    {
                        "lastupdated": "2026-06-19T08:00:00.0+0200",
                        "availableperiods": [
                            {
                                "usages": [
                                    {
                                        "producttype": "internet",
                                        "periodstart": "2026-06-01T00:00:00.0+0200",
                                        "periodend": "2026-06-30T00:00:00.0+0200",
                                        "includedvolume": 200 * mib,
                                        "extendedvolume": {"volume": 0},
                                        "totalusage": {
                                            "peak": None,
                                            "includedvolume": 50 * mib,
                                            "extendedvolume": 10 * mib,
                                        },
                                    }
                                ]
                            }
                        ],
                    }
                ]
            },
            product_details={},
        )
        sensor = SensorInternet(data, None)
        sensor._update_from_data()
        attrs = sensor.extra_state_attributes
        self.assertEqual(sensor.state, 60)
        self.assertEqual(attrs["usage_gb"], 60)
        self.assertEqual(attrs["includedvolume_usage"], 50 * mib)
        self.assertEqual(attrs["extendedvolume_usage"], 10 * mib)

    def test_peak_empty_v2_payload_defaults_to_zero(self):
        data = _make_component_data(v2=True, telemeter={}, product_details={})
        sensor = SensorPeak(data, None)
        sensor._update_from_data()
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["used_percentage"], 0)
        self.assertEqual(attrs["peak_usage"], 0)
        self.assertEqual(attrs["offpeak_usage"], 0)
        self.assertIsInstance(sensor.is_on, bool)

    def test_mobile_missing_cache_defaults_to_zero(self):
        data = _make_component_data()
        sensor = SensorMobile(data, {"identifier": "M12345678"}, None)
        sensor._update_from_data()
        self.assertEqual(sensor.state, 0)

    def test_mobile_attribute_missing_cache_defaults_by_type(self):
        data = _make_component_data()
        numeric = SensorMobileAttribute(data, {"identifier": "M12345678"}, None, "usage_gb", "usage", "GB", "mdi:database")
        text = SensorMobileAttribute(data, {"identifier": "M12345678"}, None, "last_update_formatted", "last update", None, "mdi:clock")
        self.assertEqual(numeric.state, 0)
        self.assertIsNone(text.state)

    def test_mobile_parser_empty_payload_defaults_to_zero(self):
        parsed = _parse_mobile_line_usage({"identifier": "M12345678"}, {})
        self.assertEqual(parsed["usage_gb"], 0)
        self.assertEqual(parsed["used_percentage_data"], 0)
        self.assertEqual(parsed["voice_used_minutes"], 0)
        self.assertEqual(parsed["period_days_left"], 0)

    def test_empty_internet_product_list_returns_empty_product(self):
        self.assertEqual(get_desired_internet_product([], "internet"), {})

    def test_bundle_without_internet_child_keeps_bundle_identifier(self):
        product = {
            "identifier": "BUNDLE123",
            "productType": "bundle",
            "products": [
                {"identifier": "TV123", "productType": "television"},
                {"identifier": "MOB123", "productType": "mobile"},
            ],
        }
        self.assertEqual(_internet_identifier_from_product(product), "BUNDLE123")

    def test_bundle_with_internet_child_uses_internet_identifier(self):
        product = {
            "identifier": "BUNDLE123",
            "productType": "bundle",
            "products": [
                {"identifier": "TV123", "productType": "television"},
                {"identifier": "W12345678", "productType": "internet"},
            ],
        }
        self.assertEqual(_internet_identifier_from_product(product), "W12345678")


# ---------------------------------------------------------------------------
# usage_gb computation (tested in isolation without full async_update)
# ---------------------------------------------------------------------------

class TestUsageGb(unittest.TestCase):

    def test_usage_gb_computed_from_percentage_and_total(self):
        """usage_gb = used_percentage / 100 * total_volume."""
        used_pct = 50.0
        total_vol = 200.0  # GB
        usage_gb = round(used_pct / 100 * total_vol, 2)
        self.assertAlmostEqual(usage_gb, 100.0)

    def test_usage_gb_zero_percent(self):
        usage_gb = round(0.0 / 100 * 200.0, 2)
        self.assertEqual(usage_gb, 0.0)

    def test_usage_gb_full(self):
        usage_gb = round(100.0 / 100 * 150.0, 2)
        self.assertAlmostEqual(usage_gb, 150.0)

    def test_usage_gb_fractional(self):
        usage_gb = round(33.33 / 100 * 300.0, 2)
        self.assertAlmostEqual(usage_gb, 99.99)

    @unittest.skipUnless(_SENSOR_AVAILABLE, "sensor module could not be imported without HA")
    def test_usage_gb_attribute_present_in_internet_sensor(self):
        data = _make_component_data()
        sensor = SensorInternet(data, None)
        sensor._used_percentage = 75.0
        sensor._total_volume = 200.0
        sensor._usage_gb = round(75.0 / 100 * 200.0, 2)
        attrs = sensor.extra_state_attributes
        self.assertIn("usage_gb", attrs)
        self.assertAlmostEqual(attrs["usage_gb"], 150.0)


if __name__ == "__main__":
    unittest.main()
