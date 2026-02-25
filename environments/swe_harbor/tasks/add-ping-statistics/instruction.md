# Add Ping Statistics API

The Healthchecks codebase is at `/app/`.

Add a read-only endpoint that returns aggregated ping statistics for a check.

## Requirements

- Add a `ping_stats()` method to the `Check` model in `/app/hc/api/models.py`. It should query the `Ping` table and return a dict with:
    - `total`: total number of pings
    - `success`: count of pings where `kind` is `null`
    - `fail`: count of pings where `kind="fail"`
    - `start`: count of pings where `kind="start"`
    - `ping_success_rate`: float (0-1). Calculated as `success / total`. Fallback `null`.
    - `avg_duration_seconds`: average duration in seconds calculated from matched start-success ping pairs (match on `rid`), `null` if no matched pairs. Use `MAX_DURATION` as the upper bound for valid durations, consistent with the rest of the codebase.
    - `daily`: list of the last 30 days newest first, each entry `{"date": "YYYY-MM-DD", "total": <int>, "success": <int>, "fail": <int>}`. Include days with zero pings.
- Add `ping_success_rate` to `Check.to_dict()` by calling into the same `Ping` query. Return `null` if no pings.
- `GET /api/v3/checks/<uuid:code>/stats/` returns the result of `ping_stats()` for the check (read key accepted). Add the URL route.
- Make the view function name: `check_stats`.

Don't modify existing tests. Follow existing codebase patterns for decorators, error responses, and authorization.
