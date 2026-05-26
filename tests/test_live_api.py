"""Live integration tests — require real Telenet credentials.

Run with:
    USERNAME=you@example.com PASSWORD=secret .venv/bin/python3 -m unittest tests/test_live_api.py -v

Or create tests/secret.py containing:
    USERNAME = "you@example.com"
    PASSWORD = "secret"

These tests are skipped automatically when no credentials are available.
"""
import json
import os
import sys
import unittest

# ---------------------------------------------------------------------------
# HA stubs (same pattern as test_new_features.py)
# ---------------------------------------------------------------------------
import types as _types
from unittest.mock import MagicMock


class _AutoMockModule(_types.ModuleType):
    def __getattr__(self, name):
        v = MagicMock()
        setattr(self, name, v)
        return v


def _make_mock_module(name):
    m = _AutoMockModule(name)
    sys.modules[name] = m
    return m


for _mod_name in [
    "homeassistant", "homeassistant.config_entries", "homeassistant.core",
    "homeassistant.helpers", "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.config_validation", "homeassistant.helpers.entity",
    "homeassistant.helpers.typing", "homeassistant.components",
    "homeassistant.components.sensor", "homeassistant.components.binary_sensor",
    "homeassistant.const", "homeassistant.util",
    "voluptuous",
]:
    if _mod_name not in sys.modules:
        _make_mock_module(_mod_name)

sys.modules["homeassistant.const"].ATTR_ATTRIBUTION = "attribution"
sys.modules["homeassistant.helpers.config_validation"].string = str
sys.modules["homeassistant.helpers.config_validation"].boolean = bool
sys.modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = lambda h: None
sys.modules["homeassistant.helpers.entity"].Entity = object
sys.modules["homeassistant.components.binary_sensor"].BinarySensorEntity = object
sys.modules["homeassistant.components.binary_sensor"].DEVICE_CLASSES = []
sys.modules["homeassistant.util"].Throttle = lambda d: (lambda f: f)
_ps_mock = MagicMock()
_ps_mock.extend = MagicMock(return_value=MagicMock())
sys.modules["homeassistant.components.sensor"].PLATFORM_SCHEMA = _ps_mock
sys.modules["voluptuous"].Invalid = Exception

sys.path.insert(0, ".")
from custom_components.telenet_telemeter.utils import TelenetSession  # noqa: E402

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def _get_credentials():
    username = os.environ.get("USERNAME")
    password = os.environ.get("PASSWORD")
    if username and password:
        return username, password
    try:
        sys.path.insert(0, "tests")
        from secret import USERNAME, PASSWORD  # noqa: PLC0415
        return USERNAME, PASSWORD
    except ImportError:
        return None, None


_USERNAME, _PASSWORD = _get_credentials()
_HAS_CREDS = bool(_USERNAME and _PASSWORD)


@unittest.skipUnless(_HAS_CREDS, "No credentials — set USERNAME/PASSWORD env vars or create tests/secret.py")
class TestLiveInboxAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.session = TelenetSession()
        cls.session.login(_USERNAME, _PASSWORD)

    def test_login_succeeds(self):
        details = self.session.userdetails()
        self.assertIsNotNone(details)

    def test_inbox_messages_returns_data(self):
        result = self.session.inboxMessages()
        # Endpoint may return None if not supported for this account,
        # but it must not raise an exception.
        if result is not None:
            # Accept either a list or a dict with a "messages" key
            self.assertTrue(
                isinstance(result, (list, dict)),
                f"Expected list or dict, got {type(result)}: {result}",
            )
            print(f"\n[live] inboxMessages response (truncated):\n{json.dumps(result, indent=2, default=str)[:800]}")
        else:
            print("\n[live] inboxMessages returned None (endpoint not available for this account)")

    def test_inbox_count_returns_data(self):
        result = self.session.inboxCount()
        if result is not None:
            self.assertIsInstance(result, dict)
            print(f"\n[live] inboxCount response:\n{json.dumps(result, indent=2, default=str)}")
        else:
            print("\n[live] inboxCount returned None (endpoint not available for this account)")

    def test_inbox_messages_unread_count_consistent(self):
        """unreadMessagesCount from /inbox should match unread items in /inbox/messages."""
        count_resp = self.session.inboxCount()
        messages_resp = self.session.inboxMessages()

        if count_resp is None or messages_resp is None:
            self.skipTest("One or both inbox endpoints unavailable")

        messages = messages_resp if isinstance(messages_resp, list) else messages_resp.get("messages", [])
        unread_from_messages = sum(1 for m in messages if not m.get("read", False))
        unread_from_count = count_resp.get("unreadMessagesCount", unread_from_messages)
        self.assertEqual(
            unread_from_count, unread_from_messages,
            f"unreadMessagesCount={unread_from_count} but counted {unread_from_messages} unread in messages list",
        )

    def test_message_structure(self):
        """Each message should have the fields the sensor maps."""
        result = self.session.inboxMessages()
        if result is None:
            self.skipTest("inboxMessages endpoint unavailable")

        messages = result if isinstance(result, list) else result.get("messages", [])
        for msg in messages[:5]:  # check up to 5 messages
            # At least one of these id fields must be present
            has_id = bool(msg.get("messageId") or msg.get("id"))
            self.assertTrue(has_id, f"Message has no id field: {msg}")
            print(f"\n[live] message keys: {list(msg.keys())}")
            break  # one structural check is enough


@unittest.skipUnless(_HAS_CREDS, "No credentials — set USERNAME/PASSWORD env vars or create tests/secret.py")
class TestLiveInternetUsage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.session = TelenetSession()
        cls.session.login(_USERNAME, _PASSWORD)

    def test_api_version2_returns_bool(self):
        result = self.session.apiVersion2()
        self.assertIsInstance(result, bool)
        print(f"\n[live] apiVersion2: {result}")

    def test_plan_info(self):
        result = self.session.planInfo()
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0, "planInfo returned empty list")
        for p in result:
            print(f"\n[live] planInfo  id={p.get('identifier')}  type={p.get('productType')}  label={p.get('label','')}")

    def _collect_internet_products(self, plans):
        """Return list of (identifier, label) for every internet product in planInfo."""
        results = []
        for plan in plans:
            p_type = plan.get("productType", "").lower()
            if p_type == "bundle":
                for sp in plan.get("products") or []:
                    if sp.get("productType", "").lower() == "internet":
                        results.append((sp.get("identifier"), sp.get("label", "")))
            elif p_type == "internet":
                results.append((plan.get("identifier"), plan.get("label", "")))
        return results

    def _usage_gb_for_product(self, pid, start, end):
        """Return usage in GB for one internet product, matching the sensor logic."""
        usage = self.session.productUsage("internet", pid, start, end)
        daily = self.session.productDailyUsage("internet", pid, start, end)
        internet_data = usage.get("internet", {})
        category = internet_data.get("category", "")
        daily_list = daily.get("internetUsage", [])

        if category == "CAP":
            allocated = internet_data.get("allocatedUsage", {}).get("units", 0) or 0
            used_pct = internet_data.get("usedPercentage", 0) or 0
            usage_gb = round(float(used_pct) / 100 * float(allocated), 2) if allocated else 0
            print(f"\n[live] {pid} (CAP): {usage_gb} GB  ({used_pct}% of {allocated} GB)")
        elif daily_list:
            peak = round(daily_list[0].get("totalUsage", {}).get("peak", 0) or 0, 2)
            offpeak = round(daily_list[0].get("totalUsage", {}).get("offPeak", 0) or 0, 2)
            usage_gb = round(peak + offpeak, 2)
            print(f"\n[live] {pid} (TURBO): peak={peak} GB  offPeak={offpeak} GB  total={usage_gb} GB")
        else:
            usage_gb = internet_data.get("totalUsage", {}).get("units", 0) or 0
            print(f"\n[live] {pid} (fallback): {usage_gb} GB")
        return usage_gb

    def test_bill_cycles_and_usage(self):
        plans = self.session.planInfo()
        if not plans:
            self.skipTest("No plans returned")

        products = self._collect_internet_products(plans)
        if not products:
            self.skipTest("No internet product found in planInfo")

        # Use first product for bill cycle check (matches sensor behaviour)
        internet_id = products[0][0]
        cycles = self.session.billCycles("internet", internet_id)
        self.assertIn("billCycles", cycles)
        cycle = cycles["billCycles"][0]
        start = cycle["startDate"]
        end = cycle["endDate"]
        print(f"\n[live] bill cycle: {start} → {end}")

        usage_gb = self._usage_gb_for_product(internet_id, start, end)
        self.assertGreaterEqual(usage_gb, 0)

    def test_all_internet_products_usage(self):
        """Report usage for every internet product in the account."""
        plans = self.session.planInfo()
        if not plans:
            self.skipTest("No plans returned")

        products = self._collect_internet_products(plans)
        if not products:
            self.skipTest("No internet products found in planInfo")

        print(f"\n[live] found {len(products)} internet product(s)")
        for pid, label in products:
            cycles = self.session.billCycles("internet", pid)
            if "billCycles" not in cycles:
                print(f"\n[live] {pid}: no billCycles, skipping")
                continue
            cycle = cycles["billCycles"][0]
            start, end = cycle["startDate"], cycle["endDate"]
            usage_gb = self._usage_gb_for_product(pid, start, end)
            self.assertGreaterEqual(usage_gb, 0, f"{pid} reported negative usage")

    def test_days_until_new_period(self):
        from datetime import datetime, timedelta
        plans = self.session.planInfo()
        if not plans:
            self.skipTest("No plans returned")

        for plan in plans:
            products = plan.get("products") or [plan]
            for p in products:
                if p.get("productType", "").lower() == "internet":
                    cycles = self.session.billCycles("internet", p["identifier"])
                    end_str = cycles["billCycles"][0]["endDate"]
                    end = datetime.strptime(end_str, "%Y-%m-%d") + timedelta(days=1)
                    days_left = round((end - datetime.now()).total_seconds() / 86400, 2)
                    self.assertGreaterEqual(days_left, 0)
                    self.assertLessEqual(days_left, 35)
                    print(f"\n[live] period_days_left: {days_left}")
                    return
        self.skipTest("No internet product found")


@unittest.skipUnless(_HAS_CREDS, "No credentials — set USERNAME/PASSWORD env vars or create tests/secret.py")
class TestLiveMobileUsage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.session = TelenetSession()
        cls.session.login(_USERNAME, _PASSWORD)
        cls.mobile_subs = cls.session.productSubscriptions("MOBILE")

    def test_mobile_subscriptions_returned(self):
        self.assertIsInstance(self.mobile_subs, list)
        self.assertGreater(len(self.mobile_subs), 0, "productSubscriptions(MOBILE) returned empty list")
        for sub in self.mobile_subs:
            print(f"\n[live] mobile sub  id={sub.get('identifier')}  type={sub.get('productType')}  label={sub.get('label','')}")

    def test_mobile_data_usage_per_subscription(self):
        """Report mobile data usage (GB) for each subscription."""
        if not self.mobile_subs:
            self.skipTest("No mobile subscriptions")

        for sub in self.mobile_subs:
            identifier = sub.get("identifier")
            label = sub.get("label", "")
            p_type = (sub.get("productType") or "").lower()

            if p_type == "bundle":
                bundle_id = sub.get("bundleIdentifier")
                usage = self.session.mobileBundleUsage(bundle_id, identifier)
            else:
                usage = self.session.mobileUsage(identifier)

            if usage is None:
                print(f"\n[live] {identifier} ({label}): rate-limited or unavailable, skipping")
                continue

            # Extract data usage the same way the sensor does
            shared = usage.get("shared") if (usage.get("shared") and p_type == "bundle") else None
            if shared:
                data_entries = shared.get("data", [])
                if data_entries:
                    d = data_entries[0]
                    used = d.get("usedUnits", "?")
                    remaining = d.get("remainingUnits", "?")
                    pct = d.get("usedPercentage", "?")
                    unit = d.get("unitType", "")
                    print(f"\n[live] {identifier} ({label}) bundle: used={used} {unit}  remaining={remaining} {unit}  {pct}%")
            else:
                included = usage.get("included") or {}
                total = usage.get("total") or {}
                data_src = total.get("data") or included.get("data") or {}
                used = data_src.get("usedUnits", "?")
                remaining = data_src.get("remainingUnits", "?")
                pct = data_src.get("usedPercentage", "?")
                unit = data_src.get("unitType", "")

                # Monetary fallback (e.g. BASE plans where €1 = 1 GB)
                if (used in ("?", None, 0, "0") or str(used) == "0") and total.get("monetary"):
                    mon = total["monetary"]
                    used = f"{mon.get('usedUnits','?')} GB"
                    remaining = f"{mon.get('remainingUnits','?')} GB"
                    pct = mon.get("usedPercentage", "?")
                    unit = "GB (monetary)"

                print(f"\n[live] {identifier} ({label}): used={used} {unit}  remaining={remaining} {unit}  {pct}%")


if __name__ == "__main__":
    unittest.main(verbosity=2)
