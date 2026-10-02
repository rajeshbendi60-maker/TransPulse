# System Architecture

This document outlines the technical architecture of the TransPulse platform.

## 1. High-Level Overview
TransPulse follows a classic Client-Server architecture. The backend is a monolithic Python application serving both traditional server-side rendered HTML and RESTful JSON APIs for real-time dashboard updates.

## 2. Frontend Layer
- Framework: Vanilla JavaScript (ES6) and HTML5.
- Styling: Bootstrap 5 and custom CSS.
- Navigation: Custom hash-based Single Page Application (SPA) router for driver and passenger dashboards to prevent page reloads during active trips.
- Maps: Leaflet.js with OpenStreetMap tiles.

## 3. Backend Layer
- Server: Python 3 with Flask.
- WSGI: Designed to run via Gunicorn in production for multi-threading.
- ORM: SQLAlchemy for database interactions.
- Authentication: Flask-Login with session-based cookies.

## 4. Telemetry Engine
- Driver Broadcasting: The driver's device uses the HTML5 Geolocation API to read coordinates and speed, sending POST requests to the server every few seconds.
- Passenger Polling: Passenger dashboards poll the server via GET requests to retrieve the live coordinates of active buses.
- ETA Calculation: Handled server-side using real-time distance calculations compared to scheduled arrival times.
