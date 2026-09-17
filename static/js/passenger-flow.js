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

        const uniqueStops = new Set();
        routes.forEach(route => {
            if (route.source_stop) uniqueStops.add(route.source_stop);
            if (route.destination_stop) uniqueStops.add(route.destination_stop);
            if (route.origin) uniqueStops.add(route.origin);
            if (route.destination) uniqueStops.add(route.destination);
            
            const origin = route.source_stop || route.origin || 'Unknown';
            const dest = route.destination_stop || route.destination || 'Unknown';
            let eta = 'Calculating...';
            if (route.eta_minutes != null) {
                eta = window.TransPulseUtils.formatMinutes(route.eta_minutes);
            } else if (route.eta_label) {
                const match = route.eta_label.match(/^(\d+)\s*m/i);
                eta = match ? window.TransPulseUtils.formatMinutes(match[1]) : route.eta_label;
            }
            const busCount = route.active_bus_count != null ? route.active_bus_count : 0;
            const departure = route.departure_time || '--';
            const arrival = route.arrival_time || '--';
            const duration = route.journey_duration || '--';

            const card = document.createElement('div');
            card.className = 'col-12 col-md-6 col-lg-4 mb-3';
            card.innerHTML = `
            <div class="card shadow-sm h-100 route-card-interactive position-relative"
                 data-route-code="${window.TransPulseUtils.escapeHtml(route.route_code)}"
                 data-origin="${window.TransPulseUtils.escapeHtml(origin)}"
                 data-dest="${window.TransPulseUtils.escapeHtml(dest)}">
                
                <button data-fav-route="${window.TransPulseUtils.escapeHtml(route.route_code)}" class="btn btn-link ${window.Workflow && window.Workflow.isFavorited(route.route_code) ? 'text-warning' : 'text-muted'} position-absolute top-0 end-0 p-3 text-decoration-none" onclick="window.Workflow.toggleFavorite('${window.TransPulseUtils.escapeHtml(route.route_code)}', '${window.TransPulseUtils.escapeHtml(route.route_name || route.route_code)}', this)" style="z-index: 10;">
                    <i class="${window.Workflow && window.Workflow.isFavorited(route.route_code) ? 'fa-solid' : 'fa-regular'} fa-star fs-5"></i>
                </button>
                 
                <div class="card-body p-3 text-start">
                    <h5 class="text-info fw-bold mb-1 pe-4">${window.TransPulseUtils.escapeHtml(route.route_code)}</h5>
                    <div class="text-white fw-bold mb-3" style="font-size: 0.95rem; line-height: 1.3;">${window.TransPulseUtils.escapeHtml(route.route_name || route.route_code)}</div>
                    
                    <div class="d-flex flex-wrap gap-3 mb-3 text-white-50" style="font-size: 0.8rem;">
                        <div><i class="fa-solid fa-road me-1"></i> <span class="text-light fw-bold">${window.TransPulseUtils.escapeHtml(route.distance_km || '0.0')} km</span></div>
                        <div><i class="fa-solid fa-clock me-1"></i> <span class="text-warning">${window.TransPulseUtils.escapeHtml(duration)}</span></div>
                    </div>
                    
                    <div class="d-flex justify-content-between align-items-center mb-3 p-2 rounded border border-secondary border-opacity-25" style="background: rgba(0,0,0,0.2);">
                        <div class="text-warning fw-bold" style="font-size: 0.85rem;"><i class="fa-solid fa-bolt me-1"></i> ETA: ${window.TransPulseUtils.escapeHtml(eta)}</div>
                        <div class="badge bg-success bg-opacity-25 text-success border border-success border-opacity-50 p-1 px-2">${busCount} Bus${busCount === 1 ? '' : 'es'}</div>
                    </div>
                    
                    <button type="button" class="btn btn-sm btn-outline-info w-100 fw-bold">View Schedule</button>
                </div>
            </div>`;
            card.querySelector('.route-card-interactive').addEventListener('click', () => {
                showRouteDetails(route.route_code, origin, dest);
            });
            container.appendChild(card);
        });
        
        // Inject Auto-Complete Datalist
        let datalist = document.getElementById('hubStopSuggestions');
        if (!datalist) {
            datalist = document.createElement('datalist');
            datalist.id = 'hubStopSuggestions';
            document.body.appendChild(datalist);
        }
        datalist.innerHTML = Array.from(uniqueStops).sort().map(stop => `<option value="${stop}">`).join('');
        
        // Re-apply filter if user is searching
        if (typeof window.filterMajorRoutes === 'function' && document.getElementById('majorRoutesSearch')) {
            window.filterMajorRoutes();
        }
    } catch (err) {
        console.error(err);
        if (!container.querySelector('.route-card-interactive')) {
            container.innerHTML = '<div class="col-12"><div class="alert alert-danger text-center">Failed to load routes.</div></div>';
        }
    }
}

window.filterMajorRoutes = function() {
    const query = document.getElementById('majorRoutesSearch').value.toLowerCase();
    const container = document.getElementById('dynamic-routes-container');
    if (!container) return;
    const cards = container.children;
    for (let i = 0; i < cards.length; i++) {
        const card = cards[i];
        if (!card.classList.contains('col-6')) continue; // Skip if it's the empty state
        const text = card.innerText.toLowerCase();
        if (text.includes(query)) {
            card.style.display = '';
        } else {
            card.style.display = 'none';
        }
    }
};

// Simulate real-time notification capability
setTimeout(() => {
    const notifContainer = document.getElementById('global-passenger-notifications');
    const notifTitle = document.getElementById('global-notification-title');
    const notifText = document.getElementById('global-notification-text');
    if (notifContainer && notifTitle && notifText) {
        notifTitle.innerText = "Ticket Update";
        notifText.innerText = "Your recent complaint (#1042) has been marked IN PROGRESS by admin.";
        notifContainer.classList.remove('d-none');
        // Auto hide after 8 seconds
        setTimeout(() => notifContainer.classList.add('d-none'), 8000);
    }
}, 4500);

window.Workflow = {
    apiData: { routes: [], buses: [], occupancy: {} },
    favoriteRouteCodes: new Set(),
    dataLoaded: false,
    dataInterval: null,
    notificationInterval: null,
    
    fetchFavorites: async function() {
        try {
            const res = await fetch('/api/v1/favorites');
            const data = await res.json();
            if(data.success && data.data) {
                this.favoriteRouteCodes.clear();
                const favCodes = [];
                data.data.forEach(fav => {
                    if(fav.routeId) {
                        const code = String(fav.routeId).trim().toLowerCase();
                        this.favoriteRouteCodes.add(code);
                        favCodes.push(code);
                    }
                });
                localStorage.setItem('tp_global_favorites', JSON.stringify(favCodes));
            }
        } catch(e) {
            console.warn("Failed to load favorite state", e);
        }
    },
    
    isFavorited: function(routeId) {
        if(!routeId) return false;
        const code = String(routeId).trim().toLowerCase();
        if(this.favoriteRouteCodes && this.favoriteRouteCodes.has(code)) return true;
        try {
            const cached = JSON.parse(localStorage.getItem('tp_global_favorites') || '[]');
            if(cached.includes(code)) {
                if(this.favoriteRouteCodes) this.favoriteRouteCodes.add(code);
                return true;
            }
        } catch(e) {}
        return false;
    },

    init: async function() {
        await this.fetchFavorites();
        this.loadRecentSearches();
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

            // If the timeline panel is open, silently refresh the live banner only
            const timelinePanel = document.getElementById('trip-timeline-panel');
            const openCard = document.querySelector('.fmb-result-card.active');
            if (timelinePanel && !timelinePanel.classList.contains('d-none') && openCard) {
                const busId = openCard.id.replace('fmb-card-', '');
                const bus = (this.apiData.buses || []).find(b => String(b.bus_id) === String(busId));
                if (bus) {
                    const curStopEl = document.getElementById('timeline-current-stop-text');
                    const etaEl     = document.getElementById('timeline-eta-text');
                    if (curStopEl) curStopEl.textContent = `At: ${bus.current_stop || '--'}`;
                    if (etaEl) etaEl.textContent = (bus.eta_minutes != null && bus.eta_minutes !== '--')
                        ? `ETA to dest: ${bus.eta_minutes} min` : '';
                }
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

    showScreen: function(screenId, pushState = true) {
        document.getElementById('feature-hub').classList.add('d-none');
        const header = document.getElementById('passenger-greeting-header');
        if (header) header.classList.add('d-none');
        
        document.querySelectorAll('.feature-screen').forEach(el => {
            el.classList.add('d-none');
            el.classList.remove('active-screen');
        });

        const target = document.getElementById(screenId);
        if (target) {
            target.classList.remove('d-none');
            target.classList.add('active-screen');

            if (pushState) {
                history.pushState({ screen: screenId }, "", "#" + screenId);
            }

            if (screenId === 'screen-search-bus') {
                // Reset to clean state on every open — user initiates search themselves
                const res = document.getElementById('searchResults');
                if (res) res.innerHTML = '';
                this.closeTripTimeline();
                const hdr = document.getElementById('search-results-header');
                if (hdr) hdr.classList.add('d-none');
            } else if (screenId === 'screen-routes') {
                loadAssignedRoutes();
            } else if (screenId === 'screen-live-fleet') {
                this.updateFleetSummary();
            } else if (screenId === 'screen-favorites') {
                this.loadFavorites();
            }
        }
    },

    loadFavorites: async function() {
        const container = document.getElementById('favorites-container');
        if(!container) return;
        
        container.innerHTML = '<div class="col-12 text-center text-muted py-5"><div class="spinner-border text-info mb-3"></div><div>Loading favorites...</div></div>';
        try {
            const res = await fetch('/api/v1/favorites');
            const data = await res.json();
            if(!data.success) throw new Error(data.error || 'Failed to load favorites');
            
            if(!data.data || data.data.length === 0) {
                container.innerHTML = '<div class="col-12"><div class="alert alert-dark text-center border-secondary text-muted py-4"><i class="fa-regular fa-star fs-3 d-block mb-3"></i>You have no favorite routes yet.<br><small>Tap the ⭐ on any route card in <b>Available Routes</b> or <b>Search Bus</b> to pin it here.</small></div></div>';
                return;
            }
            
            let html = '';
            data.data.forEach(fav => {
                const routeId = fav.routeId || '';
                const title = fav.title || routeId || 'Unnamed Route';
                const favId = fav.id || '';
                
                html += `
                <div class="col-12 col-md-6 col-lg-4">
                    <div class="card glass-card h-100 border-secondary position-relative" style="background: rgba(255,255,255,0.05);">
                        <button class="btn btn-link text-warning position-absolute top-0 end-0 p-3 text-decoration-none fs-5" 
                                onclick="event.stopPropagation(); window.Workflow.removeFavorite('${favId}', this)" 
                                style="z-index: 10;" title="Remove from favorites">
                            <i class="fa-solid fa-star"></i>
                        </button>
                        <div class="card-body p-4" style="cursor: pointer;" onclick="window.Workflow.showScreen('screen-routes')">
                            <div class="mb-2">
                                <span class="badge bg-info text-dark fw-bold fs-6">${routeId || '—'}</span>
                            </div>
                            <p class="text-white mb-2 fw-semibold">${title}</p>
                            <span class="badge bg-dark border border-secondary text-muted">
                                <i class="fa-solid fa-bus me-1"></i> Public Transit Route
                            </span>
                        </div>
                    </div>
                </div>`;
            });
            container.innerHTML = html;
        } catch(e) {
            container.innerHTML = `<div class="col-12"><div class="alert alert-danger"><i class="fa-solid fa-triangle-exclamation me-2"></i>${e.message}</div></div>`;
        }
    },
    
    // Remove a favorite by its DB id
    removeFavorite: async function(favId, btnEl) {
        if(event) event.stopPropagation();
        if(!favId) return;
        try {
            await fetch(`/api/v1/favorites/${favId}`, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': window.TransPulseCSRF }
            });
            // Reload the favorites list
            this.loadFavorites();
        } catch(e) {
            console.error('Remove favorite failed:', e);
        }
    },

    toggleFavorite: async function(routeId, title, btnEl, favoriteId = null) {
        if(event) event.stopPropagation();
        
        const isFavorited = btnEl.querySelector('i').classList.contains('fa-solid');
        
        try {
            if (isFavorited) {
                let idToRemove = favoriteId;
                if(!idToRemove) {
                    const res = await fetch('/api/v1/favorites');
                    const data = await res.json();
                    const fav = data.data.find(f => f.routeId === routeId);
                    if(fav) idToRemove = fav.id;
                }
                
                if(idToRemove) {
                    await fetch(`/api/v1/favorites/${idToRemove}`, {
                        method: 'DELETE',
                        headers: { 'X-CSRFToken': window.TransPulseCSRF }
                    });
                }
                
                if(window.Workflow && window.Workflow.favoriteRouteCodes) {
                    const code = String(routeId).trim().toLowerCase();
                    window.Workflow.favoriteRouteCodes.delete(code);
                    try {
                        let cached = JSON.parse(localStorage.getItem('tp_global_favorites') || '[]');
                        cached = cached.filter(c => c !== code);
                        localStorage.setItem('tp_global_favorites', JSON.stringify(cached));
                    } catch(e) {}
                }
                
                // Update all matching stars on screen
                document.querySelectorAll(`button[data-fav-route="${String(routeId).replace(/"/g, '')}"]`).forEach(btn => {
                    btn.innerHTML = '<i class="fa-regular fa-star"></i>';
                    btn.classList.remove('text-warning');
                    btn.classList.add('text-muted');
                });
                
                btnEl.innerHTML = '<i class="fa-regular fa-star"></i>';
                btnEl.classList.remove('text-warning');
                btnEl.classList.add('text-muted');
                
                if(document.getElementById('screen-favorites').classList.contains('active-screen')) {
                    this.loadFavorites();
                }
            } else {
                // Generate a random UUID for the favorite id
                const newId = crypto.randomUUID ? crypto.randomUUID() : 'fav-' + Math.random().toString(36).substr(2, 9);
                
                const payload = {
                    id: newId,
                    type: "route",
                    category: "general",
                    title: title,
                    routeId: routeId,
                    latitude: 0.0,
                    longitude: 0.0
                };
                
                const res = await fetch('/api/v1/favorites', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.TransPulseCSRF },
                    body: JSON.stringify(payload)
                });
                
                if(!res.ok) {
                    const err = await res.json();
                    throw new Error(err.error || 'Failed to save favorite');
                }
                
                if(window.Workflow && window.Workflow.favoriteRouteCodes) {
                    const code = String(routeId).trim().toLowerCase();
                    window.Workflow.favoriteRouteCodes.add(code);
                    try {
                        const cached = JSON.parse(localStorage.getItem('tp_global_favorites') || '[]');
                        if(!cached.includes(code)) cached.push(code);
                        localStorage.setItem('tp_global_favorites', JSON.stringify(cached));
                    } catch(e) {}
                }
                
                // Update all matching stars on screen
                document.querySelectorAll(`button[data-fav-route="${String(routeId).replace(/"/g, '')}"]`).forEach(btn => {
                    btn.innerHTML = '<i class="fa-solid fa-star"></i>';
                    btn.classList.remove('text-muted');
                    btn.classList.add('text-warning');
                });
                
                btnEl.innerHTML = '<i class="fa-solid fa-star"></i>';
                btnEl.classList.remove('text-muted');
                btnEl.classList.add('text-warning');
            }
        } catch(e) {
            console.error("Favorite toggle failed:", e);
        }
    },
    
    openNearbyStops: function() {
        this.showScreen('screen-nearby-stops');

        const statusEl = document.getElementById('nearby-stops-status');
        if (statusEl) {
            statusEl.style.display = 'block';
            statusEl.className = 'alert alert-info mb-3';
            statusEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i> Detecting your exact location...';
        }

        const AP_LAT = 15.9129, AP_LNG = 79.7400;

        const oldList = document.getElementById('nearby-stops-list-wrapper');
        if(oldList) oldList.innerHTML = '';

        // Safely initialize or reuse map
        if (!this.nearbyMap) {
            this.nearbyMap = L.map('nearbyStopsMap', { zoomControl: true }).setView([AP_LAT, AP_LNG], 7);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors',
                maxZoom: 19
            }).addTo(this.nearbyMap);

            const mapDiv = document.getElementById('nearbyStopsMap');
            if (mapDiv && window.ResizeObserver) {
                new ResizeObserver(() => { if(this.nearbyMap) this.nearbyMap.invalidateSize(); }).observe(mapDiv);
            }
        } else {
            // Collect markers first, THEN remove — never mutate eachLayer mid-iteration
            const markersToRemove = [];
            this.nearbyMap.eachLayer(layer => {
                if (layer instanceof L.Marker) markersToRemove.push(layer);
            });
            markersToRemove.forEach(m => m.remove());
            this.nearbyUserMarker = null;
        }

        const fixMap = () => { if(this.nearbyMap) this.nearbyMap.invalidateSize(); };
        setTimeout(fixMap, 150);
        setTimeout(fixMap, 500);
        setTimeout(fixMap, 1000);

        if (!navigator.geolocation) {
            if (statusEl) {
                statusEl.className = 'alert alert-warning mb-3';
                statusEl.innerHTML = '<i class="fa-solid fa-triangle-exclamation me-2"></i> GPS not supported. Please enable location services.';
            }
            return;
        }

        // Always force a fresh, strictly accurate GPS lock every time the screen is opened,
        // even if it takes a few seconds, to guarantee the location is perfectly up to date.
        if (this.nearbyWatchId) {
            navigator.geolocation.clearWatch(this.nearbyWatchId);
            this.nearbyWatchId = null;
        }

        this.nearbyLastPos = null;
        let locationUpdates = 0;
        
        this.nearbyWatchId = navigator.geolocation.watchPosition(
            async (pos) => {
                locationUpdates++;
                const lat = pos.coords.latitude;
                const lng = pos.coords.longitude;
                const accuracy = pos.coords.accuracy || 10000;
                
                if (accuracy > 150) return;
                
                let distanceMoved = 0;
                if (this.nearbyLastPos && this.nearbyMap) {
                    distanceMoved = this.nearbyMap.distance(this.nearbyLastPos, [lat, lng]);
                }
                
                // Also re-fetch if the location jumps by > 500m (e.g., cell tower to GPS transition)
                if (!this.nearbyLastPos || distanceMoved > 500) {
                    this.nearbyLastPos = [lat, lng];
                    if (statusEl) {
                        statusEl.style.display = 'block';
                        statusEl.className = 'alert alert-success mb-3';
                        statusEl.innerHTML = '<i class="fa-solid fa-check me-2"></i> Location locked. Finding nearby stops...';
                    }
                    if (this.nearbyMap) {
                        this.nearbyMap.setView([lat, lng], 14);
                        setTimeout(fixMap, 200);
                    }
                    await this._renderNearbyMap(lat, lng, 'You are here');
                } else if (this.nearbyLastPos && this.nearbyUserMarker) {
                    // Update user marker position silently if already fetched
                    this.nearbyUserMarker.setLatLng([lat, lng]);
                }
            },
            (err) => {
                if (statusEl && !this.nearbyLastPos) {
                    statusEl.className = 'alert alert-warning mb-3';
                    statusEl.innerHTML = '<i class="fa-solid fa-location-xmark me-2"></i> Location access denied or timed out. Please ensure GPS is enabled and try again.';
                }
            },
            { enableHighAccuracy: true, timeout: 60000, maximumAge: 0 }
        );
    },

    searchNearbyByName: async function() {
        const input = document.getElementById('nearby-location-input');
        const query = input ? input.value.trim() : '';
        if (!query) {
            input.focus();
            return;
        }

        const statusEl = document.getElementById('nearby-stops-status');
        statusEl.style.display = 'block';
        statusEl.className = 'alert alert-info mb-3';
        statusEl.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-2"></i> Searching for "<b>${query}</b>"...`;

        try {
            // Use Nominatim free geocoding
            const geoRes = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&countrycodes=in&limit=1`, {
                headers: { 'Accept-Language': 'en' }
            });
            const geoData = await geoRes.json();

            if (!geoData || geoData.length === 0) {
                statusEl.className = 'alert alert-warning mb-3';
                statusEl.innerHTML = `<i class="fa-solid fa-magnifying-glass me-2"></i> Could not find "<b>${query}</b>". Try a more specific name.`;
                return;
            }

            const lat = parseFloat(geoData[0].lat);
            const lng = parseFloat(geoData[0].lon);
            const displayName = geoData[0].display_name;

            statusEl.className = 'alert alert-success mb-3';
            statusEl.innerHTML = `<i class="fa-solid fa-check me-2"></i> Found: <b>${displayName.split(',').slice(0,2).join(',')}</b>. Searching nearby stops...`;

            await this._renderNearbyMap(lat, lng, query);

        } catch(e) {
            statusEl.className = 'alert alert-danger mb-3';
            statusEl.innerHTML = `<i class="fa-solid fa-triangle-exclamation me-2"></i> Geocoding failed: ${e.message}`;
        }
    },

    _renderNearbyMap: async function(lat, lng, locationLabel) {
        const statusEl = document.getElementById('nearby-stops-status');

        // Reuse the already-initialized map, just pan to the real location
        if(this.nearbyMap) {
            this.nearbyMap.setView([lat, lng], 12);

            // Collect markers first, THEN remove — never mutate eachLayer mid-iteration
            const markersToRemove = [];
            this.nearbyMap.eachLayer(layer => {
                if (layer instanceof L.Marker) markersToRemove.push(layer);
            });
            markersToRemove.forEach(m => m.remove());
        }

        // Reset nearbyUserMarker reference (it was already removed above)
        this.nearbyUserMarker = null;

        const userIcon = L.divIcon({
            html: '<div style="background:#34d2ff; width:16px; height:16px; border-radius:50%; border:3px solid #fff; box-shadow: 0 0 12px #34d2ff;"></div>',
            className: '',
            iconSize: [16, 16],
            iconAnchor: [8, 8]
        });

        this.nearbyUserMarker = L.marker([lat, lng], {icon: userIcon})
         .addTo(this.nearbyMap)
         .bindPopup(`<b>📍 ${locationLabel}</b>`);

        try {
            const res = await fetch(`/api/stops/nearby?lat=${lat}&lng=${lng}&radius=5`);
            const data = await res.json();

            if(!data.success) throw new Error(data.error);

            // Clear old list just before we write new results (avoids race-condition flicker)
            const listEl = document.getElementById('nearby-stops-list-wrapper');
            if (listEl) listEl.innerHTML = '';

            if(data.stops.length === 0) {
                if (statusEl) {
                    statusEl.style.display = 'block';
                    statusEl.className = 'alert alert-warning mb-3';
                    statusEl.innerHTML = `<i class="fa-solid fa-bus-slash me-2"></i> No Transit stops found within 5km of <b>${locationLabel}</b>. Try exploring the map.`;
                }
                return;
            }

            if (statusEl) statusEl.style.display = 'none';

            const stopIcon = L.divIcon({
                html: '<div style="font-size:22px;">🚏</div>',
                className: '',
                iconSize: [24, 24],
                iconAnchor: [12, 24]
            });

            let listHtml = `
            <div class="mt-3">
                <h6 class="text-white mb-2"><i class="fa-solid fa-map-pin me-2 text-info"></i>Found ${data.stops.length} stop(s) within 5km of <span class="text-info">${locationLabel}</span></h6>
                <div class="row g-2">`;

            data.stops.forEach(stop => {
                L.marker([stop.lat, stop.lng], {icon: stopIcon})
                 .addTo(this.nearbyMap)
                 .bindPopup(`
                    <div class="p-1">
                        <h6 class="fw-bold mb-1">${stop.stop_name}</h6>
                        <small class="d-block mb-2">Code: ${stop.stop_code || 'N/A'}</small>
                        <span class="badge bg-info text-dark">${stop.distance_km} km away</span>
                    </div>
                 `);

                listHtml += `
                <div class="col-12 col-md-6">
                    <div class="d-flex align-items-center gap-3 p-3 rounded border border-secondary" style="background: rgba(255,255,255,0.05);">
                        <div class="fs-4">🚏</div>
                        <div>
                            <div class="text-white fw-bold small">${stop.stop_name}</div>
                            <div class="text-muted" style="font-size:0.75rem;">Code: ${stop.stop_code || 'N/A'}</div>
                            <span class="badge bg-info text-dark mt-1">${stop.distance_km} km away</span>
                        </div>
                    </div>
                </div>`;
            });

            listHtml += '</div></div>';

            // Write the final rendered list to the permanent wrapper
            if (listEl) {
                listEl.innerHTML = listHtml;
            }

        } catch(e) {
            if (statusEl) {
                statusEl.style.display = 'block';
                statusEl.className = 'alert alert-danger mb-3';
                statusEl.innerHTML = `<i class="fa-solid fa-triangle-exclamation me-2"></i> Failed to load stops: ${e.message}`;
            }
        }
    },

    goHome: function(pushState = true) {
        document.querySelectorAll('.feature-screen').forEach(el => {
            el.classList.add('d-none');
            el.classList.remove('active-screen');
        });
        document.getElementById('feature-hub').classList.remove('d-none');
        const header = document.getElementById('passenger-greeting-header');
        if (header) header.classList.remove('d-none');

        if (pushState) {
            history.pushState({ screen: 'home' }, "", window.location.pathname);
        }

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

        ['searchSrc', 'searchDst', 'searchBusNumber', 'fleetInputBus', 'trkSearchBusId'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        this.closeTripTimeline();
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
            const routeName = bus.route_name || (route ? route.route_name : '') || bus.route_code || 'Unknown Route';
            const routeCode = bus.route_code || (route && route.route_code) || 'Unknown Code';
            const departure = bus.departure_time || (route && route.departure_time) || '--';
            const arrival = bus.arrival_time || (route && route.arrival_time) || '--';
            const duration = bus.journey_duration || (route && route.journey_duration) || '--';
            const updatedArrival = bus.updated_arrival_time || arrival;
            const currentDelay = bus.current_delay_label || window.TransPulseUtils.formatMinutes(bus.current_delay_minutes || 0);
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

            const occupancy = window.TransPulseUtils.occupancyMeta(bus);

            const trackUrl = `/tracking/${encodeURIComponent(bus.bus_number)}?source=search`;
            const trackButtonHtml = `<button onclick="openBusModal('${bus.bus_id}')" class="btn btn-sm btn-info w-100 fw-bold text-dark shadow-sm">View Details</button>`;

            resultsDiv.innerHTML += `
                <div class="col-12 col-md-6 col-lg-4">
                    <div class="card glass-panel h-100 shadow-sm" style="border: 1px solid rgba(52,210,255,0.25); background: linear-gradient(135deg, rgba(11,29,54,0.8), rgba(4,11,24,0.9));">
                        <div class="card-body p-3 d-flex flex-column">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <div>
                                    <h5 class="text-white fw-bold m-0">${window.TransPulseUtils.escapeHtml(bus.bus_number)} <small class="text-muted fs-6">(ID: ${bus.bus_id})</small></h5>
                                    <div class="d-flex align-items-center gap-2">
                                        <div class="text-info fw-bold small">${window.TransPulseUtils.escapeHtml(routeCode)}</div>
                                        <button data-fav-route="${window.TransPulseUtils.escapeHtml(routeCode)}" class="btn btn-link ${window.Workflow && window.Workflow.isFavorited(routeCode) ? 'text-warning' : 'text-muted'} p-0 text-decoration-none" onclick="window.Workflow.toggleFavorite('${window.TransPulseUtils.escapeHtml(routeCode)}', '${window.TransPulseUtils.escapeHtml(routeName)}', this)" title="Favorite this route">
                                            <i class="${window.Workflow && window.Workflow.isFavorited(routeCode) ? 'fa-solid' : 'fa-regular'} fa-star"></i>
                                        </button>
                                    </div>
                                    <div class="text-white-50 small" style="font-size: 0.75rem;">${window.TransPulseUtils.escapeHtml(routeName)}</div>
                                </div>
                                <div class="text-end">
                                    <span class="badge ${liveStatus.badge} shadow-sm text-uppercase d-block mb-1" style="font-size:0.65rem;">${window.TransPulseUtils.escapeHtml(liveStatus.live)}</span>
                                    <span class="badge ${statusColor} shadow-sm text-uppercase" style="font-size:0.65rem;">${window.TransPulseUtils.escapeHtml(tripStatus)}</span>
                                </div>
                            </div>

                            <div class="mt-2 mb-3 bg-dark bg-opacity-50 p-2 rounded border border-secondary">
                                <p class="m-0 text-muted small mb-1">Route: <span class="text-light fw-bold">${window.TransPulseUtils.escapeHtml(routeName)}</span></p>
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
        // Legacy: triggered by old form submit event — delegate to findMyBus
        this.findMyBus();
    },

    switchSearchTab: function(tab) {
        const tripPanel  = document.getElementById('tab-panel-trip');
        const busnoPanel = document.getElementById('tab-panel-busno');
        const tabTrip    = document.getElementById('tab-trip');
        const tabBusno   = document.getElementById('tab-busno');
        const activeStyle   = 'background: rgba(52,210,255,1); color: #000;';
        const inactiveStyle = 'background: rgba(52,210,255,0.15); color: #34d2ff; border: 1px solid rgba(52,210,255,0.3);';

        if (tab === 'trip') {
            tripPanel.classList.remove('d-none');
            busnoPanel.classList.add('d-none');
            tabTrip.style.cssText  += activeStyle;
            tabBusno.style.cssText += inactiveStyle;
        } else {
            tripPanel.classList.add('d-none');
            busnoPanel.classList.remove('d-none');
            tabBusno.style.cssText += activeStyle;
            tabTrip.style.cssText  += inactiveStyle;
        }
        // Reset results
        const res = document.getElementById('searchResults');
        if (res) res.innerHTML = '';
        this.closeTripTimeline();
        const hdr = document.getElementById('search-results-header');
        if (hdr) hdr.classList.add('d-none');
    },

    // ─── Recent Searches ──────────────────────────────────────────────────────────
    loadRecentSearches: function() {
        try {
            const searches = JSON.parse(localStorage.getItem('tp_recent_searches') || '[]');
            const container = document.getElementById('recent-searches-container');
            const list = document.getElementById('recent-searches-list');
            if (!container || !list) return;
            
            if (searches.length === 0) {
                container.classList.add('d-none');
                return;
            }
            container.classList.remove('d-none');
            list.innerHTML = '';
            
            searches.forEach((s, idx) => {
                let badgeHtml = '';
                let clickArg = '';
                if (s.type === 'route') {
                    const label = (s.data.src && s.data.dst) ? `${s.data.src} ➔ ${s.data.dst}` : (s.data.src || s.data.dst);
                    badgeHtml = `<i class="fa-solid fa-route me-1"></i> ${window.TransPulseUtils.escapeHtml(label)}`;
                    clickArg = `window.Workflow.applyRecentSearch('route', '${window.TransPulseUtils.escapeHtml(s.data.src)}', '${window.TransPulseUtils.escapeHtml(s.data.dst)}')`;
                } else if (s.type === 'busno') {
                    badgeHtml = `<i class="fa-solid fa-hashtag me-1"></i> ${window.TransPulseUtils.escapeHtml(s.data.bus)}`;
                    clickArg = `window.Workflow.applyRecentSearch('busno', '${window.TransPulseUtils.escapeHtml(s.data.bus)}')`;
                }
                
                list.innerHTML += `
                    <div class="badge bg-dark border border-secondary text-info p-2 rounded-pill shadow-sm" style="cursor:pointer;" onclick="${clickArg}">
                        ${badgeHtml}
                    </div>
                `;
            });
        } catch (e) {
            console.error(e);
        }
    },

    saveRecentSearch: function(type, data) {
        try {
            let searches = JSON.parse(localStorage.getItem('tp_recent_searches') || '[]');
            // Remove exact duplicates
            searches = searches.filter(s => !(s.type === type && JSON.stringify(s.data) === JSON.stringify(data)));
            searches.unshift({ type, data });
            searches = searches.slice(0, 5); // Keep top 5
            localStorage.setItem('tp_recent_searches', JSON.stringify(searches));
            this.loadRecentSearches();
        } catch (e) {}
    },
    
    clearRecentSearches: function() {
        localStorage.removeItem('tp_recent_searches');
        this.loadRecentSearches();
    },
    
    applyRecentSearch: function(type, arg1, arg2) {
        if (type === 'route') {
            this.switchSearchTab('trip');
            document.getElementById('searchSrc').value = arg1 || '';
            document.getElementById('searchDst').value = arg2 || '';
            this.findMyBus();
        } else if (type === 'busno') {
            this.switchSearchTab('busno');
            document.getElementById('searchBusNumber').value = arg1 || '';
            this.findBusByNumber();
        }
    },

    swapSearchStops: function() {
        const src = document.getElementById('searchSrc');
        const dst = document.getElementById('searchDst');
        if (!src || !dst) return;
        const tmp = src.value;
        src.value = dst.value;
        dst.value = tmp;
    },

    // ─── FLOW 1: Source + Destination → find matching buses ──────────────────
    findMyBus: function() {
        const srcEl = document.getElementById('searchSrc');
        const dstEl = document.getElementById('searchDst');
        const src = (srcEl ? srcEl.value.trim() : '').toLowerCase();
        const dst = (dstEl ? dstEl.value.trim() : '').toLowerCase();

        const resultsDiv = document.getElementById('searchResults');
        const header     = document.getElementById('search-results-header');
        const routeLabel = document.getElementById('search-route-label');
        const badge      = document.getElementById('total-buses-badge');

        if (!resultsDiv) return;
        this.closeTripTimeline();

        if (!src && !dst) {
            resultsDiv.innerHTML = '<div class="alert alert-info bg-dark border-secondary text-info text-center mt-2" style="border-radius:10px;">Enter a source and/or destination stop to find buses.</div>';
            if (header) header.classList.add('d-none');
            return;
        }
        
        // Save to recent searches
        if (src || dst) this.saveRecentSearch('route', { src: srcEl.value.trim(), dst: dstEl.value.trim() });

        if (!this.dataLoaded) {
            resultsDiv.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-info"></div><p class="text-muted mt-2 small">Loading live fleet...</p></div>';
            return;
        }

        if (!this.apiData.buses || this.apiData.buses.length === 0) {
            resultsDiv.innerHTML = '<div class="alert alert-dark border-secondary text-muted text-center mt-2" style="border-radius:10px;">No active buses in fleet right now.</div>';
            if (header) header.classList.add('d-none');
            return;
        }

        // Find routes that contain BOTH stops in the correct order
        const validRouteIds = new Set();
        const routeStopMap  = {}; // routeId → { srcIdx, dstIdx, stops }

        this.apiData.routes.forEach(route => {
            if (!route.stops || route.stops.length === 0) {
                const origin = (route.source_stop || '').toLowerCase();
                const dest   = (route.destination_stop || '').toLowerCase();
                if ((!src || origin.includes(src)) && (!dst || dest.includes(dst))) {
                    validRouteIds.add(route.route_id);
                    routeStopMap[route.route_id] = { srcIdx: 0, dstIdx: -1, stops: [] };
                }
                return;
            }
            const stopNames = route.stops.map(s => (s.name || s.stop_name || '').toLowerCase());
            const srcIdx = src ? stopNames.findIndex(n => n.includes(src)) : 0;
            const dstIdx = dst ? stopNames.findIndex(n => n.includes(dst)) : stopNames.length - 1;

            if (srcIdx >= 0 && dstIdx >= 0 && srcIdx < dstIdx) {
                validRouteIds.add(route.route_id);
                routeStopMap[route.route_id] = { srcIdx, dstIdx, stops: route.stops };
            }
        });

        if (validRouteIds.size === 0) {
            resultsDiv.innerHTML = '<div class="alert alert-warning bg-dark border-secondary text-warning text-center mt-2" style="border-radius:10px;">No buses found for this stop combination. Try different stop names.</div>';
            if (header) header.classList.add('d-none');
            return;
        }

        const matchedBuses = this.apiData.buses.filter(b => validRouteIds.has(b.route_id));
        if (matchedBuses.length === 0) {
            resultsDiv.innerHTML = '<div class="alert alert-info bg-dark border-secondary text-info text-center mt-2" style="border-radius:10px;">No active buses on matching routes right now.</div>';
            if (header) header.classList.add('d-none');
            return;
        }

        // Show header
        if (header) header.classList.remove('d-none');
        const srcLabel = srcEl.value.trim() || '—';
        const dstLabel = dstEl.value.trim() || '—';
        if (routeLabel) routeLabel.textContent = `${srcLabel}  →  ${dstLabel}`;
        if (badge) badge.textContent = `${matchedBuses.length} bus${matchedBuses.length > 1 ? 'es' : ''}`;

        this._renderTripResultCards(matchedBuses, routeStopMap, resultsDiv, src, dst);
    },

    _renderTripResultCards: function(buses, routeStopMap, container, srcQuery, dstQuery) {
        container.innerHTML = '';
        buses.forEach((bus, i) => {
            const rMap = routeStopMap[bus.route_id] || {};

            // Prefer bus.stops (has scheduled times), fall back to route stops
            const busStops   = (bus.stops && bus.stops.length > 0) ? bus.stops : [];
            const routeStops = rMap.stops || [];
            const stops      = busStops.length > 0 ? busStops : routeStops;

            // Find source / destination indices
            const srcIdx = srcQuery
                ? stops.findIndex(s => (s.name || s.stop_name || '').toLowerCase().includes(srcQuery))
                : (rMap.srcIdx ?? 0);
            const dstIdx = dstQuery
                ? stops.findIndex(s => (s.name || s.stop_name || '').toLowerCase().includes(dstQuery))
                : (rMap.dstIdx ?? stops.length - 1);

            const srcStop = stops[srcIdx >= 0 ? srcIdx : 0] || {};
            const dstStop = stops[dstIdx >= 0 ? dstIdx : stops.length - 1] || {};

            const getVal = (val) => val && val !== '--' ? val : null;
            let depTime = getVal(srcStop.departure_time) || getVal(srcStop.scheduled_time) || getVal(srcStop.expected_time) || getVal(srcStop.arrival_time) || null;
            let arrTime = getVal(dstStop.arrival_time)   || getVal(dstStop.scheduled_time) || getVal(dstStop.expected_time) || getVal(dstStop.departure_time) || null;

            if (!depTime) depTime = getVal(bus.actual_departure_time) || getVal(bus.departure_time) || '--';
            if (!arrTime) arrTime = getVal(bus.actual_arrival_time)   || getVal(bus.arrival_time)   || '--';

            const duration   = bus.journey_duration || bus.journey_duration_label || '--';
            const tripStatus = bus.trip_status || bus.status || '';
            const notStarted = ['WAITING_TO_DEPART', 'SCHEDULED', 'NOT_STARTED'].includes(tripStatus)
                            || bus.service_status === 'offline'
                            || bus.bus_status === 'OFFLINE';

            const liveStatus = window.TransPulseUtils.busStatusMeta(bus);
            let statusColor  = '#22d39a';
            if (bus.service_status === 'delayed' || (bus.current_delay_minutes || 0) > 0) statusColor = '#f5b342';
            if (bus.service_status === 'completed' || notStarted) statusColor = '#7d92b3';

            let delayLabel;
            if (notStarted) {
                delayLabel = `<span style="color:#7d92b3;font-size:0.65rem;">Not yet started</span>`;
            } else if ((bus.current_delay_minutes || 0) > 0) {
                delayLabel = `<span style="color:#f5b342;font-size:0.65rem;">+${bus.current_delay_minutes} min late</span>`;
            } else {
                delayLabel = `<span style="color:#22d39a;font-size:0.65rem;">On time</span>`;
            }

            const e = window.TransPulseUtils.escapeHtml;

            // Time row: if both dep and arr are '--', show route endpoints instead
            const showDep = depTime !== '--' ? e(depTime) : '<span style="color:rgba(255,255,255,0.3)">--</span>';
            const showArr = arrTime !== '--' ? e(arrTime) : '<span style="color:rgba(255,255,255,0.3)">--</span>';

            container.innerHTML += `
            <div class="fmb-result-card" id="fmb-card-${bus.bus_id}" onclick="window.Workflow.openTripTimeline('${bus.bus_id}', '${encodeURIComponent(srcQuery)}', '${encodeURIComponent(dstQuery)}')">
                <div class="d-flex justify-content-between align-items-start">
                    <div style="flex:1; min-width:0;">
                        <!-- Highlighted Bus ID and Route -->
                        <div class="mb-2">
                            <h5 class="fw-bold m-0" style="color:#34d2ff; font-size: 1.15rem; letter-spacing: 0.5px;">${e(bus.bus_number)}</h5>
                            <div class="text-white opacity-75 mt-1" style="font-size: 0.85rem; font-weight: 500;">${e(bus.route_name || bus.route_code || 'Route')}</div>
                        </div>
                        <!-- Timings -->
                        <div class="d-flex align-items-center mb-1">
                            <span class="fw-bold text-white" style="font-size: 0.95rem;">${showDep}</span>
                            <span class="mx-2 text-muted" style="font-size: 0.75rem;">── <span class="text-info">${e(duration)}</span> ──</span>
                            <span class="fw-bold text-white" style="font-size: 0.95rem;">${showArr}</span>
                        </div>
                        <div class="mt-1">${delayLabel}</div>
                    </div>
                    <div class="text-end ms-2 flex-shrink-0">
                        <span class="fmb-status-badge" style="background:${statusColor}22; color:${statusColor}; border:1px solid ${statusColor}44;">${e(liveStatus.live || tripStatus || 'Active')}</span>
                        <div class="text-muted mt-2 fw-bold" style="font-size:0.7rem;">Tap for stops <i class="fa-solid fa-chevron-right ms-1"></i></div>
                    </div>
                </div>
            </div>`;
        });
    },

    // ─── FLOW 2: Bus Number → full route timeline ─────────────────────────────
    findBusByNumber: function() {
        const input = document.getElementById('searchBusNumber');
        const query = input ? input.value.trim().toLowerCase() : '';
        const resultsDiv = document.getElementById('searchResults');
        const header     = document.getElementById('search-results-header');
        const badge      = document.getElementById('total-buses-badge');

        if (!resultsDiv) return;
        this.closeTripTimeline();

        if (!query) { if (input) input.focus(); return; }
        
        this.saveRecentSearch('busno', { bus: input.value.trim() });

        if (!this.dataLoaded || !this.apiData.buses) {
            resultsDiv.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-info"></div></div>';
            return;
        }

        const matched = this.apiData.buses.filter(b =>
            (b.bus_number || '').toLowerCase().includes(query) ||
            (b.registration_number || '').toLowerCase().includes(query)
        );

        if (matched.length === 0) {
            resultsDiv.innerHTML = '<div class="alert alert-warning bg-dark border-secondary text-warning text-center mt-2" style="border-radius:10px;">No bus found with that number.</div>';
            if (header) header.classList.add('d-none');
            return;
        }

        // For bus-number search: show full route (no stop filtering)
        if (header) header.classList.remove('d-none');
        const routeLabel = document.getElementById('search-route-label');
        if (routeLabel) routeLabel.textContent = `Full Route — ${matched[0].bus_number}`;
        if (badge) badge.textContent = `${matched.length} result${matched.length > 1 ? 's' : ''}`;

        // Render result cards — clicking opens the FULL route (no src/dst filter)
        this._renderTripResultCards(matched, {}, resultsDiv, '', '');
    },

    // ─── Trip Timeline Panel ──────────────────────────────────────────────────
    openTripTimeline: async function(busId, encodedSrc, encodedDst) {
        const srcQuery = decodeURIComponent(encodedSrc || '').toLowerCase();
        const dstQuery = decodeURIComponent(encodedDst || '').toLowerCase();

        const bus = this.apiData.buses.find(b => String(b.bus_id) === String(busId));
        if (!bus) return;

        // Mark active card
        document.querySelectorAll('.fmb-result-card').forEach(c => c.classList.remove('active'));
        const card = document.getElementById(`fmb-card-${busId}`);
        if (card) { card.classList.add('active'); card.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }

        // Show panel immediately (with loading state)
        const panel = document.getElementById('trip-timeline-panel');
        if (panel) { panel.classList.remove('d-none'); panel.scrollIntoView({ behavior: 'smooth', block: 'start' }); }

        // Populate panel header
        document.getElementById('timeline-bus-number').textContent = `Bus ${bus.bus_number}`;
        document.getElementById('timeline-route-name').textContent  = bus.route_name || bus.route_code || '';

        // "At: current_stop" — avoid showing raw "Source" or bad values
        const curStopRaw = bus.current_stop || '';
        const curStopDisplay = (curStopRaw && curStopRaw !== 'Source' && curStopRaw !== '--')
            ? `At: ${curStopRaw}`
            : (bus.source_stop ? `Starting from: ${bus.source_stop}` : 'Not yet started');
        document.getElementById('timeline-current-stop-text').textContent = curStopDisplay;

        // ETA — only show if bus has actually started and eta > 0
        const etaOk = bus.eta_minutes != null
            && bus.eta_minutes !== '--'
            && Number(bus.eta_minutes) > 0
            && bus.service_status !== 'offline'
            && bus.bus_status !== 'OFFLINE';
        document.getElementById('timeline-eta-text').textContent = etaOk
            ? `ETA to dest: ${bus.eta_minutes} min` : '';

        const tlDiv = document.getElementById('trip-stop-timeline');
        tlDiv.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm text-info"></div><span class="text-muted ms-2 small">Loading route stops...</span></div>';

        // ── Resolve stop list ────────────────────────────────────────────────
        // Priority: 1) bus.stops (live, has times)  2) route stops from apiData
        //           3) fetch from GTFS API (always available, even for unstarted buses)
        let stops = [];

        if (bus.stops && bus.stops.length > 0) {
            stops = bus.stops;
        } else {
            // Try cached route stops first
            const routeObj = (this.apiData.routes || []).find(r => r.route_id === bus.route_id);
            if (routeObj && routeObj.stops && routeObj.stops.length > 0) {
                stops = routeObj.stops;
            }
        }

        // If still empty — fetch from GTFS endpoint
        if (stops.length === 0 && bus.route_id) {
            try {
                const res  = await fetch(`/api/v1/gtfs/routes/${bus.route_id}/stops`);
                if (res.ok) {
                    const data = await res.json();
                    stops = data.stops || data.stop_list || [];
                    // Normalize field names (GTFS uses stop_name)
                    stops = stops.map(s => ({
                        ...s,
                        name: s.name || s.stop_name || s.stop_id || '?',
                    }));
                }
            } catch (e) {
                console.warn('GTFS stops fetch failed:', e);
            }
        }

        // ── Render timeline ──────────────────────────────────────────────────
        const curIdx = bus.current_stop_index ?? 0;

        const srcIdx = srcQuery ? stops.findIndex(s => (s.name || s.stop_name || '').toLowerCase().includes(srcQuery)) : -1;
        const dstIdx = dstQuery ? stops.findIndex(s => (s.name || s.stop_name || '').toLowerCase().includes(dstQuery)) : -1;

        // Which stops to render:
        //   route search → show from one stop before src up to dst (inclusive)
        //   bus number search → show all stops
        let renderStops = stops;
        let startOffset = 0;
        if (srcIdx >= 0 && dstIdx >= 0) {
            startOffset = Math.max(0, srcIdx - 1);
            renderStops = stops.slice(startOffset, dstIdx + 1);
        }

        if (renderStops.length === 0) {
            tlDiv.innerHTML = `<div class="text-center py-4">
                <div style="font-size:1.5rem; margin-bottom:8px;">🚌</div>
                <div class="text-white small fw-bold">Route stops unavailable</div>
                <div class="text-muted" style="font-size:0.75rem; margin-top:4px;">
                    ${stops.length > 0 ? 'Your source/destination stops were not found on this route.' : 'Stop data for this bus is not yet available.'}
                </div>
            </div>`;
        } else {
            const notStarted = bus.bus_status === 'OFFLINE'
                || ['WAITING_TO_DEPART', 'SCHEDULED', 'NOT_STARTED'].includes(bus.trip_status || bus.status || '');

            tlDiv.innerHTML = renderStops.map((stop, localIdx) => {
                const globalIdx = localIdx + startOffset;
                const isPassed  = !notStarted && globalIdx < curIdx;
                const isCurrent = !notStarted && globalIdx === curIdx;
                const isSrc     = globalIdx === srcIdx;
                const isDst     = globalIdx === dstIdx;

                let dotClass  = isPassed ? 'passed' : (isCurrent ? 'current' : 'upcoming');
                if (isSrc && !isCurrent && !isPassed) dotClass = 'source';
                if (isDst && !isCurrent && !isPassed) dotClass = 'dest';

                let nameClass = isPassed ? 'passed' : '';
                if (isCurrent) nameClass = 'current';
                if (isSrc && !isPassed) nameClass = 'source';
                if (isDst && !isPassed) nameClass = 'dest';

                const showLine  = localIdx < renderStops.length - 1;
                const lineClass = isPassed ? 'passed' : '';
                const schedTime = stop.arrival_time || stop.scheduled_time || stop.departure_time || null;
                const liveTime  = stop.actual_time || stop.rt_eta_abs || null;
                const isDelayed = (stop.delay_minutes || 0) > 0;

                let tags = '';
                if (isSrc && srcQuery) tags += `<span class="tl-stop-tag ms-1" style="background:rgba(52,210,255,0.2);color:#34d2ff;">YOUR STOP</span>`;
                if (isDst && dstQuery) tags += `<span class="tl-stop-tag ms-1" style="background:rgba(52,210,255,0.9);color:#000;">DESTINATION</span>`;
                if (isCurrent)         tags += `<span class="tl-stop-tag ms-1" style="background:rgba(34,211,154,0.2);color:#22d39a;">● HERE NOW</span>`;

                const e        = window.TransPulseUtils.escapeHtml;
                const stopName = stop.name || stop.stop_name || '--';

                return `<div class="tl-stop-row">
                    <div class="tl-dot-col">
                        <div class="tl-dot ${dotClass}"></div>
                        ${showLine ? `<div class="tl-line ${lineClass}" style="height:32px;"></div>` : ''}
                    </div>
                    <div style="flex:1; min-width:0; padding-top:1px;">
                        <div class="d-flex align-items-center flex-wrap gap-1">
                            <span class="tl-stop-name ${nameClass}">${e(stopName)}</span>
                            ${tags}
                        </div>
                        ${(schedTime || liveTime) ? `<div class="d-flex gap-3 mt-1 flex-wrap">
                            ${schedTime ? `<span class="tl-stop-time-sched">Sched: ${e(schedTime)}</span>` : ''}
                            ${liveTime  ? `<span class="tl-stop-time-live">${isDelayed ? '⚠ ' : ''}Live: ${e(liveTime)}</span>` : ''}
                        </div>` : ''}
                    </div>
                </div>`;
            }).join('');

            // Auto-scroll to YOUR STOP tag or current stop
            setTimeout(() => {
                const srcEl = tlDiv.querySelector('.tl-dot.source, .tl-dot.current');
                if (srcEl) srcEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 120);
        }
    },

    closeTripTimeline: function() {
        const panel = document.getElementById('trip-timeline-panel');
        if (panel) panel.classList.add('d-none');
        document.querySelectorAll('.fmb-result-card').forEach(c => c.classList.remove('active'));
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

            const occupancy = window.TransPulseUtils.occupancyMeta(bus);
            const departure = bus.departure_time || '--';
            const arrival = bus.arrival_time || '--';
            const updatedArrival = bus.updated_arrival_time || arrival;
            const duration = bus.journey_duration || '--';
            const updatedEta = window.TransPulseUtils.etaDisplay(bus);
            const currentDelay = bus.current_delay_label || window.TransPulseUtils.formatMinutes(bus.current_delay_minutes || 0);
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
                                <div class="col-12 col-md-4 border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Current Stop</small>
                                    <strong class="text-white fs-6">${window.TransPulseUtils.escapeHtml(bus.current_stop || '--')}</strong>
                                </div>
                                <div class="col-12 col-md-4 border-end border-secondary border-opacity-50">
                                    <small class="text-muted d-block text-uppercase fw-bold" style="font-size:0.75rem;">Next Stop</small>
                                    <strong class="text-white fs-6">${window.TransPulseUtils.escapeHtml(bus.next_stop || '--')}</strong>
                                </div>
                                <div class="col-12 col-md-4">
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
                            <div class="text-end d-flex justify-content-end gap-2">
                                <button onclick="openBusModal('${bus.bus_id}')" class="btn btn-outline-info px-4 fw-bold shadow-sm">View Details</button>
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

document.addEventListener('DOMContentLoaded', async () => {
    if(window.Workflow) {
        await window.Workflow.init();
    }
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
                busesContainer.innerHTML = '<div class="text-center text-muted py-3 small">No live buses currently operating on this route.</div>';
                stopsContainer.innerHTML = `<div class="text-white text-center py-3"><strong>${targetRoute.source_stop || originName}</strong><br><span class="text-info fs-4">↓</span><br><strong>${targetRoute.destination_stop || destName}</strong></div>`;
            } else {
                busesContainer.innerHTML = '<div class="text-center text-muted py-3 small">No live buses currently operating on this route.</div>';
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
        window.location.hash = 'screen-sos';
        clearInterval(customSosTimer);
        resolvePremiumSOSBusNumber().then(busNumber => {
            const busInput = document.getElementById('premium-sos-bus-id');
            if (busInput && busNumber) busInput.value = busNumber;
        });
    }

    function cancelPremiumSOS() {
        window.history.back();
    }

    async function confirmPremiumSOS() {
        if (premiumSosSubmitting) return;
        
        const mobileInput = document.getElementById('premium-sos-mobile');
        if(!mobileInput.value || mobileInput.value.length < 10) {
            alert('Please enter a valid 10-digit mobile number.');
            return;
        }
        
        premiumSosSubmitting = true;
        clearInterval(customSosTimer);
        const reason = document.getElementById('premium-sos-reason').value;
        const mobileNumber = mobileInput.value;
        const busNumber = await resolvePremiumSOSBusNumber() || document.getElementById('premium-sos-bus-id').value;
        
        const sendButton = document.getElementById('btn-send-sos');
        if (sendButton) {
            sendButton.disabled = true;
            sendButton.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Sending...';
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
                headers: { 'Content-Type': 'application/json', "X-CSRFToken": window.TransPulseCSRF || document.querySelector('meta[name="csrf-token"]')?.content || '' },
                body: JSON.stringify({ emergency_type: reason, bus_number: busNumber, mobile_number: mobileNumber, ...gps })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.error || 'SOS could not be sent.');
            restorePremiumSOSDashboard();
            
            // Clear the form
            document.getElementById('premium-sos-reason').selectedIndex = 0;
            if (document.getElementById('premium-sos-bus-id')) document.getElementById('premium-sos-bus-id').value = '';
            
            // Show alert below form
            const activeContainer = document.getElementById('active-sos-container');
            const activeTitle = document.getElementById('active-sos-title');
            if (activeContainer) {
                if (activeTitle) activeTitle.classList.remove('d-none');
                const now = new Date().toLocaleTimeString();
                const alertHtml = `
                    <div class="card glass-panel shadow-sm mb-3" style="background: rgba(255, 50, 50, 0.1); border: 1px solid rgba(255, 50, 50, 0.4); border-left: 4px solid #ff3232;">
                        <div class="card-body p-4">
                            <div class="d-flex justify-content-between align-items-center mb-3">
                                <span class="badge bg-danger rounded-pill px-3 py-2"><i class="fa-solid fa-satellite-dish me-2"></i>SOS ACTIVE</span>
                                <span class="text-white-50 small"><i class="fa-regular fa-clock me-1"></i>${now}</span>
                            </div>
                            <h6 class="text-white fw-bold fs-5 mb-2">Reference: SOS-${String(data.id || 'N/A').padStart(5, '0')}</h6>
                            <div class="row text-white-50 small mb-3">
                                <div class="col-6"><strong>Bus ID:</strong> ${busNumber}</div>
                                <div class="col-6"><strong>Emergency:</strong> ${reason}</div>
                            </div>
                            <div class="alert border-0 p-2 mb-0 small rounded d-flex align-items-center" style="background: rgba(255,193,7,0.1); color: #ffc107;">
                                <i class="fa-solid fa-circle-notch fa-spin me-3 fs-5"></i>
                                <span>Authorities notified and tracking active. Help is on the way.</span>
                            </div>
                        </div>
                    </div>
                `;
                activeTitle.insertAdjacentHTML('afterend', alertHtml);
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
    const handleHashNavigation = () => {
        const hash = window.location.hash;
        if (hash === '#close') {
            // Leaflet popup was closed. Prevent redirecting home.
            window.history.replaceState(null, null, window.location.pathname + '#screen-nearby-stops');
            return;
        }
        if (!hash || hash === '#' || hash === '#home') {
            if(window.Workflow && typeof window.Workflow.goHome === 'function') {
                window.Workflow.goHome(false);
            }
            return;
        }

        const tryShowScreen = () => {
            if(window.Workflow && typeof window.Workflow.showScreen === 'function') {
                // Remove the '#' to get the target
                let targetId = hash.substring(1);
                
                // Map legacy hash aliases to their screen IDs
                const aliases = {
                    'search': 'screen-search-bus',
                    'live-tracking': 'screen-live-tracking',
                    'live-fleet': 'screen-live-fleet',
                    'routes': 'screen-routes',
                    'favorites': 'screen-favorites',
                    'nearby-stops': 'screen-nearby-stops'
                };
                
                if (aliases[targetId]) {
                    targetId = aliases[targetId];
                }
                
                // Ensure it's prefixed with screen-
                if (!targetId.startsWith('screen-')) {
                    targetId = 'screen-' + targetId;
                }
                
                // Try to show it if it exists
                if (document.getElementById(targetId)) {
                    if (targetId === 'screen-nearby-stops' && typeof window.Workflow.openNearbyStops === 'function') {
                        window.Workflow.openNearbyStops();
                    } else {
                        window.Workflow.showScreen(targetId, false);
                    }
                }
            } else {
                setTimeout(tryShowScreen, 50);
            }
        };
        tryShowScreen();
    };

    document.addEventListener('DOMContentLoaded', handleHashNavigation);
    window.addEventListener('hashchange', handleHashNavigation);

window.closeBusModal = function() {
    const modal = document.getElementById('busDetailsModal');
    if(modal) {
        modal.style.display = 'none';
        document.body.classList.remove('modal-open');
    }
};

window.openBusModal = function(busId) {
    document.body.classList.add('modal-open');
    document.getElementById('busDetailsModal').style.display = 'flex';
    
    // Find bus from flow manager apiData safely
    const bus = window.Workflow.apiData.buses.find(b => b && b.bus_id && b.bus_id.toString() === String(busId));
    
    const trackBtn = document.getElementById('bus-modal-track-btn');
    if (trackBtn) {
        trackBtn.href = `/tracking/${encodeURIComponent(bus ? bus.bus_number : busId)}?source=search`;
    }
    
    const titleEl = document.getElementById('bus-modal-title');
    if (titleEl) {
        titleEl.innerText = `Live Timeline: ${bus ? bus.bus_number : busId}`;
    }
    
    const timeline = document.getElementById('bus-modal-timeline');
    if (!timeline) return;
    
    if (!bus || !bus.stops || !bus.stops.length) {
        timeline.innerHTML = '<div class="text-muted small p-4 text-center">Route path sequence unavailable.</div>';
        return;
    }

    const totalStops = bus.stops.length;
    let html = '<div class="route-timeline">';
    bus.stops.forEach((stop, index) => {
        let marker = '○';
        let stateClass = 'stop-upcoming';
        
        if (bus.service_status === 'completed') {
            marker = '✔';
            stateClass = 'stop-completed';
        } else if (index < bus.completed_stops) {
            marker = '✔';
            stateClass = 'stop-completed';
        } else if (index === bus.active_stop_index) {
            marker = '▶';
            stateClass = 'stop-current';
        }

        let nameText = stop.name || '--';
        if (index === totalStops - 1) {
            nameText += ' (Destination)';
        }

        const scheduledTime = stop.scheduled_time || '--';
        const actualTime = stop.actual_time || '--';
        const meta = `
            <div class="route-stop-meta">
                <span>Scheduled: <strong>${scheduledTime}</strong></span>
                <span>Actual: <strong>${actualTime}</strong></span>
            </div>`;
            
        html += `
            <div class="timeline-stop ${stateClass}${index === totalStops - 1 ? ' stop-final' : ''}">
                <span class="stop-name">${marker} ${nameText}</span>
                ${meta}
            </div>
        `;
    });
    html += '</div>';
    timeline.innerHTML = html;
};

window.addEventListener('popstate', function(event) {
    if (event.state && event.state.screen && event.state.screen !== 'home') {
        if (window.Workflow) window.Workflow.showScreen(event.state.screen, false);
    } else {
        if (window.Workflow) window.Workflow.goHome(false);
    }
});
/* TP-v2.0-Release */
