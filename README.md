# TransPulse
**"The Pulse of Public Transportation"**

---

## Project Overview
TransPulse is an AI-powered smart public transportation management system designed to seamlessly orchestrate the lifecycle of public transit. By unifying administrators, drivers, and passengers onto a single cohesive platform, TransPulse modernizes fleet management, enhances operational efficiency, and elevates the commuter experience through real-time telemetry and data-driven insights.

## Problem Statement
Traditional public transit systems suffer from opaque scheduling, unreliable ETAs, lack of dynamic occupancy tracking, and fragmented communication between drivers, fleet managers, and passengers. This leads to frustrated commuters and inefficient fleet utilization.

## Motivation
To build a state-of-the-art transit architecture that bridges the gap between raw GTFS static schedules and dynamic, real-world execution, ensuring every stakeholder has the right information at the exact right moment.

## Objectives
- Deliver accurate, real-time bus tracking and ETA predictions.
- Provide a robust administrative suite for fleet and personnel management.
- Empower drivers with an intuitive interface for route navigation and status reporting.
- Enhance passenger confidence with live occupancy metrics and delay notifications.

## Key Features
- **Real-Time Tracking Engine:** Sub-second GPS telemetry via HTML5 Geolocation and Leaflet.
- **Dynamic GTFS Parsing:** Automated ingestion and mapping of static transit data into actionable live routes.
- **Intelligent Dashboards:** Tailored interfaces for Admins, Drivers, and Passengers.
- **Occupancy & Delay Management:** Live reporting and automated timeline adjustments.
- **Incident Management:** Integrated SOS alerts, Complaints, and Lost & Found systems.

## System Architecture
```
Passenger Dashboard
        ↓
   Tracking API
        ↓
   Flask Backend
        ↓
    GTFS Engine
        ↓
    SQLAlchemy
        ↓
 SQLite/PostgreSQL
        ↓
   Driver GPS
        ↓
   Leaflet Map
```

## Technology Stack
- **Backend:** Python 3.10, Flask, Flask-SQLAlchemy, Flask-Login, Flask-Migrate
- **Database:** SQLite (Development) / PostgreSQL (Production)
- **Frontend:** HTML5, CSS3, Vanilla JavaScript, Bootstrap 5
- **Mapping:** Leaflet.js, OpenStreetMap
- **Deployment:** Gunicorn, Render

## Folder Structure
- `app.py`: Core application entrypoint and route definitions.
- `config.py`: Environment and application configuration.
- `models/`: SQLAlchemy database models.
- `templates/`: Jinja2 HTML templates.
- `static/`: CSS, JS, and image assets.
- `instance/`: Local database storage.
- `gtfs_data/`: Directory for GTFS static files.
- `migrations/`: Alembic database migration scripts.
- `requirements.txt`: Python package dependencies.
- `render.yaml`: Render deployment specification.

## Installation Guide
1. **Clone the repository:** `git clone https://github.com/yourusername/transpulse.git`
2. **Navigate to the directory:** `cd transpulse`
3. **Create a virtual environment:** `python -m venv venv`
4. **Activate the environment:** `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
5. **Install dependencies:** `pip install -r requirements.txt`

## Configuration & Environment Variables
Create a `.env` file or export the following:
- `SECRET_KEY`: Cryptographic key for session security.
- `FLASK_ENV`: Set to `production` or `development`.
- `DATABASE_URL`: Connection string (defaults to local SQLite).
- `MAIL_USERNAME` / `MAIL_PASSWORD`: Credentials for email notifications.

## Running Locally
1. **Initialize Database:** `flask db upgrade`
2. **Import GTFS Data:** `flask import-gtfs`
3. **Start Server:** `python app.py` (Development) or `gunicorn app:app` (Production)
4. **Access the App:** Open `http://localhost:5000`

## Admin, Driver, and Passenger Workflows
Please see the respective guides:
- [Admin Guide](ADMIN_GUIDE.md)
- [Driver Guide](DRIVER_GUIDE.md)
- [Passenger Guide](PASSENGER_GUIDE.md)

## Deployment Guide
Please see the [Deployment Guide](DEPLOYMENT.md) for Render instructions.

## Security Features
- **Role-Based Access Control (RBAC):** Strict isolation between Admin, Driver, and Passenger endpoints.
- **Secure Sessions:** HTTPOnly and SameSite configured session cookies.
- **Environment Isolation:** Sensitive keys and database URIs excluded from source control.
- **Data Validation:** Strict payload validation and SQL injection prevention via SQLAlchemy ORM.

## Screenshots
*(Placeholder for UI Screenshots)*

## Known Limitations
- Relying on mobile device GPS can introduce coordinate drift in dense urban environments (urban canyons).
- OSRM route snapping requires active internet connectivity on the backend.
- GTFS static files must be strictly formatted per the GTFS specification.

## Future Enhancements
- Push Notifications (FCM / Web Push)
- Native Mobile Applications (iOS / Android)
- Multi-State GTFS Integration
- AI-Powered ETA Prediction Models
- Machine Learning Occupancy Forecasting
- Driver Behaviour Analytics

## Contributors
- Rajesh (Lead Software Engineer)

## License
MIT License
