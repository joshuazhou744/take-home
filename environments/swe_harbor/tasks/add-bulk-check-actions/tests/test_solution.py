# All tests run against the Healthchecks Django app at /app.
#
# Tips:
#   - Extend BaseTestCase for pre-built users/projects/API keys
#   - Use descriptive test names (test_empty_input, test_duplicate_values, etc.)
#   - Include informative assertion messages
#   - Test the happy path, edge cases, and error conditions
#   - Keep tests independent (no shared mutable state)
#   - Aim for 20-40 tests

"""Tests for the bulk check actions feature"""
from __future__ import annotations

import json
import uuid

import os
import sys
sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
django.setup()

from hc.api.models import BulkActionLog, Check
from hc.test import BaseTestCase

# verify last_bulk_action field
class LastBulkActionFieldTestCase(BaseTestCase):
    """Tests for the last_bulk_action field on the Check model."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_field_exists(self):
        """Check model should have a last_bulk_action field."""
        self.assertTrue(hasattr(self.check, "last_bulk_action"))

    def test_field_default_null(self):
        """New checks should have last_bulk_action=None."""
        self.assertIsNone(self.check.last_bulk_action)

    def test_field_in_to_dict(self):
        """to_dict() should include last_bulk_action."""
        d = self.check.to_dict()
        self.assertIn("last_bulk_action", d)

    def test_field_null_in_to_dict(self):
        """to_dict() should return None when last_bulk_action is not set."""
        d = self.check.to_dict()
        self.assertIsNone(d["last_bulk_action"])

    def test_field_value_in_to_dict(self):
        """to_dict() should reflect the set last_bulk_action value."""
        self.check.last_bulk_action = "pause"
        self.check.save()
        d = self.check.to_dict()
        self.assertEqual(d["last_bulk_action"], "pause")

# verify the BulkActionLog model
class BulkActionLogModelTestCase(BaseTestCase):
    """Tests for the BulkActionLog model."""

    def test_model_exists(self):
        """BulkActionLog should be importable from hc.api.models."""
        self.assertTrue(hasattr(BulkActionLog, "objects"))

    def test_create_log(self):
        """Can create a BulkActionLog linked to a project."""
        log = BulkActionLog.objects.create(
            project=self.project,
            action="pause",
            affected=3,
        )
        self.assertIsNotNone(log.code)
        self.assertEqual(log.action, "pause")
        self.assertEqual(log.affected, 3)
        self.assertEqual(log.skipped, 0)

    def test_log_has_uuid(self):
        """Each BulkActionLog should have a unique UUID code."""
        l1 = BulkActionLog.objects.create(project=self.project, action="pause", affected=1)
        l2 = BulkActionLog.objects.create(project=self.project, action="pause", affected=1)
        self.assertNotEqual(l1.code, l2.code)

    def test_log_to_dict(self):
        """to_dict() returns all expected keys and values."""
        log = BulkActionLog.objects.create(
            project=self.project, action="resume", affected=2, skipped=1
        )
        d = log.to_dict()
        self.assertEqual(d["uuid"], str(log.code))
        self.assertEqual(d["project"], str(self.project.code))
        self.assertEqual(d["action"], "resume")
        self.assertEqual(d["affected"], 2)
        self.assertEqual(d["skipped"], 1)
        self.assertIn("created", d)

    def test_log_project_null_on_project_delete(self):
        """Deleting a project should set the log's project to null, not delete the log."""
        from django.contrib.auth.models import User
        from hc.accounts.models import Project
        user = User.objects.create_user("tmpuser", "tmp@example.com", "pass")
        project = Project.objects.create(owner=user)
        log = BulkActionLog.objects.create(project=project, action="delete", affected=1)
        project.delete()
        log.refresh_from_db()
        self.assertIsNone(log.project)

    def test_log_ordering_newest_first(self):
        """BulkActionLog entries should be ordered newest first."""
        BulkActionLog.objects.create(project=self.project, action="pause", affected=1)
        BulkActionLog.objects.create(project=self.project, action="delete", affected=2)
        logs = list(BulkActionLog.objects.filter(project=self.project))
        self.assertEqual(logs[0].action, "delete")
        self.assertEqual(logs[1].action, "pause")

# verify pause bulk batches work
class BulkPauseTestCase(BaseTestCase):
    """Tests for the bulk pause action."""

    def setUp(self):
        super().setUp()
        self.url = "/api/v3/checks/bulk/"

    def post(self, data, api_key=None):
        if api_key is None:
            api_key = "X" * 32
        return self.client.post(
            self.url,
            json.dumps({**data, "api_key": api_key}),
            content_type="application/json",
        )

    def test_pause_single_check(self):
        """Bulk pause with one check returns {"paused": 1}."""
        check = Check.objects.create(project=self.project, name="C1")
        r = self.post({"codes": [str(check.code)], "action": "pause"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"paused": 1})

    def test_pause_multiple_checks(self):
        """Bulk pause with multiple checks returns correct count."""
        checks = [Check.objects.create(project=self.project, name=f"C{i}") for i in range(3)]
        r = self.post({"codes": [str(c.code) for c in checks], "action": "pause"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["paused"], 3)

    def test_pause_sets_status(self):
        """Bulk pause sets each check's status to 'paused'."""
        check = Check.objects.create(project=self.project, name="C1")
        self.post({"codes": [str(check.code)], "action": "pause"})
        check.refresh_from_db()
        self.assertEqual(check.status, "paused")

    def test_pause_sets_last_bulk_action(self):
        """Bulk pause sets last_bulk_action='pause' on each check."""
        check = Check.objects.create(project=self.project, name="C1")
        self.post({"codes": [str(check.code)], "action": "pause"})
        check.refresh_from_db()
        self.assertEqual(check.last_bulk_action, "pause")

    def test_pause_creates_log(self):
        """Bulk pause should create a BulkActionLog entry."""
        check = Check.objects.create(project=self.project, name="C1")
        self.post({"codes": [str(check.code)], "action": "pause"})
        log = BulkActionLog.objects.get(project=self.project, action="pause")
        self.assertEqual(log.affected, 1)
        self.assertEqual(log.skipped, 0)

    def test_pause_response_shape(self):
        """Pause response should contain only the 'paused' key."""
        check = Check.objects.create(project=self.project, name="C1")
        r = self.post({"codes": [str(check.code)], "action": "pause"})
        doc = r.json()
        self.assertIn("paused", doc)
        self.assertNotIn("resumed", doc)
        self.assertNotIn("deleted", doc)

# verify resume bulk batches work
class BulkResumeTestCase(BaseTestCase):
    """Tests for the bulk resume action."""

    def setUp(self):
        super().setUp()
        self.url = "/api/v3/checks/bulk/"

    def post(self, data, api_key=None):
        if api_key is None:
            api_key = "X" * 32
        return self.client.post(
            self.url,
            json.dumps({**data, "api_key": api_key}),
            content_type="application/json",
        )

    def test_resume_single_check(self):
        """Bulk resume returns {"resumed": 1, "skipped": 0}."""
        check = Check.objects.create(project=self.project, name="C1", status="paused")
        r = self.post({"codes": [str(check.code)], "action": "resume"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"resumed": 1, "skipped": 0})

    def test_resume_sets_status_new(self):
        """Resumed check should have status='new'."""
        check = Check.objects.create(project=self.project, name="C1", status="paused")
        self.post({"codes": [str(check.code)], "action": "resume"})
        check.refresh_from_db()
        self.assertEqual(check.status, "new")

    def test_resume_sets_last_bulk_action(self):
        """Bulk resume sets last_bulk_action='resume' on resumed checks."""
        check = Check.objects.create(project=self.project, name="C1", status="paused")
        self.post({"codes": [str(check.code)], "action": "resume"})
        check.refresh_from_db()
        self.assertEqual(check.last_bulk_action, "resume")

    def test_resume_skips_manual_resume(self):
        """Checks with manual_resume=True should be counted as skipped."""
        check = Check.objects.create(
            project=self.project, name="C1", status="paused", manual_resume=True
        )
        r = self.post({"codes": [str(check.code)], "action": "resume"})
        self.assertEqual(r.status_code, 200)
        doc = r.json()
        self.assertEqual(doc["resumed"], 0)
        self.assertEqual(doc["skipped"], 1)

    def test_resume_skipped_check_stays_paused(self):
        """Skipped (manual_resume=True) checks should remain paused."""
        check = Check.objects.create(
            project=self.project, name="C1", status="paused", manual_resume=True
        )
        self.post({"codes": [str(check.code)], "action": "resume"})
        check.refresh_from_db()
        self.assertEqual(check.status, "paused")

    def test_resume_mixed_manual(self):
        """Mix of manual_resume and normal checks gives correct resumed/skipped counts."""
        normal = Check.objects.create(project=self.project, name="Normal", status="paused")
        manual = Check.objects.create(
            project=self.project, name="Manual", status="paused", manual_resume=True
        )
        r = self.post({"codes": [str(normal.code), str(manual.code)], "action": "resume"})
        self.assertEqual(r.status_code, 200)
        doc = r.json()
        self.assertEqual(doc["resumed"], 1)
        self.assertEqual(doc["skipped"], 1)

    def test_resume_all_skipped(self):
        """All manual_resume checks should return {"resumed": 0, "skipped": N}."""
        checks = [
            Check.objects.create(
                project=self.project, name=f"C{i}", status="paused", manual_resume=True
            )
            for i in range(2)
        ]
        r = self.post({"codes": [str(c.code) for c in checks], "action": "resume"})
        self.assertEqual(r.status_code, 200)
        doc = r.json()
        self.assertEqual(doc["resumed"], 0)
        self.assertEqual(doc["skipped"], 2)

    def test_resume_creates_log(self):
        """Bulk resume should create a BulkActionLog with correct affected/skipped counts."""
        normal = Check.objects.create(project=self.project, name="Normal", status="paused")
        manual = Check.objects.create(
            project=self.project, name="Manual", status="paused", manual_resume=True
        )
        self.post({"codes": [str(normal.code), str(manual.code)], "action": "resume"})
        log = BulkActionLog.objects.get(project=self.project, action="resume")
        self.assertEqual(log.affected, 1)
        self.assertEqual(log.skipped, 1)

    def test_resume_response_shape(self):
        """Resume response should contain 'resumed' and 'skipped' keys only."""
        check = Check.objects.create(project=self.project, name="C1", status="paused")
        r = self.post({"codes": [str(check.code)], "action": "resume"})
        doc = r.json()
        self.assertIn("resumed", doc)
        self.assertIn("skipped", doc)
        self.assertNotIn("paused", doc)
        self.assertNotIn("deleted", doc)

# verify delete bulk batches work
class BulkDeleteTestCase(BaseTestCase):
    """Tests for the bulk delete action."""

    def setUp(self):
        super().setUp()
        self.url = "/api/v3/checks/bulk/"

    def post(self, data, api_key=None):
        if api_key is None:
            api_key = "X" * 32
        return self.client.post(
            self.url,
            json.dumps({**data, "api_key": api_key}),
            content_type="application/json",
        )

    def test_delete_single_check(self):
        """Bulk delete with one check returns {"deleted": 1}."""
        check = Check.objects.create(project=self.project, name="C1")
        r = self.post({"codes": [str(check.code)], "action": "delete"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"deleted": 1})

    def test_delete_multiple_checks(self):
        """Bulk delete with multiple checks returns correct count."""
        checks = [Check.objects.create(project=self.project, name=f"C{i}") for i in range(3)]
        r = self.post({"codes": [str(c.code) for c in checks], "action": "delete"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["deleted"], 3)

    def test_delete_removes_from_db(self):
        """Deleted checks should no longer exist in the database."""
        check = Check.objects.create(project=self.project, name="C1")
        code = check.code
        self.post({"codes": [str(code)], "action": "delete"})
        self.assertFalse(Check.objects.filter(code=code).exists())

    def test_delete_creates_log(self):
        """Bulk delete should create a BulkActionLog entry."""
        checks = [Check.objects.create(project=self.project, name=f"C{i}") for i in range(2)]
        self.post({"codes": [str(c.code) for c in checks], "action": "delete"})
        log = BulkActionLog.objects.get(project=self.project, action="delete")
        self.assertEqual(log.affected, 2)

    def test_delete_response_shape(self):
        """Delete response should contain only the 'deleted' key."""
        check = Check.objects.create(project=self.project, name="C1")
        r = self.post({"codes": [str(check.code)], "action": "delete"})
        doc = r.json()
        self.assertIn("deleted", doc)
        self.assertNotIn("paused", doc)
        self.assertNotIn("resumed", doc)

# verify all failure and error cases
class BulkErrorTestCase(BaseTestCase):
    """Tests for error responses in bulk check operations."""

    def setUp(self):
        super().setUp()
        self.url = "/api/v3/checks/bulk/"
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def post(self, data, api_key=None):
        if api_key is None:
            api_key = "X" * 32
        return self.client.post(
            self.url,
            json.dumps({**data, "api_key": api_key}),
            content_type="application/json",
        )

    def test_missing_codes(self):
        """Missing 'codes' key should return 400."""
        r = self.post({"action": "pause"})
        self.assertEqual(r.status_code, 400)

    def test_empty_codes(self):
        """Empty codes list should return 400."""
        r = self.post({"codes": [], "action": "pause"})
        self.assertEqual(r.status_code, 400)

    def test_codes_not_a_list_string(self):
        """codes as a string should return 400."""
        r = self.post({"codes": "abc123", "action": "pause"})
        self.assertEqual(r.status_code, 400)

    def test_codes_not_a_list_integer(self):
        """codes as an integer should return 400."""
        r = self.post({"codes": 42, "action": "pause"})
        self.assertEqual(r.status_code, 400)

    def test_missing_action(self):
        """Missing 'action' key should return 400."""
        r = self.post({"codes": [str(self.check.code)]})
        self.assertEqual(r.status_code, 400)

    def test_invalid_action(self):
        """Unsupported action value should return 400."""
        r = self.post({"codes": [str(self.check.code)], "action": "archive"})
        self.assertEqual(r.status_code, 400)

    def test_null_action(self):
        """Null action should return 400."""
        r = self.post({"codes": [str(self.check.code)], "action": None})
        self.assertEqual(r.status_code, 400)

    def test_code_not_found(self):
        """Non-existent check UUID should return 404."""
        r = self.post({"codes": [str(uuid.uuid4())], "action": "pause"})
        self.assertEqual(r.status_code, 404)

    def test_code_from_different_project(self):
        """Check belonging to another project should return 403."""
        other = Check.objects.create(project=self.bobs_project, name="Bob's Check")
        r = self.post({"codes": [str(other.code)], "action": "pause"})
        self.assertEqual(r.status_code, 403)

    def test_missing_api_key(self):
        """Missing API key should return 401."""
        r = self.client.post(
            self.url,
            json.dumps({"codes": [str(self.check.code)], "action": "pause"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)

    def test_wrong_api_key(self):
        """Wrong API key should return 401."""
        r = self.post(
            {"codes": [str(self.check.code)], "action": "pause"}, api_key="Y" * 32
        )
        self.assertEqual(r.status_code, 401)

    def test_cross_project_code_blocks_all(self):
        """A cross-project code should return 403 without modifying any checks."""
        own = Check.objects.create(project=self.project, name="Own")
        other = Check.objects.create(project=self.bobs_project, name="Other")
        r = self.post({"codes": [str(own.code), str(other.code)], "action": "pause"})
        self.assertEqual(r.status_code, 403)
        own.refresh_from_db()
        self.assertNotEqual(own.status, "paused", "own check should not have been modified")

    def test_invalid_code_blocks_all(self):
        """A missing code should return 404 without modifying any checks."""
        own = Check.objects.create(project=self.project, name="Own")
        r = self.post({"codes": [str(own.code), str(uuid.uuid4())], "action": "pause"})
        self.assertEqual(r.status_code, 404)
        own.refresh_from_db()
        self.assertNotEqual(own.status, "paused", "own check should not have been modified")

# verify endpoints are reachable at their correct urls
class BulkUrlRoutingTestCase(BaseTestCase):
    """Tests that the bulk endpoint is reachable on all API versions."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def _post(self, version):
        return self.client.post(
            f"/api/v{version}/checks/bulk/",
            json.dumps({
                "codes": [str(self.check.code)],
                "action": "pause",
                "api_key": "X" * 32,
            }),
            content_type="application/json",
        )

    def test_v3_endpoint(self):
        """Bulk endpoint should be reachable under /api/v3/."""
        r = self._post(3)
        self.assertEqual(r.status_code, 200)

    # test older version endpoints as well
    def test_v1_endpoint(self):
        """Bulk endpoint should be reachable under /api/v1/."""
        r = self._post(1)
        self.assertNotEqual(r.status_code, 404)

    def test_v2_endpoint(self):
        """Bulk endpoint should be reachable under /api/v2/."""
        r = self._post(2)
        self.assertNotEqual(r.status_code, 404)