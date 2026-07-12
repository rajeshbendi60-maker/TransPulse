# Testing Guide

Static checks:

- Compile Python files with `python -m py_compile`.
- Search for hardcoded secrets and non-APSRTC heatmap labels.
- Search route declarations for duplicates.

Manual smoke tests:

- Register passenger and log in.
- Log in as admin and load dashboard, fleet, heatmap, analytics, complaints, SOS.
- Log in as driver with assigned driver code.
- Start trip, post location, update occupancy, report delay, end trip.
- Open passenger dashboard, live tracking, complaints, lost and found, notifications, SOS.
- Run `flask import-gtfs` against the GTFS feed.

Expected results:

- No Flask stack traces.
- JSON APIs return JSON errors with status codes.
- CSRF-protected forms and AJAX requests succeed with the injected token.
- Leaflet maps render markers, stops, and polylines.


<!-- Merged from Testing.md -->

# Testing

## Automated Checks Run

- Python syntax compilation passed for backend and model files.
- Targeted scans confirmed duplicate standard `confirmSOS()` was removed.
- Targeted scans confirmed stale `updateEl()` references were removed.

## Blocked Checks

- Runtime checks could not be completed inside Codex because this execution environment does not have the project dependencies installed.
- The user confirmed `python app.py` runs correctly in the local environment, GTFS initializes, and database integrity checks pass.
- Dependency installation attempts inside Codex are an environment limitation, not a project issue.

## Recommended Test Matrix

- Unit tests for Google token rejection paths using mocked verifier responses.
- API tests for `400`, `401`, `403`, `404`, `409`, and `500` behavior.
- Driver trip lifecycle tests.
- Passenger tracking session and SOS tests.
- Complaint and Lost & Found lifecycle tests.
- GTFS importer rollback test with malformed rows.
- Browser smoke tests for admin, driver, passenger, and mobile layouts.
