TransPulse - The Pulse of Public Transportation

TransPulse is a complete mobility platform designed to modernize public transit operations. It delivers real-time bus tracking, interactive route mapping, and instant ETA updates. The platform connects passengers, drivers, and administrators through dedicated dashboards to ensure a highly reliable daily commute.

Core Features

Live Fleet Tracking: Real-time GPS mapping of active buses on their routes.
Find My Bus: Search for buses by source and destination, complete with automatic stop suggestions and ETA calculations.
SOS Emergency System: A direct distress signal button for passengers and drivers that instantly notifies administrators with live GPS coordinates.
Lost & Found Recovery: A dedicated portal for passengers to report missing items, and for drivers/admins to manage and update ticket statuses with quick replies.
Service Complaints: Allow passengers to report route delays or vehicle issues directly to depot managers.

Tech Stack

Backend: Python 3, Flask, SQLAlchemy, Flask-Login
Database: PostgreSQL for Production and SQLite for Local Development
Frontend: HTML5, CSS3, Vanilla JavaScript, Bootstrap 5
Mapping: Leaflet.js
Deployment: Pre-configured for Render via render.yaml

Setup Instructions

1. Local Development
First, clone the repository. Create a virtual environment and install dependencies. Initialize the database using the provided python scripts to setup the database and import sample route data. Finally, run the application using the flask run command. The app will automatically use a local SQLite database.

2. Production Deployment
Push this repository to GitHub and connect it to your Render account. The included render.yaml file will automatically configure the Python web service and attach a PostgreSQL database.

System Architecture

TransPulse uses a role-based access system:
1. Passengers: Access live tracking, favorite routes, and submit support tickets.
2. Drivers: View assigned trip schedules, trigger en-route SOS alerts, and process lost/found items.
3. Administrators: Monitor the entire fleet on a master grid, resolve passenger complaints, and manage vehicle assignments.
