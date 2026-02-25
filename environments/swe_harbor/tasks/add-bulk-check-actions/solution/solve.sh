#!/bin/bash
set -e
cd /app

# 1. Add last_bulk_action field to Check model

python3 << 'PATCH'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = '    status = models.CharField(max_length=6, choices=STATUSES, default="new")'
new = (
    '    status = models.CharField(max_length=6, choices=STATUSES, default="new")\n'
    '    last_bulk_action = models.CharField(max_length=10, null=True, blank=True)'
)

assert old in content, "patch target not found: status field"
content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH

# 2. Add last_bulk_action to Check.to_dict()

python3 << 'PATCH'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = '            "filter_subject": self.filter_subject,\n            "filter_body": self.filter_body,\n        }'
new = '            "filter_subject": self.filter_subject,\n            "filter_body": self.filter_body,\n            "last_bulk_action": self.last_bulk_action,\n        }'

assert old in content, "patch target not found: to_dict filter_body"
content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH

# 3. Append BulkActionLog model to models.py

cat >> /app/hc/api/models.py << 'PYEOF'


class BulkActionLog(models.Model):
    code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    project = models.ForeignKey(
        Project, models.SET_NULL, null=True, related_name="bulk_action_logs"
    )
    action = models.CharField(max_length=10)
    affected = models.IntegerField()
    skipped = models.IntegerField(default=0)
    created = models.DateTimeField(default=now)

    class Meta:
        ordering = ["-created"]

    def to_dict(self) -> dict:
        return {
            "uuid": str(self.code),
            "project": str(self.project.code) if self.project else None,
            "action": self.action,
            "affected": self.affected,
            "skipped": self.skipped,
            "created": isostring(self.created),
        }
PYEOF

# 4. Add BulkActionLog to the views.py import

python3 << 'PATCH'
with open("hc/api/views.py", "r") as f:
    content = f.read()

old = "from hc.api.models import MAX_DURATION, Channel, Check, Flip, Notification, Ping"
new = "from hc.api.models import MAX_DURATION, BulkActionLog, Channel, Check, Flip, Notification, Ping"

assert old in content, "patch target not found: views.py import"
content = content.replace(old, new, 1)

with open("hc/api/views.py", "w") as f:
    f.write(content)
PATCH

# 5. Append bulk_checks view to views.py

cat >> /app/hc/api/views.py << 'VIEWEOF'


@cors("POST")
@csrf_exempt
@authorize
def bulk_checks(request: ApiRequest) -> HttpResponse:
    codes = request.json.get("codes")
    if codes is None or (isinstance(codes, list) and len(codes) == 0):
        return JsonResponse({"error": "missing or empty codes list"}, status=400)
    if not isinstance(codes, list):
        return JsonResponse({"error": "codes must be a list"}, status=400)

    action = request.json.get("action")
    if action not in ("pause", "resume", "delete"):
        return JsonResponse({"error": "missing or invalid action"}, status=400)

    checks = []
    for code_str in codes:
        try:
            check = Check.objects.get(code=code_str)
        except (Check.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"error": "check not found"}, status=404)
        if check.project_id != request.project.id:
            return HttpResponseForbidden()
        checks.append(check)

    if action == "pause":
        for check in checks:
            check.create_flip("paused", mark_as_processed=True)
            check.status = "paused"
            check.last_start = None
            check.alert_after = None
            check.last_bulk_action = "pause"
            check.save()
        request.project.update_next_nag_dates()
        BulkActionLog.objects.create(
            project=request.project, action="pause", affected=len(checks)
        )
        return JsonResponse({"paused": len(checks)})

    if action == "resume":
        resumed = 0
        skipped = 0
        for check in checks:
            if check.manual_resume:
                check.last_bulk_action = "resume"
                check.save()
                skipped += 1
            else:
                check.create_flip("new", mark_as_processed=True)
                check.status = "new"
                check.last_start = None
                check.last_ping = None
                check.alert_after = None
                check.last_bulk_action = "resume"
                check.save()
                resumed += 1
        BulkActionLog.objects.create(
            project=request.project, action="resume", affected=resumed, skipped=skipped
        )
        return JsonResponse({"resumed": resumed, "skipped": skipped})

    if action == "delete":
        for check in checks:
            check.lock_and_delete()
        BulkActionLog.objects.create(
            project=request.project, action="delete", affected=len(checks)
        )
        return JsonResponse({"deleted": len(checks)})

    return JsonResponse({"error": "unrecognized action"}, status=400)
VIEWEOF

# 6. Add URL route for checks/bulk/

python3 << 'PATCH'
with open("hc/api/urls.py", "r") as f:
    content = f.read()

old = '    path("checks/", views.checks),'
new = '    path("checks/", views.checks),\n    path("checks/bulk/", views.bulk_checks, name="hc-api-bulk-checks"),'

assert old in content, "patch target not found: urls.py checks route"
content = content.replace(old, new, 1)

with open("hc/api/urls.py", "w") as f:
    f.write(content)
PATCH

# 7. Generate and run migrations

python manage.py makemigrations api --name last_bulk_action
python manage.py migrate
