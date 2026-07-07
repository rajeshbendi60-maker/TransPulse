# API Reference

All state-changing APIs are protected by Flask-WTF CSRF. The base template injects the token into forms and same-origin `fetch()` requests.

Authentication:

- `POST /login`
- `POST /logout`
- `POST /google_login`
- `POST /google_register`
- `GET|POST /forgot-password`
- `GET|POST /reset-password/<token>`

Fleet and tracking:

- `GET /api/buses/live`
- `GET /api/buses/offline`
- `GET /api/routes/live`
- `GET /api/map/center`
- `GET /api/tracking/completed/<bus_identifier>`
- `POST /api/tracking/session`

Driver:

- `POST /api/driver/start-trip`
- `POST /api/driver/end-trip`
- `POST /api/driver/location`
- `POST /api/driver/update-occupancy`
- `POST /api/driver/report-delay`
- `POST /api/buses/delay`
- `GET /api/driver/analytics`

Operations:

- `GET|POST /api/complaints`
- `POST /api/complaints/<id>/reply`
- `GET|POST /api/lost-and-found`
- `POST /api/lost-and-found/<id>/reply`
- `POST /api/lost-and-found/<id>/return`
- `GET|POST /api/notifications`
- `GET /api/notifications/unread`
- `POST /api/notifications/<id>/read`

SOS:

- `POST /api/sos/trigger`
- `GET /api/sos/<id>/status`
- `GET /api/admin/sos`
- `POST /api/admin/sos/<id>/status`
- `POST /api/sos/driver/acknowledge/<id>`
- `POST /api/sos/resolve/<id>`

Admin analytics:

- `GET /api/command-center/stats`
- `GET /api/admin/data-integrity`
- `GET /heatmap/data`

API errors return JSON with an HTTP status code for AJAX/API callers.
