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

  // Trigger chart re-render after DOM is visible
  requestAnimationFrame(() => {
    window.dispatchEvent(new CustomEvent("stationSelected", { detail: { stationId } }));
    store.notify();
  });
}

// Make accessible for HTML onclick
window.viewStationList = viewStationList;
window.viewStation = viewStation;

function renderStations(state) {
  const container = document.getElementById("stationListContainer");
  if (!container) return;

  const now = Date.now();

  // Always render ALL registry stations, merged with live state
  const fullList = STATIONS.map(registry => {
    const live = state.stations.find(s => s.id === registry.id);
    const perStation = state.stationStatus?.[registry.id];
    return { ...registry, live, perStation };
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
    let status = "Loading";
    let statusClass = "warning";
    let temp = "--";

    if (s.perStation?.status === "ERROR") {
      status = "Error";
      statusClass = "critical";
    } else if (s.perStation?.status === "LOADING") {
      status = "Loading";
      statusClass = "warning";
    } else if (s.live) {
      temp = s.live.temperature !== null && s.live.temperature !== undefined
        ? `${s.live.temperature.toFixed(1)} °C`
        : "--";

      const obsEpoch = s.live.observedEpoch || s.live.lastUpdatedEpoch;
      const obsTime = obsEpoch ? obsEpoch * 1000 : new Date(s.live.timestamp).getTime();
      const isStale = (now - obsTime) > 5 * 60 * 1000;
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

  // Observation time (upstream dt)
  const obsEpoch = station.observedEpoch || station.lastUpdatedEpoch;
  const obsTime = obsEpoch ? new Date(obsEpoch * 1000) : (station.timestamp ? new Date(station.timestamp) : null);
  document.getElementById("stationObservationTime").textContent = obsTime && !isNaN(obsTime.getTime())
    ? obsTime.toLocaleTimeString()
    : "--";

  // Received time
  const recEpoch = station.receivedEpoch || station.fetchedAtEpoch;
  const recTime = recEpoch ? new Date(recEpoch * 1000) : (station.fetchedAt ? new Date(station.fetchedAt) : null);
  document.getElementById("stationReceivedTime").textContent = recTime && !isNaN(recTime.getTime())
    ? recTime.toLocaleTimeString()
    : "--";

  // Data age
  const dataAgeEl = document.getElementById("stationDataAge");
  if (dataAgeEl && obsEpoch) {
    const ageSeconds = Math.floor(Date.now() / 1000 - obsEpoch);
    dataAgeEl.textContent = `${ageSeconds}s ago`;
  } else if (dataAgeEl) {
    dataAgeEl.textContent = "--";
  }

  // History count
  const historySeries = store.state.history[station.id] || [];
  const histCountEl = document.getElementById("stationHistoryCount");
  if (histCountEl) {
    if (historySeries.length === 0) {
      histCountEl.textContent = "No observations yet";
    } else {
      // Calculate actual collection span
      const firstEpoch = historySeries[0].observedEpoch || historySeries[0].lastUpdatedEpoch || 0;
      const lastEpoch = historySeries[historySeries.length - 1].observedEpoch || historySeries[historySeries.length - 1].lastUpdatedEpoch || 0;
      const spanMinutes = firstEpoch && lastEpoch ? Math.floor((lastEpoch - firstEpoch) / 60) : 0;
      let spanStr = "";
      if (spanMinutes > 60) spanStr = ` over ${Math.floor(spanMinutes / 60)}h ${spanMinutes % 60}m`;
      else if (spanMinutes > 0) spanStr = ` over ${spanMinutes} min`;
      histCountEl.textContent = `${historySeries.length} observations${spanStr}`;
    }
  }

  // Source
  document.getElementById("stationSource").textContent = station.provider === "OpenWeatherMap" ? "Live OpenWeatherMap" : (station.provider || "Unknown");

  // Fill sensors
  document.getElementById("sensorTemp").textContent = station.temperature !== null && station.temperature !== undefined ? station.temperature.toFixed(1) : "--";
  document.getElementById("sensorHum").textContent = station.humidity !== null && station.humidity !== undefined ? station.humidity.toFixed(0) : "--";
  document.getElementById("sensorPres").textContent = station.pressure !== null && station.pressure !== undefined ? station.pressure.toFixed(0) : "--";
  const wind = station.windSpeed ?? station.wind_speed;
  document.getElementById("sensorWind").textContent = wind !== null && wind !== undefined ? Number(wind).toFixed(1) : "--";

  // Check state
  const now = Date.now();
  const isStale = obsEpoch ? (now - obsEpoch * 1000) > 5 * 60 * 1000 : true;
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

  // Raw API rendering (strip API key if present)
  const rawResponse = store.state.rawResponses?.[station.id];
  if (rawResponse) {
    const safeRaw = { ...rawResponse };
    // Never expose API keys
    if (safeRaw.data && typeof safeRaw.data === "object") {
      const d = { ...safeRaw.data };
      delete d.appid;
      safeRaw.data = d;
    }
    document.getElementById("rawApiContent").textContent = JSON.stringify(safeRaw, null, 2);
  } else {
    document.getElementById("rawApiContent").textContent = JSON.stringify(station, null, 2);
  }
}
