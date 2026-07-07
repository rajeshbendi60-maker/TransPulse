# Known Issues

## Remaining Manual Work

- Codex cannot complete dependency installation/runtime verification in this execution environment.
- The user confirmed the local application starts successfully with `python app.py`, GTFS initializes, and database integrity checks pass.
- Production needs real `SECRET_KEY`, `GOOGLE_CLIENT_ID`, SMTP credentials, and persistent rate-limit storage.
- In-memory GPS/tracking/delay state should be externalized for multi-worker production.
- No Alembic migration files were generated for the new indexes/constraint.
- Full browser QA was not run in this environment.

## Residual Risk

- Some dashboard views still perform repeated helper queries at fleet scale.
- OSRM road geometry generation is synchronous when cache misses occur.
- Existing mojibake text in templates remains cosmetic debt.
