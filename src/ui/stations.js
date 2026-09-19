import { store } from "../state/store.js";
import { STATIONS } from "../data/stations.js";

let currentFilter = "";

export function initStations() {
  store.subscribe(renderStations);
  
  const searchInput = document.getElementById("stationListSearch");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      currentFilter = e.target.value.toLowerCase();
      renderStations(store.state);
    });
  }
}

export function viewStationList() {
  document.getElementById("stationListView").style.display = "block";
  document.getElementById("stationDetailView").style.display = "none";
}

export function viewStation(stationId) {
  // Update state and chart selection
  store.state.selectedStationId = stationId;
  const liveStation = store.state.stations.find(s => s.id === stationId);
  const registry = STATIONS.find(s => s.id === stationId);
  const station = liveStation || registry;
  store.state.selectedStation = station;
  
  if (station) populateStationDetail(station);
  
  document.getElementById("stationListView").style.display = "none";
  document.getElementById("stationDetailView").style.display = "block";
}

// Make accessible for HTML onclick
window.viewStationList = viewStationList;
window.viewStation = viewStation;

function renderStations(state) {
  const container = document.getElementById("stationListContainer");
  if (!container) return;

  const now = Date.now();
  
  // Merge registry with live state to show offline/missing stations too
  const fullList = STATIONS.map(registry => {
    const live = state.stations.find(s => s.id === registry.id);
    return { ...registry, live };
  });

  const filtered = fullList.filter(s => {
    if (!currentFilter) return true;
    return s.name.toLowerCase().includes(currentFilter) ||
           s.id.toLowerCase().includes(currentFilter) ||
           s.region.toLowerCase().includes(currentFilter);
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-tertiary);">No stations match your search.</div>`;
    return;
  }

  container.innerHTML = filtered.map(s => {
    let status = "Offline";
    let statusClass = "offline";
    let temp = "--";
    
    if (s.live) {
      temp = `${s.live.temperature?.toFixed(1) || "--"} °C`;
      const isStale = (now - new Date(s.live.timestamp).getTime()) > 5 * 60 * 1000;
      const hasCritical = state.anomalies.some(a => a.stationId === s.id && a.severity === "CRITICAL");
      const hasWarning = state.anomalies.some(a => a.stationId === s.id && a.severity === "WARNING");
      
      if (hasCritical) { status = "Critical"; statusClass = "critical"; }
      else if (hasWarning) { status = "Warning"; statusClass = "warning"; }
      else if (isStale) { status = "Stale"; statusClass = "warning"; }
      else { status = "Healthy"; statusClass = "healthy"; }
    }

    return `
      <div class="attention-row" onclick="window.viewStation('${s.id}')">
        <span class="severity-dot ${statusClass}"></span>
        <span class="attention-station">${s.id}</span>
        <span class="attention-sensor">${s.name}</span>
        <span class="attention-issue" style="font-family: 'JetBrains Mono', monospace;">${temp}</span>
        <span class="attention-time">${s.region}</span>
        <span class="attention-severity ${statusClass}">${status}</span>
      </div>
    `;
  }).join("");
}

function populateStationDetail(station) {
  document.getElementById("stationTitle").textContent = `${station.station || station.name || station.id} — ${station.id}`;
  const lat = Number(station?.latitude || 0).toFixed(4);
  const lon = Number(station?.longitude || 0).toFixed(4);
  document.getElementById("stationLocation").textContent = `Lat: ${lat}, Lon: ${lon}`;
  
  const obsTime = new Date(station.lastUpdatedEpoch ? station.lastUpdatedEpoch * 1000 : station.timestamp);
  const recTime = new Date(station.fetchedAtEpoch ? station.fetchedAtEpoch * 1000 : (station.fetchedAt || Date.now()));
  
  document.getElementById("stationObservationTime").textContent = isNaN(obsTime.getTime()) ? "--" : obsTime.toLocaleTimeString();
  document.getElementById("stationReceivedTime").textContent = isNaN(recTime.getTime()) ? "--" : recTime.toLocaleTimeString();
  
  const historySeries = store.state.history[station.id] || [];
  document.getElementById("stationHistoryCount").textContent = `${historySeries.length} observations`;
  document.getElementById("stationSource").textContent = station.provider === "OpenWeatherMap" ? "Live OpenWeatherMap observation" : (station.provider || "Unknown");

  // Fill sensors
  document.getElementById("sensorTemp").textContent = station.temperature !== null && station.temperature !== undefined ? station.temperature.toFixed(1) : "--";
  document.getElementById("sensorHum").textContent = station.humidity !== null && station.humidity !== undefined ? station.humidity.toFixed(0) : "--";
  document.getElementById("sensorPres").textContent = station.pressure !== null && station.pressure !== undefined ? station.pressure.toFixed(0) : "--";
  const wind = station.windSpeed ?? station.wind_speed;
  document.getElementById("sensorWind").textContent = wind !== null && wind !== undefined ? Number(wind).toFixed(1) : "--";

  // Check state
  const now = Date.now();
  const isStale = (now - obsTime.getTime()) > 5 * 60 * 1000;
  const hasCritical = store.state.anomalies.some(a => a.stationId === station.id && a.severity === "CRITICAL");
  const hasWarning = store.state.anomalies.some(a => a.stationId === station.id && a.severity === "WARNING");
  
  const statusDot = document.getElementById("stationStatusDot");
  const statusText = document.getElementById("stationStatusText");
  
  if (hasCritical) {
    statusDot.className = "severity-dot critical";
    statusText.textContent = "Critical Anomaly";
  } else if (hasWarning) {
    statusDot.className = "severity-dot warning";
    statusText.textContent = "Sensor Warning";
  } else if (isStale) {
    statusDot.className = "severity-dot warning";
    statusText.textContent = "Stale Data";
  } else {
    statusDot.className = "severity-dot healthy";
    statusText.textContent = "Healthy";
  }

  // Raw API rendering
  document.getElementById("rawApiContent").textContent = JSON.stringify(station, null, 2);
  
  // Trigger chart re-render
  window.dispatchEvent(new CustomEvent("stationSelected", { detail: { stationId: station.id } }));
}
