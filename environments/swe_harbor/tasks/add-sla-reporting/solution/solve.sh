#!/bin/bash
set -e
cd /app

# 1. Add sla_target field to Check model

python3 << 'PATCH'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = '    status = models.CharField(max_length=6, choices=STATUSES, default="new")'
new = (
    '    sla_target = models.FloatField(null=True, blank=True)\n'
    '    status = models.CharField(max_length=6, choices=STATUSES, default="new")'
)

assert old in content, "patch target not found: Check.status field"
content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH

# 2. Add sla_target to Check.to_dict()

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
    '        result["sla_target"] = self.sla_target\n'
    '        return result'
)

assert old in content, "patch target not found: to_dict() return result"
content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH

# 3. Add import json to views.py

python3 << 'PATCH'
with open("hc/api/views.py", "r") as f:
    content = f.read()

assert "import time\n" in content, "patch target not found: views.py import time"
content = content.replace("import time\n", "import json\nimport time\n", 1)

with open("hc/api/views.py", "w") as f:
    f.write(content)
PATCH

# 4. Append check_sla view to views.py

cat >> /app/hc/api/views.py << 'VIEWEOF'


@cors("GET", "POST")
@csrf_exempt
@authorize_read
def check_sla(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    if request.method == "POST":
        if request.readonly:
            return HttpResponseForbidden()
        try:
            body = json.loads(request.body.decode())
        except (ValueError, AttributeError):
            return JsonResponse({"error": "could not parse request body"}, status=400)
        if not isinstance(body, dict):
            return JsonResponse({"error": "json validation error"}, status=400)

        sla_target = body.get("sla_target")
        if sla_target is None:
            check.sla_target = None
        else:
            if not isinstance(sla_target, (int, float)):
                return JsonResponse({"error": "sla_target is not a number"}, status=400)
            sla_target = float(sla_target)
            if not (0.0 < sla_target <= 100.0):
                return JsonResponse({"error": "sla_target must be between 0 and 100"}, status=400)
            check.sla_target = sla_target
        check.save()
        return JsonResponse(check.to_dict(v=request.v))

    # GET — return SLA report
    try:
        months = int(request.GET.get("months", 3))
    except (ValueError, TypeError):
        return JsonResponse({"error": "invalid months parameter"}, status=400)
    if not (1 <= months <= 12):
        return JsonResponse({"error": "months must be between 1 and 12"}, status=400)

    tz = request.GET.get("tz", check.tz or "UTC")
    if tz not in all_timezones:
        return JsonResponse({"error": "invalid timezone"}, status=400)

    records = check.downtimes(months, tz)
    month_data = []
    for r in records:
        uptime_pct = round(r.monthly_uptime() * 100, 4)
        if r.no_data:
            met_sla = None
        elif check.sla_target is not None:
            met_sla = uptime_pct >= check.sla_target
        else:
            met_sla = None
        month_data.append({
            "date": r.boundary.strftime("%Y-%m"),
            "uptime_pct": uptime_pct,
            "downtime_seconds": r.duration.total_seconds(),
            "downtime_starts": r.count,
            "met_sla": met_sla,
        })

    return JsonResponse({
        "sla_target": check.sla_target,
        "tz": tz,
        "months": month_data,
    })
VIEWEOF

# 5. Add URL route to urls.py

python3 << 'PATCH'
with open("hc/api/urls.py", "r") as f:
    content = f.read()

old = '    path("checks/<uuid:code>/pings/", views.pings, name="hc-api-pings"),'
new = (
    '    path("checks/<uuid:code>/sla/", views.check_sla, name="hc-api-sla"),\n'
    '    path("checks/<uuid:code>/pings/", views.pings, name="hc-api-pings"),'
)

assert old in content, "patch target not found: urls.py pings route"
content = content.replace(old, new, 1)

with open("hc/api/urls.py", "w") as f:
    f.write(content)
PATCH

# 6. Generate and run migration

python manage.py makemigrations api --name sla_target
python manage.py migrate
