# Optional migrations

Migrations in this directory are **not** part of the default `alembic upgrade
head` chain. They enable opt-in features that require additional application
configuration, so they must be applied deliberately.

## `004_add_rls.py` — PostgreSQL Row-Level Security

Enables and `FORCE`s RLS on the tenant tables and installs policies keyed on
`current_setting('app.current_user_id')`, plus a `set_tenant_context(uuid)`
helper.

**Do not apply this blindly.** Once RLS is forced, every query returns zero
rows until the session sets its tenant context — so the application must call
`set_config('app.current_user_id', <uuid>, false)` (or the provided
`set_tenant_context` function) at the start of each request. Enabling it also
requires `ENABLE_RLS=true` in settings.

To apply manually against your database:

```bash
psql "$DATABASE_URL" -f alembic/optional/004_add_rls.py   # after adapting to SQL, or
# wire it into the chain yourself once the request-time tenant context is in place
```

Until the request-time tenant-context plumbing lands, application-level tenant
isolation is provided by `enforce_tenant()` (see `app/core/auth.py`), which
binds an API key to its owner.
