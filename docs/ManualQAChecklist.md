# Manual Browser QA Checklist

Run this checklist after dependency installation and migrations are complete in the real local or production-like environment.

- Home: landing page loads, nav links work, static assets render.
- Login: passenger, driver, and admin local login flows work; invalid credentials fail safely.
- Register: passenger registration validates email/password and creates a passenger account.
- Google Login/Register: valid Google account succeeds; invalid/tampered tokens are rejected.
- Forgot Password: valid passenger email shows generic success and sends reset email when SMTP is configured.
- Reset Password: valid token resets password; expired/invalid/used tokens are rejected.
- Admin Dashboard: fleet metrics, cards, live fleet, command center, and admin links load.
- Driver Dashboard: assigned bus appears, start/end trip works, GPS post works, occupancy and delay actions work.
- Passenger Dashboard: routes, live fleet, search, route modal, and tracking links work.
- Tracking: live bus, offline bus, and recently completed trip views render without console errors.
- Heatmap: page and `/heatmap/data` load for authorized users.
- Analytics: dashboard loads charts/metrics.
- Notifications: list, unread count, mark-read, and admin broadcast work.
- Complaints: passenger/driver create, admin reply/close, edit/archive history views work.
- SOS: passenger trigger, driver acknowledge, admin resolve, and status polling work.
- Lost & Found: passenger create/edit/archive, driver/admin reply, returned status, and notifications work.
- Route Management: create/edit manual routes and duplicate route-code validation work.
- Bus Management: create/edit/delete buses, route assignment, driver-code uniqueness, and active/offline views work.
- Occupancy: driver updates and passenger/admin live occupancy API render correctly.
- Offline Mode: service worker/offline page works after install.
- PWA: manifest, icons, install prompt, and app display mode work.
