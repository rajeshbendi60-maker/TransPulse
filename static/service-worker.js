const CACHE_NAME = 'transpulse-v18-admin-performance-tracking'; 
const ASSETS_TO_CACHE = [
    '/',
    '/static/css/style.css',
    '/static/css/dashboard.css',
    '/static/js/enhanced-utils.js',
    '/static/js/dashboard.js',
    '/static/js/tracking.js',
    '/static/js/command-center.js',
    '/static/js/occupancy.js',
    '/static/manifest.json',
    '/static/favicon.ico?v=tp-refined-square',
    '/static/favicon-32x32.png?v=tp-refined-square',
    '/static/favicon-16x16.png?v=tp-refined-square',
    '/static/apple-touch-icon.png?v=tp-refined-square',
    '/static/icon-192.png?v=tp-refined-square',
    '/static/icon-512.png?v=tp-refined-square',
    '/static/maskable-512.png?v=tp-refined-square',
    '/static/images/auth-bus.png?v=tp-contained',
    '/offline.html',
];

// Install Event - Shell Ingestion Layer
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[ServiceWorker] Caching clean application shell wrapper assets');
                return cache.addAll(ASSETS_TO_CACHE).catch(() => {
                    console.warn('[ServiceWorker] Static resource shell precaching deferred');
                });
            })
            .then(() => self.skipWaiting())
    );
});

// Activate Event - Automatic Schema Purging & Invalidation Matrix
self.addEventListener('activate', (event) => {
    console.log('[ServiceWorker] Clean orchestration state activating...');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[ServiceWorker] Dropping obsolete asset structure cache registry:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    return self.clients.claim();
});

// Fetch Event - Split Channel API Layer Bypass Strategy
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    if (event.request.method !== 'GET' || url.origin !== location.origin) {
        return;
    }

    // Never cache live data streams or telemetry feeds
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request).catch(() => {
                return new Response(JSON.stringify({ error: 'Data link unreachable. Operating in offline mode.' }), {
                    status: 503,
                    headers: { 'Content-Type': 'application/json' }
                });
            })
        );
        return;
    }

    // Cache-First with Network Fallback strategy for static shell parameters
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) {
                return cachedResponse; 
            }

            return fetch(event.request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
                    const responseToCache = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseToCache);
                    });
                }
                return networkResponse;
            }).catch(() => {
                if (event.request.mode === 'navigate') {
                    return caches.match('/offline.html');
                }
            });
        })
    );
});

self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
