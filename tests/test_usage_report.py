"""Live usage report — exercises every relevant API endpoint and prints a
human-readable summary of all Telenet products and their current usage.

Run with:
    .venv/bin/python3 -m pytest tests/test_usage_report.py -v -s

Or:
    .venv/bin/python3 -m unittest tests/test_usage_report.py -v
"""
import json
import os
import sys
import unittest
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# HA stubs
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

try:
    import ratelimit  # noqa: F401
except ImportError:
    _ratelimit = _types.ModuleType("ratelimit")
    _ratelimit.limits = lambda *args, **kwargs: (lambda f: f)
    _ratelimit.sleep_and_retry = lambda f: f
    sys.modules["ratelimit"] = _ratelimit


for _mod_name in [
    "homeassistant", "homeassistant.config_entries", "homeassistant.core",
    "homeassistant.helpers", "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.config_validation", "homeassistant.helpers.entity",
    "homeassistant.helpers.update_coordinator",
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
    u = os.environ.get("USERNAME")
    p = os.environ.get("PASSWORD")
    if u and p:
        return u, p
    try:
        sys.path.insert(0, "tests")
        from secret import USERNAME, PASSWORD
        return USERNAME, PASSWORD
    except ImportError:
        return None, None


_USERNAME, _PASSWORD = _get_credentials()
_HAS_CREDS = bool(_USERNAME and _PASSWORD)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _days_left(date_str):
    """Return days between now and an ISO date string (UTC-aware)."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return round((dt - datetime.now(timezone.utc)).total_seconds() / 86400, 1)
    except Exception:
        return None


def _bar(consumed, total, width=20):
    if not total:
        return "[" + "?" * width + "]"
    filled = int(width * min(consumed, total) / total)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_CREDS, "No credentials — set USERNAME/PASSWORD or create tests/secret.py")
class TestUsageReport(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.session = TelenetSession()
        cls.session.login(_USERNAME, _PASSWORD)
        print(f"\n{'='*60}")
        print(f"  Telenet Usage Report")
        print(f"  Account: {_USERNAME}")
        print(f"{'='*60}")

    # ------------------------------------------------------------------
    # Mobile
    # ------------------------------------------------------------------

    def test_01_mobile_lines(self):
        """List all mobile lines from the line selector."""
        lines = self.session.mobileLines()
        self.assertIsInstance(lines, list)
        self.assertGreater(len(lines), 0, "No mobile lines returned")

        print(f"\n{'─'*60}")
        print(f"  MOBILE LINES  ({len(lines)} found)")
        print(f"{'─'*60}")
        for line in lines:
            data_only = "data-only" if line.get('isDataOnly') else "voice+data"
            print(f"  {line.get('msisdn')}  [{line.get('status')}]  {data_only}")

        # Store for use in later tests
        TestUsageReport._lines = lines

    def test_02_mobile_usage_per_line(self):
        """Fetch and display usage for each mobile line."""
        lines = getattr(TestUsageReport, '_lines', None)
        if not lines:
            lines = self.session.mobileLines()

        print(f"\n{'─'*60}")
        print(f"  MOBILE USAGE")
        print(f"{'─'*60}")

        for line in lines:
            msisdn = line.get('msisdn')
            is_data_only = line.get('isDataOnly', False)

            result = self.session.mobileLineUsage(msisdn)
            self.assertIsNotNone(result, f"mobileLineUsage returned None for {msisdn}")

            subscription = (result.get('usage') or {}).get('subscription', {})
            breakdown = subscription.get('breakdown', {})
            bars_summary = breakdown.get('barsSummary', {})
            bars = bars_summary.get('bars', [])
            tiles = breakdown.get('tiles', [])

            plan_name = (
                subscription.get('planName', {}).get('nl') or
                subscription.get('planName', {}).get('en') or 'Unknown'
            )
            next_billing = subscription.get('nextBillingDate')
            last_updated = subscription.get('lastUpdated', '')[:19]
            days_left = _days_left(next_billing)
            line_category = subscription.get('lineCategory', '')

            print(f"\n  {msisdn}  —  {plan_name}  [{line_category}]")
            print(f"    Status      : {line.get('status')}  ({'data-only' if is_data_only else 'voice+data'})")
            print(f"    Last update : {last_updated}")
            print(f"    Days left   : {days_left}")

            # Data bar
            data_bar = next((b for b in bars if b.get('category') == 'DATA'), None)
            if data_bar:
                consumed = data_bar.get('consumed', 0) or 0
                remaining = data_bar.get('remaining', 0) or 0
                total = data_bar.get('total', 0) or 0
                pct = data_bar.get('consumedPercentage', 0) or 0
                unit = data_bar.get('unit', 'GB')
                line_type = data_bar.get('lineType', '')
                validity = data_bar.get('validityEndDate', '')[:10]
                print(f"    Data        : {consumed:.2f} / {total:.2f} {unit}  ({pct:.1f}%)  {_bar(consumed, total)}  [{line_type}]")
                print(f"    Remaining   : {remaining:.2f} {unit}  (valid until {validity})")

                self.assertGreaterEqual(consumed, 0)
                self.assertGreaterEqual(total, 0)
            elif bars_summary.get('totalConsumed') is not None:
                consumed = bars_summary.get('totalConsumed', 0) or 0
                allocated = bars_summary.get('totalAllocated', 0) or 0
                print(f"    Data (agg)  : {consumed:.2f} / {allocated:.2f} GB  {_bar(consumed, allocated)}")

            # Voice tile
            call_tile = next((t for t in tiles if t.get('category') == 'CALL'), None)
            if call_tile:
                v_used = call_tile.get('consumed', 0) or 0
                v_total = call_tile.get('total', 0) or 0
                v_unit = call_tile.get('unit', 'MINUTES')
                v_type = call_tile.get('lineType', '')
                v_total_str = f"/ {v_total:.0f}" if v_total > 0 else "(unlimited)"
                print(f"    Voice       : {v_used:.1f} {v_unit.lower()}  {v_total_str}  [{v_type}]")
            elif not is_data_only:
                print(f"    Voice       : not in response")

            # SMS tile
            sms_tile = next((t for t in tiles if t.get('category') == 'SMS'), None)
            if sms_tile:
                s_used = sms_tile.get('consumed', 0) or 0
                s_total = sms_tile.get('total', 0) or 0
                s_type = sms_tile.get('lineType', '')
                s_total_str = f"/ {s_total:.0f}" if s_total > 0 else "(unlimited)"
                print(f"    SMS         : {s_used:.0f}  {s_total_str}  [{s_type}]")

            # Roaming bundles
            roaming = (result.get('usage') or {}).get('roamingBundles', [])
            if roaming:
                print(f"    Roaming     : {len(roaming)} bundle(s)")

            # Assert required fields exist
            self.assertIn('msisdn', result)
            self.assertIn('lineStatus', result)
            self.assertIn('usage', result)

    def test_03_mobile_usage_assertions(self):
        """Assert specific data fields are correct types."""
        lines = self.session.mobileLines()
        for line in lines:
            msisdn = line.get('msisdn')
            result = self.session.mobileLineUsage(msisdn)
            if result is None:
                continue

            sub = (result.get('usage') or {}).get('subscription', {})
            breakdown = sub.get('breakdown', {})
            bars = breakdown.get('barsSummary', {}).get('bars', [])

            data_bar = next((b for b in bars if b.get('category') == 'DATA'), None)
            if data_bar:
                self.assertIsInstance(data_bar.get('consumed'), (int, float),
                    f"{msisdn}: consumed should be numeric")
                self.assertIsInstance(data_bar.get('total'), (int, float),
                    f"{msisdn}: total should be numeric")
                self.assertGreaterEqual(data_bar.get('consumedPercentage', 0), 0,
                    f"{msisdn}: consumedPercentage should be >= 0")
                self.assertLessEqual(data_bar.get('consumedPercentage', 0), 100,
                    f"{msisdn}: consumedPercentage should be <= 100")

    # ------------------------------------------------------------------
    # Internet
    # ------------------------------------------------------------------

    def test_04_internet_usage(self):
        """Fetch and display internet usage via planInfo + productUsage."""
        plans = self.session.planInfo()
        self.assertIsInstance(plans, list)
        self.assertGreater(len(plans), 0)

        print(f"\n{'─'*60}")
        print(f"  INTERNET USAGE")
        print(f"{'─'*60}")

        found_internet = False
        for plan in plans:
            p_type = (plan.get('productType') or '').lower()
            products = plan.get('products') or [plan]

            for product in products:
                if (product.get('productType') or '').lower() != 'internet':
                    continue
                found_internet = True
                pid = product.get('identifier')
                label = product.get('label', pid)

                cycles = self.session.billCycles('internet', pid)
                self.assertIn('billCycles', cycles, f"No billCycles for {pid}")
                cycle = cycles['billCycles'][0]
                start, end = cycle['startDate'], cycle['endDate']

                usage = self.session.productUsage('internet', pid, start, end)
                daily = self.session.productDailyUsage('internet', pid, start, end)

                internet = usage.get('internet', {})
                category = internet.get('category', '')
                daily_list = daily.get('internetUsage', [])

                if category == 'CAP':
                    allocated = (internet.get('allocatedUsage') or {}).get('units', 0) or 0
                    used_pct = internet.get('usedPercentage', 0) or 0
                    usage_gb = round(used_pct / 100 * allocated, 2) if allocated else 0
                    print(f"\n  {label}  [{category}]")
                    print(f"    Period      : {start} → {end}")
                    print(f"    Usage       : {usage_gb:.2f} / {allocated:.0f} GB  ({used_pct:.1f}%)  {_bar(usage_gb, allocated)}")
                elif daily_list:
                    peak = round(daily_list[0].get('totalUsage', {}).get('peak', 0) or 0, 2)
                    offpeak = round(daily_list[0].get('totalUsage', {}).get('offPeak', 0) or 0, 2)
                    fup_units = (internet.get('totalUsage') or {}).get('units')
                    usage_gb = round(fup_units, 2) if fup_units is not None else peak
                    print(f"\n  {label}  [{category}]")
                    print(f"    Period      : {start} → {end}")
                    print(f"    FUP counter : {usage_gb:.2f} GB (peak only towards limit)")
                    print(f"    Peak        : {peak:.2f} GB")
                    print(f"    Off-peak    : {offpeak:.2f} GB")
                    print(f"    Total DL    : {round(peak + offpeak, 2):.2f} GB  {_bar(peak, 1024)}")
                else:
                    total = (internet.get('totalUsage') or {}).get('units', 0) or 0
                    print(f"\n  {label}  [{category}]")
                    print(f"    Period      : {start} → {end}")
                    print(f"    Usage       : {total:.2f} GB")

                # Period days left
                from datetime import timedelta
                end_dt = datetime.strptime(end, '%Y-%m-%d') + timedelta(days=1)
                days = round((end_dt - datetime.now()).total_seconds() / 86400, 1)
                print(f"    Days left   : {days}")

                self.assertGreaterEqual(days, 0)
                self.assertLessEqual(days, 35)

        if not found_internet:
            print("  (no internet product found in planInfo)")

    # ------------------------------------------------------------------
    # Announcements / inbox
    # ------------------------------------------------------------------

    def test_05_inbox(self):
        """Fetch inbox unread count."""
        result = self.session.inboxMessages()
        print(f"\n{'─'*60}")
        print(f"  INBOX")
        print(f"{'─'*60}")
        if result is None:
            print("  (endpoint not available for this account)")
            return
        messages = result if isinstance(result, list) else result.get('messages', [])
        unread = sum(1 for m in (messages or []) if not m.get('read', False))
        print(f"  Messages    : {len(messages or [])}")
        print(f"  Unread      : {unread}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def test_06_full_summary(self):
        """Print a compact summary table of all products."""
        lines = self.session.mobileLines()
        plans = self.session.planInfo()

        print(f"\n{'='*60}")
        print(f"  SUMMARY")
        print(f"{'='*60}")
        print(f"  {'Product':<35} {'Used':>8} {'Total':>8} {'Pct':>6}")
        print(f"  {'─'*35} {'─'*8} {'─'*8} {'─'*6}")

        # Internet
        for plan in plans:
            for product in (plan.get('products') or [plan]):
                if (product.get('productType') or '').lower() != 'internet':
                    continue
                pid = product.get('identifier')
                label = (product.get('label') or pid or '')[:35]
                cycles = self.session.billCycles('internet', pid)
                if 'billCycles' not in cycles:
                    continue
                cycle = cycles['billCycles'][0]
                usage = self.session.productUsage('internet', pid, cycle['startDate'], cycle['endDate'])
                daily = self.session.productDailyUsage('internet', pid, cycle['startDate'], cycle['endDate'])
                internet = usage.get('internet', {})
                category = internet.get('category', '')
                daily_list = daily.get('internetUsage', [])
                if category == 'CAP':
                    alloc = (internet.get('allocatedUsage') or {}).get('units', 0) or 0
                    pct = internet.get('usedPercentage', 0) or 0
                    used = round(pct / 100 * alloc, 2)
                    print(f"  {'[Internet] ' + label:<35} {used:>7.2f}G {alloc:>7.0f}G {pct:>5.1f}%")
                elif daily_list:
                    peak = round(daily_list[0].get('totalUsage', {}).get('peak', 0) or 0, 2)
                    fup = (internet.get('totalUsage') or {}).get('units')
                    used = round(fup, 2) if fup is not None else peak
                    print(f"  {'[Internet] ' + label:<35} {used:>7.2f}G {'FUP':>7}  {'n/a':>5}")

        # Mobile
        for line in lines:
            msisdn = line.get('msisdn', '')
            result = self.session.mobileLineUsage(msisdn)
            if not result:
                continue
            sub = (result.get('usage') or {}).get('subscription', {})
            plan_name = sub.get('planName', {}).get('nl') or sub.get('planName', {}).get('en') or msisdn
            bars = sub.get('breakdown', {}).get('barsSummary', {}).get('bars', [])
            tiles = sub.get('breakdown', {}).get('tiles', [])
            data_bar = next((b for b in bars if b.get('category') == 'DATA'), None)
            call_tile = next((t for t in tiles if t.get('category') == 'CALL'), None)
            sms_tile = next((t for t in tiles if t.get('category') == 'SMS'), None)

            label = f"[Mobile] {plan_name} ({msisdn})"[:35]
            if data_bar:
                consumed = data_bar.get('consumed', 0) or 0
                total = data_bar.get('total', 0) or 0
                pct = data_bar.get('consumedPercentage', 0) or 0
                print(f"  {label:<35} {consumed:>7.2f}G {total:>7.0f}G {pct:>5.1f}%")
            if call_tile:
                v_used = call_tile.get('consumed', 0) or 0
                v_line = call_tile.get('lineType', '')
                label2 = f"  └─ voice"
                print(f"  {label2:<35} {v_used:>6.1f}m {'∞' if v_line == 'UNLIMITED' else '':>8}  {'':>5}")
            if sms_tile:
                s_used = sms_tile.get('consumed', 0) or 0
                s_line = sms_tile.get('lineType', '')
                label3 = f"  └─ sms"
                print(f"  {label3:<35} {s_used:>7.0f}  {'∞' if s_line == 'UNLIMITED' else '':>8}  {'':>5}")

        print(f"{'='*60}\n")


if __name__ == '__main__':
    unittest.main(verbosity=2)
