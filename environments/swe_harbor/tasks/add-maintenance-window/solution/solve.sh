#!/bin/bash
set -e
cd /app

# 1. Add maintenance_count field to Check.to_dict()

python3 << 'PATCH'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = '            "filter_subject": self.filter_subject,\n            "filter_body": self.filter_body,\n        }'
new = '            "filter_subject": self.filter_subject,\n            "filter_body": self.filter_body,\n            "maintenance_count": self.maintenance_windows.count(),\n        }'

content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH

# 2. Modify Check.get_status() to return "maintenance" in place of "down"

python3 << 'PATCH'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = '''    def get_status(self, *, with_started: bool = False) -> str:
        """Return current status for display."""
        frozen_now = now()

        if self.last_start:
            if frozen_now >= self.last_start + self.grace:
                return "down"
            elif with_started:
                return "started"

        if self.status in ("new", "paused", "down"):
            return self.status

        grace_start = self.get_grace_start(with_started=False)
        if grace_start is None:
            # next elapse is "never", so this check will stay up indefinitely
            return "up"

        grace_end = grace_start + self.grace
        if frozen_now >= grace_end:
            return "down"

        if frozen_now >= grace_start:
            return "grace"

        return "up"'''

new = '''    def get_status(self, *, with_started: bool = False) -> str:
        """Return current status for display."""
        frozen_now = now()

        def _in_maintenance():
            return self.maintenance_windows.filter(
                start__lte=frozen_now, end__gt=frozen_now
            ).exists()

        if self.last_start:
            if frozen_now >= self.last_start + self.grace:
                return "maintenance" if _in_maintenance() else "down"
            elif with_started:
                return "started"

        if self.status in ("new", "paused", "down"):
            if self.status == "down" and _in_maintenance():
                return "maintenance"
            return self.status

        grace_start = self.get_grace_start(with_started=False)
        if grace_start is None:
            # next elapse is "never", so this check will stay up indefinitely
            return "up"

        grace_end = grace_start + self.grace
        if frozen_now >= grace_end:
            return "maintenance" if _in_maintenance() else "down"

        if frozen_now >= grace_start:
            return "grace"

        return "up"'''

content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH

# 3. Append MaintenanceWindow model to models.py

cat >> /app/hc/api/models.py << 'PYEOF'


class MaintenanceWindow(models.Model):
    code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    owner = models.ForeignKey(Check, models.CASCADE, related_name="maintenance_windows")
    start = models.DateTimeField()
    end = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["start"]

    def to_dict(self) -> dict:
        return {
            "uuid": str(self.code),
            "owner": str(self.owner.code),
            "start": isostring(self.start),
            "end": isostring(self.end),
            "reason": self.reason,
        }
PYEOF

# 4. Add json imports and MaintenanceWindow to views.py

python3 << 'PATCH'
with open("hc/api/views.py", "r") as f:
    content = f.read()

content = content.replace(
    "import time\n",
    "import json\nimport time\n",
    1,
)
content = content.replace(
    "from hc.api.models import MAX_DURATION, Channel, Check, Flip, Notification, Ping",
    "from hc.api.models import MAX_DURATION, Channel, Check, Flip, MaintenanceWindow, Notification, Ping",
    1,
)

with open("hc/api/views.py", "w") as f:
    f.write(content)
PATCH

# 5. Append check_maintenance and delete_maintenance_window functions to views.py

cat >> /app/hc/api/views.py << 'VIEWEOF'


@cors("GET", "POST")
@csrf_exempt
@authorize_read
def check_maintenance(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    if request.method == "GET":
        windows = check.maintenance_windows.all()
        return JsonResponse({"windows": [w.to_dict() for w in windows]})

    if request.readonly:
        return HttpResponseForbidden()

    try:
        body = json.loads(request.body.decode())
    except (ValueError, AttributeError):
        return JsonResponse({"error": "could not parse request body"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "json validation error"}, status=400)

    start_str = body.get("start")
    end_str = body.get("end")
    if not start_str or not end_str:
        return JsonResponse({"error": "missing start or end"}, status=400)

    try:
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
    except (ValueError, TypeError):
        return JsonResponse({"error": "invalid datetime format"}, status=400)

    if end <= start:
        return JsonResponse({"error": "end must be after start"}, status=400)

    window = MaintenanceWindow.objects.create(
        owner=check,
        start=start,
        end=end,
        reason=body.get("reason", ""),
    )
    return JsonResponse(window.to_dict(), status=201)


@cors("DELETE")
@csrf_exempt
@authorize
def delete_maintenance_window(
    request: ApiRequest, code: UUID, window_code: UUID
) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    window = get_object_or_404(MaintenanceWindow, owner=check, code=window_code)
    window.delete()
    return HttpResponse(status=204)
VIEWEOF

# 6. Add URL routes to urls.py

python3 << 'PATCH'
with open("hc/api/urls.py", "r") as f:
    content = f.read()

old = '    path("checks/<uuid:code>/pings/", views.pings, name="hc-api-pings"),'
new = (
    '    path("checks/<uuid:code>/maintenance/", views.check_maintenance, name="hc-api-maintenance"),\n'
    '    path("checks/<uuid:code>/maintenance/<uuid:window_code>/", views.delete_maintenance_window, name="hc-api-delete-maintenance"),\n'
    '    path("checks/<uuid:code>/pings/", views.pings, name="hc-api-pings"),'
)

content = content.replace(old, new, 1)

with open("hc/api/urls.py", "w") as f:
    f.write(content)
PATCH

# 7. Generate and run migration so MaintenanceWindow has a table in the sqlite db

python manage.py makemigrations api --name maintenance_window
python manage.py migrate
