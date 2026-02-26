# Add SLA Reporting

The Healthchecks codebase is at `/app/`.

Add per-check SLA (Service Level Agreement) tracking. Checks can have a target uptime percentage, and the API returns a monthly breakdown showing whether each month's actual uptime met the target.

## Requirements

- Add a `sla_target` field to the `Check` model in `/app/hc/api/models.py`:
    - `FloatField`, nullable and blank-allowed (default is null, SLA reporting is optional).
    - Include `sla_target` in `Check.to_dict()`.
- Generate and run the migration for the new field.
- `GET /api/v3/checks/<uuid:code>/sla/`: return a monthly SLA report (read key accepted).
    - Query parameters: `months` (integer, 1–12, default 3) and `tz` (IANA timezone string, default `"UTC"` or the check's own `tz` field).
    - Return `{"sla_target": <float|null>, "tz": <str>, "months": [<month_entry>, ...]}` where each month entry has `"date"` (YYYY-MM string), `"uptime_pct"` (float, 0.0–100.0, rounded to 4 decimal places), `"downtime_seconds"` (float), `"downtime_starts"` (int), and `"met_sla"` (bool or null).
    - `met_sla` is `true` if `uptime_pct >= sla_target`, `false` if not, and `null` if `sla_target` is not set or the period has no data.
    - Use the existing `Check.downtimes(months, tz)` method and `DowntimeRecord.monthly_uptime()` to compute uptime.
    - Return error if `months` is not an integer or is outside 1–12.
    - Return error if `tz` is not a valid IANA timezone string.
- `POST /api/v3/checks/<uuid:code>/sla/`: set (or clear) the check's `sla_target` (write key required).
    - Accept a JSON body with a `sla_target` key. If the key is absent or its value is `null`, clear the target. If present and non-null, it must be a number in the range (0, 100], return appropriate error code otherwise.
    - On success, return the check's full `to_dict()` with appropriate status.
- Handle both GET and POST in a single view named `check_sla`. Add the URL route.
- Raise error if the check belongs to a different project than the API key, return error if the check does not exist.

Don't modify existing tests. Follow existing codebase patterns for decorators, error responses, return statuses, and authorization.
