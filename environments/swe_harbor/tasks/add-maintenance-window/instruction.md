# Add Maintenance Windows

The Healthchecks codebase is at `/app/`.

Add the ability to schedule maintenance windows on individual checks. While a maintenance window is active, the check should report a maintenance status instead of down. Past windows are kept as a record and must be deleted explicitly, no pruning logic needed.

## Requirements

- Create a `MaintenanceWindow` model in `/app/hc/api/models.py` with the following fields:
    - `code`: UUID, auto-generated, unique, non-editable.
    - `owner`: ForeignKey to `Check`. Use "maintenance_windows" as the related name. Cascade on delete.
    - `start`: DateTimeField (timezone-aware).
    - `end`: DateTimeField (timezone-aware).
    - `reason`: CharField, max 200 characters, blanks allowed, default is empty string.
    - Add a `to_dict()` method that returns all five fields. Serialize `owner` as the check's UUID string.
    - Sort windows of a check by `start` datetime ascending (soonest first).
- Add a `maintenance_count` field to `Check.to_dict()` that returns the total number of maintenance windows associated with the check (active or not).
- Modify `Check.get_status()` to return `"maintenance"` in place of `"down"` when an active window exists (`start <= now < end`).
    - Only modify in place of `"down"`.
- Generate and run the migration for `MaintenanceWindow`.
- `GET /api/v3/checks/<uuid:code>/maintenance/`: list all maintenance windows for a check (read key accepted). Returns `{"windows": [<to_dict>, ...]}`.
- `POST /api/v3/checks/<uuid:code>/maintenance/`: create a new maintenance window (write key required). Body fields: `start`, `end`, `reason`.
    - Both `start` and `end` are required, return error if either is missing.
    - `end` must be after `start`, return appropriate error if not.
    - Raise error for unparseable datetime strings.
    - On success return the created window's `to_dict()` with a success status.
- `DELETE /api/v3/checks/<uuid:code>/maintenance/<uuid:window_code>/`: delete a specific maintenance window (write key required).
    - Return error if the window does not exist.
- Handle both GET and POST in a single view function named `check_maintenance`.
- Handle DELETE in a separate view function named `delete_maintenance_window`.
- Add all three URL routes.

Don't modify existing tests. Follow existing codebase patterns for decorators, **error responses**, return statuses, and authorization.
