# Project Architecture

TransPulse is a single-file Flask application for APSRTC public transport operations. The project intentionally keeps route registration, dashboards, APIs, GPS simulation, notifications, SOS, complaints, lost and found, and GTFS helpers in `app.py`.

```mermaid
flowchart TD
    Browser["Browser: Bootstrap, Leaflet, Chart.js"] --> Flask["Flask app.py"]
    Flask --> Auth["Flask-Login + CSRF"]
    Flask --> DB["SQLAlchemy models"]
    DB --> SQLite["SQLite/PostgreSQL via DATABASE_URL"]
    Flask --> GPS["LIVE_GPS_DATA + trip simulation"]
    Flask --> GTFS["GTFS importer"]
    GTFS --> DB
    Flask --> Mail["SMTP password reset"]
```

Key modules:

- `app.py`: routes, APIs, app factory, dashboards, GPS engine, notifications.
- `models/`: SQLAlchemy models and relationships.
- `import_apsrtc_data.py`: batched GTFS ingestion.
- `templates/`: Bootstrap/Jinja dashboards and pages.
- `static/js/`: Leaflet tracking, heatmap, dashboard polling, SOS handling.
- `static/css/`: shared visual styling.

Architecture rule: do not split `app.py` or convert routes to Blueprints unless the project owner explicitly changes that constraint.
