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
        fetch('/heatmap/data')
            .then(r => r.json())
            .then(data => {
                this.citiesData = data.cities || [];
                this.initMap();
            })
            .catch(e => console.error("Heatmap Load Error:", e));
    },
    
    initMap: function() {
        this.map = L.map('real-heatmap-container', {
            zoomControl: true,
            minZoom: 5,
            maxBounds: [[6.0, 70.0], [23.0, 88.0]] 
        }).setView([15.9129, 79.7400], 6);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors',
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