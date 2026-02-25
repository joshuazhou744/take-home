# All tests run against the Healthchecks Django app at /app.
#
# Tips:
#   - Extend BaseTestCase for pre-built users/projects/API keys
#   - Use descriptive test names (test_empty_input, test_duplicate_values, etc.)
#   - Include informative assertion messages
#   - Test the happy path, edge cases, and error conditions
#   - Keep tests independent (no shared mutable state)
#   - Aim for 20-40 tests

"""Tests for the ping statistics feature."""
from __future__ import annotations

import uuid
from datetime import timedelta as td

import os
import sys
sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
django.setup()

from django.utils.timezone import now

from hc.api.models import Check, Ping
from hc.test import BaseTestCase


# verify ping_success_rate field in Check.to_dict()
class PingSuccessRateInToDictTestCase(BaseTestCase):
    """Tests for the ping_success_rate field in Check.to_dict()."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_field_present_in_to_dict(self):
        """to_dict() should include a ping_success_rate key."""
        d = self.check.to_dict()
        self.assertIn("ping_success_rate", d)

    def test_field_null_when_no_pings(self):
        """ping_success_rate should be None when there are no pings."""
        d = self.check.to_dict()
        self.assertIsNone(d["ping_success_rate"])

    def test_field_is_one_when_all_success(self):
        """ping_success_rate should be 1.0 when all pings succeeded."""
        Ping.objects.create(owner=self.check, kind=None)
        Ping.objects.create(owner=self.check, kind=None)
        d = self.check.to_dict()
        self.assertEqual(d["ping_success_rate"], 1.0)

    def test_field_correct_with_mixed_pings(self):
        """ping_success_rate should be success / total."""
        Ping.objects.create(owner=self.check, kind=None) # None is success
        Ping.objects.create(owner=self.check, kind="fail")
        d = self.check.to_dict()
        self.assertAlmostEqual(d["ping_success_rate"], 0.5)

    def test_field_zero_when_all_fail(self):
        """ping_success_rate should be 0.0 when all pings failed."""
        Ping.objects.create(owner=self.check, kind="fail")
        Ping.objects.create(owner=self.check, kind="fail")
        d = self.check.to_dict()
        self.assertEqual(d["ping_success_rate"], 0.0)


# verify ping_stats() method in Check model
class PingStatsMethodTestCase(BaseTestCase):
    """Tests for the Check.ping_stats() method."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Stats Check")

    def test_method_exists(self):
        """Check model should have a ping_stats() method."""
        self.assertTrue(callable(getattr(self.check, "ping_stats", None)))

    def test_returns_all_required_keys(self):
        """ping_stats() should return a dict with all 7 required keys."""
        result = self.check.ping_stats()
        for key in ("total", "success", "fail", "start", "ping_success_rate",
            "avg_duration_seconds", "daily"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_no_pings_total_is_zero(self):
        """ping_stats() total should be 0 when there are no pings."""
        result = self.check.ping_stats()
        self.assertEqual(result["total"], 0)

    def test_no_pings_success_rate_is_null(self):
        """ping_stats() ping_success_rate should be None when there are no pings."""
        result = self.check.ping_stats()
        self.assertIsNone(result["ping_success_rate"])

    def test_no_pings_avg_duration_is_null(self):
        """ping_stats() avg_duration_seconds should be None when there are no pings."""
        result = self.check.ping_stats()
        self.assertIsNone(result["avg_duration_seconds"])

    def test_counts_success_pings(self):
        """ping_stats() success count should equal pings where kind is null."""
        Ping.objects.create(owner=self.check, kind=None)
        Ping.objects.create(owner=self.check, kind=None)
        Ping.objects.create(owner=self.check, kind="fail")
        result = self.check.ping_stats()
        self.assertEqual(result["success"], 2)
        self.assertEqual(result["total"], 3)

    def test_counts_fail_pings(self):
        """ping_stats() fail count should equal pings where kind='fail'."""
        Ping.objects.create(owner=self.check, kind="fail")
        Ping.objects.create(owner=self.check, kind="fail")
        Ping.objects.create(owner=self.check, kind=None)
        result = self.check.ping_stats()
        self.assertEqual(result["fail"], 2)

    def test_counts_start_pings(self):
        """ping_stats() start count should equal pings where kind='start'."""
        Ping.objects.create(owner=self.check, kind="start")
        Ping.objects.create(owner=self.check, kind=None)
        result = self.check.ping_stats()
        self.assertEqual(result["start"], 1)

    def test_ping_success_rate_calculation(self):
        """ping_success_rate should be success / total as a float."""
        Ping.objects.create(owner=self.check, kind=None)
        Ping.objects.create(owner=self.check, kind=None)
        Ping.objects.create(owner=self.check, kind="fail")
        result = self.check.ping_stats()
        self.assertAlmostEqual(result["ping_success_rate"], 2 / 3)

    def test_avg_duration_matched_start_success_pairs(self):
        """avg_duration_seconds should be calculated from matched start->success pairs."""
        rid = uuid.uuid4()
        start_time = now() - td(seconds=10)
        Ping.objects.create(owner=self.check, kind="start", rid=rid, created=start_time)
        Ping.objects.create(owner=self.check, kind=None, rid=rid, created=now())
        result = self.check.ping_stats()
        self.assertIsNotNone(result["avg_duration_seconds"])
        # Duration should be approximately 10 seconds
        self.assertGreater(result["avg_duration_seconds"], 0)
        self.assertLess(result["avg_duration_seconds"], 30)

    def test_avg_duration_null_when_no_matched_pairs(self):
        """avg_duration_seconds should be None when start and success have different rids."""
        Ping.objects.create(owner=self.check, kind="start", rid=uuid.uuid4())
        Ping.objects.create(owner=self.check, kind=None, rid=uuid.uuid4())
        result = self.check.ping_stats()
        self.assertIsNone(result["avg_duration_seconds"])

    def test_avg_duration_null_when_only_start(self):
        """avg_duration_seconds should be None when there are only start pings."""
        Ping.objects.create(owner=self.check, kind="start", rid=uuid.uuid4())
        result = self.check.ping_stats()
        self.assertIsNone(result["avg_duration_seconds"])

    def test_daily_has_30_entries(self):
        """daily should contain exactly 30 entries."""
        result = self.check.ping_stats()
        self.assertEqual(len(result["daily"]), 30)

    def test_daily_entries_ordered_newest_first(self):
        """daily entries should be ordered newest first."""
        result = self.check.ping_stats()
        dates = [entry["date"] for entry in result["daily"]]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_daily_entry_has_required_keys(self):
        """Each daily entry should have date, total, success, and fail keys."""
        result = self.check.ping_stats()
        for entry in result["daily"]:
            for key in ("date", "total", "success", "fail"):
                self.assertIn(key, entry, f"Daily entry missing key: {key}")

    def test_daily_date_format(self):
        """Daily entry dates should be in YYYY-MM-DD format."""
        from datetime import date
        result = self.check.ping_stats()
        for entry in result["daily"]:
            # This will raise ValueError if format is wrong
            parsed = date.fromisoformat(entry["date"])
            self.assertIsNotNone(parsed)

    def test_daily_includes_zero_days(self):
        """Daily entries should include days with zero pings."""
        result = self.check.ping_stats()
        # With no pings at all, every day should be zero
        for entry in result["daily"]:
            self.assertEqual(entry["total"], 0)
            self.assertEqual(entry["success"], 0)
            self.assertEqual(entry["fail"], 0)

    def test_daily_today_counts_recent_ping(self):
        """Today's daily entry should count a ping created now."""
        Ping.objects.create(owner=self.check, kind=None)
        result = self.check.ping_stats()
        today_entry = result["daily"][0]  # newest first, so index 0 is today
        self.assertEqual(today_entry["total"], 1)
        self.assertEqual(today_entry["success"], 1)


# verify GET /api/v3/checks/<uuid:code>/stats/ endpoint
class CheckStatsViewTestCase(BaseTestCase):
    """Tests for the GET /api/v3/checks/<uuid>/stats/ endpoint."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Stats Check")
        self.url = f"/api/v3/checks/{self.check.code}/stats/"

    def get(self, url=None, api_key="X" * 32):
        url = url or self.url
        return self.client.get(url, HTTP_X_API_KEY=api_key)

    def test_returns_200(self):
        """GET stats endpoint should return 200 for a valid check."""
        r = self.get()
        self.assertEqual(r.status_code, 200)

    def test_response_is_json(self):
        """Response should be valid JSON with all required keys."""
        r = self.get()
        doc = r.json()
        for key in ("total", "success", "fail", "start", "ping_success_rate",
                    "avg_duration_seconds", "daily"):
            self.assertIn(key, doc, f"Response missing key: {key}")

    def test_cors_header_present(self):
        """Response should include CORS header."""
        r = self.get()
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")

    def test_readonly_key_accepted(self):
        """Read-only API key should be accepted for the stats endpoint."""
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        r = self.get(api_key=self.project.api_key_readonly)
        self.assertEqual(r.status_code, 200)

    def test_no_api_key_returns_401(self):
        """Missing API key should return 401."""
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 401)

    def test_wrong_api_key_returns_401(self):
        """Wrong API key should return 401."""
        r = self.get(api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)

    def test_other_project_check_returns_403(self):
        """A check belonging to another project should return 403."""
        other = Check.objects.create(project=self.bobs_project, name="Bob's Check")
        url = f"/api/v3/checks/{other.code}/stats/"
        r = self.get(url=url)
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_check_returns_404(self):
        """A non-existent check UUID should return 404."""
        url = f"/api/v3/checks/{uuid.uuid4()}/stats/"
        r = self.get(url=url)
        self.assertEqual(r.status_code, 404)

    def test_post_not_allowed(self):
        """POST to the stats endpoint should not succeed (read-only endpoint)."""
        r = self.client.post(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertNotEqual(r.status_code, 200)

    def test_total_reflects_pings(self):
        """Response total should match the number of pings for the check."""
        Ping.objects.create(owner=self.check, kind=None)
        Ping.objects.create(owner=self.check, kind="fail")
        r = self.get()
        doc = r.json()
        self.assertEqual(doc["total"], 2)

    def test_daily_has_30_entries(self):
        """Response daily list should have exactly 30 entries."""
        r = self.get()
        doc = r.json()
        self.assertEqual(len(doc["daily"]), 30)


# verify endpoint is reachable at correct URLs
class CheckStatsUrlRoutingTestCase(BaseTestCase):
    """Tests that the stats endpoint is reachable on all API versions."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def _get(self, version):
        url = f"/api/v{version}/checks/{self.check.code}/stats/"
        return self.client.get(url, HTTP_X_API_KEY="X" * 32)

    def test_v3_endpoint(self):
        """Stats endpoint should be reachable under /api/v3/."""
        r = self._get(3)
        self.assertEqual(r.status_code, 200)

    # test older version endpoints as well
    def test_v1_endpoint(self):
        """Stats endpoint should be reachable under /api/v1/."""
        r = self._get(1)
        self.assertNotEqual(r.status_code, 404)

    def test_v2_endpoint(self):
        """Stats endpoint should be reachable under /api/v2/."""
        r = self._get(2)
        self.assertNotEqual(r.status_code, 404)