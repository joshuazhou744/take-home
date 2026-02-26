# Add Check Dependency Suppression

The Healthchecks codebase is at `/app/`.

Add the ability to declare that one check depends on another. When a check flips to "down" and one of its declared dependencies is also currently "down", all alert notifications for that flip are suppressed — the outage is treated as a downstream effect rather than an independent incident.

## Requirements

- Create a `CheckDependency` model in `/app/hc/api/models.py` with the following fields:
    - `code`: UUID, auto-generated, unique, non-editable.
    - `check`: ForeignKey to `Check`. Use `"dependencies"` as the related name. Cascade on delete.
    - `depends_on`: ForeignKey to `Check`. Use `"dependents"` as the related name. Cascade on delete.
    - `created`: DateTimeField, defaults to `now`.
    - Enforce `unique_together = [("check", "depends_on")]`.
    - Add a `to_dict()` method returning `"uuid"`, `"check"` (the check's UUID string), `"depends_on"` (the dependency's UUID string), and `"created"` (ISO 8601 string via `isostring()`).
- Add a `"dependencies"` key to `Check.to_dict()` that returns a list of UUID strings for all checks this check depends on.
- Patch `Flip.select_channels()` in `/app/hc/api/models.py`: when `new_status == "down"`, iterate over the flip owner's `dependencies` relation; if any dependency's `get_status()` returns `"down"`, return `[]` immediately to suppress all notifications.
- Generate and run the migration for `CheckDependency`.
- `GET /api/v3/checks/<uuid:code>/dependencies/`: list all dependency records for a check (read key accepted). Returns `{"dependencies": [<to_dict>, ...]}`.
- `POST /api/v3/checks/<uuid:code>/dependencies/`: add a new dependency (write key required). Body field: `depends_on` (UUID of the check to depend on).
    - The `depends_on` check must belong to the same project; return 403 otherwise.
    - A check cannot depend on itself; return 400.
    - Duplicate dependencies should return 400.
    - Return 400 for a missing or invalid `depends_on` UUID.
    - On success return the created `CheckDependency.to_dict()` with status 201.
- `DELETE /api/v3/checks/<uuid:code>/dependencies/<uuid:dep_code>/`: remove a dependency by its `code` UUID (write key required). Returns 204 on success, 404 if not found.
- Handle GET and POST in a single view named `check_dependencies`. Handle DELETE in a separate view named `delete_check_dependency`. Add both URL routes.
- Return 403 if the check belongs to a different project than the API key. Return 404 if the check does not exist.

Don't modify existing tests. Follow existing codebase patterns for decorators, error responses, return statuses, and authorization.
