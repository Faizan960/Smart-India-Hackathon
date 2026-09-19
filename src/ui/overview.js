import { store } from "../state/store.js";

export function initOverview() {
  store.subscribe(renderOverview);
  window.addEventListener("tick", renderTicker);
}

function renderOverview(state) {
  // KPI Strip
  const total = document.getElementById("kpi-total");
  const healthy = document.getElementById("kpi-healthy");
  const attention = document.getElementById("kpi-attention");
  const critical = document.getElementById("kpi-critical");

  if (total) total.textContent = state.stations.length;
  
  const now = Date.now();
  let healthyCount = 0;
  let attentionCount = 0;
  let criticalCount = 0;
  
  state.stations.forEach(s => {
    // Check if stale (> 5 mins)
    const isStale = (now - new Date(s.timestamp).getTime()) > 5 * 60 * 1000;
    const hasCritical = state.anomalies.some(a => a.stationId === s.id && a.severity === "CRITICAL");
    const hasWarning = state.anomalies.some(a => a.stationId === s.id && a.severity === "WARNING");

    if (hasCritical) criticalCount++;
    else if (hasWarning || isStale) attentionCount++;
    else healthyCount++;
  });

  if (healthy) healthy.textContent = healthyCount;
  if (attention) attention.textContent = attentionCount;
  if (critical) critical.textContent = criticalCount;

  // Needs Attention List
  renderAttentionList(state.anomalies);
}

function renderAttentionList(anomalies) {
  const container = document.getElementById("attentionList");
  if (!container) return;

  // Take top 4 most severe/recent anomalies
  const topAnomalies = [...anomalies]
    .sort((a, b) => {
      if (a.severity === "CRITICAL" && b.severity !== "CRITICAL") return -1;
      if (b.severity === "CRITICAL" && a.severity !== "CRITICAL") return 1;
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
    })
    .slice(0, 4);

  if (topAnomalies.length === 0) {
    container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-tertiary);">All stations healthy</div>`;
    return;
  }

  container.innerHTML = topAnomalies.map(a => {
    const isCrit = a.severity === "CRITICAL";
    return `
      <div class="attention-row" onclick="window.navigateTo('stations'); window.viewStation('${a.stationId}')">
        <span class="severity-dot ${isCrit ? "critical" : "warning"}"></span>
        <span class="attention-station">${a.stationId}</span>
        <span class="attention-sensor">${a.sensor}</span>
        <span class="attention-issue">${a.anomalyType}</span>
        <span class="attention-time" data-timestamp="${a.timestamp}"></span>
        <span class="attention-severity ${isCrit ? "critical" : "warning"}">${a.severity}</span>
      </div>
    `;
  }).join("");
  
  // Populate Developer Data Diagnostics
  const debugEl = document.getElementById("overviewDebugContent");
  if (debugEl) {
    const totalStored = Object.values(store.state.history).reduce((acc, arr) => acc + arr.length, 0);
    const storedKeys = Object.keys(store.state.history);
    
    let earliest = Infinity;
    let latest = -Infinity;
    Object.values(store.state.history).forEach(series => {
      if (series.length > 0) {
        const firstEpoch = series[0].lastUpdatedEpoch || (new Date(series[0].timestamp).getTime() / 1000);
        const lastEpoch = series[series.length - 1].lastUpdatedEpoch || (new Date(series[series.length - 1].timestamp).getTime() / 1000);
        if (firstEpoch < earliest) earliest = firstEpoch;
        if (lastEpoch > latest) latest = lastEpoch;
      }
    });
    
    let durationStr = "0 minutes";
    if (earliest !== Infinity && latest !== -Infinity) {
       const durationMs = (latest - earliest) * 1000;
       const mins = Math.floor(durationMs / 60000);
       const hrs = Math.floor(mins / 60);
       if (hrs > 0) {
         durationStr = `${hrs}h ${mins % 60}m`;
       } else {
         durationStr = `${mins} minutes`;
       }
    }

    debugEl.textContent = [
      `API Connection:    ${store.state.mode}`,
      `Last fetch:        ${store.state.lastSync ? new Date(store.state.lastSync).toLocaleTimeString() : 'Never'}`,
      `Stations:          ${store.state.stations.length}`,
      `Live observations: ${store.state.stations.filter(s => s.temperature !== null).length}`,
      `Stored points:     ${totalStored} across ${storedKeys.length} stations`,
      `Collection span:   ${totalStored > 0 ? durationStr : 'N/A'}`,
      `History key:       ${localStorage.getItem("aws-history-v1") ? 'Present (V1)' : 'Missing'}`,
      `Anomalies:         ${store.state.anomalies.length}`
    ].join("\n");
  }

  updateTimestamps();
}

function renderTicker() {
  updateTimestamps();

  const dataSourceLabel = document.getElementById("dataSourceLabel");
  const lastUpdateText = document.getElementById("lastUpdateText");

  if (!store.state.lastSync) {
    if (lastUpdateText) lastUpdateText.textContent = "Connecting...";
    return;
  }

  const msSince = Date.now() - new Date(store.state.lastSync).getTime();
  const secsSince = Math.floor(msSince / 1000);
  
  if (lastUpdateText) {
    if (store.state.mode === "CONNECTING") {
      lastUpdateText.textContent = "Refreshing...";
    } else {
      const nextRefreshIn = Math.max(0, store.state.settings.refreshInterval - secsSince);
      lastUpdateText.textContent = `Updated ${secsSince}s ago · Next in ${nextRefreshIn}s`;
    }
  }

  if (dataSourceLabel) {
    dataSourceLabel.className = "data-source-label " + (
      store.state.mode === "LIVE" ? "live" :
      store.state.mode === "DEMO" ? "demo" : "cached"
    );
    dataSourceLabel.textContent = store.state.mode === "LIVE" ? "Live API" : 
                                  store.state.mode === "DEMO" ? "Demo" : "Cached";
  }
}

function updateTimestamps() {
  document.querySelectorAll("[data-timestamp]").forEach(el => {
    const ts = el.dataset.timestamp;
    if (!ts) return;
    const ms = Date.now() - new Date(ts).getTime();
    const mins = Math.floor(ms / 60000);
    if (mins < 1) el.textContent = "just now";
    else if (mins < 60) el.textContent = `${mins}m ago`;
    else el.textContent = `${Math.floor(mins / 60)}h ago`;
  });
}
