# Testing Guide

Static checks:

1. Compile Python files with `python -m py_compile`.
2. Search for hardcoded secrets and heatmap labels.
3. Search route declarations for duplicates.

Manual smoke tests:

1. Register passenger and log in.
2. Log in as admin and load dashboard, fleet, heatmap, analytics, complaints, SOS.
3. Log in as driver with assigned driver code.
4. Start trip, post location, update occupancy, report delay, end trip.
5. Open passenger dashboard, live tracking, complaints, lost and found, notifications, SOS.
6. Run `flask import-gtfs` against the GTFS feed.

Expected results:

1. No Flask stack traces.
2. JSON APIs return JSON errors with status codes.
3. CSRF-protected forms and AJAX requests succeed with the injected token.
4. Leaflet maps render markers, stops, and polylines.

Automated Checks Run

1. Python syntax compilation passed for backend and model files.
2. Targeted scans confirmed duplicate standard `confirmSOS()` was removed.
3. Targeted scans confirmed stale `updateEl()` references were removed.

Blocked Checks

1. Runtime checks could not be completed inside Codex because this execution environment does not have the project dependencies installed.
2. The user confirmed `python app.py` runs correctly in the local environment, GTFS initializes, and database integrity checks pass.
3. Dependency installation attempts inside Codex are an environment limitation, not a project issue.

Recommended Test Matrix

1. Unit tests for Google token rejection paths using mocked verifier responses.
2. API tests for `400`, `401`, `403`, `404`, `409`, and `500` behavior.
3. Driver trip lifecycle tests.
4. Passenger tracking session and SOS tests.
5. Complaint and Lost & Found lifecycle tests.
6. GTFS importer rollback test with malformed rows.
7. Browser smoke tests for admin, driver, passenger, and mobile layouts.
<!-- TP-v2.0-Release -->
