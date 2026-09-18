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

function initUI() {
  initMap("mapContainer");
  initCharts();

  const nav = document.getElementById("navTabs");
  if (nav) {
    nav.addEventListener("click", e => {
      const btn = e.target.closest("button[data-tab]");
      if (!btn) return;

      document.querySelectorAll("#navTabs button[data-tab]").forEach(b => {
        b.classList.toggle("bg-primary", b === btn);
        b.classList.toggle("text-on-primary", b === btn);
        b.classList.toggle("bg-surface-container", b !== btn);
        b.classList.toggle("text-on-surface", b !== btn);
      });

      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      document.getElementById("tab-" + btn.dataset.tab)?.classList.add("active");
    });
  }

  store.subscribe(state => {
    const connText = document.getElementById("connText");
    const connDot = document.getElementById("connDot");

    if (connText) connText.textContent = state.status;
    if (connDot) {
      connDot.className = "w-2 h-2 rounded-full " +
        (state.status === "CONNECTED" ? "bg-secondary" :
         state.status === "CACHED" ? "bg-tertiary" :
         state.status === "ERROR" ? "bg-error" : "bg-outline animate-pulse");
    }

    const count = document.getElementById("kpi-anomalies");
    if (count) count.textContent = String(state.anomalies.length);

    renderInvestigationTable(state.anomalies);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initUI();
  store.fetchLiveData().catch(err => console.error("Initial IMD fetch failed:", err));

  setInterval(() => {
    store.fetchLiveData().catch(err => console.error("IMD refresh failed:", err));
  }, store.state.settings.refreshInterval * 1000);
});
