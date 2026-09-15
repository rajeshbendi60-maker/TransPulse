# Code Structure

1. `app.py`: app factory, route registration, auth, dashboards, APIs, GPS, GTFS helpers.
2. `config.py`: environment-driven Flask and database configuration.
3. `models/`: SQLAlchemy models.
4. `templates/`: Jinja HTML pages.
5. `static/js/`: dashboard, tracking, heatmap, SOS, passenger flow, occupancy scripts.
6. `static/css/`: shared dashboard and site styles.
7. `gtfs_data/`: extracted GTFS text files.
8. `docs/`: project, API, security, performance, deployment, and testing documentation.

The project currently keeps routes in one file by design. Shared helper functions should remain in `app.py` unless the architecture rule changes.
<!-- TP-v2.0-Release -->
