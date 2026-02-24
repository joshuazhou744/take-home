## Rough draft of the three tasks I plan to implement

Create `insteruction.md` specs for each task such that the agent can follow them exaclty and implement the task properly to pass all tests. Should try to be deterministic in instructions without giving direct solutions in a manner that mimics how real developers use AI.

1. Bulk check operations
Create a feature for users to operate on checks in batches. Will be implemented as an endpoint:

```
POST /api/v3/checks/bulk/
```

that accepts a list of check ids and actions (pause, delete, resume).

This is the easiest task that should only touch `views.py`, `urls.py`, and `models.py`.
- Add a `bulk_check` function to views
- Add a new endpoint to urls and connect to the `bulk_check` function
- Ensure that the bulk resume gives precendence to `manual_resume` flag for checks
- Add a new field `last_bulk_action` to `Check` in models so there's a mini "log" on bulk ops
    - Edit the db migration for the new field

There's some cross file alignment needed here in that the view must set `last_bulk_action` on each check after acting on it, `to_dict()` also needs to the incldue the new field. These force the agent to read and edit `models.py` before writing the actual logic of bulk operations (in `views.py`).

Hard specs:
- View function name: `bulk_checks`
- Endpoint response shapes per action:
    - pause: {"paused": int}
    - resume: {"resumed": int, "skipped": int}
    - deleted: {"deleted": int}
    - skip when `manual_resume=True`
- Action names: `pause`, `resume`, `delete`
- `last_bulk_action` field: CharField, max_length=10, null=True, blank=True (null before any bulk action)
- Error responses:
    - `400`: missing or empty `codes` list
    - `400`: `codes` is not a list
    - `400`: missing or invalid `action` (not one of pause/resume/delete)
    - `403`: any code belongs to a different project
    - `404`: any code does not exist
- follow existing codebase patterns for decorators


2. Ping statistics

Create a read only endpoint:
```
GET /api/v3/checks/<uuid>/stats/
```

that queries the existing `Ping` table in the sqlite db and returns a formatted table of statistics for each ping in a given check.

This task should touch:
- `models.py` for a `ping_stats` method to the Check that queries and aggregates ping data
    - Also create a new field for `ping_success_rate` in the `Check.to_dict` method by querying the `Ping` table, this stat will be returned in the ping stats response along with existing API responses
    - This requires the agent to read the existing `Check` model, `to_dict` method, and `Ping` before writing anything.
- `views.py` for a new `check_stats` view that calls the ping stats method in a given check and returns the result
- `urls.py` for the new route under checks

Hard specs:
- Method name on `Check`: `ping_stats`
- View function name: `check_stats`
- Response format:
    - `total`: total ping count
    - `success`: pings with a `kind` of `null` (this means successful ping with no issues)
    - `fail`: pings where `kind=fail`
    - `start`: pings where `kind=start`
    - `ping_success_rate`: float (0-1), `null` if no pings
    - `avg_duration_seconds`: float, `null` if no duration data
    - `daily`: newest first, capped at 30 entries, include days with zero pings

- Response shape example:
```json
{
    "total": 150,
    "success": 120,
    "fail": 20,
    "start": 10,
    "ping_success_rate": 0.85,
    "avg_duration_seconds": 45.3,
    "daily": [
        {"date": "2026-02-24", "total": 5, "success": 4, "fail": 1},
        {"date": "2026-02-23", "total": 0, "success": 0, "fail": 0}
    ]
}
```
- Error responses:
    - `401`: wrong or missing API key
    - `403`: check belongs to a different project
    - `404`: check does not exist
- Follow existing codebase patterns for decorator convention

3. Maintenance windows

Create a new `MaintenanceWindow` model that links to a specific `Check` with start, end, and reason fields. Each should be identified uniquely using uuids.

Files to touch:
- `models.py`: Modify the `get_status` method in the `Check` model to returns status of "maintenance" rather than "down" while in a maintenance window.
    - Also add a `maintenance_count` field to the `Check.to_dict` method to count how many maintenance windows is on a check, active or not
    - past windows are not auto deleted, they are manually deleted and serve as logs for past maintenance windows
- `urls.py`: Create three new endpoints to manage maintenance windows: create, list, delete.
- `views.py`: three new view functions to manage maintenance windows, matches each new endpoint: create, list, 

Hard specs:
- Model name: `MaintenanceWindow`
- Model return method: `to_dict()` with field name validation of the field names below.
- Field names and types of the model:
    - `code`: UUID
    - `owner` ForeignKey to `Check`
    - `start`: DateTimeField
    - `end`: DateTimeField
    - `reason`: CharField(max_length=200, blank=True, default="")
- Foreign Key related name: `maintenance_windows` for the count
- Sort the listed maintenance windows by soonest first
- URL paths:
    - `GET /api/v3/checks/<uuid:code>/maintenance/` for list
    - `POST /api/v3/checks/<uuid:code>/maintenance/` for create
    - `DELETE /api/v3/checks/<uuid:code>/maintenance/<uuid:window_code>/` for delete (second uuid is maintenance uuid)
- Change `get_status` to check for an active maintenance window (start <= now < end)
- View function names:
    - `check_maintenance`: handles both GET (list) and POST (create) on the /maintenance/ endpoint
    - `delete_maintenance_window`: handle DELETE maintenance windows
- Error responses:
    - `400`: missing `start` or `end`
    - `400`: `end` is not after `start`
    - `400`: invalid datetime format for `start` or `end`
    - `401`: wrong or missing API key
    - `403`: check belongs to a different project
    - `404`: check does not exist
    - `404`: window does not exist (delete)
- Migration: generate with `python manage.py makemigrations api`