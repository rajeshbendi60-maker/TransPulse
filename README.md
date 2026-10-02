TransPulse - Real-Time Public Transit Platform

TransPulse is a comprehensive mobility platform designed to modernize public transit operations. It delivers real-time bus tracking, interactive route mapping, and instant ETA updates. The platform connects passengers, drivers, and administrators through dedicated, role-based dashboards to ensure a highly reliable daily commute.

---

## Core Features Built

The following features are fully implemented and operational within the system:

1. Live Fleet Tracking & Telemetry
   - Real-time GPS mapping of active buses on their designated routes.
   - Dynamic ETA calculations based on live speed, current stop index, and traffic delays.

2. Role-Based Dashboards
   - Passenger Portal: Search for buses, view live routes, save favorite stops, and track incoming vehicles.
   - Driver Operations: Manage trip status (Start/End/Return), update passenger occupancy, and report physical delays.
   - Admin Control Center: High-level overview of the entire fleet, driver assignments, and system metrics.

3. Emergency & Support Systems
   - SOS Emergency Protocol: A direct distress signal button for drivers and passengers that instantly notifies administrators with live coordinates.
   - Lost & Found Recovery: A dedicated portal to report, track, and resolve missing items found on transit vehicles.
   - Service Complaints: Passengers can report route delays or vehicle issues directly to depot managers.

---

## Technology Stack

- Backend: Python 3, Flask, SQLAlchemy (ORM)
- Database: SQLite (Local Development) / PostgreSQL (Production)
- Frontend: HTML5, CSS3, Vanilla JavaScript, Bootstrap 5
- Mapping: Leaflet.js with OpenStreetMap integration
- Deployment: Gunicorn WSGI, ready for PaaS deployment (Railway/Render)

---

## Deployment & Setup Instructions

### 1. Local Development
Clone the repository and install the dependencies:
```bash
pip install -r requirements.txt
```
Initialize the database and run the development server:
```bash
python run.py
```
The application will be available at http://127.0.0.1:5000.

### 2. Production Deployment (Railway / Cloud)
This application is configured for seamless deployment on cloud platforms. 
For production environments, ensure you use a multi-threaded WSGI server to handle the live GPS polling.

Set your Custom Start Command to:
```bash
gunicorn app:app --workers 4 --threads 2
```
Ensure you mount a persistent volume to your `/instance` directory if using SQLite in production, or attach a PostgreSQL database and provide the connection URI in your environment variables.
