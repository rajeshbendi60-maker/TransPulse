window.TransportHeatmap = {
    map: null,
    heatLayer: null,
    citiesData: [],
    
    init: function() {
        if (document.getElementById('real-heatmap-container')) {
            this.fetchDataAndInitMap();
        }
    },
    
    fetchDataAndInitMap: function() {
        Promise.all([
            fetch('/heatmap/data').then(r => r.ok ? r.json() : { cities: [] }).catch(() => ({ cities: [] })),
            fetch('/api/routes/live').then(r => r.ok ? r.json() : { routes: [] }).catch(() => ({ routes: [] }))
        ]).then(([heatmapData, liveRoutesData]) => {
            this.citiesData = heatmapData.cities || [];
            this.liveRoutes = liveRoutesData.routes || [];
            this.initMap();
        }).catch(e => console.error("Heatmap Load Error:", e));
    },
    
    initMap: function() {
        this.map = L.map('real-heatmap-container', {
            zoomControl: true,
            minZoom: 5,
            maxBounds: [[6.0, 70.0], [23.0, 88.0]] 
        }).setView([15.9129, 79.7400], 6);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
            maxZoom: 19
        }).addTo(this.map);

        const heatPoints = this.citiesData.map(city => [city.lat, city.lng, city.intensity]);

        this.heatLayer = L.heatLayer(heatPoints, {
            radius: 35,
            blur: 25,
            maxZoom: 8,
            gradient: {
                0.2: 'blue',
                0.4: 'green',
                0.6: 'yellow',
                0.8: 'orange',
                1.0: 'red'
            }
        }).addTo(this.map);

        this.citiesData.forEach(city => {
            const marker = L.circleMarker([city.lat, city.lng], {
                radius: 6,
                color: 'transparent',
                fillColor: 'transparent',
                fillOpacity: 0.0
            }).addTo(this.map);

            marker.bindPopup(`
                <div style="text-align:center; padding: 4px; color: #333;">
                    <strong style="font-family:'Poppins',sans-serif;font-size:1rem;display:block;margin-bottom:2px;">${city.name}</strong>
                    <span style="font-weight:700;color:#0b1d36;">Density Score: ${city.intensity.toFixed(2)}</span>
                </div>
            `);
        });

        // Draw solid colored route lines on main heatmap map
        this.routesLayerGroup = L.layerGroup().addTo(this.map);
        this.liveRoutes.forEach(route => {
            const path = route.display_path || route.path || (route.stops ? route.stops.map(s => ({ lat: s.lat, lng: s.lng || s.lon })) : []);
            if (path && path.length >= 2) {
                let totalIntensity = 0;
                let matchCount = 0;
                if (route.stops && route.stops.length) {
                    route.stops.forEach(s => {
                        const match = this.citiesData.find(c => String(c.name).toLowerCase().trim() === String(s.name || s.stop_name).toLowerCase().trim());
                        if (match) {
                            totalIntensity += match.intensity || 0;
                            matchCount++;
                        }
                    });
                }
                const avgIntensity = matchCount > 0 ? (totalIntensity / matchCount) : 0.1;
                
                let color = '#22c55e'; // Green
                if (avgIntensity >= 0.8) color = '#ef4444'; // Red
                else if (avgIntensity >= 0.6) color = '#fb923c'; // Orange
                else if (avgIntensity >= 0.4) color = '#facc15'; // Yellow
                else if (avgIntensity >= 0.2) color = '#4ade80'; // Light Green

                L.polyline(path.map(p => [p.lat, p.lng || p.lon]), {
                    color: color,
                    weight: 5,
                    opacity: 0.85
                }).addTo(this.routesLayerGroup).bindPopup(`
                    <div style="padding: 4px; color:#333;">
                        <strong>Route: ${route.route_name || route.route_code}</strong><br>
                        <span>Traffic Status: ${avgIntensity >= 0.8 ? 'Heavy' : avgIntensity >= 0.6 ? 'Moderate-Heavy' : avgIntensity >= 0.4 ? 'Moderate' : 'Low'}</span>
                    </div>
                `);
            }
        });

        const legend = L.control({ position: 'bottomright' });
        legend.onAdd = function () {
            const div = L.DomUtil.create('div', 'info-legend');
            div.style.background = 'rgba(255, 255, 255, 0.95)';
            div.style.color = '#333';
            div.style.padding = '12px';
            div.style.borderRadius = '8px';
            div.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
            div.innerHTML = `
                <h6 style="margin: 0 0 8px 0; font-weight: 700; color: #000;">Passenger Density</h6>
                <div style="margin-bottom: 4px;"><i style="background:red; width:16px; height:16px; float:left; margin-right:8px; border-radius:3px;"></i> High (1.0)</div>
                <div style="margin-bottom: 4px;"><i style="background:orange; width:16px; height:16px; float:left; margin-right:8px; border-radius:3px;"></i> Medium-High (0.8)</div>
                <div style="margin-bottom: 4px;"><i style="background:yellow; width:16px; height:16px; float:left; margin-right:8px; border-radius:3px; border:1px solid #ccc;"></i> Medium (0.6)</div>
                <div style="margin-bottom: 4px;"><i style="background:green; width:16px; height:16px; float:left; margin-right:8px; border-radius:3px;"></i> Low-Medium (0.4)</div>
                <div><i style="background:blue; width:16px; height:16px; float:left; margin-right:8px; border-radius:3px;"></i> Low (0.2)</div>
            `;
            return div;
        };
        legend.addTo(this.map);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => window.TransportHeatmap.init(), 100);
});