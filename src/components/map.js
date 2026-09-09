import { store } from '../state/store.js';

let mapInstance = null;
let markers = [];

export function initMap(containerId) {
    if (mapInstance) return;
    
    // Default to India center
    mapInstance = L.map(containerId).setView([20.5937, 78.9629], 5);
    
    // Add dark/light compatible tiles (using CartoDB Voyager as base, we can use CartoDB Dark Matter for dark mode)
    const lightLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
    });
    
    const darkLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
    });
    
    function updateMapTheme() {
        if (document.documentElement.classList.contains('dark')) {
            mapInstance.removeLayer(lightLayer);
            darkLayer.addTo(mapInstance);
        } else {
            mapInstance.removeLayer(darkLayer);
            lightLayer.addTo(mapInstance);
        }
    }
    
    updateMapTheme();
    window.addEventListener('themeChanged', updateMapTheme);
    
    // Listen to store updates to draw markers
    store.subscribe((state) => {
        if (!state.data || state.data.length === 0) return;
        
        // Clear old markers
        markers.forEach(m => mapInstance.removeLayer(m));
        markers = [];
        
        state.data.forEach(station => {
            if (!station.latitude || !station.longitude) return;
            
            // Determine color based on anomalies
            const stationAnomalies = state.anomalies.filter(a => a.stationId === station.id);
            let color = '#2fa876'; // Healthy Green
            if (stationAnomalies.some(a => a.severity === 'CRITICAL')) color = '#d9483f'; // Red
            else if (stationAnomalies.some(a => a.severity === 'WARNING')) color = '#d9752f'; // Amber
            
            const markerHtml = `<div style="background-color: ${color}; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 5px rgba(0,0,0,0.5);"></div>`;
            const icon = L.divIcon({ html: markerHtml, className: 'custom-leaflet-marker', iconSize: [14, 14], iconAnchor: [7, 7] });
            
            const popupHtml = `
                <div class="p-2">
                    <h3 class="font-bold text-sm mb-1">${station.callSign || station.station}</h3>
                    <p class="text-xs text-gray-500">${station.district || ''}, ${station.state || ''}</p>
                    <div class="mt-2 text-xs">
                        <div>Temp: ${station.temperature}°C</div>
                        <div>Hum: ${station.humidity}%</div>
                        <div class="mt-1 font-medium text-${color === '#2fa876' ? 'green' : 'red'}-600">
                            ${stationAnomalies.length > 0 ? stationAnomalies.length + ' Anomalies' : 'Healthy'}
                        </div>
                    </div>
                </div>
            `;
            
            const marker = L.marker([station.latitude, station.longitude], { icon })
                .bindPopup(popupHtml)
                .addTo(mapInstance);
                
            markers.push(marker);
        });
    });
}
