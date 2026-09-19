import { store } from "../state/store.js";

let mapInstance = null;
let markers = [];
let lightLayer;
let darkLayer;

export async function initMap(containerId) {
  if (mapInstance || !document.getElementById(containerId)) return;

  mapInstance = L.map(containerId).setView([20.5937, 78.9629], 5);

  const cartoKey = window.appConfig?.cartoBasemapKey || "";
  const keyParam = cartoKey ? `?key=${encodeURIComponent(cartoKey)}` : "";

  lightLayer = L.tileLayer(
    `https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png${keyParam}`,
    { attribution: "&copy; OpenStreetMap contributors &copy; CARTO" }
  );
  darkLayer = L.tileLayer(
    `https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png${keyParam}`,
    { attribution: "&copy; OpenStreetMap contributors &copy; CARTO" }
  );

  updateMapTheme();
  window.addEventListener("themeChanged", updateMapTheme);
  store.subscribe(renderMarkers);
}

function updateMapTheme() {
  if (!mapInstance) return;
  const dark = document.documentElement.classList.contains("dark");
  if (dark) {
    if (mapInstance.hasLayer(lightLayer)) mapInstance.removeLayer(lightLayer);
    if (!mapInstance.hasLayer(darkLayer)) darkLayer.addTo(mapInstance);
  } else {
    if (mapInstance.hasLayer(darkLayer)) mapInstance.removeLayer(darkLayer);
    if (!mapInstance.hasLayer(lightLayer)) lightLayer.addTo(mapInstance);
  }
}

function renderMarkers(state) {
  if (!mapInstance) return;

  markers.forEach(m => mapInstance.removeLayer(m));
  markers = [];

  const stations = state.data || [];
  stations.forEach(station => {
    if (!Number.isFinite(station.latitude) || !Number.isFinite(station.longitude)) return;

    const stationAnomalies = (state.anomalies || []).filter(a => a.stationId === station.id);
    const color = stationAnomalies.some(a => a.severity === "CRITICAL")
      ? "#ff453a"
      : stationAnomalies.length
        ? "#ff9f0a"
        : "#34c759";

    const icon = L.divIcon({
      html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 1px 8px rgba(0,0,0,.3)"></div>`,
      className: "",
      iconSize: [14,14],
      iconAnchor: [7,7]
    });

    const popup = document.createElement("div");
    popup.innerHTML = `
      <strong>${escapeHtml(station.station || station.callSign || station.id)}</strong><br>
      ${escapeHtml(station.callSign || station.id)}<br>
      ${escapeHtml(station.district || "")}, ${escapeHtml(station.state || "")}<br>
      Temperature: ${station.temperature ?? "—"} °C<br>
      Humidity: ${station.humidity ?? "—"}%
    `;

    const marker = L.marker([station.latitude, station.longitude], { icon })
      .bindPopup(popup)
      .addTo(mapInstance);

    marker.on("click", () => store.setSelectedStation(station.id));
    markers.push(marker);
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}
