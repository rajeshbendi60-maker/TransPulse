window.RouteRecommendation = {
    routesData: [],

    init: async function() {
        const sourceSelect = document.getElementById('route-source');
        const destSelect = document.getElementById('route-destination');
        const btn = document.getElementById('recommend-route-btn');
        
        if (!sourceSelect || !destSelect || !btn) return;

        try {
            const response = await fetch('/api/routes/live');
            if (!response.ok) throw new Error('Network response was not ok');
            
            const data = await response.json();
            this.routesData = data.routes || []; 
            
            this.populateDropdowns(sourceSelect, destSelect);
            btn.addEventListener('click', () => this.findRecommendations());
        } catch (error) {
            console.error("Error loading routes for recommendation:", error);
        }
    },

    populateDropdowns: function(sourceSelect, destSelect) {
        const origins = new Set();
        const destinations = new Set();

        this.routesData.forEach(route => {
            if (route.source_stop) origins.add(route.source_stop);
            if (route.destination_stop) destinations.add(route.destination_stop);
        });

        sourceSelect.innerHTML = '<option value="">Select origin...</option>';
        destSelect.innerHTML = '<option value="">Select destination...</option>';

        Array.from(origins).sort().forEach(origin => {
            const opt = document.createElement('option');
            opt.value = origin;
            opt.textContent = origin;
            sourceSelect.appendChild(opt);
        });

        Array.from(destinations).sort().forEach(dest => {
            const opt = document.createElement('option');
            opt.value = dest;
            opt.textContent = dest;
            destSelect.appendChild(opt);
        });
    },

    findRecommendations: function() {
        const source = document.getElementById('route-source').value;
        const dest = document.getElementById('route-destination').value;
        const container = document.getElementById('recommendations-container');
        
        if (!container) return;

        if (!source && !dest) {
            container.innerHTML = '<div style="color:#f5b342; padding:10px; background:rgba(245,179,66,0.1); border-radius:8px;">Please select an origin or destination.</div>';
            return;
        }

        const results = this.routesData.filter(route => {
            const matchSource = source ? route.source_stop === source : true;
            const matchDest = dest ? route.destination_stop === dest : true;
            return matchSource && matchDest;
        });

        if (results.length === 0) {
            container.innerHTML = '<div style="color:#aebed8; padding:10px; background:rgba(255,255,255,0.05); border-radius:8px;">No direct routes found matching your criteria.</div>';
            return;
        }

        let html = '<div class="list-group" style="gap:8px;">';
        results.forEach(route => {
            html += `
                <div class="list-group-item d-flex justify-content-between align-items-center" style="background: rgba(8, 22, 40, 0.6); border-radius: 8px; border: 1px solid rgba(52,210,255,0.2); padding: 12px;">
                    <div>
                        <h6 style="color:#34d2ff; margin-bottom:4px; font-weight:700;">${route.route_code}</h6>
                        <small style="color:#e6f1ff;">${route.source_stop} → ${route.destination_stop}</small>
                    </div>
                    <div class="text-end">
                        <span class="badge" style="background:rgba(255,255,255,0.1); color:#aebed8; margin-bottom:6px; display:inline-block;">${route.distance_km || '--'} km</span><br>
                        <button class="btn btn-sm" style="background:rgba(52,210,255,0.15); color:#34d2ff; border:1px solid rgba(52,210,255,0.3);" onclick="if(window.TransPulseTracking) window.TransPulseTracking.openFullscreenTracking(${route.route_id}, '${route.route_code}', '${route.source_stop}', '${route.destination_stop}')">📍 Track</button>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        container.innerHTML = html;
    }
};

document.addEventListener('DOMContentLoaded', () => {
    if (window.RouteRecommendation) {
        window.RouteRecommendation.init();
    }
});