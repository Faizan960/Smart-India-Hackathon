import { initCharts } from "./components/charts.js";
import { initMap } from "./components/map.js";
import { store } from "./state/store.js";

function initTheme() {
  const toggle = document.getElementById("themeToggle");
  if (!toggle) return;

  toggle.addEventListener("click", () => {
    document.documentElement.classList.toggle("dark");
    localStorage.theme = document.documentElement.classList.contains("dark") ? "dark" : "light";
    window.dispatchEvent(new Event("themeChanged"));
  });
}

function renderInvestigationTable(anomalies) {
  const tbody = document.getElementById("investigationTableBody");
  if (!tbody) return;

  tbody.innerHTML = anomalies.length
    ? ""
    : '<tr><td colspan="8" class="text-center py-8 text-on-surface-variant">No anomalies detected yet. More live history is required.</td></tr>';

  anomalies.forEach(a => {
    const row = document.createElement("tr");
    row.className = "border-b border-surface-container-low";
    row.innerHTML = `
      <td class="p-3 text-sm">${new Date(a.timestamp).toLocaleString()}</td>
      <td class="p-3 text-sm font-medium">${a.stationId}</td>
      <td class="p-3 text-sm">${a.sensor}</td>
      <td class="p-3 text-sm">${a.severity}</td>
      <td class="p-3 text-sm">${a.anomalyType}</td>
      <td class="p-3 text-sm">${(a.confidence * 100).toFixed(1)}%</td>
      <td class="p-3 text-sm">${a.status}</td>
      <td class="p-3 text-sm"><button class="text-primary text-xs" data-anomaly="${a.id}">Details</button></td>`;
    row.querySelector("[data-anomaly]").addEventListener("click", () => alert(a.evidence));
    tbody.appendChild(row);
  });
}

import { initNavigation } from "./ui/navigation.js";
import { initOverview } from "./ui/overview.js";
import { initStations } from "./ui/stations.js";
import { initAnomalies } from "./ui/anomalies.js";

async function initUI() {
  await initMap("mapContainer");
  initCharts();
  initNavigation();
  initOverview();
  initStations();
  initAnomalies();

  store.subscribe(state => {
    const statusText = document.getElementById("statusText");
    const statusDot = document.getElementById("statusDot");
    
    if (statusText && statusDot) {
      if (state.mode === "LOADING") {
        statusText.textContent = "Connecting";
        statusDot.className = "dot connecting";
      } else if (state.mode === "ERROR" || state.mode === "OFFLINE") {
        statusText.textContent = "Error";
        statusDot.className = "dot error";
      } else if (state.mode === "DEGRADED") {
        statusText.textContent = "Degraded";
        statusDot.className = "dot warning";
      } else {
        statusText.textContent = "Connected";
        statusDot.className = "dot connected";
      }
    }

    const count = document.getElementById("kpi-anomalies");
    if (count) count.textContent = String(state.anomalies.length);

    renderInvestigationTable(state.anomalies);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  
  try {
    const configRes = await fetch("/api/config/public");
    if (configRes.ok) {
      window.appConfig = await configRes.json();
    } else {
      window.appConfig = {};
    }
  } catch (err) {
    console.warn("Could not fetch public config:", err);
    window.appConfig = {};
  }

  await initUI();

  // 1. Load persisted history into memory
  try {
    const saved = localStorage.getItem("aws-history-v1");
    if (saved) {
      store.state.history = JSON.parse(saved);
      // Trigger a render so charts display immediately
      store.notify();
    }
  } catch {}

  // 2. Initial fetch
  store.fetchLiveData().catch(err => console.error("Initial live fetch failed:", err));

  // Polling engine
  setInterval(() => {
    // Notify subscribers periodically (e.g. for relative timestamps and countdowns)
    window.dispatchEvent(new Event("tick"));

    if (store.state.mode === "LOADING") return;
    
    if (store.state.lastSync) {
      const msSince = Date.now() - new Date(store.state.lastSync).getTime();
      const interval = window.__demoFastPolling ? 5000 : store.state.settings.refreshInterval * 1000;
      if (msSince >= interval) {
        store.fetchLiveData().catch(err => console.error("Live refresh failed:", err));
      }
    }
  }, 1000);

  // Manual refresh wiring
  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      if (store.state.mode !== "LOADING") {
        store.fetchLiveData();
      }
    });
  }
});
