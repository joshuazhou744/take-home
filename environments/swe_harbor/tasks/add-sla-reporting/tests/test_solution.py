"""Tests for the SLA Reporting feature."""
from __future__ import annotations

import json
import uuid

import os
import sys
sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
django.setup()

from hc.api.models import Check
from hc.test import BaseTestCase


class SlaTargetFieldTestCase(BaseTestCase):
    """Tests for the sla_target field on Check."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_field_present_in_to_dict(self):
        """to_dict() should include sla_target."""
        self.assertIn("sla_target", self.check.to_dict())

    def test_field_defaults_to_null(self):
        """sla_target should default to null."""
        self.assertIsNone(self.check.to_dict()["sla_target"])

    def test_field_persists_value(self):
        """sla_target should persist when set and retrieved."""
        self.check.sla_target = 99.9
        self.check.save()
        refreshed = Check.objects.get(pk=self.check.pk)
        self.assertEqual(refreshed.sla_target, 99.9)

    def test_field_reflects_in_to_dict(self):
        """to_dict() should show the set sla_target value."""
        self.check.sla_target = 95.0
        self.check.save()
        self.assertEqual(self.check.to_dict()["sla_target"], 95.0)


class SetSlaTargetApiTestCase(BaseTestCase):
    """Tests for POST /api/v3/checks/<uuid>/sla/."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/sla/"

    def _post(self, data, api_key="X" * 32):
        return self.client.post(
            self.url,
            json.dumps(data),
            content_type="application/json",
            HTTP_X_API_KEY=api_key,
        )

    def test_post_sets_sla_target(self):
        """POST should set sla_target and return 200."""
        r = self._post({"sla_target": 99.9})
        self.assertEqual(r.status_code, 200)
        self.check.refresh_from_db()
        self.assertEqual(self.check.sla_target, 99.9)

    def test_post_returns_check_dict(self):
        """POST response should include check fields including sla_target."""
        r = self._post({"sla_target": 95.0})
        doc = r.json()
        self.assertIn("sla_target", doc)
        self.assertEqual(doc["sla_target"], 95.0)

    def test_post_null_clears_target(self):
        """POST with sla_target=null should clear the target."""
        self.check.sla_target = 99.9
        self.check.save()
        r = self._post({"sla_target": None})
        self.assertEqual(r.status_code, 200)
        self.check.refresh_from_db()
        self.assertIsNone(self.check.sla_target)

    def test_post_absent_key_clears_target(self):
        """POST with no sla_target key should clear the target."""
        self.check.sla_target = 99.9
        self.check.save()
        r = self._post({})
        self.assertEqual(r.status_code, 200)
        self.check.refresh_from_db()
        self.assertIsNone(self.check.sla_target)

    def test_post_sla_target_zero_returns_400(self):
        """sla_target=0 should return 400 (must be > 0)."""
        r = self._post({"sla_target": 0})
        self.assertEqual(r.status_code, 400)

    def test_post_sla_target_above_100_returns_400(self):
        """sla_target > 100 should return 400."""
        r = self._post({"sla_target": 100.1})
        self.assertEqual(r.status_code, 400)

    def test_post_sla_target_not_a_number_returns_400(self):
        """Non-numeric sla_target should return 400."""
        r = self._post({"sla_target": "99.9"})
        self.assertEqual(r.status_code, 400)

    def test_post_boundary_100_accepted(self):
        """sla_target=100 (exactly) should be accepted."""
        r = self._post({"sla_target": 100})
        self.assertEqual(r.status_code, 200)

    def test_post_no_api_key_returns_401(self):
        """Missing API key should return 401."""
        r = self.client.post(
            self.url,
            json.dumps({"sla_target": 99.9}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)

    def test_post_readonly_key_returns_403(self):
        """Read-only API key should not be able to POST."""
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        r = self._post({"sla_target": 99.9}, api_key="R" * 32)
        self.assertEqual(r.status_code, 403)

    def test_post_wrong_project_returns_403(self):
        """Check from another project should return 403."""
        other = Check.objects.create(project=self.bobs_project, name="Bob")
        url = f"/api/v3/checks/{other.code}/sla/"
        r = self.client.post(
            url,
            json.dumps({"sla_target": 99.9}),
            content_type="application/json",
            HTTP_X_API_KEY="X" * 32,
        )
        self.assertEqual(r.status_code, 403)

    def test_post_nonexistent_check_returns_404(self):
        """Non-existent check UUID should return 404."""
        url = f"/api/v3/checks/{uuid.uuid4()}/sla/"
        r = self.client.post(
            url,
            json.dumps({"sla_target": 99.9}),
            content_type="application/json",
            HTTP_X_API_KEY="X" * 32,
        )
        self.assertEqual(r.status_code, 404)


class GetSlaReportTestCase(BaseTestCase):
    """Tests for GET /api/v3/checks/<uuid>/sla/ response shape."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/sla/"

    def _get(self, params="", api_key="X" * 32):
        return self.client.get(
            self.url + (f"?{params}" if params else ""),
            HTTP_X_API_KEY=api_key,
        )

    def test_get_returns_200(self):
        """GET should return 200."""
        r = self._get()
        self.assertEqual(r.status_code, 200)

    def test_get_response_has_required_keys(self):
        """GET response should include sla_target, tz, and months keys."""
        r = self._get()
        doc = r.json()
        for key in ("sla_target", "tz", "months"):
            self.assertIn(key, doc, f"Missing key: {key}")

    def test_get_months_is_list(self):
        """months should be a list."""
        r = self._get()
        self.assertIsInstance(r.json()["months"], list)

    def test_get_default_months_count(self):
        """Default request should return 3 month entries."""
        r = self._get()
        self.assertEqual(len(r.json()["months"]), 3)

    def test_get_months_param_respected(self):
        """?months=6 should return 6 month entries."""
        r = self._get("months=6")
        self.assertEqual(len(r.json()["months"]), 6)

    def test_get_month_entry_keys(self):
        """Each month entry should have date, uptime_pct, downtime_seconds, downtime_starts, met_sla."""
        r = self._get()
        entry = r.json()["months"][0]
        for key in ("date", "uptime_pct", "downtime_seconds", "downtime_starts", "met_sla"):
            self.assertIn(key, entry, f"Month entry missing key: {key}")

    def test_get_date_format(self):
        """date field should be in YYYY-MM format."""
        r = self._get()
        date_str = r.json()["months"][0]["date"]
        self.assertRegex(date_str, r"^\d{4}-\d{2}$", "date should be YYYY-MM")

    def test_get_met_sla_null_when_no_target(self):
        """met_sla should be null when sla_target is not set."""
        r = self._get()
        for entry in r.json()["months"]:
            self.assertIsNone(entry["met_sla"], "met_sla should be null without target")

    def test_get_met_sla_true_when_no_downtime(self):
        """met_sla should be true for a period with no downtime and a target set."""
        self.check.sla_target = 99.0
        self.check.save()
        r = self._get()
        doc = r.json()
        # A new check with no flips: no_data=True for months before creation,
        # so just check that months with uptime data show correct met_sla
        entries_with_data = [e for e in doc["months"] if e["met_sla"] is not None]
        for entry in entries_with_data:
            if entry["uptime_pct"] >= 99.0:
                self.assertTrue(entry["met_sla"])

    def test_get_sla_target_reflected_in_response(self):
        """sla_target in response should match the check's sla_target."""
        self.check.sla_target = 99.5
        self.check.save()
        r = self._get()
        self.assertEqual(r.json()["sla_target"], 99.5)

    def test_get_sla_target_null_in_response(self):
        """sla_target in response should be null when not set."""
        r = self._get()
        self.assertIsNone(r.json()["sla_target"])

    def test_get_tz_reflected_in_response(self):
        """tz param should appear in response."""
        r = self._get("tz=America/New_York")
        self.assertEqual(r.json()["tz"], "America/New_York")

    def test_get_downtime_seconds_is_numeric(self):
        """downtime_seconds should be a number."""
        r = self._get()
        for entry in r.json()["months"]:
            self.assertIsInstance(entry["downtime_seconds"], (int, float))

    def test_get_downtime_starts_is_integer(self):
        """downtime_starts should be an integer."""
        r = self._get()
        for entry in r.json()["months"]:
            self.assertIsInstance(entry["downtime_starts"], int)


class SlaReportParamsTestCase(BaseTestCase):
    """Tests for query parameter validation on GET /api/v3/checks/<uuid>/sla/."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/sla/"

    def _get(self, params=""):
        return self.client.get(
            self.url + (f"?{params}" if params else ""),
            HTTP_X_API_KEY="X" * 32,
        )

    def test_months_1_accepted(self):
        """months=1 should return 200."""
        r = self._get("months=1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["months"]), 1)

    def test_months_12_accepted(self):
        """months=12 should return 200."""
        r = self._get("months=12")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["months"]), 12)

    def test_months_0_returns_400(self):
        """months=0 should return 400."""
        r = self._get("months=0")
        self.assertEqual(r.status_code, 400)

    def test_months_13_returns_400(self):
        """months=13 should return 400."""
        r = self._get("months=13")
        self.assertEqual(r.status_code, 400)

    def test_months_non_integer_returns_400(self):
        """Non-integer months should return 400."""
        r = self._get("months=foo")
        self.assertEqual(r.status_code, 400)

    def test_valid_tz_accepted(self):
        """A valid IANA timezone should be accepted."""
        r = self._get("tz=Europe/London")
        self.assertEqual(r.status_code, 200)

    def test_invalid_tz_returns_400(self):
        """An invalid timezone string should return 400."""
        r = self._get("tz=Not/ATimezone")
        self.assertEqual(r.status_code, 400)

    def test_utc_tz_accepted(self):
        """UTC timezone should be accepted."""
        r = self._get("tz=UTC")
        self.assertEqual(r.status_code, 200)


class SlaAuthTestCase(BaseTestCase):
    """Tests for authentication and authorization on /api/v3/checks/<uuid>/sla/."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/sla/"

    def test_get_readonly_key_accepted(self):
        """Read-only key should be accepted for GET."""
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        r = self.client.get(self.url, HTTP_X_API_KEY="R" * 32)
        self.assertEqual(r.status_code, 200)

    def test_get_write_key_accepted(self):
        """Write key should be accepted for GET."""
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_get_no_key_returns_401(self):
        """Missing API key should return 401 for GET."""
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 401)

    def test_get_wrong_key_returns_401(self):
        """Wrong API key should return 401 for GET."""
        r = self.client.get(self.url, HTTP_X_API_KEY="Z" * 32)
        self.assertEqual(r.status_code, 401)

    def test_get_wrong_project_returns_403(self):
        """Check from another project should return 403 for GET."""
        other = Check.objects.create(project=self.bobs_project, name="Bob")
        url = f"/api/v3/checks/{other.code}/sla/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 403)

    def test_get_nonexistent_check_returns_404(self):
        """Non-existent check UUID should return 404 for GET."""
        url = f"/api/v3/checks/{uuid.uuid4()}/sla/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 404)

    def test_post_readonly_key_returns_403(self):
        """Read-only API key should return 403 for POST."""
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        r = self.client.post(
            self.url,
            json.dumps({"sla_target": 99.9}),
            content_type="application/json",
            HTTP_X_API_KEY="R" * 32,
        )
        self.assertEqual(r.status_code, 403)


class SlaUrlRoutingTestCase(BaseTestCase):
    """Tests that the SLA endpoint is reachable on all API versions."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def _get(self, version):
        url = f"/api/v{version}/checks/{self.check.code}/sla/"
        return self.client.get(url, HTTP_X_API_KEY="X" * 32)

    def test_v3_endpoint(self):
        """SLA endpoint should be reachable under /api/v3/."""
        r = self._get(3)
        self.assertEqual(r.status_code, 200)

    def test_v1_endpoint(self):
        """SLA endpoint should be reachable under /api/v1/."""
        r = self._get(1)
        self.assertNotEqual(r.status_code, 404)

    def test_v2_endpoint(self):
        """SLA endpoint should be reachable under /api/v2/."""
        r = self._get(2)
        self.assertNotEqual(r.status_code, 404)
