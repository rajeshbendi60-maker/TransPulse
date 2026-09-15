# Manual Browser QA Checklist

Run this checklist after dependency installation and migrations are complete in the real local or production-like environment.

1. Home: landing page loads, nav links work, static assets render.
2. Login: passenger, driver, and admin local login flows work; invalid credentials fail safely.
3. Register: passenger registration validates email/password and creates a passenger account.
4. Google Login/Register: valid Google account succeeds; invalid/tampered tokens are rejected.
5. Forgot Password: valid passenger email shows generic success and sends reset email when SMTP is configured.
6. Reset Password: valid token resets password; expired/invalid/used tokens are rejected.
7. Admin Dashboard: fleet metrics, cards, live fleet, command center, and admin links load.
8. Driver Dashboard: assigned bus appears, start/end trip works, GPS post works, occupancy and delay actions work.
9. Passenger Dashboard: routes, live fleet, search, route modal, and tracking links work.
10. Tracking: live bus, offline bus, and recently completed trip views render without console errors.
11. Heatmap: page and `/heatmap/data` load for authorized users.
12. Analytics: dashboard loads charts/metrics.
13. Notifications: list, unread count, mark-read, and admin broadcast work.
14. Complaints: passenger/driver create, admin reply/close, edit/archive history views work.
15. SOS: passenger trigger, driver acknowledge, admin resolve, and status polling work.
16. Lost & Found: passenger create/edit/archive, driver/admin reply, returned status, and notifications work.
17. Route Management: create/edit manual routes and duplicate route-code validation work.
18. Bus Management: create/edit/delete buses, route assignment, driver-code uniqueness, and active/offline views work.
19. Occupancy: driver updates and passenger/admin live occupancy API render correctly.
20. Offline Mode: service worker/offline page works after install.
21. PWA: manifest, icons, install prompt, and app display mode work.
<!-- TP-v2.0-Release -->
