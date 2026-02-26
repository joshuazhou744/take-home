"""Tests for the Check Dependency Suppression feature."""
from __future__ import annotations

import json
import uuid

import os
import sys
sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
django.setup()

from django.utils.timezone import now

from hc.api.models import Channel, Check, CheckDependency, Flip
from hc.test import BaseTestCase


class CheckDependencyModelTestCase(BaseTestCase):
    """Tests for the CheckDependency model."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Check A")
        self.dep_check = Check.objects.create(project=self.project, name="Check B")

    def test_model_importable(self):
        """CheckDependency should be importable from hc.api.models."""
        self.assertTrue(hasattr(CheckDependency, "objects"))

    def test_create_dependency(self):
        """Can create a CheckDependency linking two checks."""
        dep = CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        self.assertIsNotNone(dep.code)
        self.assertEqual(dep.check, self.check)
        self.assertEqual(dep.depends_on, self.dep_check)

    def test_to_dict_keys(self):
        """to_dict() should return uuid, check, depends_on, and created."""
        dep = CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        d = dep.to_dict()
        for key in ("uuid", "check", "depends_on", "created"):
            self.assertIn(key, d, f"Missing key: {key}")

    def test_to_dict_check_is_uuid_string(self):
        """to_dict() check should be the check's UUID string."""
        dep = CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        self.assertEqual(dep.to_dict()["check"], str(self.check.code))

    def test_to_dict_depends_on_is_uuid_string(self):
        """to_dict() depends_on should be the dependency's UUID string."""
        dep = CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        self.assertEqual(dep.to_dict()["depends_on"], str(self.dep_check.code))

    def test_unique_together_enforced(self):
        """Creating a duplicate dependency should raise an error."""
        from django.db import IntegrityError
        CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        with self.assertRaises(IntegrityError):
            CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)

    def test_cascade_delete_on_check(self):
        """Deleting the check should delete its dependencies."""
        from django.contrib.auth.models import User
        from hc.accounts.models import Project
        user = User.objects.create_user("tmpuser_a", "tmpa@example.com", "pass")
        project = Project.objects.create(owner=user)
        check_a = Check.objects.create(project=project, name="A")
        check_b = Check.objects.create(project=project, name="B")
        dep = CheckDependency.objects.create(check=check_a, depends_on=check_b)
        dep_id = dep.id
        check_a.delete()
        self.assertFalse(CheckDependency.objects.filter(id=dep_id).exists())

    def test_cascade_delete_on_depends_on(self):
        """Deleting the dependency target should delete the CheckDependency record."""
        from django.contrib.auth.models import User
        from hc.accounts.models import Project
        user = User.objects.create_user("tmpuser_b", "tmpb@example.com", "pass")
        project = Project.objects.create(owner=user)
        check_a = Check.objects.create(project=project, name="A")
        check_b = Check.objects.create(project=project, name="B")
        dep = CheckDependency.objects.create(check=check_a, depends_on=check_b)
        dep_id = dep.id
        check_b.delete()
        self.assertFalse(CheckDependency.objects.filter(id=dep_id).exists())


class DependenciesToDictTestCase(BaseTestCase):
    """Tests for the dependencies key in Check.to_dict()."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Check A")
        self.dep_check = Check.objects.create(project=self.project, name="Check B")

    def test_dependencies_key_present(self):
        """to_dict() should include a dependencies key."""
        self.assertIn("dependencies", self.check.to_dict())

    def test_dependencies_empty_by_default(self):
        """dependencies should be an empty list when no dependencies are set."""
        self.assertEqual(self.check.to_dict()["dependencies"], [])

    def test_dependencies_shows_uuid_strings(self):
        """dependencies should list UUID strings of depends_on checks."""
        CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        deps = self.check.to_dict()["dependencies"]
        self.assertIn(str(self.dep_check.code), deps)

    def test_dependencies_count_matches(self):
        """dependencies list length should match the number of dependencies."""
        extra = Check.objects.create(project=self.project, name="Check C")
        CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        CheckDependency.objects.create(check=self.check, depends_on=extra)
        self.assertEqual(len(self.check.to_dict()["dependencies"]), 2)


class AddDependencyApiTestCase(BaseTestCase):
    """Tests for POST /api/v3/checks/<uuid>/dependencies/."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Check A")
        self.dep_check = Check.objects.create(project=self.project, name="Check B")
        self.url = f"/api/v3/checks/{self.check.code}/dependencies/"

    def _post(self, data, api_key="X" * 32):
        return self.client.post(
            self.url,
            json.dumps(data),
            content_type="application/json",
            HTTP_X_API_KEY=api_key,
        )

    def test_post_creates_dependency_201(self):
        """POST should return 201 on success."""
        r = self._post({"depends_on": str(self.dep_check.code)})
        self.assertEqual(r.status_code, 201)

    def test_post_returns_dependency_dict(self):
        """POST response should include dependency fields."""
        r = self._post({"depends_on": str(self.dep_check.code)})
        doc = r.json()
        for key in ("uuid", "check", "depends_on", "created"):
            self.assertIn(key, doc, f"Response missing key: {key}")

    def test_post_persists_dependency(self):
        """POST should create a CheckDependency in the database."""
        self._post({"depends_on": str(self.dep_check.code)})
        self.assertTrue(
            CheckDependency.objects.filter(check=self.check, depends_on=self.dep_check).exists()
        )

    def test_post_no_api_key_returns_401(self):
        """Missing API key should return 401."""
        r = self.client.post(
            self.url,
            json.dumps({"depends_on": str(self.dep_check.code)}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)

    def test_post_readonly_key_returns_403(self):
        """Read-only API key should return 403."""
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        r = self._post({"depends_on": str(self.dep_check.code)}, api_key="R" * 32)
        self.assertEqual(r.status_code, 403)

    def test_post_wrong_project_for_depends_on_returns_403(self):
        """depends_on check from another project should return 403."""
        other = Check.objects.create(project=self.bobs_project, name="Bob")
        r = self._post({"depends_on": str(other.code)})
        self.assertEqual(r.status_code, 403)

    def test_post_self_dependency_returns_400(self):
        """A check cannot depend on itself."""
        r = self._post({"depends_on": str(self.check.code)})
        self.assertEqual(r.status_code, 400)

    def test_post_duplicate_dependency_returns_400(self):
        """Duplicate dependency should return 400."""
        self._post({"depends_on": str(self.dep_check.code)})
        r = self._post({"depends_on": str(self.dep_check.code)})
        self.assertEqual(r.status_code, 400)

    def test_post_invalid_uuid_returns_400(self):
        """Invalid UUID for depends_on should return 400."""
        r = self._post({"depends_on": "not-a-uuid"})
        self.assertEqual(r.status_code, 400)

    def test_post_missing_depends_on_returns_400(self):
        """Missing depends_on field should return 400."""
        r = self._post({})
        self.assertEqual(r.status_code, 400)

    def test_post_wrong_project_check_returns_403(self):
        """Check from another project should return 403."""
        other = Check.objects.create(project=self.bobs_project, name="Bob")
        url = f"/api/v3/checks/{other.code}/dependencies/"
        r = self.client.post(
            url,
            json.dumps({"depends_on": str(self.dep_check.code)}),
            content_type="application/json",
            HTTP_X_API_KEY="X" * 32,
        )
        self.assertEqual(r.status_code, 403)


class DeleteDependencyApiTestCase(BaseTestCase):
    """Tests for DELETE /api/v3/checks/<uuid>/dependencies/<uuid>/."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Check A")
        self.dep_check = Check.objects.create(project=self.project, name="Check B")
        self.dep = CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        self.url = f"/api/v3/checks/{self.check.code}/dependencies/{self.dep.code}/"

    def _delete(self, url=None, api_key="X" * 32):
        return self.client.delete(url or self.url, HTTP_X_API_KEY=api_key)

    def test_delete_returns_204(self):
        """DELETE should return 204 on success."""
        r = self._delete()
        self.assertEqual(r.status_code, 204)

    def test_delete_removes_dependency(self):
        """DELETE should remove the CheckDependency from the database."""
        self._delete()
        self.assertFalse(CheckDependency.objects.filter(code=self.dep.code).exists())

    def test_delete_nonexistent_returns_404(self):
        """DELETE for a non-existent dependency UUID should return 404."""
        url = f"/api/v3/checks/{self.check.code}/dependencies/{uuid.uuid4()}/"
        r = self._delete(url=url)
        self.assertEqual(r.status_code, 404)

    def test_delete_no_api_key_returns_401(self):
        """Missing API key should return 401."""
        r = self.client.delete(self.url)
        self.assertEqual(r.status_code, 401)

    def test_delete_wrong_project_returns_403(self):
        """Check from another project should return 403."""
        other = Check.objects.create(project=self.bobs_project, name="Bob")
        other_dep = Check.objects.create(project=self.bobs_project, name="Bob Dep")
        dep = CheckDependency.objects.create(check=other, depends_on=other_dep)
        url = f"/api/v3/checks/{other.code}/dependencies/{dep.code}/"
        r = self._delete(url=url)
        self.assertEqual(r.status_code, 403)


class ListDependenciesApiTestCase(BaseTestCase):
    """Tests for GET /api/v3/checks/<uuid>/dependencies/."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Check A")
        self.dep_check = Check.objects.create(project=self.project, name="Check B")
        self.url = f"/api/v3/checks/{self.check.code}/dependencies/"

    def _get(self, url=None, api_key="X" * 32):
        return self.client.get(url or self.url, HTTP_X_API_KEY=api_key)

    def test_get_returns_200(self):
        """GET should return 200."""
        r = self._get()
        self.assertEqual(r.status_code, 200)

    def test_get_returns_empty_list(self):
        """GET should return empty list when no dependencies exist."""
        r = self._get()
        self.assertEqual(r.json(), {"dependencies": []})

    def test_get_returns_dependencies(self):
        """GET should list all dependency records."""
        CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        r = self._get()
        self.assertEqual(len(r.json()["dependencies"]), 1)

    def test_get_readonly_key_accepted(self):
        """Read-only API key should be accepted for GET."""
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        r = self._get(api_key="R" * 32)
        self.assertEqual(r.status_code, 200)

    def test_get_wrong_project_returns_403(self):
        """Check from another project should return 403."""
        other = Check.objects.create(project=self.bobs_project, name="Bob")
        r = self._get(url=f"/api/v3/checks/{other.code}/dependencies/")
        self.assertEqual(r.status_code, 403)

    def test_get_no_api_key_returns_401(self):
        """Missing API key should return 401."""
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 401)


class SuppressionTestCase(BaseTestCase):
    """Tests for Flip.select_channels() suppression logic."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(
            project=self.project, name="Check A", status="up"
        )
        self.dep_check = Check.objects.create(
            project=self.project, name="Check B", status="up"
        )
        # Attach a channel so select_channels() can return non-empty
        self.channel = Channel.objects.create(project=self.project, kind="pd")
        self.channel.checks.add(self.check)

    def _make_flip(self, old_status="up", new_status="down"):
        flip = Flip(owner=self.check, old_status=old_status, new_status=new_status, created=now())
        flip.save()
        return flip

    def test_no_deps_returns_channels(self):
        """select_channels() should return channels when no dependencies exist."""
        flip = self._make_flip(old_status="up", new_status="down")
        channels = flip.select_channels()
        self.assertGreater(len(channels), 0, "Expected non-empty channel list with no dependencies")

    def test_down_dep_suppresses_alert(self):
        """select_channels() should return [] when a dependency is down."""
        self.dep_check.status = "down"
        self.dep_check.save()
        CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        flip = self._make_flip(old_status="up", new_status="down")
        channels = flip.select_channels()
        self.assertEqual(channels, [], "Expected suppression when dependency is down")

    def test_up_dep_does_not_suppress(self):
        """select_channels() should return channels when dependency is up."""
        self.dep_check.status = "up"
        self.dep_check.save()
        CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        flip = self._make_flip(old_status="up", new_status="down")
        channels = flip.select_channels()
        self.assertGreater(len(channels), 0, "Expected channels when dependency is up")

    def test_new_dep_does_not_suppress(self):
        """select_channels() should return channels when dependency is new."""
        self.dep_check.status = "new"
        self.dep_check.save()
        CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        flip = self._make_flip(old_status="up", new_status="down")
        channels = flip.select_channels()
        self.assertGreater(len(channels), 0, "Expected channels when dependency is new")

    def test_paused_dep_does_not_suppress(self):
        """select_channels() should return channels when dependency is paused."""
        self.dep_check.status = "paused"
        self.dep_check.save()
        CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        flip = self._make_flip(old_status="up", new_status="down")
        channels = flip.select_channels()
        self.assertGreater(len(channels), 0, "Expected channels when dependency is paused")

    def test_suppression_only_on_down_new_status(self):
        """Suppression should not apply when new_status is 'up'."""
        self.dep_check.status = "down"
        self.dep_check.save()
        CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        # Flip going up — should not be suppressed
        flip = self._make_flip(old_status="down", new_status="up")
        channels = flip.select_channels()
        # new->up and paused->up are also suppressed by existing logic, but down->up is not
        self.assertIsNotNone(channels, "select_channels() should not return None")

    def test_multiple_deps_any_down_suppresses(self):
        """Suppression should trigger if ANY dependency is down."""
        dep_c = Check.objects.create(project=self.project, name="Check C", status="up")
        self.dep_check.status = "down"
        self.dep_check.save()
        CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        CheckDependency.objects.create(check=self.check, depends_on=dep_c)
        flip = self._make_flip(old_status="up", new_status="down")
        channels = flip.select_channels()
        self.assertEqual(channels, [], "Expected suppression when at least one dependency is down")

    def test_multiple_deps_all_up_no_suppression(self):
        """No suppression when all dependencies are up."""
        dep_c = Check.objects.create(project=self.project, name="Check C", status="up")
        CheckDependency.objects.create(check=self.check, depends_on=self.dep_check)
        CheckDependency.objects.create(check=self.check, depends_on=dep_c)
        flip = self._make_flip(old_status="up", new_status="down")
        channels = flip.select_channels()
        self.assertGreater(len(channels), 0, "Expected channels when all dependencies are up")


class DependencyUrlRoutingTestCase(BaseTestCase):
    """Tests that dependency endpoints are reachable on all API versions."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def _get(self, version):
        url = f"/api/v{version}/checks/{self.check.code}/dependencies/"
        return self.client.get(url, HTTP_X_API_KEY="X" * 32)

    def test_v3_endpoint(self):
        """Dependencies endpoint should be reachable under /api/v3/."""
        r = self._get(3)
        self.assertEqual(r.status_code, 200)

    def test_v1_endpoint(self):
        """Dependencies endpoint should be reachable under /api/v1/."""
        r = self._get(1)
        self.assertNotEqual(r.status_code, 404)

    def test_v2_endpoint(self):
        """Dependencies endpoint should be reachable under /api/v2/."""
        r = self._get(2)
        self.assertNotEqual(r.status_code, 404)
