window.DriverPerformance = {
    drivers: [],
    analytics: {},
    
    init: function() {
        if (!document.getElementById('driver-analytics-container')) return;
        this.loadData();
    },
    
    loadData: function() {
        fetch('/api/driver/analytics')
            .then(r => {
                if (!r.ok) throw new Error('API Error');
                return r.json();
            })
            .catch(() => ({ drivers: [], analytics: {} }))
            .then(data => {
                this.drivers = data.drivers || [];
                this.analytics = data.analytics || {};
                this.renderAnalytics();
            });
    },
    
    renderAnalytics: function() {
        const container = document.getElementById('driver-analytics-container');
        if (!container) return;
        
        // 1. Safely compute aggregates utilizing backend keys and driver arrays
        const driverCount = this.drivers.length || 1;
        const totalTrips = this.analytics.total_trips || this.drivers.reduce((sum, d) => sum + d.trips_completed, 0);
        const avgScore = this.analytics.average_score || Math.round(this.drivers.reduce((sum, d) => sum + d.driver_score, 0) / driverCount);
        const avgOnTime = Math.round(this.drivers.reduce((sum, d) => sum + d.on_time_percentage, 0) / driverCount);
        const totalDistance = this.drivers.reduce((sum, d) => sum + d.distance_covered, 0);
        
        // 2. Build the top metrics grid
        const metrics = [
            { label: 'Total Trips', value: totalTrips, icon: '🚌', color: '#34d2ff' },
            { label: 'Avg On-Time', value: avgOnTime + '%', icon: '⏱️', color: '#22d39a' },
            { label: 'Team Score', value: avgScore, icon: '⭐', color: '#f5b342' },
            { label: 'Distance', value: (totalDistance / 1000).toFixed(1) + 'k', icon: '📍', color: '#6a5cff' }
        ];
        
        let html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px;">';
        metrics.forEach(metric => {
            html += `
                <div style="background: linear-gradient(135deg, rgba(52,210,255,0.08), rgba(79,141,255,0.04)); border: 1px solid rgba(52,210,255,0.2); border-radius: 10px; padding: 12px; text-align: center;">
                    <div style="font-size:1.5rem;margin-bottom:4px">${metric.icon}</div>
                    <p style="margin:0;font-weight:700;font-size:1.2rem;color:${metric.color}">${metric.value}</p>
                    <small style="color:#9ec0e6;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.5px">${metric.label}</small>
                </div>
            `;
        });
        html += '</div>';
        
        // 3. Build the leaderboard (Top 5 Drivers)
        html += '<div class="d-flex justify-content-between align-items-center mb-3">';
        html += '<h6 style="color:#e6f1ff;margin:0;font-weight:600;">Top Performers</h6>';
        html += '<span class="badge" style="background:rgba(245,179,66,0.2);color:#f5b342;">Ranked by Score</span>';
        html += '</div>';
        
        html += '<div style="display:flex;flex-direction:column;gap:8px;">';
        
        const topDrivers = [...this.drivers].sort((a, b) => b.driver_score - a.driver_score).slice(0, 5);
        
        if (topDrivers.length === 0) {
            html += '<div class="text-center text-muted small py-3">No active drivers found.</div>';
        }
        
        topDrivers.forEach((driver, index) => {
            // Gold, Silver, Bronze, and Standard styling
            const rankColor = index === 0 ? '#f5b342' : index === 1 ? '#e6f1ff' : index === 2 ? '#cd7f32' : '#34d2ff';
            const bgOpacity = index === 0 ? '0.15' : '0.05';
            
            html += `
                <div style="display:flex;align-items:center;background:rgba(255,255,255,${bgOpacity});border:1px solid rgba(52,210,255,0.1);border-radius:8px;padding:12px;">
                    <div style="width:28px;height:28px;border-radius:50%;background:rgba(255,255,255,0.1);color:${rankColor};display:flex;align-items:center;justify-content:center;font-weight:700;font-size:0.85rem;margin-right:12px;box-shadow:0 0 8px rgba(${index === 0 ? '245,179,66' : '0,0,0'},0.3);">
                        ${index + 1}
                    </div>
                    <div style="flex-grow:1;">
                        <div style="font-weight:600;color:#e6f1ff;font-size:0.95rem;margin-bottom:2px;">${driver.name}</div>
                        <div style="font-size:0.75rem;color:#22d39a;">${driver.on_time_percentage}% On-Time · ${driver.trips_completed} Trips</div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-weight:800;color:#34d2ff;font-size:1.1rem;">${driver.driver_score}</div>
                        <div style="font-size:0.7rem;color:#9ec0e6;text-transform:uppercase;">Score</div>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        
        container.innerHTML = html;
    }
};

// INITIALIZATION HOOK: This was missing previously!
document.addEventListener('DOMContentLoaded', () => {
    if (window.DriverPerformance) {
        window.DriverPerformance.init();
    }
});