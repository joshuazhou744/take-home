#!/bin/bash
set -e
cd /app

# 1. Append CheckDependency model to models.py

cat >> /app/hc/api/models.py << 'PYEOF'


class CheckDependency(models.Model):
    code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    owner = models.ForeignKey(Check, models.CASCADE, related_name="dependencies")
    depends_on = models.ForeignKey(Check, models.CASCADE, related_name="dependents")
    created = models.DateTimeField(default=now)

    class Meta:
        unique_together = [("owner", "depends_on")]

    def to_dict(self) -> dict:
        return {
            "uuid": str(self.code),
            "check": str(self.owner.code),
            "depends_on": str(self.depends_on.code),
            "created": isostring(self.created),
        }
PYEOF

# 2. Add dependencies list to Check.to_dict()

python3 << 'PATCH'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = (
    '        if self.kind == "simple":\n'
    '            result["timeout"] = int(self.timeout.total_seconds())\n'
    '        elif self.kind in ("cron", "oncalendar"):\n'
    '            result["schedule"] = self.schedule\n'
    '            result["tz"] = self.tz\n'
    '\n'
    '        return result'
)
new = (
    '        if self.kind == "simple":\n'
    '            result["timeout"] = int(self.timeout.total_seconds())\n'
    '        elif self.kind in ("cron", "oncalendar"):\n'
    '            result["schedule"] = self.schedule\n'
    '            result["tz"] = self.tz\n'
    '\n'
    '        result["dependencies"] = [str(d.depends_on.code) for d in self.dependencies.all()]\n'
    '        return result'
)

assert old in content, "patch target not found: to_dict() return result"
content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH

# 3. Patch Flip.select_channels() to suppress alerts when a dependency is down

python3 << 'PATCH'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = (
    '        if self.new_status not in ("up", "down"):\n'
    '            raise NotImplementedError(f"Unexpected status: {self.new_status}")\n'
    '\n'
    '        q = self.owner.channel_set.exclude(disabled=True)\n'
    '        return [ch for ch in q if not ch.transport.is_noop(self.new_status)]'
)
new = (
    '        if self.new_status not in ("up", "down"):\n'
    '            raise NotImplementedError(f"Unexpected status: {self.new_status}")\n'
    '\n'
    '        # Suppress alerts if a dependency is currently down\n'
    '        if self.new_status == "down":\n'
    '            for dep in self.owner.dependencies.select_related("depends_on"):\n'
    '                if dep.depends_on.get_status() == "down":\n'
    '                    return []\n'
    '\n'
    '        q = self.owner.channel_set.exclude(disabled=True)\n'
    '        return [ch for ch in q if not ch.transport.is_noop(self.new_status)]'
)

assert old in content, "patch target not found: Flip.select_channels() q = self.owner.channel_set"
content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH

# 4. Add import json and CheckDependency import to views.py

python3 << 'PATCH'
with open("hc/api/views.py", "r") as f:
    content = f.read()

assert "import time\n" in content, "patch target not found: views.py import time"
content = content.replace("import time\n", "import json\nimport time\n", 1)

assert "from hc.api.models import MAX_DURATION, Channel, Check, Flip, Notification, Ping" in content, \
    "patch target not found: views.py model import"
content = content.replace(
    "from hc.api.models import MAX_DURATION, Channel, Check, Flip, Notification, Ping",
    "from hc.api.models import MAX_DURATION, Channel, Check, CheckDependency, Flip, Notification, Ping",
    1,
)

with open("hc/api/views.py", "w") as f:
    f.write(content)
PATCH

# 5. Append check_dependencies and delete_check_dependency views to views.py

cat >> /app/hc/api/views.py << 'VIEWEOF'


@cors("GET", "POST")
@csrf_exempt
@authorize_read
def check_dependencies(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    if request.method == "GET":
        deps = check.dependencies.select_related("depends_on")
        return JsonResponse({"dependencies": [d.to_dict() for d in deps]})

    if request.readonly:
        return HttpResponseForbidden()

    try:
        body = json.loads(request.body.decode())
    except (ValueError, AttributeError):
        return JsonResponse({"error": "could not parse request body"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "json validation error"}, status=400)

    dep_code_str = body.get("depends_on", "")
    if not dep_code_str:
        return JsonResponse({"error": "depends_on is required"}, status=400)

    try:
        dep_uuid = UUID(str(dep_code_str))
    except (ValueError, AttributeError):
        return JsonResponse({"error": "invalid depends_on uuid"}, status=400)

    depends_on = get_object_or_404(Check, code=dep_uuid)
    if depends_on.project_id != request.project.id:
        return HttpResponseForbidden()

    if depends_on.id == check.id:
        return JsonResponse({"error": "a check cannot depend on itself"}, status=400)

    if check.dependencies.filter(depends_on=depends_on).exists():
        return JsonResponse({"error": "dependency already exists"}, status=400)

    dep = CheckDependency.objects.create(owner=check, depends_on=depends_on)
    return JsonResponse(dep.to_dict(), status=201)


@cors("DELETE")
@csrf_exempt
@authorize
def delete_check_dependency(request: ApiRequest, code: UUID, dep_code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    dep = get_object_or_404(CheckDependency, owner=check, code=dep_code)
    dep.delete()
    return HttpResponse(status=204)
VIEWEOF

# 6. Add URL routes to urls.py

python3 << 'PATCH'
with open("hc/api/urls.py", "r") as f:
    content = f.read()

old = '    path("checks/<uuid:code>/pings/", views.pings, name="hc-api-pings"),'
new = (
    '    path("checks/<uuid:code>/dependencies/", views.check_dependencies, name="hc-api-dependencies"),\n'
    '    path("checks/<uuid:code>/dependencies/<uuid:dep_code>/", views.delete_check_dependency, name="hc-api-delete-dependency"),\n'
    '    path("checks/<uuid:code>/pings/", views.pings, name="hc-api-pings"),'
)

assert old in content, "patch target not found: urls.py pings route"
content = content.replace(old, new, 1)

with open("hc/api/urls.py", "w") as f:
    f.write(content)
PATCH

# 7. Generate and run migration

python manage.py makemigrations api --name check_dependency
python manage.py migrate
