/* static/js/passenger-flow.js */

function displayDriverCode(bus) {
    return (bus && (bus.assigned_driver_code || bus.driver_id)) || 'Unassigned';
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
                 data-route-code="${window.TransPulseUtils.escapeHtml(route.route_code)}"
                 data-origin="${window.TransPulseUtils.escapeHtml(origin)}"
                 data-dest="${window.TransPulseUtils.escapeHtml(dest)}">
                <div class="card-body p-3">
                    <h6 class="text-info fw-bold mb-1">${window.TransPulseUtils.escapeHtml(route.route_code)}</h6>
                    <p class="text-white mb-1 fs-6">${window.TransPulseUtils.escapeHtml(route.route_name || route.route_code)}</p>
                    <p class="text-white-50 mb-2 small">Distance: <span class="text-light fw-bold">${window.TransPulseUtils.escapeHtml(route.distance_km || '0.0')} km</span></p>
                    <p class="text-white-50 mb-2 small">Departure: <span class="text-info">${window.TransPulseUtils.escapeHtml(departure)}</span> | Arrival: <span class="text-info">${window.TransPulseUtils.escapeHtml(arrival)}</span> | Duration: <span class="text-warning">${window.TransPulseUtils.escapeHtml(duration)}</span></p>
                    <div class="d-flex justify-content-between">
                        <small class="text-warning fw-bold">ETA: ${window.TransPulseUtils.escapeHtml(eta)}</small>
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
        if (this.dataInterval) clearInterval(this.dataInterval);
        this.dataInterval = setInterval(() => this.fetchData(), 3000);

        this.pollNotifications();
        if (this.notificationInterval) clearInterval(this.notificationInterval);
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
        this.availableStops = Array.from(stops).sort();
        
        this.initAutocomplete('searchSrc', 'searchSrcDropdown');
        this.initAutocomplete('searchDst', 'searchDstDropdown');
    },

    initAutocomplete: function(inputId, dropdownId) {
        const input = document.getElementById(inputId);
        const dropdown = document.getElementById(dropdownId);
        if (!input || !dropdown) return;

        let activeIndex = -1;
        let currentSuggestions = [];

        const renderSuggestions = (query) => {
            dropdown.innerHTML = '';
            activeIndex = -1;
            
            if (!query) {
                dropdown.classList.add('d-none');
                return;
            }

            const lowerQuery = query.toLowerCase();
            currentSuggestions = this.availableStops
                .filter(stop => stop.toLowerCase().includes(lowerQuery))
                .slice(0, 10);

            if (currentSuggestions.length === 0) {
                dropdown.classList.add('d-none');
                return;
            }

            currentSuggestions.forEach((stop, index) => {
                const item = document.createElement('div');
                item.className = 'autocomplete-item';
                item.textContent = stop;
                item.addEventListener('click', (e) => {
                    input.value = stop;
                    dropdown.classList.add('d-none');
                    const errEl = document.getElementById(inputId + 'Error');
                    if (errEl) errEl.classList.add('d-none');
                    // Focus input so user knows it's selected
                    input.focus();
                });
                dropdown.appendChild(item);
            });
            dropdown.classList.remove('d-none');
        };

        const setActive = (items) => {
            if (!items || items.length === 0) return;
            Array.from(items).forEach(item => item.classList.remove('active'));
            if (activeIndex >= items.length) activeIndex = 0;
            if (activeIndex < 0) activeIndex = items.length - 1;
            items[activeIndex].classList.add('active');
            items[activeIndex].scrollIntoView({ block: 'nearest' });
        };

        input.addEventListener('input', () => {
            const errEl = document.getElementById(inputId + 'Error');
            if (errEl) errEl.classList.add('d-none');
            renderSuggestions(input.value.trim());
        });

        input.addEventListener('keydown', (e) => {
            const items = dropdown.getElementsByClassName('autocomplete-item');
            if (e.key === 'ArrowDown') {
                activeIndex++;
                setActive(items);
                e.preventDefault();
            } else if (e.key === 'ArrowUp') {
                activeIndex--;
                setActive(items);
                e.preventDefault();
            } else if (e.key === 'Enter') {
                if (activeIndex > -1 && !dropdown.classList.contains('d-none')) {
                    e.preventDefault();
                    items[activeIndex].click();
                }
            } else if (e.key === 'Escape') {
                dropdown.classList.add('d-none');
                activeIndex = -1;
            }
        });

        input.addEventListener('focus', () => {
            if (input.value.trim().length > 0) {
                renderSuggestions(input.value.trim());
            }
        });

        document.addEventListener('click', (e) => {
            if (e.target !== input && e.target !== dropdown) {
                dropdown.classList.add('d-none');
            }
        });
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
            const updatedEta = window.TransPulseUtils.etaDisplay(bus);
            const liveStatus = window.TransPulseUtils.busStatusMeta(bus);
            const tripStatus = liveStatus.text === 'Trip Completed' ? 'Trip Completed' : (bus.trip_status || bus.schedule_status || bus.status || 'ACTIVE');

            let statusColor = "bg-success";
            if (bus.status === "AT BUS STAND" || bus.status === "AT STOP") statusColor = "bg-warning text-dark";
            if (bus.status === "ARRIVED TERMINAL" || bus.status === "ARRIVED") statusColor = "bg-secondary";
            if (bus.status === "DELAYED") statusColor = "bg-danger";
            if (bus.status === "RETURN TRIP") statusColor = "bg-info text-dark";
            if (bus.service_status === "completed") statusColor = "bg-secondary";
            if (bus.service_status === "offline" || bus.service_status === "maintenance") statusColor = "bg-secondary";

            const driverCode = displayDriverCode(bus);
            const occupancy = window.TransPulseUtils.occupancyMeta(bus);

            const trackUrl = `/tracking/${encodeURIComponent(bus.bus_number)}?source=search`;
            const trackButtonHtml = `<a href="${trackUrl}" class="btn btn-sm btn-info w-100 fw-bold text-dark shadow-sm">${bus.service_status === 'completed' || bus.trip_status === 'RETURN_COMPLETED' || bus.trip_status === 'COMPLETED' ? 'View Trip Completed' : 'Track Bus'}</a>`;

            resultsDiv.innerHTML += `
                <div class="col-12 col-md-6 col-lg-4">
                    <div class="card glass-panel h-100 shadow-sm" style="border: 1px solid rgba(52,210,255,0.25); background: linear-gradient(135deg, rgba(11,29,54,0.8), rgba(4,11,24,0.9));">
                        <div class="card-body p-3 d-flex flex-column">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <div>
                                    <h5 class="text-white fw-bold m-0">${window.TransPulseUtils.escapeHtml(bus.bus_number)} <small class="text-muted fs-6">(ID: ${bus.bus_id})</small></h5>
                                    <div class="text-info fw-bold small">${window.TransPulseUtils.escapeHtml(routeCode)}</div>
                                    <div class="text-white-50 small" style="font-size: 0.75rem;">${window.TransPulseUtils.escapeHtml(routeName)}</div>
                                </div>
                                <div class="text-end">
                                    <span class="badge ${liveStatus.badge} shadow-sm text-uppercase d-block mb-1" style="font-size:0.65rem;">${window.TransPulseUtils.escapeHtml(liveStatus.live)}</span>
                                    <span class="badge ${statusColor} shadow-sm text-uppercase" style="font-size:0.65rem;">${window.TransPulseUtils.escapeHtml(tripStatus)}</span>
                                </div>
                            </div>

                            <div class="mt-2 mb-3 bg-dark bg-opacity-50 p-2 rounded border border-secondary">
                                <p class="m-0 text-muted small mb-1">Route: <span class="text-light fw-bold">${window.TransPulseUtils.escapeHtml(routeName)}</span></p>
                                <p class="m-0 text-muted small mb-1">Driver: <span class="text-info fw-bold">${window.TransPulseUtils.escapeHtml(driverCode)}</span></p>
                                <p class="m-0 text-muted small mb-1">Current: <span class="text-light fw-bold">${window.TransPulseUtils.escapeHtml(bus.current_stop || '--')}</span></p>
                                <p class="m-0 text-muted small">Next: <span class="text-light fw-bold">${window.TransPulseUtils.escapeHtml(bus.next_stop || 'Calculating...')}</span> <span class="text-warning fw-bold">(${window.TransPulseUtils.escapeHtml(updatedEta)})</span></p>
                                <p class="m-0 text-muted small">Schedule: <span class="text-info">${window.TransPulseUtils.escapeHtml(departure)}</span> → <span class="text-info">${window.TransPulseUtils.escapeHtml(updatedArrival)}</span> <span class="text-warning fw-bold">(${window.TransPulseUtils.escapeHtml(duration)})</span></p>
                                <p class="m-0 text-muted small">Delay: <span class="text-warning fw-bold">${window.TransPulseUtils.escapeHtml(currentDelay)}</span> | Status: <span class="text-info fw-bold">${window.TransPulseUtils.escapeHtml(tripStatus)}</span></p>
                            </div>

                            <div class="d-flex justify-content-between mb-3 mt-auto">
                                <div class="text-center">
                                    <small class="text-muted d-block text-uppercase" style="font-size:0.65rem">Occupancy</small>
                                    <span class="fw-bold" style="color:${occupancy.color}">${occupancy.pct}% (${occupancy.level})</span>
                                </div>
                                <div class="text-center border-start border-end border-secondary px-3">
                                    <small class="text-muted d-block text-uppercase" style="font-size:0.65rem">ETA</small>
                                    <span class="text-warning fw-bold">${window.TransPulseUtils.escapeHtml(updatedEta)}</span>
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

        let hasError = false;
        if (src) {
            const srcExists = this.availableStops && this.availableStops.some(s => s.toLowerCase() === src);
            if (!srcExists) {
                const errEl = document.getElementById('searchSrcError');
                if (errEl) {
                    errEl.classList.remove('d-none');
                    errEl.textContent = 'Source stop not found.';
                }
                hasError = true;
            }
        }
        if (dst) {
            const dstExists = this.availableStops && this.availableStops.some(s => s.toLowerCase() === dst);
            if (!dstExists) {
                const errEl = document.getElementById('searchDstError');
                if (errEl) {
                    errEl.classList.remove('d-none');
                    errEl.textContent = 'Destination stop not found.';
                }
                hasError = true;
            }
        }
        if (hasError) {
            const resultsDiv = document.getElementById('searchResults');
            if (resultsDiv) resultsDiv.innerHTML = '';
            return;
        }

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
            const occupancy = window.TransPulseUtils.occupancyMeta(bus);
            const departure = bus.departure_time || '--';
            const arrival = bus.arrival_time || '--';
            const updatedArrival = bus.updated_arrival_time || arrival;
            const duration = bus.journey_duration || '--';
            const updatedEta = window.TransPulseUtils.etaDisplay(bus);
            const currentDelay = bus.current_delay_label || `${bus.current_delay_minutes || 0} min`;
            const liveStatus = window.TransPulseUtils.busStatusMeta(bus);
            const tripStatus = liveStatus.text === 'Trip Completed' ? 'Trip Completed' : (bus.trip_status || bus.schedule_status || bus.status || 'ACTIVE');

            const trackUrl = `/tracking/${encodeURIComponent(bus.bus_number)}?source=live_fleet`;

            res.innerHTML += `
                <div class="col-12">
                    <div class="card glass-panel border-primary shadow-sm">
                        <div class="card-body p-4">
                            <div class="d-flex justify-content-between align-items-start mb-3">
                                <div>
                                    <h4 class="text-white fw-bold mb-1">${window.TransPulseUtils.escapeHtml(bus.bus_number)} <span class="badge bg-secondary ms-2" style="font-size:0.8rem;vertical-align:middle;">ID: ${bus.bus_id}</span></h4>
                                    <p class="text-primary mb-0 fw-bold fs-5">${window.TransPulseUtils.escapeHtml(bus.route_name || bus.route_code || '')}</p>
                                </div>
                                <div class="text-end">
                                    <span class="badge ${liveStatus.badge} p-2 text-uppercase fs-6 shadow d-block mb-2">${window.TransPulseUtils.escapeHtml(liveStatus.live)}</span>
                                    <span class="badge ${statusColor} p-2 text-uppercase fs-6 shadow">${window.TransPulseUtils.escapeHtml(tripStatus)}</span>
                                </div>
                            </div>

                            <div class="row g-3 bg-dark bg-opacity-75 p-3 rounded-3 border border-secondary mb-4 text-center">
                                <div class="col-6 col-md-3 border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Driver</small>
                                    <strong class="text-info fs-6">${window.TransPulseUtils.escapeHtml(driverCode)}</strong>
                                </div>
                                <div class="col-6 col-md-3 border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Current Stop</small>
                                    <strong class="text-white fs-6">${window.TransPulseUtils.escapeHtml(bus.current_stop || '--')}</strong>
                                </div>
                                <div class="col-6 col-md-3 border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Next Stop</small>
                                    <strong class="text-white fs-6">${window.TransPulseUtils.escapeHtml(bus.next_stop || '--')}</strong>
                                </div>
                                <div class="col-6 col-md-3">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">ETA</small>
                                    <strong class="text-warning fs-5">${window.TransPulseUtils.escapeHtml(updatedEta)}</strong>
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
                                    <strong class="text-info fs-6">${window.TransPulseUtils.escapeHtml(departure)}</strong>
                                </div>
                                <div class="col-4 border-start border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Arrival</small>
                                    <strong class="text-info fs-6">${window.TransPulseUtils.escapeHtml(updatedArrival)}</strong>
                                </div>
                                <div class="col-4">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Duration</small>
                                    <strong class="text-warning fs-6">${window.TransPulseUtils.escapeHtml(duration)}</strong>
                                </div>
                                <div class="col-12">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Current Delay</small>
                                    <strong class="text-warning fs-6">${window.TransPulseUtils.escapeHtml(currentDelay)}</strong>
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


// --- Extracted from passenger_dashboard.html ---
// ----------------------------------------------------
    // ESC & Click-Outside Modal Handlers (Items 9 & 10)
    // ----------------------------------------------------
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeRouteModal();
            cancelPremiumSOS();
        }
    });

    window.addEventListener("click", (e) => {
        const routeModal = document.getElementById('routeDetailsModal');
        const sosModal = document.getElementById('sos-premium-modal');
        if (e.target === routeModal) closeRouteModal();
        if (e.target === sosModal) cancelPremiumSOS();
    });

    // ----------------------------------------------------
    // NEXT-LEVEL: Interactive Route Layout Modal Logic
    // ----------------------------------------------------
    async function showRouteDetails(routeCode, originName, destName) {
        document.body.classList.add('modal-open');
        document.getElementById('routeDetailsModal').style.display = 'flex';

        // Temporarily set forward direction title; will be updated once buses are loaded
        document.getElementById('route-modal-title').innerHTML = `
            <div class="text-info fw-bold">${routeCode}</div>
            <div class="text-white-50 small mt-1">${originName} ➜ ${destName}</div>
        `;
        
        const busesContainer = document.getElementById('route-modal-buses');
        const stopsContainer = document.getElementById('route-modal-stops');
        
        busesContainer.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-info spinner-border-sm"></div><p class="text-muted small mt-2">Searching live telemetry grid...</p></div>';
        stopsContainer.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-info spinner-border-sm"></div><p class="text-muted small mt-2">Loading route path configuration...</p></div>';
        
        try {
            const [routesRes, busesRes] = await Promise.all([
                fetch('/api/routes/live'),
                fetch('/api/buses/live')
            ]);
            
            const routesData = routesRes.ok ? await routesRes.json() : { routes: [] };
            const busesData = busesRes.ok ? await busesRes.json() : { buses: [] };
            const cachedRoutes = window.Workflow?.apiData?.routes || [];
            const cachedBuses = window.Workflow?.apiData?.buses || [];
            const routes = (routesData.routes && routesData.routes.length) ? routesData.routes : cachedRoutes;
            const buses = (busesData.buses && busesData.buses.length) ? busesData.buses : cachedBuses;
            const normalizeRouteValue = value => String(value ?? '').trim().toLowerCase();
            const selectedRouteCode = normalizeRouteValue(routeCode);
            
            const targetRoute = routes.find(r => normalizeRouteValue(r.route_code) === selectedRouteCode);
            
            let activeBuses = [];
            if(targetRoute) {
                const targetRouteId = normalizeRouteValue(targetRoute.route_id);
                const targetRouteCode = normalizeRouteValue(targetRoute.route_code);
                activeBuses = buses.filter(b => {
                    const busRouteId = normalizeRouteValue(b.route_id);
                    const busRouteCode = normalizeRouteValue(b.route_code);
                    return (
                        (targetRouteId && busRouteId && busRouteId === targetRouteId) ||
                        (targetRouteCode && busRouteCode && busRouteCode === targetRouteCode)
                    );
                });
                if (activeBuses.length === 0 && Number(targetRoute.active_bus_count || 0) > 0) {
                    console.warn('Route has assigned bus count but no bus matched modal filter.', {
                        route_id: targetRoute.route_id,
                        route_code: targetRoute.route_code,
                        bus_routes: buses.map(b => ({ bus_number: b.bus_number, route_id: b.route_id, route_code: b.route_code }))
                    });
                }
            }
            
            if(activeBuses.length > 0) {
                // Update modal title to reflect direction of the active bus
                const activeBus0 = activeBuses[0];
                const isReturnTrip = activeBus0 && (
                    Number(activeBus0.direction_id) === 1 ||
                    ['RETURN_READY', 'RETURN_RUNNING', 'RETURN_COMPLETED'].includes(activeBus0.trip_status)
                );
                const modalTitleEl = document.getElementById('route-modal-title');
                if (modalTitleEl) {
                    const displayOrigin = isReturnTrip ? destName : originName;
                    const displayDest   = isReturnTrip ? originName : destName;
                    const directionBadge = isReturnTrip
                        ? ' <span class="badge bg-info text-dark ms-2" style="font-size:0.7rem;">Return Trip</span>'
                        : '';
                    modalTitleEl.innerHTML = `
                        <div class="text-info fw-bold">${routeCode}${directionBadge}</div>
                        <div class="text-white-50 small mt-1">${displayOrigin} ➜ ${displayDest}</div>
                    `;
                }

                busesContainer.innerHTML = activeBuses.map(b => {
                    const trackBtn = `<a href="/tracking/${encodeURIComponent(b.bus_number)}?source=routes" class="btn btn-sm btn-info fw-bold text-dark">📍 Track</a>`;
                    return `
                        <div class="d-flex justify-content-between align-items-center p-3 mb-2" style="background: rgba(255,255,255,0.03); border: 1px solid rgba(52,210,255,0.15); border-radius: 12px;">
                            <div>
                                <h6 class="text-white fw-bold mb-0">${b.bus_number}</h6>
                                <small class="text-muted">${b.current_stop || '--'} ➜ ${b.next_stop || '--'}</small>
                                <small class="text-muted d-block">Delay: <span class="text-warning">${b.current_delay_label || '0 min'}</span> | ETA: <span class="text-info">${b.updated_eta_minutes || b.eta_minutes || 0} min</span></small>
                            </div>
                            ${trackBtn}
                        </div>
                    `;
                }).join('');
            } else {
                busesContainer.innerHTML = '<span class="text-muted small">No assigned buses are currently available for this route.</span>';
            }
            
            if(targetRoute && targetRoute.stops && targetRoute.stops.length > 0) {
                const activeBus = activeBuses[0];
                const isOffline = activeBus && (activeBus.gps_status === 'Offline' || activeBus.service_status === 'offline' || activeBus.service_status === 'OFFLINE');

                if (isOffline) {
                    stopsContainer.innerHTML = `<div class="p-4 text-center text-muted fw-bold">GPS is Offline. Waiting for the driver to start the trip.</div>`;
                } else {
                    let stopsHtml = `
                        <div class="mb-3 p-3" style="background: rgba(255,255,255,0.03); border: 1px solid rgba(52,210,255,0.12); border-radius: 12px;">
                            <div class="d-flex flex-wrap gap-3 small">
                                <span class="text-muted">Departure: <strong class="text-info">${targetRoute.departure_time || '--'}</strong></span>
                                <span class="text-muted">Arrival: <strong class="text-info">${targetRoute.arrival_time || '--'}</strong></span>
                                <span class="text-muted">Journey Duration: <strong class="text-warning">${targetRoute.journey_duration || '--'}</strong></span>
                            </div>
                        </div>
                        <div class="route-vertical-timeline" style="position: relative; border-left: 2px solid rgba(52, 210, 255, 0.2); margin-left: 12px; padding-left: 25px; padding-top: 5px; padding-bottom: 5px;">`;

                    const stopsToRender = activeBus && activeBus.stops ? activeBus.stops : targetRoute.stops;
                    const currentIdx = activeBus ? (activeBus.current_stop_index != null ? activeBus.current_stop_index : 0) : -1;
                    // tripCompleted: rely strictly on backend trip_status
                    const tripCompleted = activeBus ? (activeBus.trip_status === 'COMPLETED' || activeBus.trip_status === 'RETURN_COMPLETED') : false;

                    stopsToRender.forEach((s, i) => {
                        let dotColor = "#00e5ff"; 
                        let textColor = "text-white-50";
                        let prefix = "○";
                        let subText = "Upcoming Stop";

                        if (tripCompleted || (activeBus && i < currentIdx)) {
                            dotColor = "#22d39a"; 
                            textColor = "text-success fw-bold";
                            prefix = "✔";
                            subText = "Completed Stop";
                        } else if (activeBus && i === currentIdx) {
                            dotColor = "#ffc107"; 
                            textColor = "text-warning fw-bold";
                            prefix = "▶";
                            subText = "Current Stop";
                        } else {
                            if (!activeBus) {
                                if (i === 0) {
                                    dotColor = "#22d39a";
                                    textColor = "text-success fw-bold";
                                    subText = "Origin Point";
                                } else if (i === stopsToRender.length - 1) {
                                    dotColor = "#ff5d6c";
                                    textColor = "text-danger fw-bold";
                                    subText = "Final Destination";
                                }
                            }
                        }

                        stopsHtml += `
                            <div style="position: relative; margin-bottom: ${i === stopsToRender.length - 1 ? '0' : '24px'};">
                                <div style="position: absolute; left: -32px; top: 4px; width: 12px; height: 12px; border-radius: 50%; background: ${dotColor}; box-shadow: 0 0 10px ${dotColor}; border: 2px solid #040b18;"></div>
                                <h6 class="fw-bold mb-0 ${textColor}" style="letter-spacing: 0.5px;">${prefix} ${s.name || s.stop_name}</h6>
                                <small class="text-info d-block" style="font-size: 0.75rem;">${s.scheduled_time || s.arrival_time || '--'}</small>
                                <small class="text-muted" style="font-size: 0.75rem;">${subText}</small>
                            </div>
                        `;
                    });
                    stopsHtml += '</div>';
                    stopsContainer.innerHTML = stopsHtml;
                }
            } else if (targetRoute) {
                stopsContainer.innerHTML = `<div class="text-white text-center py-3"><strong>${targetRoute.source_stop || originName}</strong><br><span class="text-info fs-4">↓</span><br><strong>${targetRoute.destination_stop || destName}</strong></div>`;
            } else {
                stopsContainer.innerHTML = '<span class="text-muted small">Route structural trajectory map unavailable.</span>';
            }
            
        } catch (err) {
            console.error(err);
            busesContainer.innerHTML = '<span class="text-danger small fw-bold">Connection structural error.</span>';
            stopsContainer.innerHTML = '<span class="text-danger small fw-bold">Connection structural error.</span>';
        }
    }

    function closeRouteModal() {
        const modal = document.getElementById('routeDetailsModal');
        if(modal) {
            modal.style.display = 'none';
            document.body.classList.remove('modal-open');
        }
    }

    // ----------------------------------------------------
    // BULLETPROOF GLOBAL CAPTURE INTERCEPTOR 
    // Forces source parameters onto Search results and Live Fleet items dynamically
    // ----------------------------------------------------
    window.addEventListener('click', function(event) {
        const targetLink = event.target.closest('a, button');
        if (!targetLink) return;
        
        let targetUrl = targetLink.getAttribute('href') || targetLink.getAttribute('onclick') || '';
        
        if (targetUrl.includes('/tracking/')) {
            if (targetUrl.includes('source=')) return;
            
            event.preventDefault();
            event.stopPropagation();
            
            let extractedBusId = '';
            const pathSegments = targetUrl.match(/\/tracking\/([^?&#"'\s)]+)/);
            if (pathSegments && pathSegments[1]) {
                extractedBusId = decodeURIComponent(pathSegments[1]);
            } else {
                return;
            }
            
            let currentActiveViewSource = 'live_tracking';
            const visibleScreen = document.querySelector('.feature-screen:not(.d-none)');
            
            if (visibleScreen) {
                if (visibleScreen.id === 'screen-search-bus') currentActiveViewSource = 'search';
                else if (visibleScreen.id === 'screen-live-fleet') currentActiveViewSource = 'live_fleet';
                else if (visibleScreen.id === 'screen-routes') currentActiveViewSource = 'routes';
            }
            
            const routeOverlayModal = document.getElementById('routeDetailsModal');
            if (routeOverlayModal && routeOverlayModal.style.display === 'flex') {
                currentActiveViewSource = 'routes';
            }
            
            if (currentActiveViewSource === 'search') {
                sessionStorage.setItem('fromSearchBusPage', 'true');
            } else {
                sessionStorage.setItem('fromSearchBusPage', 'false');
            }
            
            window.location.href = '/tracking/' + encodeURIComponent(extractedBusId) + '?source=' + currentActiveViewSource;
        }
    }, true);

    // ----------------------------------------------------
    // Custom Premium SOS Implementation
    // ----------------------------------------------------
    let customSosTimer;
    let customSosCount = 10;
    let premiumSosSubmitting = false;

    function restorePremiumSOSDashboard() {
        clearInterval(customSosTimer);
        const sosModal = document.getElementById('sos-premium-modal');
        if (sosModal) sosModal.style.display = 'none';
        document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';
        document.documentElement.style.overflow = '';
    }

    async function resolvePremiumSOSBusNumber() {
        const modalBus = document.getElementById('premium-sos-bus-id')?.value.trim();
        if (modalBus) return modalBus;

        const trackedBus = sessionStorage.getItem('tp-active-tracking-bus') || localStorage.getItem('tp-active-tracking-bus') || '';
        if (trackedBus.trim()) return trackedBus.trim();

        const typedBus = document.getElementById('trkSearchBusId')?.value.trim();
        if (typedBus) return typedBus;

        const workflowBus = window.Workflow?.apiData?.buses?.find(bus => bus && bus.bus_number);
        if (workflowBus && workflowBus.bus_number) return workflowBus.bus_number;

        try {
            const res = await fetch('/api/buses/live');
            if (!res.ok) return '';
            const data = await res.json();
            const bus = (data.buses || []).find(item => item && item.bus_number);
            return bus ? bus.bus_number : '';
        } catch (e) {
            return '';
        }
    }

    function executePremiumSOSTrigger() {
        if (premiumSosSubmitting) return;
        document.body.classList.add('modal-open');
        document.getElementById('sos-premium-modal').style.display = 'flex';
        clearInterval(customSosTimer);
        resolvePremiumSOSBusNumber().then(busNumber => {
            const busInput = document.getElementById('premium-sos-bus-id');
            if (busInput && busNumber) busInput.value = busNumber;
        });
    }

    function cancelPremiumSOS() {
        restorePremiumSOSDashboard();
    }

    async function confirmPremiumSOS() {
        if (premiumSosSubmitting) return;
        premiumSosSubmitting = true;
        clearInterval(customSosTimer);
        const reason = document.getElementById('premium-sos-reason').value;
        const busNumber = await resolvePremiumSOSBusNumber();
        const sendButton = document.querySelector('#sos-premium-modal .btn-danger');
        if (sendButton) {
            sendButton.disabled = true;
            sendButton.textContent = 'Sending...';
        }
        
        try {
            if (!busNumber) throw new Error('No active bus available for SOS.');
            const gps = await new Promise(resolve => {
                if (!navigator.geolocation) {
                    resolve({});
                    return;
                }
                navigator.geolocation.getCurrentPosition(
                    pos => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
                    () => resolve({}),
                    { enableHighAccuracy: true, timeout: 5000, maximumAge: 60000 }
                );
            });
            const res = await fetch('/api/sos/trigger', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || '' },
                body: JSON.stringify({ emergency_type: reason, bus_number: busNumber, ...gps })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.error || 'SOS could not be sent.');
            restorePremiumSOSDashboard();
            if (window.SOSHandler && typeof window.SOSHandler.showSuccessModal === 'function') {
                window.SOSHandler.showSuccessModal(data);
            } else {
                const ref = document.getElementById('sos-success-ref');
                if (ref && data.id) ref.innerText = `SOS-${String(data.id).padStart(5, '0')}`;
                document.getElementById('sosSuccessModal').style.display = 'flex';
            }
        } catch(e) {
            console.error(e);
            restorePremiumSOSDashboard();
            if (window.TransPulseUtils && typeof window.TransPulseUtils.showPremiumModal === 'function') {
                window.TransPulseUtils.showPremiumModal({
                    type: 'danger',
                    title: 'SOS Not Sent',
                    message: e.message || 'Unable to send SOS right now. Please try again.',
                    icon: '&#9888;'
                });
            }
        } finally {
            premiumSosSubmitting = false;
            if (sendButton) {
                sendButton.disabled = false;
                sendButton.textContent = 'Send SOS';
            }
        }
    }

    // ----------------------------------------------------
    // Hash Navigator System
    // ----------------------------------------------------
    document.addEventListener('DOMContentLoaded', () => {
        const hash = window.location.hash;
        const tryShowScreen = () => {
            if(window.Workflow && typeof window.Workflow.showScreen === 'function') {
                if(hash === '#search') window.Workflow.showScreen('screen-search-bus');
                else if (hash === '#live-tracking') window.Workflow.showScreen('screen-live-tracking');
                else if (hash === '#live-fleet') window.Workflow.showScreen('screen-live-fleet');
                else if (hash === '#routes') window.Workflow.showScreen('screen-routes');
            } else {
                setTimeout(tryShowScreen, 50);
            }
        };
        if(hash) tryShowScreen();
    });
