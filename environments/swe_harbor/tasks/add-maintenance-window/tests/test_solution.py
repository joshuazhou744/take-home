# All tests run against the Healthchecks Django app at /app.
#
# Tips:
#   - Extend BaseTestCase for pre-built users/projects/API keys
#   - Use descriptive test names (test_empty_input, test_duplicate_values, etc.)
#   - Include informative assertion messages
#   - Test the happy path, edge cases, and error conditions
#   - Keep tests independent (no shared mutable state)
#   - Aim for 20-40 tests

"""Tests for the Maintenance Windows feature."""
from __future__ import annotations

import uuid
from datetime import timedelta as td

import os
import sys
sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
django.setup()

import json
from django.utils.timezone import now

from hc.api.models import Check, MaintenanceWindow
from hc.test import BaseTestCase


# verify MaintenanceWindow model creation, fields, to_dict() method return shape, owner is UUID string and cascade delete
class MaintenanceWindowModelTestCase(BaseTestCase):
    """Tests for the MaintenanceWindow model."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.start = now()
        self.end = now() + td(hours=2)

    def test_model_exists(self):
        """MaintenanceWindow should be importable from hc.api.models."""
        self.assertTrue(hasattr(MaintenanceWindow, "objects"))

    def test_create_window(self):
        """Can create a MaintenanceWindow linked to a check."""
        w = MaintenanceWindow.objects.create(
            owner=self.check, start=self.start, end=self.end
        )
        self.assertIsNotNone(w.code)
        self.assertEqual(w.owner, self.check)
        self.assertEqual(w.reason, "")

    def test_reason_default_empty(self):
        """Reason field should default to empty string."""
        w = MaintenanceWindow.objects.create(
            owner=self.check, start=self.start, end=self.end
        )
        self.assertEqual(w.reason, "")

    def test_to_dict_keys(self):
        """to_dict() should return uuid, owner, start, end, reason."""
        w = MaintenanceWindow.objects.create(
            owner=self.check, start=self.start, end=self.end, reason="Deploy"
        )
        d = w.to_dict()
        for key in ("uuid", "owner", "start", "end", "reason"):
            self.assertIn(key, d, f"Missing key: {key}")

    def test_to_dict_owner_is_check_uuid(self):
        """to_dict() owner should be the check's UUID string."""
        w = MaintenanceWindow.objects.create(
            owner=self.check, start=self.start, end=self.end
        )
        d = w.to_dict()
        self.assertEqual(d["owner"], str(self.check.code))

    def test_to_dict_uuid_is_string(self):
        """to_dict() uuid should be a string."""
        w = MaintenanceWindow.objects.create(
            owner=self.check, start=self.start, end=self.end
        )
        d = w.to_dict()
        self.assertIsInstance(d["uuid"], str)

    def test_ordering_soonest_first(self):
        """Windows should be ordered by start ascending."""
        later = now() + td(days=1)
        w1 = MaintenanceWindow.objects.create(owner=self.check, start=later, end=later + td(hours=1))
        w2 = MaintenanceWindow.objects.create(owner=self.check, start=self.start, end=self.end)
        windows = list(MaintenanceWindow.objects.filter(owner=self.check))
        self.assertEqual(windows[0].id, w2.id)
        self.assertEqual(windows[1].id, w1.id)

    def test_cascade_delete(self):
        """Deleting a check should delete its maintenance windows."""
        from django.contrib.auth.models import User
        from hc.accounts.models import Project
        user = User.objects.create_user("tmpuser2", "tmp2@example.com", "pass")
        project = Project.objects.create(owner=user)
        check = Check.objects.create(project=project, name="Temp")
        MaintenanceWindow.objects.create(owner=check, start=self.start, end=self.end)
        check_id = check.id
        check.delete()
        self.assertFalse(MaintenanceWindow.objects.filter(owner_id=check_id).exists())


# verify maintenance_count in Check.to_dict(), it's default values, and it's accuracy
class MaintenanceCountInToDictTestCase(BaseTestCase):
    """Tests for the maintenance_count field in Check.to_dict()."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_field_present(self):
        """to_dict() should include maintenance_count."""
        self.assertIn("maintenance_count", self.check.to_dict())

    def test_field_zero_when_no_windows(self):
        """maintenance_count should be 0 when no windows exist."""
        self.assertEqual(self.check.to_dict()["maintenance_count"], 0)

    def test_field_counts_all_windows(self):
        """maintenance_count should count both active and past windows."""
        past_start = now() - td(hours=4)
        past_end = now() - td(hours=2)
        MaintenanceWindow.objects.create(owner=self.check, start=past_start, end=past_end)
        MaintenanceWindow.objects.create(owner=self.check, start=now(), end=now() + td(hours=1))
        self.assertEqual(self.check.to_dict()["maintenance_count"], 2)


# verify get_status() returns "maintenance" in place of "down", other statuses are not overriden
class GetStatusMaintenanceTestCase(BaseTestCase):
    """Tests for Check.get_status() maintenance window behavior."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def _active_window(self):
        MaintenanceWindow.objects.create(
            owner=self.check,
            start=now() - td(hours=1),
            end=now() + td(hours=1),
        )

    def test_down_status_with_active_window_returns_maintenance(self):
        """A check with status='down' and an active window should return 'maintenance'."""
        self.check.status = "down"
        self.check.save()
        self._active_window()
        self.assertEqual(self.check.get_status(), "maintenance")

    def test_down_status_without_window_returns_down(self):
        """A check with status='down' and no active window should return 'down'."""
        self.check.status = "down"
        self.check.save()
        self.assertEqual(self.check.get_status(), "down")

    def test_paused_status_not_overridden(self):
        """A paused check should remain 'paused' even with an active window."""
        self.check.status = "paused"
        self.check.save()
        self._active_window()
        self.assertEqual(self.check.get_status(), "paused")

    def test_new_status_not_overridden(self):
        """A new check should remain 'new' even with an active window."""
        self.check.status = "new"
        self.check.save()
        self._active_window()
        self.assertEqual(self.check.get_status(), "new")

    def test_expired_window_does_not_trigger_maintenance(self):
        """An expired maintenance window should not affect status."""
        self.check.status = "down"
        self.check.save()
        MaintenanceWindow.objects.create(
            owner=self.check,
            start=now() - td(hours=4),
            end=now() - td(hours=2),
        )
        self.assertEqual(self.check.get_status(), "down")

    def test_future_window_does_not_trigger_maintenance(self):
        """A future maintenance window should not affect status."""
        self.check.status = "down"
        self.check.save()
        MaintenanceWindow.objects.create(
            owner=self.check,
            start=now() + td(hours=1),
            end=now() + td(hours=3),
        )
        self.assertEqual(self.check.get_status(), "down")


# verify GET /api/v3/checks/<uuid>/maintenance/ works
class ListMaintenanceWindowsTestCase(BaseTestCase):
    """Tests for GET /api/v3/checks/<uuid>/maintenance/."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/maintenance/"

    def get(self, url=None, api_key="X" * 32):
        return self.client.get(url or self.url, HTTP_X_API_KEY=api_key)

    def test_returns_200_with_empty_list(self):
        """GET should return 200 with empty windows list when no windows exist."""
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"windows": []})

    def test_returns_windows(self):
        """GET should return all maintenance windows for the check."""
        MaintenanceWindow.objects.create(
            owner=self.check, start=now(), end=now() + td(hours=1)
        )
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["windows"]), 1)

    def test_readonly_key_accepted(self):
        """Read-only API key should be accepted for listing windows."""
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        r = self.get(api_key=self.project.api_key_readonly)
        self.assertEqual(r.status_code, 200)

    def test_no_api_key_returns_401(self):
        """Missing API key should return 401."""
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 401)

    def test_wrong_project_returns_403(self):
        """Check from another project should return 403."""
        other = Check.objects.create(project=self.bobs_project, name="Bob")
        r = self.get(url=f"/api/v3/checks/{other.code}/maintenance/")
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_check_returns_404(self):
        """Non-existent check UUID should return 404."""
        r = self.get(url=f"/api/v3/checks/{uuid.uuid4()}/maintenance/")
        self.assertEqual(r.status_code, 404)


# verify POST /api/v3/checks/<uuid>/maintenance/ creates a maintenance window and validates it's features, shapes, response codes
class CreateMaintenanceWindowTestCase(BaseTestCase):
    """Tests for POST /api/v3/checks/<uuid>/maintenance/."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/maintenance/"
        self.start = (now() + td(hours=1)).isoformat()
        self.end = (now() + td(hours=3)).isoformat()

    def post(self, data, api_key="X" * 32):
        return self.client.post(
            self.url,
            json.dumps(data),
            content_type="application/json",
            HTTP_X_API_KEY=api_key,
        )

    def test_create_returns_201(self):
        """POST should return 201 on success."""
        r = self.post({"start": self.start, "end": self.end})
        self.assertEqual(r.status_code, 201)

    def test_create_returns_window_dict(self):
        """POST response should include the created window's fields."""
        r = self.post({"start": self.start, "end": self.end, "reason": "Deploy"})
        doc = r.json()
        for key in ("uuid", "owner", "start", "end", "reason"):
            self.assertIn(key, doc, f"Response missing key: {key}")
        self.assertEqual(doc["reason"], "Deploy")

    def test_create_persists_window(self):
        """POST should create a MaintenanceWindow in the database."""
        self.post({"start": self.start, "end": self.end})
        self.assertEqual(MaintenanceWindow.objects.filter(owner=self.check).count(), 1)

    def test_reason_optional(self):
        """POST should succeed without a reason field."""
        r = self.post({"start": self.start, "end": self.end})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["reason"], "")

    def test_missing_start_returns_400(self):
        """Missing start should return 400."""
        r = self.post({"end": self.end})
        self.assertEqual(r.status_code, 400)

    def test_missing_end_returns_400(self):
        """Missing end should return 400."""
        r = self.post({"start": self.start})
        self.assertEqual(r.status_code, 400)

    def test_end_before_start_returns_400(self):
        """end before start should return 400."""
        r = self.post({"start": self.end, "end": self.start})
        self.assertEqual(r.status_code, 400)

    def test_end_equal_start_returns_400(self):
        """end equal to start should return 400."""
        r = self.post({"start": self.start, "end": self.start})
        self.assertEqual(r.status_code, 400)

    def test_invalid_datetime_returns_400(self):
        """Unparseable datetime string should return 400."""
        r = self.post({"start": "not-a-date", "end": self.end})
        self.assertEqual(r.status_code, 400)

    def test_readonly_key_rejected(self):
        """Read-only API key should not be able to create a window."""
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        r = self.post({"start": self.start, "end": self.end}, api_key="R" * 32)
        self.assertNotEqual(r.status_code, 201)

    def test_no_api_key_returns_401(self):
        """Missing API key should return 401."""
        r = self.client.post(
            self.url,
            json.dumps({"start": self.start, "end": self.end}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)

    def test_wrong_project_returns_403(self):
        """Check from another project should return 403."""
        other = Check.objects.create(project=self.bobs_project, name="Bob")
        url = f"/api/v3/checks/{other.code}/maintenance/"
        r = self.client.post(
            url,
            json.dumps({"start": self.start, "end": self.end}),
            content_type="application/json",
            HTTP_X_API_KEY="X" * 32,
        )
        self.assertEqual(r.status_code, 403)


# verify DELETE /api/v3/checks/<uuid>/maintenance/<uuid>/ works and returns proper error codes that match with similar return types, also ensure deletion in database
class DeleteMaintenanceWindowTestCase(BaseTestCase):
    """Tests for DELETE /api/v3/checks/<uuid>/maintenance/<uuid>/."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.window = MaintenanceWindow.objects.create(
            owner=self.check,
            start=now(),
            end=now() + td(hours=2),
        )
        self.url = f"/api/v3/checks/{self.check.code}/maintenance/{self.window.code}/"

    def delete(self, url=None, api_key="X" * 32):
        return self.client.delete(url or self.url, HTTP_X_API_KEY=api_key)

    def test_delete_returns_204(self):
        """DELETE should return 204 on success."""
        r = self.delete()
        self.assertEqual(r.status_code, 204)

    def test_delete_removes_window(self):
        """DELETE should remove the window from the database."""
        self.delete()
        self.assertFalse(MaintenanceWindow.objects.filter(code=self.window.code).exists())

    def test_delete_nonexistent_returns_404(self):
        """DELETE for a non-existent window should return 404."""
        url = f"/api/v3/checks/{self.check.code}/maintenance/{uuid.uuid4()}/"
        r = self.delete(url=url)
        self.assertEqual(r.status_code, 404)

    def test_no_api_key_returns_401(self):
        """Missing API key should return 401."""
        r = self.client.delete(self.url)
        self.assertEqual(r.status_code, 401)

    def test_wrong_project_returns_403(self):
        """Check from another project should return 403."""
        other = Check.objects.create(project=self.bobs_project, name="Bob")
        window = MaintenanceWindow.objects.create(
            owner=other, start=now(), end=now() + td(hours=1)
        )
        url = f"/api/v3/checks/{other.code}/maintenance/{window.code}/"
        r = self.delete(url=url)
        self.assertEqual(r.status_code, 403)


# verify url routing
class MaintenanceUrlRoutingTestCase(BaseTestCase):
    """Tests that maintenance endpoints are reachable on all API versions."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def _get(self, version):
        url = f"/api/v{version}/checks/{self.check.code}/maintenance/"
        return self.client.get(url, HTTP_X_API_KEY="X" * 32)

    def test_v3_endpoint(self):
        """Maintenance endpoint should be reachable under /api/v3/."""
        r = self._get(3)
        self.assertEqual(r.status_code, 200)
    
    # tests for older endpoint versions
    def test_v1_endpoint(self):
        """Maintenance endpoint should be reachable under /api/v1/."""
        r = self._get(1)
        self.assertNotEqual(r.status_code, 404)

    def test_v2_endpoint(self):
        """Maintenance endpoint should be reachable under /api/v2/."""
        r = self._get(2)
        self.assertNotEqual(r.status_code, 404)