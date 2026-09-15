# TransPulse Quick Reference Guide

Getting Started

Start the Application

Visit: http://localhost:5000

Test Accounts
| Role | Email | Password |
|------|-------|----------|
| Admin | admin@transpulse.com | Admin@123 |
| Driver | driver1@transpulse.com | Driver@123 |
| Passenger | passenger1@transpulse.com | Passenger@123 |

---

Key Routes

Palasa Hub Routes (Mandatory)
1. PAL-VIS: Palasa → Visakhapatnam (156 km)
2. PAL-VIJ: Palasa → Vijayawada (428 km)
3. PAL-TIR: Palasa → Tirupati (548 km)
4. PAL-RAJ: Palasa → Rajahmundry (238 km)

Regional Routes
1. North, Coastal, Central, South Coastal routes

---

PWA Installation

Android (Chrome)
1. Open TransPulse in Chrome
2. Tap the address bar
3. Tap "Install" button
4. Confirm installation
5. App appears on home screen

iOS (Safari)
1. Open TransPulse in Safari
2. Tap Share button
3. Tap "Add to Home Screen"
4. Name the app
5. Tap "Add"

---

Feature Locations

Admin Dashboard
1. URL: `/dashboard/admin`
2. Shows: Fleet KPIs, active buses, route stats
3. Actions: Manage buses, routes, notifications

Driver Dashboard
1. URL: `/dashboard/driver`
2. Shows: Assigned bus, route, trip progress
3. Actions: Start/end trips, update status

Passenger Dashboard
1. URL: `/dashboard/passenger`
2. Shows: Live map, routes, ETAs
3. Actions: Search routes, track buses

Admin Bus Management
1. URL: `/admin/buses`
2. Shows: All buses, assignments
3. Actions: Add, edit, delete buses

Admin Route Management
1. URL: `/admin/routes`
2. Shows: All routes
3. Actions: Add, edit, delete routes

Analytics Dashboard
1. URL: `/dashboard/analytics`
2. Shows: Statistics, charts, insights
3. Actions: View performance data

Notifications Center
1. URL: `/notifications`
2. Shows: Recent notifications
3. Actions: View, send (admin only)

---

Configuration

Customize Center Map
Edit `app.py`:

Customize Colors
Edit `static/css/style.css`:

Add Routes
Edit `app.py` ROUTE_GEOMETRY:

---

File Structure

---

Common Tasks

Add a New Bus
1. Go to Admin Dashboard → Bus Management
2. Click "Add Bus"
3. Enter bus number (e.g., BUS-111)
4. Enter registration number
5. Enter capacity
6. Select driver
7. Click "Add"

Add a New Route
1. Go to Admin Dashboard → Route Management
2. Click "Add Route"
3. Enter route code (e.g., NEW-01)
4. Enter route name
5. Enter origin and destination
6. Enter distance
7. Click "Add"

Create a Trip
1. Admin creates route and assigns bus
2. Driver gets assignment
3. Driver starts trip in dashboard
4. Bus appears on live map
5. Passengers can track in real-time

Send Notification
1. Go to Notifications Center
2. Click "Create Notification"
3. Enter message
4. Select target (drivers, passengers, all)
5. Click "Send"

---

Dashboard Metrics

Admin Dashboard Shows
1. Total buses
2. Total routes
3. Total drivers
4. Total passengers
5. Active buses
6. Active routes
7. Active trips
8. Average feedback rating

Analytics Dashboard Shows
1. User breakdown by role
2. Trip status distribution
3. Routes and trip counts
4. Performance charts

Driver Dashboard Shows
1. Assigned bus
2. Current route
3. Trip status
4. Trip progress
5. Next stop info
6. Recent notifications

Passenger Dashboard Shows
1. Live bus tracking map
2. Route search
3. Bus search
4. ETA predictions
5. Live route list

---

Customization Tips

Change Theme
Edit root CSS variables in `style.css`

Modify Landing Page
Edit `templates/index.html`

Add Custom Routes
Update ROUTE_GEOMETRY in `app.py`

Change Map Center
Update SOUTH_INDIA_CENTER in `app.py`

Customize PWA
Edit `static/manifest.json`

---

Security

Change Secret Key
Edit `config.py`:

Change Database
Edit `config.py`:

Enable HTTPS
Set in production:

---

Performance Tips

1. Cache API Responses: Service Worker auto-caches
2. Optimize Images: Use SVG for icons
3. Minimize CSS: Production minification
4. Use CDNs: Bootstrap, Leaflet via CDN
5. Monitor Performance: Check DevTools

---

Troubleshooting

Map Not Loading
1. Check Leaflet CDN is accessible
2. Verify map container element exists
3. Check browser console for errors

Routes Not Showing
1. Verify ROUTE_GEOMETRY is populated
2. Check route codes match in database
3. Inspect API response `/api/routes/live`

PWA Not Installing
1. Use HTTPS in production
2. Check manifest.json syntax
3. Verify service-worker.js registers
4. Check browser requirements (Chrome 42+)

Buses Not Appearing
1. Check database has active trips
2. Verify bus simulation is running
3. Check trip status is "in_progress"
4. Inspect API response `/api/buses/live`

Offline Not Working
1. Check service worker registered
2. Verify assets cached (DevTools → Application)
3. Check offline.html exists
4. Test on actual offline (dev tools)

---

Documentation Files

| File | Purpose |
|------|---------|
| README.md | Features & quick start |
| UPGRADES.md | Detailed changelog |
| IMPLEMENTATION_SUMMARY.md | Technical details |
| This file | Quick reference |
| Code comments | Implementation details |

---

Key Endpoints

---

New Features

1. Palasa as mandatory routing hub
2. 95 strategic routes (from 10)
3. PWA mobile app capability
4. Offline route viewing
5. Service Worker caching
6. Enhanced animations
7. Glassmorphic UI
8. Bottom navigation (mobile)
9. Counter animations
10. Status indicators
11. Premium styling
12. Better documentation

---

For more details, see README.md, UPGRADES.md, and IMPLEMENTATION_SUMMARY.md

Last Updated: June 3, 2026
<!-- TP-v2.0-Release -->
