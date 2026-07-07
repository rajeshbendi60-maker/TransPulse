# Database Audit

## Verified

- Foreign keys, relationships, nullable fields, unique constraints, indexes, cascades, and defaults across all models.

## Fixes Applied

- Added `uq_subscription_user_stop` to prevent duplicate subscriptions.
- Added notification polling index: `recipient_id`, `is_read`, `created_at`.
- Added SOS indexes for status/time and bus/status filtering.
- Added road geometry cache indexes for route/shape and status/update filtering.
- Startup schema safety now creates these indexes for existing SQLite databases and deduplicates subscriptions first.

## Notes

- Schema changes were intentionally narrow.
- Full migration scripts should be generated before production deployment if using Flask-Migrate/Alembic rather than startup schema patching.
