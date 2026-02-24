# Add Bulk Check Operations

The Healthchecks codebase is at `/app/`.

Add the ability to perform bulk actions on multiple checks at once via the REST API, pausing, resuming, or deleting a batch of checks in a single request.

## Requirements

- Add a `last_bulk_action` field (nullable CharField, max 10 characters) to the `Check` model in `/app/hc/api/models.py`
    - Also add the field to `Check.to_dict()`.
    - Generate and run the migration.
- `POST /api/v3/checks/bulk/`: perform a bulk action (write key required). Body takes `codes` (list of check UUIDs) and `action` (one of `pause`, `resume`, `delete`).
    - All checks must be validated to belong to the authenticated project.
    - After acting on each check, set `last_bulk_action` to the action name.
- Bulk resume must respect the existing `manual_resume` flag on each check.
    - Checks with `manual_resume=True` should be skipped, not resumed.
- Response shapes vary by specified action:
  - `pause` → `{"paused": <count>}`
  - `resume` → `{"resumed": <count>, "skipped": <count>}`
  - `delete` → `{"deleted": <count>}`
- Add the URL route for the endpoint.

Don't modify existing tests. Follow existing codebase patterns for decorators, error responses, and authorization.