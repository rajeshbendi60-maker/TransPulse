window.CommandCenter = {
    activeBuses: [],
    activeRoutes: [],
    activeDrivers: 0,
    delayedVehicles: [],
    stats: {},
    refreshInterval: null,

    init: function() {
        if (!document.getElementById('command-center-widget')) return;
        this.loadData();
        this.startAutoRefresh();
    },

    startAutoRefresh: function() {
        this.refreshInterval = setInterval(() => {
            if (!document.hidden) {
                this.loadData();
            }
        }, 5000);
    },

    loadData: function() {
        Promise.all([
            fetch('/api/buses/live').then(r => r.json()),
            fetch('/api/routes/live').then(r => r.json()),
            fetch('/api/command-center/stats').then(r => r.json()).catch(() => ({}))
        ]).then(([busesResponse, routesResponse, statsResponse]) => {
            
            // ROOT CAUSE FIX: Safely extract the nested arrays from the API wrapper objects
            const busesArray = busesResponse.buses || [];
            const routesArray = routesResponse.routes || [];

            this.activeBuses = busesArray.filter(b => b.status === 'in_progress' || b.status === 'active');
            this.activeRoutes = routesArray;
            
            // Utilize the dedicated stats payload from the backend
            this.stats = statsResponse || {};
            this.activeDrivers = this.stats.active_drivers || 0;
            this.delayedVehicles = this.calculateDelayedBuses(busesArray);

            this.updateDashboard();
        }).catch(err => console.error("Command Center Load Error:", err));
    },

    calculateDelayedBuses: function(busesArray) {
        return busesArray.filter(bus => bus.service_status === 'delayed');
    },

    updateDashboard: function() {
        const container = document.getElementById('command-center-widget');
        if (!container) return;
        
        // Structure the metrics dynamically using backend stats or calculated fallbacks
        const metrics = [
            { label: 'Active Buses', value: this.stats.active_buses || this.activeBuses.length || 0, color: '#34d2ff', icon: '🚌' },
            { label: 'Active Routes', value: this.stats.active_routes || this.activeRoutes.length || 0, color: '#22d39a', icon: '🗺️' },
            { label: 'Active Drivers', value: this.stats.active_drivers || this.activeDrivers || 0, color: '#f5b342', icon: '👨‍✈️' },
            { label: 'Passengers Served', value: this.stats.passengers_served || 0, color: '#6a5cff', icon: '👥' },
            { label: 'Delayed Vehicles', value: this.stats.delayed_vehicles || this.delayedVehicles.length || 0, color: '#ff5d6c', icon: '⚠️' },
            { label: 'Avg ETA', value: (this.stats.average_eta || 0) + ' mins', color: '#e6f1ff', icon: '⏱️' }
        ];

        let html = '<div class="row g-3 mb-3">';
        metrics.forEach(m => {
            html += `
                <div class="col-6 col-md-4">
                    <div style="background:rgba(255,255,255,0.05); padding:15px; border-radius:10px; border:1px solid rgba(52,210,255,0.1); text-align:center;">
                        <div style="font-size:1.5rem; margin-bottom:5px;">${m.icon}</div>
                        <h4 style="color:${m.color}; margin-bottom:5px; font-weight:700;">${m.value}</h4>
                        <small style="color:#9ec0e6; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.5px;">${m.label}</small>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        
        // Preserve Fleet Health insertion point
        html += '<div id="fleet-health"></div>';

        container.innerHTML = html;
        this.updateFleetHealthIndicator();
    },

    updateFleetHealthIndicator: function() {
        const healthContainer = document.getElementById('fleet-health');
        if (!healthContainer) return;

        const count = this.stats.active_buses || this.activeBuses.length || 0;
        const health = Math.min(Math.round((count / 15) * 100), 100);
        const statusText = health > 80 ? 'Excellent' : health > 60 ? 'Good' : health > 40 ? 'Fair' : 'Poor';
        const statusColor = health > 80 ? '#22d39a' : health > 60 ? '#f5b342' : '#ff5d6c';

        healthContainer.innerHTML = `
            <div style="margin-bottom:10px; padding-top:10px; border-top: 1px solid rgba(52,210,255,0.2);">
                <div style="display:flex;justify-content:space-between;margin-bottom:5px">
                    <span style="font-weight:600; color:#e6f1ff;">Fleet Health</span>
                    <span style="color:${statusColor};font-weight:700">${health}%</span>
                </div>
                <div style="width:100%;height:8px;background:rgba(255,255,255,0.1);border-radius:4px;overflow:hidden">
                    <div style="width:${health}%;height:100%;background:linear-gradient(90deg,#34d2ff,#4f8dff);transition:width 0.5s ease"></div>
                </div>
            </div>
            <small style="color:#9ec0e6">System Status: ${statusText}</small>
        `;
    }
};

document.addEventListener('DOMContentLoaded', () => {
    if (window.CommandCenter) window.CommandCenter.init();
});