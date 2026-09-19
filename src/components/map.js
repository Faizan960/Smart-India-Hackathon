import { store } from "../state/store.js";
import { STATIONS } from "../data/stations.js";

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

function isDarkMode() {
  // Support both classList and data-theme attribute
  return document.documentElement.getAttribute("data-theme") === "dark" ||
         document.documentElement.classList.contains("dark");
}

function updateMapTheme() {
  if (!mapInstance) return;
  const dark = isDarkMode();
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

  const now = Date.now();

  STATIONS.forEach(registry => {
    const live = state.stations.find(s => s.id === registry.id);
    const perStation = state.stationStatus?.[registry.id];

    let color = "#8e8e93"; // Offline grey by default
    let status = "Loading";
    let temp = "—";
    let hum = "—";

    if (perStation?.status === "LOADING") {
      color = "#ff9f0a";
      status = "Loading";
    } else if (perStation?.status === "ERROR") {
      color = "#ff3b30";
      status = "Error";
    } else if (live) {
      temp = live.temperature?.toFixed(1) || "—";
      hum = live.humidity?.toFixed(0) || "—";
      const obsEpoch = live.observedEpoch || live.lastUpdatedEpoch;
      const obsTime = obsEpoch ? obsEpoch * 1000 : new Date(live.timestamp).getTime();
      const isStale = (now - obsTime) > 5 * 60 * 1000;
      const hasCritical = state.anomalies.some(a => a.stationId === registry.id && a.severity === "CRITICAL");
      const hasWarning = state.anomalies.some(a => a.stationId === registry.id && a.severity === "WARNING");

      if (hasCritical) { color = "#ff3b30"; status = "Critical"; }
      else if (hasWarning) { color = "#ff9f0a"; status = "Warning"; }
      else if (isStale) { color = "#ff9f0a"; status = "Stale"; }
      else { color = "#34c759"; status = "Healthy"; }
    }

    const icon = L.divIcon({
      html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 1px 8px rgba(0,0,0,.3)"></div>`,
      className: "",
      iconSize: [14,14],
      iconAnchor: [7,7]
    });

    const popup = document.createElement("div");
    let metaHtml = "";
    if (live) {
      const obsEpoch = live.observedEpoch || live.lastUpdatedEpoch;
      const obsTimeStr = obsEpoch ? new Date(obsEpoch * 1000).toLocaleTimeString() : "--";
      const recEpoch = live.receivedEpoch || live.fetchedAtEpoch;
      const recTimeStr = recEpoch ? new Date(recEpoch * 1000).toLocaleTimeString() : new Date(live.fetchedAt || Date.now()).toLocaleTimeString();
      const ageSeconds = obsEpoch ? Math.floor((Date.now() / 1000) - obsEpoch) : 0;
      metaHtml = `
        <div style="margin-top:6px; font-size:11px; color:var(--text-tertiary);">
          Observed: ${obsTimeStr}<br>
          Received: ${recTimeStr}<br>
          Data age: ${ageSeconds}s ago<br>
          Provider: ${escapeHtml(live.provider || "Unknown")}
        </div>
      `;
    }

    popup.innerHTML = `
      <strong style="display:block;margin-bottom:2px;">${escapeHtml(registry.name)}</strong>
      <span style="font-size:12px;color:var(--text-secondary)">${escapeHtml(registry.id)} • ${status}</span><br>
      <div style="margin-top:6px;font-family:'JetBrains Mono', monospace;font-size:13px;">
        Temp: ${temp} °C<br>
        Hum: ${hum}%
      </div>
      ${metaHtml}
    `;

    const marker = L.marker([registry.latitude, registry.longitude], { icon })
      .bindPopup(popup)
      .addTo(mapInstance);

    marker.on("click", () => {
      window.navigateTo("stations");
      if (typeof window.viewStation === "function") {
        window.viewStation(registry.id);
      }
    });
    markers.push(marker);
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}
