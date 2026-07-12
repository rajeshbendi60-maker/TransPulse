# TransPulse System Architecture

This document describes the high-level system overview, module interactions, request flows, and telemetry processing systems for TransPulse.

---

## 1. System Overview

TransPulse is a live transit tracking system built to synchronize GTFS schedule data with real-time driver GPS coordinates. The application acts as a bridge between transit operations (drivers) and the public (passengers/admins).

```mermaid
graph TD
    subgraph Clients
        DriverClient[Driver Dashboard Mobile]
        PassengerClient[Passenger Dashboard Web]
        AdminClient[Admin Command Center Web]
    end

    subgraph Backend [Flask Application]
        API[REST APIs /api/...]
        GPSEngine[Live Telemetry & GPS Processing Engine]
        RouteManager[GTFS / Route Management System]
        Auth[Authentication & Session Controls]
    end

    subgraph Storage [Database]
        DB[(SQLite / PostgreSQL db.Model)]
    end

    DriverClient -->|GPS Broadcast| GPSEngine
    DriverClient -->|Actions: Start/End Trip| API
    PassengerClient -->|Fetch Live Status| API
    AdminClient -->|Track Fleet / Search| API
    
    API --> Auth
    GPSEngine --> DB
    RouteManager --> DB
    Auth --> DB
```

---

## 2. Module Interaction

- **Driver Module:** Collects live telemetry from driver devices (lat, lon, speed, bearing) via HTTP POST requests and broadcasts status updates.
- **Passenger Module:** Provides a client-oriented route search, interactive stop timeline, and map tracking screens using Leaflet.js.
- **Admin Module:** Aggregates overall system statistics, live fleet card grids, active operational delays, and interactive search portals.
- **Live GPS Engine:** Computes nearest stop coordinates, tracks monotonic trip progress, checks stop radii, and calculates smoothed blended ETAs.
- **GTFS / Import Engine:** Reads stop sequences, shapes, and journey configurations from standard GTFS imports to populate routes and stops.

---

## 3. Data & Request Flows

### A. Driver GPS Telemetry Flow

```mermaid
sequenceDiagram
    autonumber
    actor Driver as Driver Device
    participant API as Telemetry Endpoint (/api/driver/location)
    participant Engine as GPS Engine
    participant Cache as LIVE_GPS_DATA (Memory Cache)
    
    Driver->>API: Broadcast (lat, lon, speed, bearing)
    API->>Engine: Validate Session and Permissions
    Engine->>Engine: Compute Nearest Stop (Haversine)
    Engine->>Engine: Enforce Monotonic Progress (current_stop >= prev_stop)
    Engine->>Engine: Perform configurable radius boundary check
    Engine->>Cache: Save/Update telemetry snapshot
    API-->>Driver: Acknowledgement & current delay status
```

### B. GTFS Route Import Flow

```mermaid
sequenceDiagram
    autonumber
    actor CLI as Import Command
    participant Parser as GTFS Parser
    participant DB as SQLite Database
    
    CLI->>Parser: Run import_apsrtc_data.py
    Parser->>Parser: Parse stops.txt, routes.txt, shapes.txt
    Parser->>DB: Save Stops, Routes, Shapes
    Parser->>Parser: Interpolate stop sequence path coordinates
    Parser->>DB: Save StopTimes and route geometries
```

### C. Blended ETA Calculation Flow

```mermaid
graph TD
    GPS[Live GPS Speed] -->|0.5 weight| SpeedBlend[Blended Velocity Speed]
    Hist[Historical Route Average 35km/h] -->|0.3 weight| SpeedBlend
    Sched[Scheduled Speed route distance / duration] -->|0.2 weight| SpeedBlend

    SpeedBlend --> TravelTime[Travel Time to Destination]
    RemainingDist[Remaining Route Distance] --> TravelTime

    TravelTime -->|0.8 weight| BaseETA[Base ETA minutes]
    SchedRemaining[Scheduled Remaining Duration] -->|0.2 weight| BaseETA

    BaseETA --> FinalETA[Final Smooth ETA Minutes]
    Delay[Current Live Delay Minutes] --> FinalETA
```

### D. Tracking Page Resilient Routing Flow

```mermaid
graph TD
    Start[Load Live Tracking Page] --> Priority1{GTFS Shapes Available?}
    Priority1 -->|Yes| Draw1[Render Route using GTFS Shapes]
    Priority1 -->|No| Priority2{Backend Road Snapping Available?}
    
    Priority2 -->|Yes| Draw2[Render Route using Backend Road Coordinates]
    Priority2 -->|No| Priority3{Client-Side OSRM Reachable?}
    
    Priority3 -->|Yes| Draw3[Fetch snap line from router.project-osrm.org]
    Priority3 -->|No| Draw4[Final Fallback: Draw straight stop-to-stop lines with warning]
```


<!-- Merged from PROJECT_ARCHITECTURE.md -->

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
