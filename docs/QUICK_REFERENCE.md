# TransPulse Quick Reference Guide

## 🚀 Getting Started

### Start the Application
```bash
python app.py
```
Visit: http://localhost:5000

### Test Accounts
| Role | Email | Password |
|------|-------|----------|
| Admin | admin@transpulse.com | Admin@123 |
| Driver | driver1@transpulse.com | Driver@123 |
| Passenger | passenger1@transpulse.com | Passenger@123 |

---

## 📍 Key Routes (Andhra Pradesh Network)

### Palasa Hub Routes (Mandatory)
- **PAL-VIS**: Palasa → Visakhapatnam (156 km)
- **PAL-VIJ**: Palasa → Vijayawada (428 km)
- **PAL-TIR**: Palasa → Tirupati (548 km)
- **PAL-RAJ**: Palasa → Rajahmundry (238 km)

### Regional Routes
- North Andhra, Coastal, Central, South Coastal routes
---

## 📱 PWA Installation

### Android (Chrome)
1. Open TransPulse in Chrome
2. Tap the address bar
3. Tap "Install" button
4. Confirm installation
5. App appears on home screen

### iOS (Safari)
1. Open TransPulse in Safari
2. Tap Share button
3. Tap "Add to Home Screen"
4. Name the app
5. Tap "Add"

---

## 🎯 Feature Locations

### Admin Dashboard
- **URL**: `/dashboard/admin`
- **Shows**: Fleet KPIs, active buses, route stats
- **Actions**: Manage buses, routes, notifications

### Driver Dashboard
- **URL**: `/dashboard/driver`
- **Shows**: Assigned bus, route, trip progress
- **Actions**: Start/end trips, update status

### Passenger Dashboard
- **URL**: `/dashboard/passenger`
- **Shows**: Live map, routes, ETAs
- **Actions**: Search routes, track buses

### Admin Bus Management
- **URL**: `/admin/buses`
- **Shows**: All buses, assignments
- **Actions**: Add, edit, delete buses

### Admin Route Management
- **URL**: `/admin/routes`
- **Shows**: All routes
- **Actions**: Add, edit, delete routes

### Analytics Dashboard
- **URL**: `/dashboard/analytics`
- **Shows**: Statistics, charts, insights
- **Actions**: View performance data

### Notifications Center
- **URL**: `/notifications`
- **Shows**: Recent notifications
- **Actions**: View, send (admin only)

---

## 🛠️ Configuration

### Customize Center Map
Edit `app.py`:
```python
AP_DEFAULT_CENTER = {"lat": 15.9129, "lng": 79.7400}
```

### Customize Colors
Edit `static/css/style.css`:
```css
--tp-accent: #34d2ff;        /* Primary color */
--tp-accent-2: #4f8dff;      /* Secondary */
--tp-success: #22d39a;       /* Success */
```

### Add Routes
Edit `app.py` ROUTE_GEOMETRY:
```python
"NEW-ROUTE": [
    {"name": "City1", "lat": 15.123, "lng": 78.456},
    {"name": "City2", "lat": 16.789, "lng": 79.012},
]
```

---

## 💻 File Structure

```
Transpulse/
├── app.py                    # Flask app + routes
├── config.py                 # Configuration
├── requirements.txt          # Dependencies
├── README.md                 # Documentation
├── UPGRADES.md               # Change log
├── IMPLEMENTATION_SUMMARY.md # Implementation details
├── models/
│   ├── bus.py
│   ├── route.py
│   ├── trip.py
│   ├── stop.py
│   ├── user.py
│   ├── notification.py
│   └── feedback.py
├── static/
│   ├── css/
│   │   ├── style.css         # Enhanced styles
│   │   └── dashboard.css     # Dashboard theme
│   ├── js/
│   │   ├── dashboard.js      # Dashboard utilities
│   │   ├── enhanced-utils.js # PWA & animations
│   │   ├── tracking.js       # Map tracking
│   │   ├── analytics.js      # Analytics
│   │   └── notifications.js  # Notifications
│   ├── manifest.json         # PWA manifest
│   └── service-worker.js     # Service Worker
└── templates/
    ├── base.html             # Base template
    ├── index.html            # Landing page
    ├── login.html            # Login page
    ├── register.html         # Register page
    ├── offline.html          # Offline page
    ├── admin_dashboard.html
    ├── driver_dashboard.html
    ├── passenger_dashboard.html
    ├── admin_buses.html
    ├── admin_routes.html
    ├── notifications.html
    └── analytics_dashboard.html
```

---

## 🔧 Common Tasks

### Add a New Bus
1. Go to Admin Dashboard → Bus Management
2. Click "Add Bus"
3. Enter bus number (e.g., APSRTC-111)
4. Enter registration number
5. Enter capacity
6. Select driver
7. Click "Add"

### Add a New Route
1. Go to Admin Dashboard → Route Management
2. Click "Add Route"
3. Enter route code (e.g., NEW-01)
4. Enter route name
5. Enter origin and destination
6. Enter distance
7. Click "Add"

### Create a Trip
1. Admin creates route and assigns bus
2. Driver gets assignment
3. Driver starts trip in dashboard
4. Bus appears on live map
5. Passengers can track in real-time

### Send Notification
1. Go to Notifications Center
2. Click "Create Notification"
3. Enter message
4. Select target (drivers, passengers, all)
5. Click "Send"

---

## 📊 Dashboard Metrics

### Admin Dashboard Shows
- Total buses
- Total routes
- Total drivers
- Total passengers
- Active buses
- Active routes
- Active trips
- Average feedback rating

### Analytics Dashboard Shows
- User breakdown by role
- Trip status distribution
- Routes and trip counts
- Performance charts

### Driver Dashboard Shows
- Assigned bus
- Current route
- Trip status
- Trip progress
- Next stop info
- Recent notifications

### Passenger Dashboard Shows
- Live bus tracking map
- Route search
- Bus search
- ETA predictions
- Live route list

---

## 🎨 Customization Tips

### Change Theme
Edit root CSS variables in `style.css`

### Modify Landing Page
Edit `templates/index.html`

### Add Custom Routes
Update ROUTE_GEOMETRY in `app.py`

### Change Map Center
Update SOUTH_INDIA_CENTER in `app.py`

### Customize PWA
Edit `static/manifest.json`

---

## 🔐 Security

### Change Secret Key
Edit `config.py`:
```python
SECRET_KEY = "your-secret-key-here"
```

### Change Database
Edit `config.py`:
```python
SQLALCHEMY_DATABASE_URI = "sqlite:///your-db.db"
```

### Enable HTTPS
Set in production:
```python
app.run(ssl_context='adhoc')
```

---

## 📈 Performance Tips

1. **Cache API Responses**: Service Worker auto-caches
2. **Optimize Images**: Use SVG for icons
3. **Minimize CSS**: Production minification
4. **Use CDNs**: Bootstrap, Leaflet via CDN
5. **Monitor Performance**: Check DevTools

---

## 🐛 Troubleshooting

### Map Not Loading
- Check Leaflet CDN is accessible
- Verify map container element exists
- Check browser console for errors

### Routes Not Showing
- Verify ROUTE_GEOMETRY is populated
- Check route codes match in database
- Inspect API response `/api/routes/live`

### PWA Not Installing
- Use HTTPS in production
- Check manifest.json syntax
- Verify service-worker.js registers
- Check browser requirements (Chrome 42+)

### Buses Not Appearing
- Check database has active trips
- Verify bus simulation is running
- Check trip status is "in_progress"
- Inspect API response `/api/buses/live`

### Offline Not Working
- Check service worker registered
- Verify assets cached (DevTools → Application)
- Check offline.html exists
- Test on actual offline (dev tools)

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| README.md | Features & quick start |
| UPGRADES.md | Detailed changelog |
| IMPLEMENTATION_SUMMARY.md | Technical details |
| This file | Quick reference |
| Code comments | Implementation details |

---

## 🎯 Key Endpoints

```
GET  /                          Landing page
POST /register                  User registration
POST /login                     User login
POST /logout                    User logout

GET  /dashboard/admin           Admin dashboard
GET  /dashboard/driver          Driver dashboard
GET  /dashboard/passenger       Passenger dashboard

GET  /admin/buses               Bus management
POST /admin/buses               Add bus
GET  /admin/buses/<id>/edit     Edit bus
POST /admin/buses/<id>/edit     Update bus
POST /admin/buses/<id>/delete   Delete bus

GET  /admin/routes              Route management
POST /admin/routes              Add route
GET  /admin/routes/<id>/edit    Edit route
POST /admin/routes/<id>/edit    Update route
POST /admin/routes/<id>/delete  Delete route

GET  /notifications             Notifications center
POST /notifications             Send notification

GET  /dashboard/analytics       Analytics dashboard

GET  /routes/<id>               Route details

GET  /api/buses/live            Live buses JSON
GET  /api/routes/live           Live routes JSON
GET  /api/eta/<bus_id>          Bus ETA JSON
```

---

## ✨ New Features

✅ Palasa as mandatory routing hub
✅ 95 Andhra Pradesh routes (from 10)
✅ PWA mobile app capability
✅ Offline route viewing
✅ Service Worker caching
✅ Enhanced animations
✅ Glassmorphic UI
✅ Bottom navigation (mobile)
✅ Counter animations
✅ Status indicators
✅ Premium styling
✅ Better documentation

---

**For more details, see README.md, UPGRADES.md, and IMPLEMENTATION_SUMMARY.md**

Last Updated: June 3, 2026
