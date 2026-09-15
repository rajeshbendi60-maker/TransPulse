# Database Audit

Verified

1. Foreign keys, relationships, nullable fields, unique constraints, indexes, cascades, and defaults across all models.

Fixes Applied

1. Added `uq_subscription_user_stop` to prevent duplicate subscriptions.
2. Added notification polling index: `recipient_id`, `is_read`, `created_at`.
3. Added SOS indexes for status/time and bus/status filtering.
4. Added road geometry cache indexes for route/shape and status/update filtering.
5. Startup schema safety now creates these indexes for existing SQLite databases and deduplicates subscriptions first.

Notes

1. Schema changes were intentionally narrow.
2. Full migration scripts should be generated before production deployment if using Flask-Migrate/Alembic rather than startup schema patching.
<!-- TP-v2.0-Release -->
