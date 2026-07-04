window.OccupancyTracker = {
    occupancyData: {},
    map: null,
    markers: [],
    
    init: function() {
        this.loadOccupancyData();
        setInterval(() => this.loadOccupancyData(), 5000);
    },
    
    loadOccupancyData: function() {
        fetch('/api/occupancy/live')
            .then(r => r.json())
            .catch(() => this.generateSampleOccupancy())
            .then(data => {
                this.occupancyData = data;
                this.updateOccupancyDisplay();
            });
    },
    
    generateSampleOccupancy: function() {
        const occupancy = {};
        for (let i = 1; i <= 15; i++) {
            occupancy[i] = {
                bus_id: i,
                total_seats: 55,
                occupied_seats: Math.floor(Math.random() * 55),
                occupancy_level: ['low', 'medium', 'high'][Math.floor(Math.random() * 3)]
            };
        }
        return occupancy;
    },
    
    updateOccupancyDisplay: function() {
        Object.entries(this.occupancyData).forEach(([busId, data]) => {
            this.updateBusOccupancy(busId, data);
        });
    },
    
    updateBusOccupancy: function(busId, data) {
        const occupancyBar = document.querySelector(`[data-occupancy-bus="${busId}"]`);
        if (!occupancyBar) return;
        
        const percentage = Math.round((data.occupied_seats / data.total_seats) * 100);
        const available = data.total_seats - data.occupied_seats;
        
        let color = '#22d39a';
        let levelText = 'Low';
        
        if (data.occupancy_level === 'medium') {
            color = '#f5b342';
            levelText = 'Medium';
        } else if (data.occupancy_level === 'high') {
            color = '#ff5d6c';
            levelText = 'High';
        }
        
        occupancyBar.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <span style="font-weight:600">Occupancy</span>
                <span style="background:${color}33;color:${color};padding:4px 10px;border-radius:20px;font-size:0.8rem;font-weight:600">${levelText} ${percentage}%</span>
            </div>
            <div style="width:100%;height:12px;background:rgba(255,255,255,0.1);border-radius:6px;overflow:hidden;margin-bottom:8px">
                <div style="width:${percentage}%;height:100%;background:${color};border-radius:6px;transition:width 0.5s ease"></div>
            </div>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:0.85rem">
                <div style="background:rgba(255,255,255,0.05);padding:8px;border-radius:6px;text-align:center">
                    <small style="color:#9ec0e6">Occupied</small>
                    <p style="margin:4px 0;font-weight:600;color:#e6f1ff">${data.occupied_seats}</p>
                </div>
                <div style="background:rgba(255,255,255,0.05);padding:8px;border-radius:6px;text-align:center">
                    <small style="color:#9ec0e6">Available</small>
                    <p style="margin:4px 0;font-weight:600;color:#22d39a">${available}</p>
                </div>
                <div style="background:rgba(255,255,255,0.05);padding:8px;border-radius:6px;text-align:center">
                    <small style="color:#9ec0e6">Total</small>
                    <p style="margin:4px 0;font-weight:600;color:#34d2ff">${data.total_seats}</p>
                </div>
            </div>
        `;
    },
    
    getOccupancyColor: function(level) {
        const colors = {
            'low': '#22d39a',
            'medium': '#f5b342',
            'high': '#ff5d6c'
        };
        return colors[level] || '#9ec0e6';
    }
};

document.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('[data-occupancy-bus]')) {
        window.OccupancyTracker.init();
    }
});
