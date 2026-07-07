/* static/js/passenger-flow.js */

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function displayDriverCode(bus) {
    return (bus && (bus.assigned_driver_code || bus.driver_id)) || 'Unassigned';
}

function occupancyMeta(bus) {
    const pct = Math.max(0, Math.min(100, Math.round(Number(bus && bus.occupancy_pct) || 0)));
    const explicitLevel = String((bus && bus.occupancy_level) || '').trim().toUpperCase();
    let level = ['LOW', 'MEDIUM', 'HIGH'].includes(explicitLevel) ? explicitLevel : 'LOW';
    let color = '#22d39a';
    if (!['LOW', 'MEDIUM', 'HIGH'].includes(explicitLevel)) {
        if (pct >= 71) level = 'HIGH';
        else if (pct >= 31) level = 'MEDIUM';
    }
    if (level === 'HIGH') {
        level = 'HIGH';
        color = '#ff9f43';
    } else if (level === 'MEDIUM') {
        level = 'MEDIUM';
        color = '#f5b342';
    }
    return { pct, level, color };
}

function busStatusMeta(bus) {
    if (!bus) return { text: 'OFFLINE', badge: 'bg-secondary', live: 'OFFLINE' };
    const tripStatus = String(bus.trip_status || '').toUpperCase();
    const serviceStatus = String(bus.service_status || '').toLowerCase();
    const gpsStatus = String(bus.gps_status || '').toLowerCase();

    const completed = serviceStatus === 'completed' || tripStatus === 'COMPLETED' || tripStatus === 'RETURN_COMPLETED';
    if (completed) {
        return { text: 'Completed', badge: 'bg-secondary', live: 'OFFLINE' };
    }

    if (tripStatus === 'RUNNING' || tripStatus === 'RETURN_RUNNING' || bus.bus_status === 'Running') {
        if (gpsStatus === 'offline' || serviceStatus === 'gps_lost' || bus.is_live_gps === false) {
            return { text: 'Running', badge: 'bg-warning text-dark', live: 'GPS Offline' };
        }
        return { text: 'Running', badge: 'bg-success', live: 'GPS Online' };
    }

    if (tripStatus === 'WAITING_TO_DEPART') {
        return { text: 'Waiting to Depart', badge: 'bg-warning text-dark', live: 'GPS Offline' };
    }

    return { text: 'OFFLINE', badge: 'bg-secondary', live: 'OFFLINE' };
}

function etaDisplay(bus) {
    if (!bus) return '--';
    const tripStatus = String(bus.trip_status || '').toUpperCase();
    const serviceStatus = String(bus.service_status || '').toLowerCase();
    const completed = serviceStatus === 'completed' || tripStatus === 'COMPLETED' || tripStatus === 'RETURN_COMPLETED';
    if (completed) {
        return 'Completed';
    }
    if (tripStatus === 'WAITING_TO_DEPART') return '--';
    if (bus.eta_label) return bus.eta_label;
    const eta = bus.updated_eta_minutes ?? bus.eta_minutes;
    return eta === null || eta === undefined ? '--' : `${eta} min`;
}

function preserveNonEmptyTelemetry(currentItems, nextItems, label) {
    const current = Array.isArray(currentItems) ? currentItems : [];
    const next = Array.isArray(nextItems) ? nextItems : [];
    if (next.length === 0 && current.length > 0) {
        console.warn(`Preserving last ${label} snapshot after an empty refresh.`);
        return current;
    }
    return next;
}

async function loadAssignedRoutes() {
    const container = document.getElementById('dynamic-routes-container');
    if (!container) return;

    try {
        const res = await fetch('/api/routes/live');
        if (!res.ok) {
            if (!container.querySelector('.route-card-interactive')) {
                container.innerHTML = '<div class="col-12"><div class="alert alert-warning text-center">Unable to load routes. Please refresh.</div></div>';
            }
            return;
        }
        const data = await res.json();
        container.innerHTML = '';

        const previousRoutes = (window.Workflow && window.Workflow.apiData && window.Workflow.apiData.routes) || [];
        const routes = preserveNonEmptyTelemetry(previousRoutes, data.routes || [], 'route');
        if (window.Workflow && window.Workflow.apiData) {
            window.Workflow.apiData.routes = routes;
        }
        if (routes.length === 0) {
            container.innerHTML = '<div class="col-12"><div class="alert alert-info text-center">No routes available yet.</div></div>';
            return;
        }

        routes.forEach(route => {
            const origin = route.source_stop || route.origin || 'Unknown';
            const dest = route.destination_stop || route.destination || 'Unknown';
            const eta = route.eta_label || (route.eta_minutes != null ? `${route.eta_minutes} min` : 'Calculating...');
            const busCount = route.active_bus_count != null ? route.active_bus_count : 0;
            const departure = route.departure_time || '--';
            const arrival = route.arrival_time || '--';
            const duration = route.journey_duration || '--';

            const card = document.createElement('div');
            card.className = 'col-md-4 col-6';
            card.innerHTML = `
            <div class="card shadow-sm h-100 route-card-interactive"
                 data-route-code="${escapeHtml(route.route_code)}"
                 data-origin="${escapeHtml(origin)}"
                 data-dest="${escapeHtml(dest)}">
                <div class="card-body p-3">
                    <h6 class="text-info fw-bold mb-1">${escapeHtml(route.route_code)}</h6>
                    <p class="text-white mb-1 fs-6">${escapeHtml(route.route_name || route.route_code)}</p>
                    <p class="text-white-50 mb-2 small">Distance: <span class="text-light fw-bold">${escapeHtml(route.distance_km || '0.0')} km</span></p>
                    <p class="text-white-50 mb-2 small">Departure: <span class="text-info">${escapeHtml(departure)}</span> | Arrival: <span class="text-info">${escapeHtml(arrival)}</span> | Duration: <span class="text-warning">${escapeHtml(duration)}</span></p>
                    <div class="d-flex justify-content-between">
                        <small class="text-warning fw-bold">ETA: ${escapeHtml(eta)}</small>
                        <small class="text-success fw-bold">${busCount} bus${busCount === 1 ? '' : 'es'}</small>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-info w-100 mt-3 fw-bold">View Schedule</button>
                </div>
            </div>`;
            card.querySelector('.route-card-interactive').addEventListener('click', () => {
                showRouteDetails(route.route_code, origin, dest);
            });
            container.appendChild(card);
        });
    } catch (err) {
        console.error(err);
        if (!container.querySelector('.route-card-interactive')) {
            container.innerHTML = '<div class="col-12"><div class="alert alert-danger text-center">Failed to load routes.</div></div>';
        }
    }
}

window.Workflow = {
    apiData: { routes: [], buses: [], occupancy: {} },
    dataLoaded: false,
    dataInterval: null,
    notificationInterval: null,

    init: async function() {
        await this.fetchData();
        this.dataInterval = setInterval(() => this.fetchData(), 3000);

        this.pollNotifications();
        this.notificationInterval = setInterval(() => this.pollNotifications(), 15000);

        const srcInput = document.getElementById('searchSrc');
        const dstInput = document.getElementById('searchDst');
        if (srcInput) srcInput.addEventListener('input', () => this.handleSearchBus());
        if (dstInput) dstInput.addEventListener('input', () => this.handleSearchBus());

        const searchForm = document.getElementById('searchBusForm');
        if (searchForm) {
            searchForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleSearchBus();
            });
        }

        const fleetForm = document.getElementById('fleetStatusForm');
        if (fleetForm) {
            fleetForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleFleetStatus();
            });
        }

        const trackingForm = document.getElementById('trackingSearchForm');
        if (trackingForm) {
            trackingForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleLiveTrackingSearch();
            });
        }
    },

    pollNotifications: async function() {
        try {
            const res = await fetch('/api/notifications/unread');
            if (res.ok) {
                const data = await res.json();
                const badge = document.getElementById('nav-notification-badge');
                if (badge) {
                    if (data.unread_count > 0) {
                        badge.textContent = `Notifications (${data.unread_count})`;
                        badge.classList.remove('d-none');
                    } else {
                        badge.classList.add('d-none');
                    }
                }
            }
        } catch (e) {
            console.error("Notification Poll Error:", e);
        }
    },

    fetchData: async function() {
        let routesOk = false;
        let busesOk = false;
        try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 12000);

            const [rRes, bRes, oRes] = await Promise.all([
                fetch('/api/routes/live', { signal: controller.signal }),
                fetch('/api/buses/live', { signal: controller.signal }),
                fetch('/api/occupancy/live', { signal: controller.signal })
            ]);
            clearTimeout(timeout);

            if (rRes.ok) {
                const routesPayload = await rRes.json();
                this.apiData.routes = preserveNonEmptyTelemetry(this.apiData.routes, routesPayload.routes || [], 'route');
                routesOk = true;
            }
            if (bRes.ok) {
                const busesPayload = await bRes.json();
                this.apiData.buses = preserveNonEmptyTelemetry(this.apiData.buses, busesPayload.buses || [], 'bus');
                busesOk = true;
            }
            if (oRes.ok) this.apiData.occupancy = await oRes.json() || {};

            this.apiData.buses = (this.apiData.buses || []).map(bus => {
                const occ = this.apiData.occupancy[String(bus.bus_id)];
                if (occ && occ.occupancy_percentage != null) {
                    bus.occupancy_pct = occ.occupancy_percentage;
                    bus.occupancy_level = occ.occupancy_level || bus.occupancy_level;
                }
                return bus;
            });

            this.populateDatalist();
            this.updateTotalBusesBadge();
            this.updateFleetSummary();

            const searchScreen = document.getElementById('screen-search-bus');
            if (searchScreen && !searchScreen.classList.contains('d-none')) {
                this.handleSearchBus();
            }

            const fleetElement = document.getElementById('fleetInputBus');
            const fleetInput = fleetElement ? fleetElement.value.trim() : '';
            const fleetScreen = document.getElementById('screen-live-fleet');

            if (fleetInput && fleetScreen && !fleetScreen.classList.contains('d-none')) {
                this.handleFleetStatus();
            }

        } catch (err) {
            console.error("Telemetry API Error:", err);
        } finally {
            this.dataLoaded = true;
            if (!routesOk && document.getElementById('dynamic-routes-container')) {
                const rc = document.getElementById('dynamic-routes-container');
                if (rc.querySelector('.spinner-border')) {
                    rc.innerHTML = '<div class="col-12"><div class="alert alert-warning text-center">Unable to load routes. Please refresh.</div></div>';
                }
            }
        }
    },

    findRouteForBus: function(bus) {
        return (this.apiData.routes || []).find(r =>
            r.route_id === bus.route_id ||
            (bus.route_code && r.route_code === bus.route_code)
        );
    },

    updateFleetSummary: function() {
        const summaryContainer = document.getElementById('fleet-summary-metrics');
        if (!summaryContainer) return;

        const total = this.apiData.buses.length;
        let running = 0, delayed = 0, maintenance = 0, offline = 0;

        this.apiData.buses.forEach(b => {
            if (b.service_status === 'completed' || b.bus_status === 'OFFLINE' || b.service_status === 'offline') offline++;
            else if (b.service_status === 'maintenance') maintenance++;
            else if (b.service_status === 'delayed') delayed++;
            else running++;
        });

        summaryContainer.innerHTML = `
            <div class="col-4 col-md-2">
                <div class="card glass-panel text-center p-2 border-primary">
                    <h5 class="text-white mb-0 fw-bold">${total}</h5>
                    <small class="text-muted text-uppercase" style="font-size: 0.65rem;">Active</small>
                </div>
            </div>
            <div class="col-4 col-md-2">
                <div class="card glass-panel text-center p-2 border-success">
                    <h5 class="text-success mb-0 fw-bold">${running}</h5>
                    <small class="text-muted text-uppercase" style="font-size: 0.65rem;">Running</small>
                </div>
            </div>
            <div class="col-4 col-md-2">
                <div class="card glass-panel text-center p-2 border-danger">
                    <h5 class="text-danger mb-0 fw-bold">${delayed}</h5>
                    <small class="text-muted text-uppercase" style="font-size: 0.65rem;">Delayed</small>
                </div>
            </div>
            <div class="col-6 col-md-3">
                <div class="card glass-panel text-center p-2 border-warning">
                    <h5 class="text-warning mb-0 fw-bold">${maintenance}</h5>
                    <small class="text-muted text-uppercase" style="font-size: 0.65rem;">Maintenance</small>
                </div>
            </div>
            <div class="col-6 col-md-3">
                <div class="card glass-panel text-center p-2 border-secondary">
                    <h5 class="text-secondary mb-0 fw-bold">${offline}</h5>
                    <small class="text-muted text-uppercase" style="font-size: 0.65rem;">Offline</small>
                </div>
            </div>
        `;
    },

    updateTotalBusesBadge: function() {
        const badge = document.getElementById('total-buses-badge');
        if (badge && this.apiData.buses) {
            badge.textContent = `Total Available Buses: ${this.apiData.buses.length}`;
        }
    },

    populateDatalist: function() {
        const stops = new Set();
        this.apiData.routes.forEach(r => {
            if (r.stops && r.stops.length > 0) {
                r.stops.forEach(s => stops.add(s.name || s.stop_name));
            } else {
                if (r.source_stop) stops.add(r.source_stop);
                if (r.destination_stop) stops.add(r.destination_stop);
            }
        });
        const dl = document.getElementById('hubStopSuggestions');
        if (dl) {
            let html = '';
            Array.from(stops).sort().forEach(s => {
                html += `<option value="${escapeHtml(s)}"></option>`;
            });
            dl.innerHTML = html;
        }
    },

    showScreen: function(screenId) {
        document.getElementById('feature-hub').classList.add('d-none');
        document.querySelectorAll('.feature-screen').forEach(el => {
            el.classList.add('d-none');
            el.classList.remove('active-screen');
        });

        const target = document.getElementById(screenId);
        if (target) {
            target.classList.remove('d-none');
            target.classList.add('active-screen');

            if (screenId === 'screen-search-bus') {
                this.handleSearchBus();
            } else if (screenId === 'screen-routes') {
                loadAssignedRoutes();
            } else if (screenId === 'screen-live-fleet') {
                this.updateFleetSummary();
            }
        }
    },

    goHome: function() {
        document.querySelectorAll('.feature-screen').forEach(el => {
            el.classList.add('d-none');
            el.classList.remove('active-screen');
        });
        document.getElementById('feature-hub').classList.remove('d-none');

        const searchRes = document.getElementById('searchResults');
        if (searchRes) searchRes.innerHTML = '';

        const fleetRes = document.getElementById('fleetStatusResults');
        if (fleetRes) {
            fleetRes.innerHTML = `
            <div class="col-12">
                <div class="alert alert-info bg-dark border-secondary text-info text-center">
                    Search a Bus ID or Bus Number
                </div>
            </div>`;
        }

        ['searchSrc', 'searchDst', 'fleetInputBus', 'trkSearchBusId'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        this.updateTotalBusesBadge();
    },

    renderBusCards: function(buses, containerId) {
        const resultsDiv = document.getElementById(containerId);
        if (!resultsDiv) return;
        resultsDiv.innerHTML = '';

        if (buses.length === 0) {
            resultsDiv.innerHTML = '<div class="col-12"><div class="alert alert-dark text-center border-secondary text-muted">No buses available matching your criteria.</div></div>';
            return;
        }

        buses.forEach(bus => {
            const route = this.findRouteForBus(bus);
            const routeName = route ? route.route_name : (bus.route_name || bus.route_code || 'Unknown Route');
            const routeCode = bus.route_code || (route && route.route_code) || 'Unknown Code';
            const departure = bus.departure_time || (route && route.departure_time) || '--';
            const arrival = bus.arrival_time || (route && route.arrival_time) || '--';
            const duration = bus.journey_duration || (route && route.journey_duration) || '--';
            const updatedArrival = bus.updated_arrival_time || arrival;
            const currentDelay = bus.current_delay_label || `${bus.current_delay_minutes || 0} min`;
            const updatedEta = etaDisplay(bus);
            const liveStatus = busStatusMeta(bus);
            const tripStatus = liveStatus.text === 'Trip Completed' ? 'Trip Completed' : (bus.trip_status || bus.schedule_status || bus.status || 'ACTIVE');

            let statusColor = "bg-success";
            if (bus.status === "AT BUS STAND" || bus.status === "AT STOP") statusColor = "bg-warning text-dark";
            if (bus.status === "ARRIVED TERMINAL" || bus.status === "ARRIVED") statusColor = "bg-secondary";
            if (bus.status === "DELAYED") statusColor = "bg-danger";
            if (bus.status === "RETURN TRIP") statusColor = "bg-info text-dark";
            if (bus.service_status === "completed") statusColor = "bg-secondary";
            if (bus.service_status === "offline" || bus.service_status === "maintenance") statusColor = "bg-secondary";

            const driverCode = displayDriverCode(bus);
            const occupancy = occupancyMeta(bus);

            const trackUrl = `/tracking/${encodeURIComponent(bus.bus_number)}?source=search`;
            
            let trackButtonHtml = '';
            if (bus.trip_status === 'WAITING_TO_DEPART') {
                trackButtonHtml = `<button class="btn btn-sm btn-info w-100 fw-bold text-dark shadow-sm" disabled title="Tracking will be available once the driver starts the trip.">Track Bus</button>`;
            } else {
                trackButtonHtml = `<a href="${trackUrl}" class="btn btn-sm btn-info w-100 fw-bold text-dark shadow-sm">${bus.service_status === 'completed' || bus.trip_status === 'RETURN_COMPLETED' || bus.trip_status === 'COMPLETED' ? 'View Trip Completed' : 'Track Bus'}</a>`;
            }

            resultsDiv.innerHTML += `
                <div class="col-12 col-md-6 col-lg-4">
                    <div class="card glass-panel h-100 shadow-sm" style="border: 1px solid rgba(52,210,255,0.25); background: linear-gradient(135deg, rgba(11,29,54,0.8), rgba(4,11,24,0.9));">
                        <div class="card-body p-3 d-flex flex-column">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <div>
                                    <h5 class="text-white fw-bold m-0">${escapeHtml(bus.bus_number)} <small class="text-muted fs-6">(ID: ${bus.bus_id})</small></h5>
                                    <div class="text-info fw-bold small">${escapeHtml(routeCode)}</div>
                                    <div class="text-white-50 small" style="font-size: 0.75rem;">${escapeHtml(routeName)}</div>
                                </div>
                                <div class="text-end">
                                    <span class="badge ${liveStatus.badge} shadow-sm text-uppercase d-block mb-1" style="font-size:0.65rem;">${escapeHtml(liveStatus.live)}</span>
                                    <span class="badge ${statusColor} shadow-sm text-uppercase" style="font-size:0.65rem;">${escapeHtml(tripStatus)}</span>
                                </div>
                            </div>

                            <div class="mt-2 mb-3 bg-dark bg-opacity-50 p-2 rounded border border-secondary">
                                <p class="m-0 text-muted small mb-1">Route: <span class="text-light fw-bold">${escapeHtml(routeName)}</span></p>
                                <p class="m-0 text-muted small mb-1">Driver: <span class="text-info fw-bold">${escapeHtml(driverCode)}</span></p>
                                <p class="m-0 text-muted small mb-1">Current: <span class="text-light fw-bold">${escapeHtml(bus.current_stop || '--')}</span></p>
                                <p class="m-0 text-muted small">Next: <span class="text-light fw-bold">${escapeHtml(bus.next_stop || 'Calculating...')}</span> <span class="text-warning fw-bold">(${escapeHtml(updatedEta)})</span></p>
                                <p class="m-0 text-muted small">Schedule: <span class="text-info">${escapeHtml(departure)}</span> → <span class="text-info">${escapeHtml(updatedArrival)}</span> <span class="text-warning fw-bold">(${escapeHtml(duration)})</span></p>
                                <p class="m-0 text-muted small">Delay: <span class="text-warning fw-bold">${escapeHtml(currentDelay)}</span> | Status: <span class="text-info fw-bold">${escapeHtml(tripStatus)}</span></p>
                            </div>

                            <div class="d-flex justify-content-between mb-3 mt-auto">
                                <div class="text-center">
                                    <small class="text-muted d-block text-uppercase" style="font-size:0.65rem">Occupancy</small>
                                    <span class="fw-bold" style="color:${occupancy.color}">${occupancy.pct}% (${occupancy.level})</span>
                                </div>
                                <div class="text-center border-start border-end border-secondary px-3">
                                    <small class="text-muted d-block text-uppercase" style="font-size:0.65rem">ETA</small>
                                    <span class="text-warning fw-bold">${escapeHtml(updatedEta)}</span>
                                </div>
                                <div class="text-center">
                                    <small class="text-muted d-block text-uppercase" style="font-size:0.65rem">Dist Left</small>
                                    <span class="text-white fw-bold">${bus.distance_remaining_km || 0} km</span>
                                </div>
                            </div>

                            <div class="mt-2 text-end">
                                ${trackButtonHtml}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
    },

    handleSearchBus: function() {
        const srcElement = document.getElementById('searchSrc');
        const dstElement = document.getElementById('searchDst');

        const src = srcElement ? srcElement.value.toLowerCase().trim() : '';
        const dst = dstElement ? dstElement.value.toLowerCase().trim() : '';

        const resultsDiv = document.getElementById('searchResults');
        if (!resultsDiv) return;

        if (!this.dataLoaded) {
            resultsDiv.innerHTML = '<div class="col-12 text-center py-4"><div class="spinner-border text-info"></div><p class="text-muted mt-2">Loading live fleet...</p></div>';
            setTimeout(() => {
                if (!this.dataLoaded) {
                    resultsDiv.innerHTML = '<div class="col-12"><div class="alert alert-warning text-center">Fleet data is taking longer than expected. Please wait or refresh.</div></div>';
                }
            }, 8000);
            return;
        }

        if (!this.apiData.buses || this.apiData.buses.length === 0) {
            resultsDiv.innerHTML = '<div class="col-12"><div class="alert alert-dark text-center border-secondary text-muted">No active buses in the fleet right now. Try again shortly.</div></div>';
            return;
        }

        if (!src && !dst) {
            this.renderBusCards(this.apiData.buses, 'searchResults');
            return;
        }

        const validRouteIds = new Set();

        this.apiData.routes.forEach(route => {
            if (!route.stops || route.stops.length === 0) {
                const origin = (route.source_stop || "").toLowerCase();
                const dest = (route.destination_stop || "").toLowerCase();

                if ((!src || origin.includes(src)) && (!dst || dest.includes(dst))) {
                    validRouteIds.add(route.route_id);
                }
                return;
            }

            const stopNames = route.stops.map(s => (s.name || s.stop_name || '').toLowerCase());
            const srcIdx = src ? stopNames.findIndex(name => name.includes(src)) : 0;
            const dstIdx = dst ? stopNames.findIndex(name => name.includes(dst)) : stopNames.length - 1;

            if (srcIdx >= 0 && dstIdx >= 0 && srcIdx < dstIdx) {
                validRouteIds.add(route.route_id);
            }
        });

        if (validRouteIds.size === 0) {
            resultsDiv.innerHTML = '<div class="col-12"><div class="alert alert-warning bg-dark border-secondary text-warning text-center">No buses found for selected route.</div></div>';
            return;
        }

        const activeBuses = this.apiData.buses.filter(b => validRouteIds.has(b.route_id));

        if (activeBuses.length === 0) {
            resultsDiv.innerHTML = '<div class="col-12"><div class="alert alert-info bg-dark border-secondary text-info text-center">No buses found for selected route.</div></div>';
            return;
        }

        this.renderBusCards(activeBuses, 'searchResults');
    },

    handleFleetStatus: function() {
        const fleetInputElement = document.getElementById('fleetInputBus');
        if (!fleetInputElement) return;

        const bInput = fleetInputElement.value.toLowerCase().trim();
        const res = document.getElementById('fleetStatusResults');
        if (!res) return;
        res.innerHTML = '';

        if (!bInput) return;

        if (!this.apiData.buses || this.apiData.buses.length === 0) {
            if (!this.dataLoaded) {
                res.innerHTML = '<div class="col-12"><div class="alert alert-info text-center">Loading fleet data...</div></div>';
            } else {
                res.innerHTML = '<div class="col-12"><div class="alert alert-warning bg-dark text-warning border-secondary text-center">No active buses in fleet.</div></div>';
            }
            return;
        }

        let targetBuses = this.apiData.buses.filter(b =>
            b.bus_id.toString() === bInput ||
            (b.registration_number && b.registration_number.toLowerCase().includes(bInput)) ||
            (b.bus_number && b.bus_number.toLowerCase().includes(bInput))
        );

        if (targetBuses.length === 0) {
            res.innerHTML = '<div class="col-12"><div class="alert alert-warning bg-dark text-warning border-secondary text-center">No vehicle found matching this ID or Number.</div></div>';
            return;
        }

        targetBuses.forEach(bus => {
            let statusColor = "bg-success";
            if (bus.status === "AT BUS STAND" || bus.status === "AT STOP") statusColor = "bg-warning text-dark";
            if (bus.status === "ARRIVED TERMINAL" || bus.status === "ARRIVED") statusColor = "bg-secondary";
            if (bus.status === "DELAYED") statusColor = "bg-danger";
            if (bus.status === "RETURN TRIP") statusColor = "bg-info text-dark";
            if (bus.service_status === "completed") statusColor = "bg-secondary";
            if (bus.service_status === "offline" || bus.service_status === "maintenance") statusColor = "bg-secondary";

            const driverCode = displayDriverCode(bus);
            const occupancy = occupancyMeta(bus);
            const departure = bus.departure_time || '--';
            const arrival = bus.arrival_time || '--';
            const updatedArrival = bus.updated_arrival_time || arrival;
            const duration = bus.journey_duration || '--';
            const updatedEta = etaDisplay(bus);
            const currentDelay = bus.current_delay_label || `${bus.current_delay_minutes || 0} min`;
            const liveStatus = busStatusMeta(bus);
            const tripStatus = liveStatus.text === 'Trip Completed' ? 'Trip Completed' : (bus.trip_status || bus.schedule_status || bus.status || 'ACTIVE');

            const trackUrl = `/tracking/${encodeURIComponent(bus.bus_number)}?source=live_fleet`;

            res.innerHTML += `
                <div class="col-12">
                    <div class="card glass-panel border-primary shadow-sm">
                        <div class="card-body p-4">
                            <div class="d-flex justify-content-between align-items-start mb-3">
                                <div>
                                    <h4 class="text-white fw-bold mb-1">${escapeHtml(bus.bus_number)} <span class="badge bg-secondary ms-2" style="font-size:0.8rem;vertical-align:middle;">ID: ${bus.bus_id}</span></h4>
                                    <p class="text-primary mb-0 fw-bold fs-5">${escapeHtml(bus.route_name || bus.route_code || '')}</p>
                                </div>
                                <div class="text-end">
                                    <span class="badge ${liveStatus.badge} p-2 text-uppercase fs-6 shadow d-block mb-2">${escapeHtml(liveStatus.live)}</span>
                                    <span class="badge ${statusColor} p-2 text-uppercase fs-6 shadow">${escapeHtml(tripStatus)}</span>
                                </div>
                            </div>

                            <div class="row g-3 bg-dark bg-opacity-75 p-3 rounded-3 border border-secondary mb-4 text-center">
                                <div class="col-6 col-md-3 border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Driver</small>
                                    <strong class="text-info fs-6">${escapeHtml(driverCode)}</strong>
                                </div>
                                <div class="col-6 col-md-3 border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Current Stop</small>
                                    <strong class="text-white fs-6">${escapeHtml(bus.current_stop || '--')}</strong>
                                </div>
                                <div class="col-6 col-md-3 border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Next Stop</small>
                                    <strong class="text-white fs-6">${escapeHtml(bus.next_stop || '--')}</strong>
                                </div>
                                <div class="col-6 col-md-3">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">ETA</small>
                                    <strong class="text-warning fs-5">${escapeHtml(updatedEta)}</strong>
                                </div>

                                <div class="col-12 m-0 p-0"><hr class="border-secondary my-2 opacity-25"></div>

                                <div class="col-6 col-md-4 border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Distance Left</small>
                                    <strong class="text-white fs-6">${bus.distance_remaining_km || 0} km</strong>
                                </div>
                                <div class="col-6 col-md-4 border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Occupancy</small>
                                    <strong class="fs-6" style="color:${occupancy.color}">${occupancy.pct}% (${occupancy.level})</strong>
                                </div>
                                <div class="col-12 col-md-4">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Speed</small>
                                    <strong class="text-info fs-6">${bus.speed} km/h</strong>
                                </div>
                                <div class="col-12 m-0 p-0"><hr class="border-secondary my-2 opacity-25"></div>
                                <div class="col-4">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Departure</small>
                                    <strong class="text-info fs-6">${escapeHtml(departure)}</strong>
                                </div>
                                <div class="col-4 border-start border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Arrival</small>
                                    <strong class="text-info fs-6">${escapeHtml(updatedArrival)}</strong>
                                </div>
                                <div class="col-4">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Duration</small>
                                    <strong class="text-warning fs-6">${escapeHtml(duration)}</strong>
                                </div>
                                <div class="col-12">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Current Delay</small>
                                    <strong class="text-warning fs-6">${escapeHtml(currentDelay)}</strong>
                                </div>
                            </div>
                            <div class="text-end">
                                <a href="${trackUrl}" class="btn btn-primary px-4 fw-bold shadow-sm">${bus.service_status === 'completed' ? 'View Trip Completed' : 'Track Live in Map'}</a>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
    },

    handleLiveTrackingSearch: function() {
        const trkInput = document.getElementById('trkSearchBusId');
        if (!trkInput) return;

        const bInput = trkInput.value.trim();
        if (!bInput) return;

        window.location.assign(`/tracking/${encodeURIComponent(bInput)}?source=live_tracking`);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    Workflow.init();
    loadAssignedRoutes();
});
