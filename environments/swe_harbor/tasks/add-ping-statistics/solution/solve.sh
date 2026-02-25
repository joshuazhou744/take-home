#!/bin/bash
set -e
cd /app

# 1. Add ping_success_rate field to Check.to_dict()

python3 << 'PATCH'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = '''        if self.last_duration:
            result["last_duration"] = int(self.last_duration.total_seconds())'''

assert old in content, "patch target not found: to_dict last_duration"
new = '''        _total = Ping.objects.filter(owner=self).count()
        _success = Ping.objects.filter(owner=self, kind__isnull=True).count()
        result["ping_success_rate"] = (_success / _total) if _total > 0 else None

        if self.last_duration:
            result["last_duration"] = int(self.last_duration.total_seconds())'''

content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH

# 2. Add ping_stats() method to Check

python3 << 'PATCH'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = '''    def ping(
        self,
        remote_addr: str,'''

assert old in content, "patch target not found: ping() method"
new = '''    def ping_stats(self) -> dict:
        from collections import defaultdict
        from datetime import timedelta

        pings = Ping.objects.filter(owner=self)
        total = pings.count()
        success = pings.filter(kind__isnull=True).count()
        fail = pings.filter(kind="fail").count()
        start_count = pings.filter(kind="start").count()

        ping_success_rate = (success / total) if total > 0 else None

        # avg_duration: match start->success pairs by rid
        start_times = {
            p.rid: p.created
            for p in pings.filter(kind="start", rid__isnull=False)
        }
        durations = []
        for p in pings.filter(kind__isnull=True, rid__isnull=False):
            if p.rid in start_times:
                duration = p.created - start_times[p.rid]
                if td() < duration < MAX_DURATION:
                    durations.append(duration.total_seconds())

        avg_duration_seconds = (sum(durations) / len(durations)) if durations else None

        # daily breakdown: last 30 days newest first
        today = now().date()
        days = [today - timedelta(days=i) for i in range(30)]
        day_set = set(days)
        daily_counts = defaultdict(lambda: [0, 0, 0])  # [total, success, fail]
        for p in pings.filter(created__date__gte=days[-1]).only("created", "kind"):
            d = p.created.date()
            if d in day_set:
                daily_counts[d][0] += 1
                if p.kind is None:
                    daily_counts[d][1] += 1
                elif p.kind == "fail":
                    daily_counts[d][2] += 1

        daily = [
            {
                "date": str(d),
                "total": daily_counts[d][0],
                "success": daily_counts[d][1],
                "fail": daily_counts[d][2],
            }
            for d in days
        ]

        return {
            "total": total,
            "success": success,
            "fail": fail,
            "start": start_count,
            "ping_success_rate": ping_success_rate,
            "avg_duration_seconds": avg_duration_seconds,
            "daily": daily,
        }

    def ping(
        self,
        remote_addr: str,'''

content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH

# 3. Append check_stats view to views.py

cat >> /app/hc/api/views.py << 'VIEWEOF'


@cors("GET")
@csrf_exempt
@authorize_read
def check_stats(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    return JsonResponse(check.ping_stats())
VIEWEOF

# 4. Add URL route to urls.py

python3 << 'PATCH'
with open("hc/api/urls.py", "r") as f:
    content = f.read()

old = '    path("checks/<uuid:code>/pings/", views.pings, name="hc-api-pings"),'
new = (
    '    path("checks/<uuid:code>/stats/", views.check_stats, name="hc-api-stats"),\n'
    '    path("checks/<uuid:code>/pings/", views.pings, name="hc-api-pings"),'
)

assert old in content, "patch target not found: urls.py pings route"
content = content.replace(old, new, 1)

with open("hc/api/urls.py", "w") as f:
    f.write(content)
PATCH
