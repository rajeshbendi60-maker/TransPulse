# Code Structure

- `app.py`: app factory, route registration, auth, dashboards, APIs, GPS, GTFS helpers.
- `config.py`: environment-driven Flask and database configuration.
- `models/`: SQLAlchemy models.
- `templates/`: Jinja HTML pages.
- `static/js/`: dashboard, tracking, heatmap, SOS, passenger flow, occupancy scripts.
- `static/css/`: shared dashboard and site styles.
- `gtfs_data/`: extracted GTFS text files.
- `docs/`: project, API, security, performance, deployment, and testing documentation.

The project currently keeps routes in one file by design. Shared helper functions should remain in `app.py` unless the architecture rule changes.
