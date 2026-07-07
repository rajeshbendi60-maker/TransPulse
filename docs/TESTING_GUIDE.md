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
