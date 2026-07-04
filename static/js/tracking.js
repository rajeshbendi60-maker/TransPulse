window.TransPulseTracking = {
    activeMap: null,
    busMarker: null,
    intermediateMarkers: [],
    polyline: null,
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
            console.warn('Map center fallback used', e);
        }

        this.activeMap = L.map('osm-map', { zoomControl: false }).setView(center, zoom);
        L.control.zoom({ position: 'bottomleft' }).addTo(this.activeMap);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors',
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
                (err) => console.warn("GPS Tracking Error: ", err.message),
                { enableHighAccuracy: true, maximumAge: 5000, timeout: 10000 }
            );
        }

        this.mapCenterLoaded = true;
    },

    startTracking: async function(busIdentifier) {
        this.currentBusIdentifier = busIdentifier;
        this.initialBusZoomDone = false;
        await this._initMap();
        setTimeout(() => this.activeMap && this.activeMap.invalidateSize(), 300);
        this.updateMap();
        if (this.trackingInterval) clearInterval(this.trackingInterval);
        this.trackingInterval = setInterval(() => this.updateMap(), 1000);
    },

    stopTracking: function() {
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
        const pct = Math.max(0, Math.min(100, Math.round(Number(bus && bus.occupancy_pct) || 0)));
        const explicitLevel = String((bus && bus.occupancy_level) || '').trim().toUpperCase();
        let level = ['LOW', 'MEDIUM', 'HIGH'].includes(explicitLevel) ? explicitLevel : 'LOW';
        if (!['LOW', 'MEDIUM', 'HIGH'].includes(explicitLevel)) {
            if (pct >= 71) level = 'HIGH';
            else if (pct >= 31) level = 'MEDIUM';
        }
        return `${level.charAt(0)}${level.slice(1).toLowerCase()} (${pct}%)`;
    },

    _isTripCompleted: function(bus) {
        return String((bus && bus.service_status) || '').toLowerCase() === 'completed' ||
            String((bus && bus.trip_status) || '').toUpperCase() === 'COMPLETED';
    },

    _etaText: function(bus) {
        if (!bus) return 'Waiting for GPS';
        if (this._isTripCompleted(bus)) return 'Completed';
        if (bus.eta_label) return bus.eta_label;
        const eta = bus.updated_eta_minutes ?? bus.eta_minutes;
        return eta === null || eta === undefined ? 'Calculating...' : `${eta} min`;
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
        if (!this.busMarker) return;
        if (!targetPos || !Number.isFinite(targetPos[0]) || !Number.isFinite(targetPos[1])) {
            return;
        }

        const start = this.busMarker.getLatLng();
        const startLat = start.lat;
        const startLng = start.lng;
        const targetLat = targetPos[0];
        const targetLng = targetPos[1];
        const distanceToTarget = this.activeMap
            ? this.activeMap.distance([startLat, startLng], [targetLat, targetLng])
            : Infinity;
        const path = this._validPath(options.path) ? options.path : null;
        const targetFraction = Number.isFinite(Number(options.targetFraction))
            ? Math.max(0, Math.min(1, Number(options.targetFraction)))
            : null;
        const startFraction = path && targetFraction !== null
            ? (Number.isFinite(this.markerPathFraction)
                ? this.markerPathFraction
                : this._nearestPathFraction(path, start))
            : null;

        if (distanceToTarget < 0.75) {
            this._setMarkerBearing(options.bearing || this.lastBearing || 0);
            return;
        }

        this.markerAnimation = {
            startLat,
            startLng,
            targetLat,
            targetLng,
            startFraction,
            targetFraction,
            path,
            bearing: Number(options.bearing || this.lastBearing || 0),
            startTime: performance.now(),
            duration: Number.isFinite(Number(options.duration)) ? Number(options.duration) : 950,
            previousFrame: this.lastRenderedLatLng || { lat: startLat, lng: startLng }
        };

        if (!this.markerAnimFrame) {
            this.markerAnimFrame = requestAnimationFrame((now) => this._runMarkerAnimation(now));
        }
    },

    _runMarkerAnimation: function(now) {
        if (!this.busMarker || !this.markerAnimation) {
            this.markerAnimFrame = null;
            return;
        }

        const anim = this.markerAnimation;
        const rawProgress = Math.min(1, Math.max(0, (now - anim.startTime) / anim.duration));
        const progress = rawProgress * rawProgress * (3 - (2 * rawProgress));
        let lat = anim.startLat + ((anim.targetLat - anim.startLat) * progress);
        let lng = anim.startLng + ((anim.targetLng - anim.startLng) * progress);
        let frameBearing = anim.bearing;
        let frameFraction = null;

        if (anim.path && anim.startFraction !== null && anim.targetFraction !== null) {
            frameFraction = anim.startFraction + ((anim.targetFraction - anim.startFraction) * progress);
            const pathPoint = this._pointOnPathFraction(anim.path, frameFraction);
            if (pathPoint) {
                lat = pathPoint.lat;
                lng = pathPoint.lng;
                frameBearing = pathPoint.bearing;
            }
        }

        const currentFrame = { lat, lng };
        const previousFrame = anim.previousFrame || this.lastRenderedLatLng || currentFrame;
        const movedEnough = Math.abs(currentFrame.lat - previousFrame.lat) > 0.000001 ||
            Math.abs(currentFrame.lng - previousFrame.lng) > 0.000001;
        if (movedEnough) {
            frameBearing = this._bearingBetween(previousFrame, currentFrame);
            anim.previousFrame = currentFrame;
        }

        this.busMarker.setLatLng([lat, lng]);
        this._setMarkerBearing(frameBearing);
        this.lastRenderedLatLng = currentFrame;
        if (frameFraction !== null) this.markerPathFraction = frameFraction;

        if (rawProgress < 1) {
            this.markerAnimFrame = requestAnimationFrame((nextNow) => this._runMarkerAnimation(nextNow));
            return;
        }

        this.lastRenderedLatLng = { lat: anim.targetLat, lng: anim.targetLng };
        if (anim.targetFraction !== null) this.markerPathFraction = anim.targetFraction;
        this.markerAnimation = null;
        this.markerAnimFrame = null;
    },

    _renderTimeline: function(bus) {
        const tContainer = document.getElementById('verticalTimelineContainer') || document.getElementById('stopsTimeline');
        if (!tContainer) return;

        const timelineStops = this._getTimelineStops(bus);

        if (!timelineStops.length) {
            tContainer.innerHTML = '<div class="text-muted small">No stop sequence available for this trip.</div>';
            return;
        }

        const currentIdx = bus.current_stop_index != null ? bus.current_stop_index : 0;
        let verticalHtml = '';

        timelineStops.forEach((stop, idx) => {
            const isLast = idx === timelineStops.length - 1;
            const isFirst = idx === 0;
            let dotColor = '#007bff';
            let textClass = 'text-white-50';
            let statusLabel = 'Upcoming Stop';
            let prefix = '🔵';

            if (isFirst) {
                dotColor = '#ffc107';
                prefix = '🟡';
            } else if (isLast) {
                dotColor = '#dc3545';
                prefix = '🔴';
            }

            if (idx < currentIdx) {
                textClass = 'text-success fw-bold';
                statusLabel = 'Completed';
            } else if (idx === currentIdx) {
                textClass = 'text-warning fw-bold fs-5';
                statusLabel = bus.status === 'AT BUS STAND' ? 'At Bus Stand (Current)' : 'Current Stop';
            } else if (isLast) {
                textClass = 'text-danger fw-bold';
                statusLabel = 'Final Destination';
            } else if (isFirst) {
                textClass = 'text-warning';
                statusLabel = 'Route Origin';
            }

            const delayMinutes = Number(stop.delay_minutes != null ? stop.delay_minutes : (bus.current_delay_minutes || 0));
            const timeLabel = idx <= currentIdx ? 'Actual' : 'Expected';
            const actualTime = stop.actual_time || stop.expected_time || this._timeWithDelay(stop.scheduled_time, delayMinutes);
            const delayLabel = stop.delay_label || this._delayLabel(delayMinutes);

            verticalHtml += `
                <div class="timeline-node-card">
                    <div class="timeline-node-dot" style="background:${dotColor}; box-shadow: 0 0 10px ${dotColor};"></div>
                    <h5 class="m-0 ${textClass}">${prefix} ${stop.name}</h5>
                    <small class="text-info d-block" style="font-size:0.75rem;">Scheduled: ${stop.scheduled_time || '--'}</small>
                    <small class="text-white-50 d-block" style="font-size:0.75rem;">${timeLabel}: ${actualTime}</small>
                    <small class="text-muted d-block" style="font-size:0.75rem;">Delay: ${delayLabel}</small>
                    <small class="text-muted d-block" style="font-size:0.75rem;">Reason: ${stop.delay_reason || bus.current_delay_reason || 'On time'}</small>
                    <small class="text-muted d-block" style="font-size:0.75rem;">${statusLabel}</small>
                </div>`;
        });
        tContainer.innerHTML = verticalHtml;
    },

    _showNoGeometry: function(message, keepTimeline) {
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

    updateMap: async function() {
        if (!this.currentBusIdentifier || this.currentBusIdentifier.toLowerCase() === 'search' || document.hidden) return;
        if (this.mapUpdateInFlight) return;

        if (!navigator.onLine) {
            this.mapUpdateInFlight = false;
            return;
        }

        this.mapUpdateInFlight = true;

        try {
            if (!this.activeMap) {
                await this._initMap();
            }

            const busesRes = await fetch('/api/buses/live');
            if (!busesRes.ok) {
                this.fetchFailures++;
                if (this.fetchFailures >= 3) {
                    this._showNoGeometry('Unable to reach tracking service. Retrying...', true);
                }
                return;
            }
            
            this.fetchFailures = 0;
            const busesData = await busesRes.json();
            
            if (!busesData || !Array.isArray(busesData.buses)) {
                return;
            }

            const bus = busesData.buses.find(b =>
                b.bus_id.toString() === this.currentBusIdentifier.toString() ||
                (b.bus_number && b.bus_number.toLowerCase() === this.currentBusIdentifier.toString().toLowerCase()) ||
                (b.bus_number && b.bus_number.toLowerCase().includes(this.currentBusIdentifier.toString().toLowerCase()))
            );

            if (!bus) {
                this._showNoGeometry('Bus not found in live fleet. Check the bus number and try again.');
                return;
            }

            const telemetryReceivedAt = performance.now();
            const animationDuration = this.lastTelemetryReceivedAt
                ? Math.max(900, Math.min(8000, telemetryReceivedAt - this.lastTelemetryReceivedAt + 350))
                : 950;
            this.lastTelemetryReceivedAt = telemetryReceivedAt;

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
            const updateEl = (id, text) => {
                const el = document.getElementById(id);
                if (el) el.innerHTML = text;
            };

            let busNumberText = bus.bus_number;
            if (bus.is_live_gps) {
                busNumberText += ' <i class="fa-solid fa-satellite-dish text-success ms-1" title="Live GPS Active"></i>';
            }

            const driverCode = bus.assigned_driver_code || bus.driver_id || '--';
            const driverName = driverCode;

            updateEl('trk-bus-num', busNumberText);
            updateEl('trk-route', bus.route_name || '--');
            updateEl('trk-driver-code', driverCode);
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
            const tripCompleted = this._isTripCompleted(bus);

            updateEl('trk-current-stop', currentStopName);
            updateEl('trk-next-stop', nextStopName);
            updateEl('trk-eta', this._etaText(bus));
            updateEl('trk-dist', (bus.distance_remaining_km || 0) + " km");
            updateEl('trk-progress', (bus.trip_progress || 0) + "%");
            updateEl('trk-status', tripCompleted ? 'Trip Completed' : (bus.status || '--'));
            updateEl('trk-schedule-status', bus.schedule_status || bus.delay_status || '--');
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

            if (bus.geometry_available === false) {
                this._renderTimeline(bus);
                this._showNoGeometry(bus.geometry_message, true);
                return;
            }

            const activeLinePath = (bus.display_path && bus.display_path.length)
                ? bus.display_path
                : bus.path;
            const currentStopsHash = `${bus.stops ? bus.stops.map(s => s.name).join('|') : ''}|${bus.current_stop_index}|${bus.status}|${bus.direction}|${bus.shape_id || ''}|${bus.path ? bus.path.length : 0}|${bus.display_geometry_source || 'gtfs'}|${bus.display_path ? bus.display_path.length : 0}`;

            if (this.cachedStopsHash !== currentStopsHash && bus.stops) {
                this.cachedStopsHash = currentStopsHash;

                const lineCoords = (activeLinePath && activeLinePath.length)
                    ? activeLinePath.map(p => [p.lat, p.lng])
                    : bus.stops.map(s => [s.lat, s.lng]);

                if (lineCoords.length >= 2) {
                    if (!this.polyline) {
                        this.polyline = L.polyline(lineCoords, {
                            color: '#00e5ff',
                            weight: 6,
                            opacity: 0.85,
                            smoothFactor: 0,
                            noClip: true
                        }).addTo(this.activeMap);
                    } else {
                        this.polyline.setLatLngs(lineCoords);
                    }
                }

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

                this._renderTimeline(bus);
            } else if (bus.stops) {
                this._renderTimeline(bus);
            }

            const hasDisplayCoordinates = bus.display_current_lat != null && bus.display_current_lon != null;
            const displayLat = hasDisplayCoordinates && Number.isFinite(Number(bus.display_current_lat))
                ? Number(bus.display_current_lat)
                : bus.current_lat;
            const displayLon = hasDisplayCoordinates && Number.isFinite(Number(bus.display_current_lon))
                ? Number(bus.display_current_lon)
                : bus.current_lon;
            
            if (displayLat != null && displayLon != null) {
                const pos = [displayLat, displayLon];
                const bearing = bus.bearing || 0;
                const popupEta = this._etaText(bus);
                const popupHtml = `<strong>Bus ${bus.bus_number}</strong><br>Driver: ${driverName} (${driverCode})<br>Route: ${bus.route_name || '--'}<br>Status: ${tripCompleted ? 'Trip Completed' : bus.status}<br>Progress: ${bus.trip_progress || 0}%<br>ETA: ${popupEta}<br>Occupancy: ${this._occupancyLabel(bus)}<br>Delay: ${bus.current_delay_label || this._delayLabel(bus.current_delay_minutes || 0)}`;

                if (!this.busMarker) {
                    this.busMarker = L.marker(pos, { icon: this._busIcon(bearing), zIndexOffset: 1000 })
                        .bindPopup(popupHtml)
                        .addTo(this.activeMap);
                    this.lastBearing = bearing;
                    this.lastRenderedLatLng = { lat: pos[0], lng: pos[1] };
                    this.markerPathFraction = Number.isFinite(Number(bus.display_path_fraction))
                        ? Math.max(0, Math.min(1, Number(bus.display_path_fraction)))
                        : this.markerPathFraction;
                    const initialPathIndex = (bus.display_path && bus.display_path.length)
                        ? bus.display_path_index
                        : bus.shape_point_index;
                    this.lastShapePointIndex = Number.isInteger(Number(initialPathIndex))
                        ? Number(initialPathIndex)
                        : null;
                    this.busMarker.on('click', () => {
                        this.activeMap.setView(this.busMarker.getLatLng(), 14);
                        this.busMarker.openPopup();
                    });
                    if (!this.initialBusZoomDone) {
                        this.activeMap.setView(pos, 14);
                        this.initialBusZoomDone = true;
                    }
                } else {
                    this._animateMarkerTo(pos, {
                        path: activeLinePath,
                        targetFraction: bus.display_path_fraction,
                        bearing,
                        duration: animationDuration
                    });
                    this.busMarker.setPopupContent(popupHtml);
                    this.busMarker.off('click');
                    this.busMarker.on('click', () => {
                        this.activeMap.setView(this.busMarker.getLatLng(), 14);
                        this.busMarker.openPopup();
                    });
                }
            }

        } catch (e) {
            console.error("Tracking Data Layer Exception:", e);
        } finally {
            this.mapUpdateInFlight = false;
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    let busIdentifier = null;
    const pathParts = window.location.pathname.split('/');
    if (pathParts.includes('tracking')) {
        busIdentifier = decodeURIComponent(pathParts[pathParts.length - 1]);
    }

    if (busIdentifier && busIdentifier.toLowerCase() !== "search") {
        window.TransPulseTracking.startTracking(busIdentifier);
    }
});

// Clean up location polling and Leaflet interactions when the user leaves the page
window.addEventListener("beforeunload", () => {
    if (window.TransPulseTracking) {
        window.TransPulseTracking.stopTracking();
    }
});
