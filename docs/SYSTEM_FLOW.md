# System Flow

```mermaid
sequenceDiagram
    participant Passenger
    participant Driver
    participant Flask
    participant DB
    participant Admin

    Driver->>Flask: Start trip
    Flask->>DB: Create active trip
    Driver->>Flask: Post GPS
    Flask->>Flask: Validate and store live GPS
    Passenger->>Flask: Track bus
    Flask->>Passenger: Live fleet snapshot
    Passenger->>Flask: Trigger SOS
    Flask->>DB: Store SOS alert
    Flask->>Admin: Notification payload
    Admin->>Flask: Resolve SOS
    Flask->>DB: Update status
```

Dashboard flow:

- Admin views fleet, heatmap, analytics, SOS, complaints, and management pages.
- Driver manages assigned bus trip lifecycle, GPS, occupancy, delays, reports, and alerts.
- Passenger searches routes, tracks buses, receives notifications, and submits SOS/complaints/lost-and-found reports.
