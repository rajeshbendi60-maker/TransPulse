window.TransPulseTracking = {
    activeMap: null,
    busMarker: null,
    intermediateMarkers: [],
    polyline: null,
    completedPolyline: null,
    plannedPolyline: null,
    diversionPolyline: null,
    remainingPolyline: null,
    stopLayerGroup: null,
    trackingInterval: null,
    currentBusIdentifier: null,
    userHasZoomed: false,
    cachedStopsHash: "",
    userMarker: null,
    userLatLng: null,
    animTimer: null,
    markerAnimFrame: null,
    markerAnimation: null,
    lastBearing: null,
    lastRenderedLatLng: null,
    lastShapePointIndex: null,
    markerPathFraction: null,
    mapCenterLoaded: false,
    initialBusZoomDone: false,
    lastTrackingSessionAt: 0,
    mapUpdateInFlight: false,
    lastTelemetryReceivedAt: null,
    geoWatchId: null,
    fetchFailures: 0,
    savedHistoryBusId: null,
    lastTimelineState: null,
    lastTelemetryState: null,


    escapeHtml: function(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },

    normalizeIdentifier: function(value) {
        if (value === null || value === undefined) return "";
        return String(value)
            .toLowerCase()
            .replace(/\s+/g, '')
            .replace(/-/g, '')
            .replace(/_/g, '')
            .replace(/[^a-z0-9]/g, '');
    },

    handleOfflineState: function(busNumber) {
        console.info("[TransPulse] Handling GPS Offline State for bus:", busNumber);
        
        const overlay = document.getElementById('offline-overlay');
        const dashboard = document.getElementById('dashboard-section');
        const attribution = document.querySelector('.leaflet-control-attribution');
        
        if (overlay) {
            overlay.classList.remove('d-none');
            overlay.classList.add('d-flex');
        }
        if (dashboard) dashboard.style.display = 'none';
        if (attribution) attribution.style.display = 'none';

        if (this.polyline && this.activeMap) {
            this.activeMap.removeLayer(this.polyline);
            this.polyline = null;
        }
        if (this.busMarker && this.activeMap) {
            this.activeMap.removeLayer(this.busMarker);
            this.busMarker = null;
        }
        if (this.stopLayerGroup) {
            this.stopLayerGroup.clearLayers();
        }
        this.cachedStopsHash = null;

        if (this.activeMap && !this.mapCenterLoaded) {
            this.activeMap.setView([15.9129, 79.7400], 7);
            this.mapCenterLoaded = true;
        }
    },

    openFullscreenTracking: function(routeId, routeCode, sourceStop, destStop) {
        const buses = window.Workflow && window.Workflow.apiData && window.Workflow.apiData.buses;
        if (buses && buses.length) {
            const match = buses.find(b => b.route_id === routeId);
            if (match) {
                window.location.href = `/tracking/${encodeURIComponent(match.bus_number)}?source=routes`;
                return;
            }
        }
        window.location.href = `/tracking/search?source=routes`;
    },

    _busIcon: function(bearing) {
        const rotation = bearing || 0;
        return L.divIcon({
            className: '',
            html: `
                <div class="apsrtc-bus-marker" style="
                    width:36px;height:48px;
                    transform:rotate(${rotation}deg);
                    transform-origin:50% 50%;
                    transition:none;
                    filter:drop-shadow(0 4px 5px rgba(0,0,0,0.55)) drop-shadow(0 0 8px rgba(255,193,7,0.45));
                ">
                    <svg viewBox="0 0 64 96" width="36" height="48" xmlns="http://www.w3.org/2000/svg" aria-label="APSRTC bus">
                        <ellipse cx="32" cy="88" rx="22" ry="4" fill="rgba(0,0,0,0.28)"/>
                        <rect x="9" y="8" width="46" height="76" rx="11" fill="#f4ead8" stroke="#7b1e18" stroke-width="2"/>
                        <path d="M12 31H52V67H12Z" fill="#d12b22"/>
                        <path d="M12 39H52V47H12Z" fill="#f6d44a"/>
                        <path d="M15 12Q32 5 49 12L51 27H13Z" fill="#243746" stroke="#f8fbff" stroke-width="1.4"/>
                        <path d="M17 14Q32 9 47 14L48 24H16Z" fill="#7fc8e8" opacity="0.78"/>
                        <path d="M32 12V25" stroke="#dceff7" stroke-width="1"/>
                        <rect x="16" y="33" width="8" height="11" rx="2" fill="#263b4a" stroke="#f8fbff" stroke-width="1"/>
                        <rect x="40" y="33" width="8" height="11" rx="2" fill="#263b4a" stroke="#f8fbff" stroke-width="1"/>
                        <rect x="16" y="50" width="8" height="12" rx="2" fill="#263b4a" stroke="#f8fbff" stroke-width="1"/>
                        <rect x="40" y="50" width="8" height="12" rx="2" fill="#263b4a" stroke="#f8fbff" stroke-width="1"/>
                        <rect x="25" y="34" width="14" height="28" rx="3" fill="#b8201a" opacity="0.7"/>
                        <text x="32" y="48" text-anchor="middle" font-size="5.5" font-family="Arial, sans-serif" font-weight="700" fill="#ffffff">APSRTC</text>
                        <path d="M14 69H50L47 79Q32 84 17 79Z" fill="#243746" stroke="#f8fbff" stroke-width="1.2"/>
                        <rect x="17" y="72" width="30" height="5" rx="2" fill="#88cce7" opacity="0.8"/>
                        <rect x="13" y="18" width="4" height="9" rx="1.5" fill="#7b1e18"/>
                        <rect x="47" y="18" width="4" height="9" rx="1.5" fill="#7b1e18"/>
                        <rect x="5" y="24" width="5" height="16" rx="2.5" fill="#202a31"/>
                        <rect x="54" y="24" width="5" height="16" rx="2.5" fill="#202a31"/>
                        <rect x="5" y="58" width="5" height="16" rx="2.5" fill="#202a31"/>
                        <rect x="54" y="58" width="5" height="16" rx="2.5" fill="#202a31"/>
                        <circle cx="17" cy="16" r="2.6" fill="#fff4a8" stroke="#9d6b00" stroke-width="0.8"/>
                        <circle cx="47" cy="16" r="2.6" fill="#fff4a8" stroke="#9d6b00" stroke-width="0.8"/>
                        <rect x="25" y="8" width="14" height="4" rx="2" fill="#d12b22"/>
                    </svg>
                </div>`,
            iconSize: [36, 48],
            iconAnchor: [18, 24]
        });
    },

    _initMap: async function() {
        const mapContainer = document.getElementById('osm-map');
        if (!mapContainer || this.activeMap) return;

        let center = [20.5937, 78.9629];
        let zoom = 6;
        try {
            const centerRes = await fetch('/api/map/center');
            if (centerRes.ok) {
                const centerData = await centerRes.json();
                if (centerData.lat && centerData.lng) {
                    center = [centerData.lat, centerData.lng];
                    zoom = 8;
                }
            }
        } catch (e) {
            console.warn('[TransPulse] Map center fallback used:', e.message);
        }

        this.activeMap = L.map('osm-map', { zoomControl: false }).setView(center, zoom);
        L.control.zoom({ position: 'bottomleft' }).addTo(this.activeMap);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
            maxZoom: 19
        }).addTo(this.activeMap);

        this.stopLayerGroup = L.layerGroup().addTo(this.activeMap);

        this.activeMap.on('zoomend dragend', () => {
            this.userHasZoomed = true;
        });

        if ("geolocation" in navigator) {
            this.geoWatchId = navigator.geolocation.watchPosition(
                (pos) => {
                    this.userLatLng = [pos.coords.latitude, pos.coords.longitude];
                    if (!this.userMarker && this.activeMap) {
                        this.userMarker = L.circleMarker(this.userLatLng, {
                            radius: 7, fillColor: '#0d6efd', color: '#ffffff', weight: 2, fillOpacity: 1
                        }).addTo(this.activeMap).bindTooltip("You are here", {
                            permanent: true, direction: "top",
                            className: "bg-primary text-white border-0 shadow"
                        });
                    } else if (this.userMarker) {
                        this.userMarker.setLatLng(this.userLatLng);
                    }
                },
                (err) => console.warn("[TransPulse] GPS Watch Error:", err.message),
                { enableHighAccuracy: true, maximumAge: 5000, timeout: 10000 }
            );
        }

        this.mapCenterLoaded = true;
    },

    drawPolyline: function(lineCoords) {
        // Legacy single-polyline used as backward-compat fallback
        if (!this.polyline) {
            this.polyline = L.polyline(lineCoords, {
                color: '#007bff',
                weight: 6,
                opacity: 0.85,
                smoothFactor: 0,
                noClip: true
            }).addTo(this.activeMap);
        } else {
            this.polyline.setLatLngs(lineCoords);
        }
    },

    _removeAllRouteLayers: function() {
        const layers = [
            'polyline', 'completedPolyline', 'plannedPolyline',
            'diversionPolyline', 'remainingPolyline'
        ];
        layers.forEach(key => {
            if (this[key] && this.activeMap) {
                this.activeMap.removeLayer(this[key]);
                this[key] = null;
            }
        });
    },

    drawSectionedRoute: function(sections) {
        // Remove all existing route layers before redrawing
        this._removeAllRouteLayers();

        const toCoords = pts => pts.map(p => [Number(p.lat), Number(p.lng)]);

        // Completed journey — gray, solid, semi-transparent
        if (sections.completed && sections.completed.length >= 2) {
            this.completedPolyline = L.polyline(toCoords(sections.completed), {
                color: '#7a7a7a',
                weight: 5,
                opacity: 0.45,
                smoothFactor: 0,
                noClip: true
            }).addTo(this.activeMap);
        }

        // Bypassed planned route (legacy) — removed
        // Dynamic diversion road (legacy) — removed

        // Remaining journey — cyan, solid (primary colour)
        if (sections.remaining && sections.remaining.length >= 2) {
            this.remainingPolyline = L.polyline(toCoords(sections.remaining), {
                color: '#00e5ff',
                weight: 6,
                opacity: 0.85,
                smoothFactor: 0,
                noClip: true
            }).addTo(this.activeMap);
        }
    },

    initialize: async function(busIdentifier) {
        console.info("[TransPulse] Initializing pipeline for bus:", busIdentifier);
        this.currentBusIdentifier = busIdentifier;
        this.initialBusZoomDone = false;
        
        await this._initMap();
        setTimeout(() => this.activeMap && this.activeMap.invalidateSize(), 300);
        
        await this.updateTracking();
        
        if (this.trackingInterval) clearInterval(this.trackingInterval);
        this.trackingInterval = setInterval(() => this.updateTracking(), 1000);
    },

    startTracking: async function(busIdentifier) {
        await this.initialize(busIdentifier);
    },

    stopTracking: function() {
        console.info("[TransPulse] Stopping tracking loop and clearing watches.");
        if (this.trackingInterval) clearInterval(this.trackingInterval);
        if (this.markerAnimFrame) cancelAnimationFrame(this.markerAnimFrame);
        
        if (this.geoWatchId != null) {
            navigator.geolocation.clearWatch(this.geoWatchId);
            this.geoWatchId = null;
        }

        this.markerAnimation = null;
        this.currentBusIdentifier = null;
        this.lastRenderedLatLng = null;
        this.markerPathFraction = null;
        this.fetchFailures = 0;
        this.lastTelemetryReceivedAt = null;
        this.mapUpdateInFlight = false;
    },

    _bearingBetween: function(start, end) {
        const dLat = end.lat - start.lat;
        const dLng = end.lng - start.lng;
        return Math.atan2(dLng, dLat) * (180 / Math.PI);
    },

    _validPath: function(path) {
        return Array.isArray(path) && path.length >= 2 &&
            path.every(p => p && Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lng)));
    },

    _pathDistance: function(path) {
        let total = 0;
        for (let i = 0; i < path.length - 1; i++) {
            total += this.activeMap.distance([path[i].lat, path[i].lng], [path[i + 1].lat, path[i + 1].lng]);
        }
        return total;
    },

    _pointOnPathFraction: function(path, fraction) {
        if (!this._validPath(path)) return null;
        const clamped = Math.max(0, Math.min(1, Number(fraction) || 0));
        const total = this._pathDistance(path);
        if (total <= 0) {
            const first = path[0];
            return { lat: Number(first.lat), lng: Number(first.lng), bearing: 0, fraction: 0 };
        }

        const target = total * clamped;
        let travelled = 0;
        for (let i = 0; i < path.length - 1; i++) {
            const start = { lat: Number(path[i].lat), lng: Number(path[i].lng) };
            const end = { lat: Number(path[i + 1].lat), lng: Number(path[i + 1].lng) };
            const segment = this.activeMap.distance([start.lat, start.lng], [end.lat, end.lng]);
            if (segment <= 0) continue;
            if (target <= travelled + segment || i === path.length - 2) {
                const segmentProgress = Math.max(0, Math.min(1, (target - travelled) / segment));
                const lat = start.lat + ((end.lat - start.lat) * segmentProgress);
                const lng = start.lng + ((end.lng - start.lng) * segmentProgress);
                return {
                    lat,
                    lng,
                    bearing: this._bearingBetween(start, end),
                    fraction: clamped
                };
            }
            travelled += segment;
        }

        const last = path[path.length - 1];
        const prev = path[path.length - 2];
        return {
            lat: Number(last.lat),
            lng: Number(last.lng),
            bearing: this._bearingBetween(
                { lat: Number(prev.lat), lng: Number(prev.lng) },
                { lat: Number(last.lat), lng: Number(last.lng) }
            ),
            fraction: 1
        };
    },

    _nearestPathFraction: function(path, latLng) {
        if (!this._validPath(path) || !latLng) return null;
        const total = this._pathDistance(path);
        if (total <= 0) return 0;

        let bestFraction = 0;
        let bestDistance = Infinity;
        let travelled = 0;
        const target = L.latLng(latLng.lat, latLng.lng);

        for (let i = 0; i < path.length - 1; i++) {
            const start = L.latLng(Number(path[i].lat), Number(path[i].lng));
            const end = L.latLng(Number(path[i + 1].lat), Number(path[i + 1].lng));
            const segment = this.activeMap.distance(start, end);
            if (segment <= 0) continue;

            const startPoint = this.activeMap.latLngToLayerPoint(start);
            const endPoint = this.activeMap.latLngToLayerPoint(end);
            const targetPoint = this.activeMap.latLngToLayerPoint(target);
            const dx = endPoint.x - startPoint.x;
            const dy = endPoint.y - startPoint.y;
            const lengthSq = (dx * dx) + (dy * dy);
            const t = lengthSq > 0
                ? Math.max(0, Math.min(1, (((targetPoint.x - startPoint.x) * dx) + ((targetPoint.y - startPoint.y) * dy)) / lengthSq))
                : 0;
            const projected = L.point(startPoint.x + (dx * t), startPoint.y + (dy * t));
            const distance = targetPoint.distanceTo(projected);
            if (distance < bestDistance) {
                bestDistance = distance;
                bestFraction = (travelled + (segment * t)) / total;
            }
            travelled += segment;
        }

        return Math.max(0, Math.min(1, bestFraction));
    },

    _timeWithDelay: function(timeText, delayMinutes) {
        if (!timeText || timeText === '--') return 'Calculating...';
        const match = String(timeText).trim().match(/^(\d{1,2}):(\d{2})\s*([AP]M)$/i);
        if (!match) return timeText;
        let hour = Number(match[1]);
        const minute = Number(match[2]);
        const suffix = match[3].toUpperCase();
        if (hour === 12) hour = 0;
        if (suffix === 'PM') hour += 12;
        let total = (hour * 60) + minute + Number(delayMinutes || 0);
        total = ((total % 1440) + 1440) % 1440;
        const hour24 = Math.floor(total / 60);
        const outMinute = total % 60;
        const outSuffix = hour24 < 12 ? 'AM' : 'PM';
        const hour12 = hour24 % 12 || 12;
        return `${String(hour12).padStart(2, '0')}:${String(outMinute).padStart(2, '0')} ${outSuffix}`;
    },

    _delayLabel: function(delayMinutes) {
        const delay = Number(delayMinutes || 0);
        return delay > 0 ? `+${Math.abs(delay)} min` : '0 min';
    },

    _occupancyLabel: function(bus) {
        if (!bus || bus.occupancy_pct === null || bus.occupancy_pct === undefined) {
            return '--';
        }
        const pct = Math.max(0, Math.min(100, Math.round(Number(bus.occupancy_pct) || 0)));
        const explicitLevel = String(bus.occupancy_level || '').trim().toUpperCase();
        let level = ['LOW', 'MEDIUM', 'HIGH'].includes(explicitLevel) ? explicitLevel : 'LOW';
        if (!['LOW', 'MEDIUM', 'HIGH'].includes(explicitLevel)) {
            if (pct >= 71) level = 'HIGH';
            else if (pct >= 31) level = 'MEDIUM';
        }
        return `${level.charAt(0)}${level.slice(1).toLowerCase()} (${pct}%)`;
    },

    _isTripCompleted: function(bus) {
        return String((bus && bus.service_status) || '').toLowerCase() === 'completed' ||
            String((bus && bus.trip_status) || '').toUpperCase() === 'COMPLETED' ||
            String((bus && bus.trip_status) || '').toUpperCase() === 'RETURN_COMPLETED';
    },

    _etaText: function(bus) {
        if (!bus) return '--';
        return bus.eta_display || bus.eta_label || (bus.eta_minutes !== null && bus.eta_minutes !== undefined ? `${bus.eta_minutes} min` : '--');
    },

    _getTimelineStops: function(bus) {
        if (Array.isArray(bus.stops) && bus.stops.length) return bus.stops;
        if (Array.isArray(bus.display_schedule_stops) && bus.display_schedule_stops.length) return bus.display_schedule_stops;
        if (bus.schedule && Array.isArray(bus.schedule.stops) && bus.schedule.stops.length) return bus.schedule.stops;
        return [];
    },

    _smoothBearingValue: function(targetBearing) {
        const target = Number.isFinite(Number(targetBearing)) ? Number(targetBearing) : 0;
        if (this.lastBearing === null || !Number.isFinite(this.lastBearing)) {
            this.lastBearing = target;
            return target;
        }
        const delta = ((target - this.lastBearing + 540) % 360) - 180;
        this.lastBearing += delta;
        return this.lastBearing;
    },

    _setMarkerBearing: function(bearing) {
        if (!this.busMarker) return;
        const markerEl = this.busMarker.getElement();
        const busEl = markerEl ? markerEl.querySelector('.apsrtc-bus-marker') : null;
        if (busEl) {
            const smoothBearing = this._smoothBearingValue(bearing);
            const displayBearing = ((smoothBearing % 360) + 360) % 360;
            busEl.style.transform = `rotate(${displayBearing}deg)`;
        }
    },

    _animateMarkerTo: function(targetPos, options = {}) {
        // Deprecated: No interpolation or simulation allowed in production tracking
    },

    _runMarkerAnimation: function(now) {
        // Deprecated
    },

    _renderTimeline: function(bus) {
        // Render timeline directly using renderTimeline(bus) function
        this.renderTimeline(bus);
    },

    _showNoGeometry: function(message, keepTimeline) {
        console.warn("[TransPulse] Geometry unavailable alert:", message);
        const tContainer = document.getElementById('verticalTimelineContainer') || document.getElementById('stopsTimeline');
        if (tContainer && !keepTimeline) {
            tContainer.innerHTML = `<div class="text-warning small fw-bold"><i class="fa-solid fa-triangle-exclamation"></i> ${message || 'No GTFS Geometry Available'}</div>`;
        }
        if (this.polyline) {
            this.activeMap.removeLayer(this.polyline);
            this.polyline = null;
        }
        if (this.stopLayerGroup) {
            this.stopLayerGroup.clearLayers();
        }
        if (this.busMarker) {
            this.activeMap.removeLayer(this.busMarker);
            this.busMarker = null;
            this.lastRenderedLatLng = null;
        }
    },

    _heartbeatTrackingSession: function(bus) {
        const now = Date.now();
        if (!bus || !bus.bus_id || (now - this.lastTrackingSessionAt) < 60000) return;
        this.lastTrackingSessionAt = now;
        fetch('/api/tracking/session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
            },
            body: JSON.stringify({
                bus_id: bus.bus_id,
                route_id: bus.route_id || null,
                trip_id: bus.trip_id || null
            })
        }).catch(() => {});
    },

    fetchTrackingData: async function() {
        if (!this.currentBusIdentifier || this.currentBusIdentifier.toLowerCase() === 'search' || document.hidden) {
            return null;
        }
        if (!navigator.onLine) {
            console.warn("[TransPulse] Navigator is offline.");
            return null;
        }
        try {
            // Priority: Try single bus tracking endpoint first
            const trackingId = encodeURIComponent(this.currentBusIdentifier.trim());
            const busRes = await fetch(`/api/tracking/${trackingId}`);
            if (busRes.ok) {
                const busData = await busRes.json();
                this.fetchFailures = 0;
                return [busData];
            } else {
                console.warn(`[TransPulse] Single bus API fetch returned status ${busRes.status}. Falling back to live fleet list.`);
            }
        } catch (err) {
            console.warn("[TransPulse] Error fetching from single bus API:", err.message);
        }

        // Fallback to /api/buses/live
        try {
            const fleetRes = await fetch('/api/buses/live');
            if (!fleetRes.ok) {
                this.fetchFailures++;
                if (this.fetchFailures >= 3) {
                    this._showNoGeometry('Unable to reach tracking service. Retrying...', true);
                }
                console.error("[TransPulse] Failed to fetch live fleet list:", fleetRes.status);
                return null;
            }
            this.fetchFailures = 0;
            const fleetData = await fleetRes.json();
            if (!fleetData || !Array.isArray(fleetData.buses)) {
                console.error("[TransPulse] Live fleet response format invalid.");
                return null;
            }
            return fleetData.buses;
        } catch (err) {
            console.error("[TransPulse] Error fetching live fleet list:", err.message);
            return null;
        }
    },

    findBus: function(buses, identifier) {
        if (!Array.isArray(buses) || !identifier) return null;
        const normTrackingId = this.normalizeIdentifier(identifier);
        
        // Exact normalized match
        let matched = buses.find(b => {
            const normBusId = this.normalizeIdentifier(b.bus_id);
            const normBusNo = this.normalizeIdentifier(b.bus_number);
            const normRegNo = this.normalizeIdentifier(b.registration_number);
            const normVehId = this.normalizeIdentifier(b.vehicle_id);

            return (normBusId === normTrackingId || 
                    normBusNo === normTrackingId || 
                    normRegNo === normTrackingId || 
                    (normVehId && normVehId === normTrackingId));
        });

        if (!matched) {
            // Substring or numeric parts fallback matching (Phase 3)
            matched = buses.find(b => {
                const normBusNo = this.normalizeIdentifier(b.bus_number);
                const normRegNo = this.normalizeIdentifier(b.registration_number);

                if (normTrackingId.length >= 2) {
                    if (normBusNo.includes(normTrackingId) || normRegNo.includes(normTrackingId)) {
                        return true;
                    }
                }
                
                const numTracking = String(identifier).replace(/[^0-9]/g, "");
                const numBusNo = String(b.bus_number || b.bus_id || "").replace(/[^0-9]/g, "");
                if (numTracking.length >= 2 && numTracking === numBusNo) {
                    return true;
                }
                return false;
            });
        }
        return matched;
    },

    updateTracking: async function() {
        if (this.mapUpdateInFlight) return;
        this.mapUpdateInFlight = true;

        try {
            const buses = await this.fetchTrackingData();
            if (!buses) {
                return;
            }

            const bus = this.findBus(buses, this.currentBusIdentifier);
            if (!bus) {
                console.error("[TransPulse] Bus not found in live fleet tracking data. Identifier:", this.currentBusIdentifier);
                this.handleOfflineState(this.currentBusIdentifier);
                return;
            }

            // Verify properties exist, default if missing (Phase 2)
            if (bus.tracking_available === undefined) {
                console.warn("[TransPulse] tracking_available property was missing, defaulting to false.");
                bus.tracking_available = false;
            }

            // Determine if this is a terminal/completed state that should show full data
            const tripStatus = String(bus.trip_status || '').toUpperCase();
            const isCompleted = tripStatus === 'COMPLETED' || tripStatus === 'RETURN_COMPLETED';

            const overlay = document.getElementById('offline-overlay');
            const dashboard = document.getElementById('dashboard-section');
            const attribution = document.querySelector('.leaflet-control-attribution');

            if (!bus.tracking_available && !isCompleted) {
                if (overlay) {
                    overlay.classList.remove('d-none');
                    overlay.classList.add('d-flex');
                }
                if (dashboard) dashboard.style.display = 'none';
                if (attribution) attribution.style.display = 'none';
                
                // Clear map layers
                if (this.polyline && this.activeMap) { this.activeMap.removeLayer(this.polyline); this.polyline = null; }
                if (this.busMarker && this.activeMap) { this.activeMap.removeLayer(this.busMarker); this.busMarker = null; }
                if (this.stopLayerGroup) this.stopLayerGroup.clearLayers();
                this.cachedStopsHash = null;
                
                return; // Stop further rendering since UI is hidden
            } else {
                if (overlay) {
                    overlay.classList.add('d-none');
                    overlay.classList.remove('d-flex');
                }
                if (dashboard) dashboard.style.display = 'block';
                if (attribution) attribution.style.display = 'block';
            }

            // Clean map components if route or trip has changed
            const routeTripKey = `${bus.route_id || ''}|${bus.shape_id || ''}|${bus.trip_id || ''}`;
            if (this.currentRouteTripKey && this.currentRouteTripKey !== routeTripKey) {
                this._removeAllRouteLayers();
                if (this.busMarker) {
                    this.activeMap.removeLayer(this.busMarker);
                    this.busMarker = null;
                }
                if (this.stopLayerGroup) {
                    this.stopLayerGroup.clearLayers();
                }
                this.cachedStopsHash = null;
                this.initialBusZoomDone = false;
            }
            this.currentRouteTripKey = routeTripKey;

            // Session tracking and history
            if (bus.bus_number) {
                sessionStorage.setItem('tp-active-tracking-bus', bus.bus_number);
                localStorage.setItem('tp-active-tracking-bus', bus.bus_number);
            }
            const historyBusId = String(bus.bus_number || bus.bus_id || '');
            if (window.TransPulseTrackingHistory && historyBusId && this.savedHistoryBusId !== historyBusId) {
                window.TransPulseTrackingHistory.saveFromBus(bus);
                this.savedHistoryBusId = historyBusId;
            }
            this._heartbeatTrackingSession(bus);

            // Execute modular rendering pipeline in sequence (Phase 4 / Phase 9)
            // Wrap in individual try-catch to prevent a failure in one stage from breaking the others (Phase 5)
            try {
                this.updateMap(bus);
            } catch (err) {
                console.error("[TransPulse] Error rendering Leaflet map/marker updates:", err);
            }

            try {
                this.renderTimeline(bus);
            } catch (err) {
                console.error("[TransPulse] Error rendering timeline components:", err);
            }

            try {
                this.renderTelemetry(bus);
            } catch (err) {
                console.error("[TransPulse] Error rendering telemetry metrics:", err);
            }

        } catch (e) {
            console.error("[TransPulse] Critical exception inside updateTracking pipeline:", e);
        } finally {
            this.mapUpdateInFlight = false;
        }
    },

    updateMap: function(bus) {
        if (!this.activeMap) return;

        const isCompleted = this._isTripCompleted(bus);
        if (!bus.tracking_available && !isCompleted) {
            return; // Do not draw any geometry or markers if tracking is unavailable
        }

        // ── Colour palette (final production palette) ──────────────────────
        const COLOUR = {
            completed: '#6B7280',   // Gray  — travelled road
            planned:   '#60A5FA',   // Blue  — bypassed original route (dashed)
            dynamic:   '#F97316',   // Orange — active diversion
            remaining: '#06B6D4',   // Cyan  — ahead on official route
        };

        // ── Route/trip change detection key ────────────────────────────────
        const sections = bus.geometry_sections || null;
        // Draw the sectioned geometry directly from the backend payload (applies to all trips, diverged or normal)
        const hasSections = sections &&
            (sections.completed || sections.planned ||
             sections.dynamic  || sections.remaining);

        const activeLinePath = (bus.display_path && bus.display_path.length)
            ? bus.display_path : bus.path;

        // Include section lengths in hash so redraws fire on GPS movement
        const completedLen = sections && sections.completed ? sections.completed.length : 0;
        const remainingLen = sections && sections.remaining ? sections.remaining.length : 0;
        const dynamicLen  = sections && sections.dynamic  ? sections.dynamic.length  : 0;

        const currentStopsHash =
            `${bus.route_id || ''}|${bus.shape_id || ''}|${bus.trip_id || ''}` +
            `|${bus.stops ? bus.stops.map(s => s.name).join('|') : ''}` +
            `|${bus.current_stop_index}|${bus.status}|${bus.direction}` +
            `|${bus.path ? bus.path.length : 0}` +
            `|${bus.display_geometry_source || 'gtfs'}` +
            `|${bus.display_path ? bus.display_path.length : 0}` +
            `|${completedLen}|${remainingLen}|${dynamicLen}`;

        const geomWarningBanner = document.getElementById('geometry-warning-banner');
        const tripCompleted = this._isTripCompleted(bus);

        if (this.cachedStopsHash !== currentStopsHash) {
            this.cachedStopsHash = currentStopsHash;

            // ── Priority 1: Four-section geometry (production mode) ─────────
            if (hasSections) {
                // Completed trip: entire route shown as gray
                let drawSections = sections;
                if (tripCompleted) {
                    const fullPath = [
                        ...(sections.completed || []),
                        ...(sections.remaining || []),
                    ];
                    drawSections = {
                        completed: fullPath,
                        remaining: [],
                    };
                }

                // Remove legacy single polyline if present
                if (this.polyline && this.activeMap) {
                    this.activeMap.removeLayer(this.polyline);
                    this.polyline = null;
                }

                // Draw in correct z-order: completed → planned → remaining → dynamic
                // Dynamic (orange) is last so it renders ABOVE cyan remaining.
                const removeLayer = (key) => {
                    if (this[key] && this.activeMap) {
                        this.activeMap.removeLayer(this[key]);
                        this[key] = null;
                    }
                };
                removeLayer('completedPolyline');
                removeLayer('plannedPolyline');
                removeLayer('remainingPolyline');
                removeLayer('diversionPolyline');

                const toCoords = pts => pts.map(p => [Number(p.lat), Number(p.lng)]);

                // 1. Completed — gray, solid
                if (drawSections.completed && drawSections.completed.length >= 2) {
                    this.completedPolyline = L.polyline(toCoords(drawSections.completed), {
                        color: COLOUR.completed, weight: 5, opacity: 0.50,
                        smoothFactor: 0, noClip: true
                    }).addTo(this.activeMap);
                }

                // 2. Planned (legacy) — removed
                
                // 3. Remaining — cyan, solid
                if (drawSections.remaining && drawSections.remaining.length >= 2) {
                    this.remainingPolyline = L.polyline(toCoords(drawSections.remaining), {
                        color: COLOUR.remaining, weight: 6, opacity: 0.85,
                        smoothFactor: 0, noClip: true
                    }).addTo(this.activeMap);
                }

                // 4. Dynamic diversion (legacy) — removed

                if (geomWarningBanner) geomWarningBanner.style.display = 'none';

                // Fit bounds to entire journey (all four sections) on first load only
                if (!this.initialBusZoomDone && !this.userHasZoomed) {
                    const allPts = [
                        ...(drawSections.completed || []),
                        ...(drawSections.remaining || []),
                    ];
                    if (allPts.length >= 2) {
                        this.activeMap.fitBounds(
                            allPts.map(p => [Number(p.lat), Number(p.lng)]),
                            { padding: [48, 48] }
                        );
                        this.initialBusZoomDone = true;
                    }
                }

            // ── Priority 2: Legacy single-path fallback ─────────────────────
            } else if (activeLinePath && activeLinePath.length >= 2) {
                this._removeAllRouteLayers();
                const lineCoords = activeLinePath.map(p => [p.lat, p.lng]);
                this.drawPolyline(lineCoords);
                if (geomWarningBanner) geomWarningBanner.style.display = 'none';

            // ── Priority 3: Client-side OSRM (last resort) ─────────────────
            } else if (bus.stops && bus.stops.length >= 2) {
                console.info('[TransPulse] display_path empty. Querying client OSRM router...');
                const coords = bus.stops.map(s => `${s.lng},${s.lat}`).join(';');
                const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson`;
                fetch(osrmUrl)
                    .then(res => res.ok ? res.json() : Promise.reject(new Error('OSRM error')))
                    .then(data => {
                        if (data.routes && data.routes.length > 0 && data.routes[0].geometry) {
                            const lineCoords = data.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
                            this._removeAllRouteLayers();
                            this.drawPolyline(lineCoords);
                            if (geomWarningBanner) geomWarningBanner.style.display = 'none';
                        } else {
                            throw new Error('No usable geometry in OSRM response');
                        }
                    })
                    .catch(err => {
                        console.warn('[TransPulse] Client OSRM failed:', err.message);
                        this._removeAllRouteLayers();
                        if (geomWarningBanner) geomWarningBanner.style.display = 'block';
                    });

            // ── Priority 4: No geometry at all ─────────────────────────────
            } else {
                console.warn('[TransPulse] Route geometry completely unavailable.');
                this._removeAllRouteLayers();
                if (geomWarningBanner) geomWarningBanner.style.display = 'block';
            }

            // ── Stop markers ────────────────────────────────────────────────
            if (bus.stops && bus.stops.length) {
                this.stopLayerGroup.clearLayers();
                bus.stops.forEach((stop, idx) => {
                    let circleColor = '#007bff';
                    if (idx === 0) circleColor = '#ffc107';
                    else if (idx === bus.stops.length - 1) circleColor = '#dc3545';

                    L.circleMarker([stop.lat, stop.lng], {
                        radius: 8,
                        fillColor: '#040b14',
                        color: circleColor,
                        weight: 3,
                        fillOpacity: 1
                    }).bindPopup(stop.name).addTo(this.stopLayerGroup);
                });
            } else {
                console.warn('[TransPulse] Stops data missing. Cannot render stop markers.');
            }
        }

        // ── Bus Marker (always uses real GPS, never moves the route) ────────
        let displayLat = Number(bus.current_lat);
        let displayLon = Number(bus.current_lon);

        const isWaiting = String(bus.trip_status || '').toUpperCase() === 'WAITING_TO_DEPART' || String(bus.trip_status || '').toUpperCase() === 'RETURN_READY';

        // Native GPS only; we no longer anchor to stops when waiting.

        if (displayLat !== null && displayLat !== undefined &&
            displayLon !== null && displayLon !== undefined &&
            !Number.isNaN(displayLat) && !Number.isNaN(displayLon) &&
            displayLat !== 0.0) {

            const pos = [displayLat, displayLon];
            const bearing = bus.bearing || 0;
            const popupEta = this._etaText(bus);
            const routeName = bus.route_name || bus.route_code || '--';
            const popupHtml = `<strong>Bus ${this.escapeHtml(bus.bus_number)}</strong><br>` +
                `Route: ${this.escapeHtml(routeName)}<br>` +
                `Current: ${this.escapeHtml(bus.current_stop || '--')}<br>` +
                `ETA: ${this.escapeHtml(popupEta)}<br>` +
                `Occupancy: ${this._occupancyLabel(bus)}<br>` +
                `Delay: ${bus.current_delay_label || this._delayLabel(bus.current_delay_minutes || 0)}`;

            if (!this.busMarker) {
                this.busMarker = L.marker(pos, { icon: this._busIcon(bearing), zIndexOffset: 1000 })
                    .bindPopup(popupHtml)
                    .addTo(this.activeMap);

                this.lastBearing = bearing;
                this.lastRenderedLatLng = { lat: pos[0], lng: pos[1] };

                this.busMarker.on('click', () => {
                    this.activeMap.setView(this.busMarker.getLatLng(), 14);
                    this.busMarker.openPopup();
                });

                // First-load zoom: if sections haven't already fitBounds, centre on bus
                if (!this.initialBusZoomDone && !this.userHasZoomed) {
                    this.activeMap.setView(pos, 14);
                    this.initialBusZoomDone = true;
                }
            } else {
                this.busMarker.setLatLng(pos);
                this.busMarker.setIcon(this._busIcon(bearing));
                this.busMarker.setPopupContent(popupHtml);

                this.lastBearing = bearing;
                this.lastRenderedLatLng = { lat: pos[0], lng: pos[1] };
            }
        } else {
            console.error('[TransPulse] GPS coordinates invalid. Cannot draw bus marker:',
                { lat: bus.current_lat, lon: bus.current_lon });
        }
    },



    renderTimeline: function(bus) {
        const tContainer = document.getElementById('verticalTimelineContainer') || document.getElementById('stopsTimeline');
        if (!tContainer) return;

        const timelineStops = this._getTimelineStops(bus);

        if (!timelineStops || !timelineStops.length) {
            tContainer.innerHTML = '<div class="text-muted small">No stop sequence available for this trip.</div>';
            console.warn("[TransPulse] Stops data missing for timeline rendering.");
            return;
        }

        // Timeline progression must use backend values only. Never calculate indexes on the frontend.
        const completedStopsCount = bus.completed_stops || 0;
        const currentStopIdx = bus.current_stop_index || 0;

        // Performance Optimization: Cache check using timeline state signature
        const timelineState = `${bus.trip_id || ''}|${completedStopsCount}|${currentStopIdx}|${bus.current_delay_minutes}|${timelineStops.length}`;
        if (this.lastTimelineState === timelineState) {
            return; // State did not change, skip DOM updates
        }
        this.lastTimelineState = timelineState;

        let verticalHtml = '';

        timelineStops.forEach((stop, idx) => {
            const isLast = idx === timelineStops.length - 1;
            const isFirst = idx === 0;
            let dotColor = '#007bff';
            let textClass = 'text-white-50';
            let statusLabel = 'Upcoming Stop';
            let prefix = '○';
            let timeRows = '';

            const isCompleted = idx < completedStopsCount;
            const isCurrent = idx === currentStopIdx;

            if (isCompleted) {
                prefix = '✔';
                textClass = 'text-success fw-bold';
                statusLabel = 'Completed';
                dotColor = '#22d39a'; // Green
                
                const sched = stop.scheduled_time || stop.arrival_time || '--';
                const act = stop.actual_time && stop.actual_time !== '--' ? stop.actual_time : (stop.expected_time || sched);
                const delayMin = Number(stop.delay_minutes != null ? stop.delay_minutes : 0);
                const delayLabel = delayMin > 0 ? `+${delayMin} min` : (delayMin < 0 ? `${delayMin} min` : '0 min');
                
                timeRows = `
                    <small class="text-white-50 d-block" style="font-size:0.75rem;">Scheduled: ${this.escapeHtml(sched)}</small>
                    <small class="text-success d-block" style="font-size:0.75rem;">Actual: ${this.escapeHtml(act)}</small>
                    <small class="text-warning d-block" style="font-size:0.75rem;">Delay: ${this.escapeHtml(delayLabel)}</small>
                `;
            } else if (isCurrent) {
                prefix = '▶';
                textClass = 'text-warning fw-bold fs-5';
                statusLabel = 'Current Stop';
                dotColor = '#ffc107'; // Yellow
                
                const sched = stop.scheduled_time || stop.arrival_time || '--';
                const act = stop.actual_time && stop.actual_time !== '--' ? stop.actual_time : (stop.expected_time || sched);
                
                timeRows = `
                    <small class="text-white-50 d-block" style="font-size:0.75rem;">Scheduled: ${this.escapeHtml(sched)}</small>
                    <small class="text-warning d-block" style="font-size:0.75rem;">Actual: ${this.escapeHtml(act)}</small>
                `;
            } else {
                prefix = '○';
                textClass = 'text-white-50';
                statusLabel = isLast ? 'Final Destination' : (isFirst ? 'Route Origin' : 'Upcoming Stop');
                dotColor = '#007bff'; // Blue
                
                const sched = stop.scheduled_time || stop.arrival_time || '--';
                const exp = stop.expected_time && stop.expected_time !== '--' ? stop.expected_time : (stop.actual_time || sched);
                
                timeRows = `
                    <small class="text-white-50 d-block" style="font-size:0.75rem;">Scheduled: ${this.escapeHtml(sched)}</small>
                    <small class="text-info d-block" style="font-size:0.75rem;">Expected: ${this.escapeHtml(exp)}</small>
                `;
            }

            let nameText = stop.name || stop.stop_name || '--';

            verticalHtml += `
                <div class="timeline-node-card">
                    <div class="timeline-node-dot" style="background:${dotColor}; box-shadow: 0 0 10px ${dotColor};"></div>
                    <h5 class="m-0 ${textClass}">${prefix} ${this.escapeHtml(nameText)}</h5>
                    ${timeRows}
                    <small class="text-muted d-block" style="font-size:0.7rem;">${statusLabel}</small>
                </div>`;
        });
        tContainer.innerHTML = verticalHtml;
    },

    renderTelemetry: function(bus) {
        const updateEl = (id, text) => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = text;
        };

        const telemetryState = `${bus.bus_number}|${bus.current_lat}|${bus.current_lon}|${bus.current_speed}|${bus.eta_display}|${bus.distance_remaining}|${bus.progress}|${bus.trip_status}|${bus.occupancy_pct}|${bus.current_delay_minutes}`;
        if (this.lastTelemetryState === telemetryState) {
            if (this.userLatLng && bus.current_lat && bus.current_lon) {
                const distMeters = this.activeMap.distance(this.userLatLng, [bus.current_lat, bus.current_lon]);
                updateEl('trk-user-dist', (distMeters / 1000).toFixed(1) + " km");
            }
            return;
        }
        this.lastTelemetryState = telemetryState;

        let busNumberText = bus.bus_number;
        if (bus.is_live_gps) {
            busNumberText += ' <i class="fa-solid fa-satellite-dish text-success ms-1" title="Live GPS Active"></i>';
        }

        // Phase 9: Telemetry card values populate strictly from backend snapshot parameters
        updateEl('trk-bus-num', busNumberText);
        updateEl('trk-route', bus.route_name || '--');
        // trk-driver-code element removed from HTML — guard against stale references
        const driverCodeEl = document.getElementById('trk-driver-code');
        if (driverCodeEl) driverCodeEl.innerHTML = '--';

        const scheduleStops = this._getTimelineStops(bus);
        const currentStopIndex = Math.max(0, Number(bus.current_stop_index || 0));
        const currentScheduleStop = scheduleStops[currentStopIndex] || null;
        const nextScheduleStop = scheduleStops[Math.min(scheduleStops.length - 1, currentStopIndex + 1)] || null;

        const hasCurrentStop = bus.current_stop && bus.current_stop !== '--';
        const hasNextStop = bus.next_stop && bus.next_stop !== '--';

        const currentStopName = hasCurrentStop ? bus.current_stop : ((currentScheduleStop && currentScheduleStop.name) || '--');
        const nextStopName = hasNextStop ? bus.next_stop : ((nextScheduleStop && nextScheduleStop.name) || '--');

        const currentScheduledTime = bus.current_stop_scheduled_time || ((currentScheduleStop && currentScheduleStop.scheduled_time) || '--');
        const nextScheduledTime = hasNextStop
            ? (bus.next_stop_scheduled_time || ((nextScheduleStop && nextScheduleStop.scheduled_time) || '--'))
            : (((nextScheduleStop && nextScheduleStop.scheduled_time) || bus.next_stop_scheduled_time) || '--');

        const isWaiting = String(bus.trip_status || '').toUpperCase() === 'WAITING_TO_DEPART' || String(bus.trip_status || '').toUpperCase() === 'RETURN_READY';

        updateEl('trk-current-stop', currentStopName);
        updateEl('trk-next-stop', nextStopName);
        updateEl('trk-eta', isWaiting ? 'Waiting' : this._etaText(bus));

        const distRemainingText = bus.distance_remaining === '--' || bus.distance_remaining == null
            ? '--'
            : `${bus.distance_remaining} km`;
        updateEl('trk-dist', distRemainingText);
        updateEl('trk-progress', (isWaiting ? 0 : (bus.progress != null ? bus.progress : 0)) + "%");
        
        const statusMap = {
            WAITING_TO_DEPART: 'Waiting to Depart',
            RUNNING: 'Running',
            COMPLETED: 'Trip Completed',
            RETURN_READY: 'Waiting',
            RETURN_RUNNING: 'Running (Return)',
            RETURN_COMPLETED: 'Trip Completed'
        };
        const trkStatusText = statusMap[String(bus.trip_status).toUpperCase()] || bus.status || '--';
        updateEl('trk-status', trkStatusText);
        updateEl('trk-schedule-status', bus.tracking_available ? 'GPS Online' : 'GPS Offline');
        updateEl('trk-departure', bus.departure_time || '--');
        updateEl('trk-arrival', bus.updated_arrival_time || bus.arrival_time || '--');
        updateEl('trk-current-scheduled', currentScheduledTime);
        updateEl('trk-current-actual', bus.current_stop_actual_time || '--');
        updateEl('trk-delay', `${bus.current_delay_label || this._delayLabel(bus.current_delay_minutes || 0)}<small class="d-block text-muted">${bus.current_delay_reason || 'On time'}</small>`);
        updateEl('trk-occupancy', this._occupancyLabel(bus));
        updateEl('trk-current-stop-time', `<span class="d-block">Scheduled: ${currentScheduledTime}</span><span class="d-block">Actual: ${bus.current_stop_actual_time || '--'}</span><span class="d-block">Delay: ${bus.current_delay_label || this._delayLabel(bus.current_delay_minutes || 0)}</span>`);
        updateEl('trk-next-stop-time', `<span class="d-block">Scheduled: ${nextScheduledTime}</span><span class="d-block">Expected: ${bus.next_stop_expected_time || this._timeWithDelay(nextScheduledTime, bus.current_delay_minutes || 0)}</span><span class="d-block">Delay: ${bus.current_delay_label || this._delayLabel(bus.current_delay_minutes || 0)}</span>`);

        if (this.userLatLng && bus.current_lat && bus.current_lon) {
            const distMeters = this.activeMap.distance(this.userLatLng, [bus.current_lat, bus.current_lon]);
            updateEl('trk-user-dist', (distMeters / 1000).toFixed(1) + " km");
        }
    },
};

document.addEventListener('DOMContentLoaded', () => {
    let busIdentifier = null;
    const pathParts = window.location.pathname.split('/').filter(part => part.trim() !== "");
    if (pathParts.includes('tracking')) {
        const trackingIndex = pathParts.indexOf('tracking');
        if (trackingIndex !== -1 && trackingIndex + 1 < pathParts.length) {
            busIdentifier = decodeURIComponent(pathParts[trackingIndex + 1]);
        }
    }

    if (busIdentifier && busIdentifier.toLowerCase() !== "search") {
        window.TransPulseTracking.initialize(busIdentifier);
    }
});

// Clean up polling and geolocation watches when navigating away
window.addEventListener("beforeunload", () => {
    if (window.TransPulseTracking) {
        window.TransPulseTracking.stopTracking();
    }
});
