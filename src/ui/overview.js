import { store } from "../state/store.js";
import { STATIONS } from "../data/stations.js";

export function initOverview() {
  store.subscribe(renderOverview);
  window.addEventListener("tick", renderTicker);
}

function renderOverview(state) {
  // KPI Strip — derive from registry + state
  const total = document.getElementById("kpi-total");
  const healthy = document.getElementById("kpi-healthy");
  const attention = document.getElementById("kpi-attention");
  const critical = document.getElementById("kpi-critical");

  // Total is always registry length
  if (total) total.textContent = STATIONS.length;

  const now = Date.now();
  let healthyCount = 0;
  let attentionCount = 0;
  let criticalCount = 0;
  let loadingCount = 0;
  let errorCount = 0;

  STATIONS.forEach(registry => {
    const live = state.stations.find(s => s.id === registry.id);
    const perStation = state.stationStatus?.[registry.id];

    if (!live) {
      // Station hasn't returned data yet
      if (perStation?.status === "ERROR") {
        errorCount++;
      } else {
        loadingCount++;
      }
      return;
    }

    const obsEpoch = live.observedEpoch || live.lastUpdatedEpoch;
    const obsTime = obsEpoch ? obsEpoch * 1000 : new Date(live.timestamp).getTime();
    const isStale = (now - obsTime) > 5 * 60 * 1000;
    const hasCritical = state.anomalies.some(a => a.stationId === registry.id && a.severity === "CRITICAL");
    const hasWarning = state.anomalies.some(a => a.stationId === registry.id && a.severity === "WARNING");

    if (hasCritical) criticalCount++;
    else if (hasWarning || isStale) attentionCount++;
    else healthyCount++;
  });

  if (healthy) healthy.textContent = healthyCount;
  if (attention) attention.textContent = attentionCount + loadingCount;
  if (critical) critical.textContent = criticalCount + errorCount;

  // Data source label
  const dataSourceLabel = document.getElementById("dataSourceLabel");
  if (dataSourceLabel) {
    const mode = state.mode;
    if (mode === "CONNECTED") {
      dataSourceLabel.className = "data-source-label live";
      dataSourceLabel.textContent = "Live API";
    } else if (mode === "DEGRADED") {
      dataSourceLabel.className = "data-source-label live";
      dataSourceLabel.textContent = "Degraded";
    } else if (mode === "CACHED") {
      dataSourceLabel.className = "data-source-label cached";
      dataSourceLabel.textContent = "Cached";
    } else if (mode === "DEMO") {
      dataSourceLabel.className = "data-source-label demo";
      dataSourceLabel.textContent = "Demo";
    } else if (mode === "ERROR" || mode === "OFFLINE") {
      dataSourceLabel.className = "data-source-label demo";
      dataSourceLabel.textContent = "Error";
    } else {
      dataSourceLabel.className = "data-source-label cached";
      dataSourceLabel.textContent = "Loading";
    }
  }

  // Needs Attention List
  renderAttentionList(state.anomalies);

  // Live Data Monitor
  renderLiveMonitor(state);
}

function renderLiveMonitor(state) {
  const debugEl = document.getElementById("overviewDebugContent");
  if (!debugEl) return;

  const totalStored = Object.values(store.state.history).reduce((acc, arr) => acc + (Array.isArray(arr) ? arr.length : 0), 0);
  const storedKeys = Object.keys(store.state.history).filter(k => Array.isArray(store.state.history[k]) && store.state.history[k].length > 0);

  let earliest = Infinity;
  let latest = -Infinity;
  Object.values(store.state.history).forEach(series => {
    if (!Array.isArray(series) || series.length === 0) return;
    const firstEpoch = series[0].observedEpoch || series[0].lastUpdatedEpoch || 0;
    const lastEpoch = series[series.length - 1].observedEpoch || series[series.length - 1].lastUpdatedEpoch || 0;
    if (firstEpoch < earliest && firstEpoch > 0) earliest = firstEpoch;
    if (lastEpoch > latest) latest = lastEpoch;
  });

  let durationStr = "0 minutes";
  if (earliest !== Infinity && latest !== -Infinity) {
    const durationMs = (latest - earliest) * 1000;
    const mins = Math.floor(durationMs / 60000);
    const hrs = Math.floor(mins / 60);
    if (hrs > 0) durationStr = `${hrs}h ${mins % 60}m`;
    else durationStr = `${mins} minutes`;
  }

  const liveCount = STATIONS.filter(r => state.stationStatus?.[r.id]?.status === "LIVE").length;
  const errorCount = STATIONS.filter(r => state.stationStatus?.[r.id]?.status === "ERROR").length;
  const loadingCount = STATIONS.filter(r => state.stationStatus?.[r.id]?.status === "LOADING").length;

  const refreshInterval = store.state.settings.refreshInterval;
  const msSinceLast = state.lastSync ? Date.now() - new Date(state.lastSync).getTime() : 0;
  const nextRefreshIn = Math.max(0, refreshInterval - Math.floor(msSinceLast / 1000));

  debugEl.textContent = [
    `Live Data Monitor`,
    `─────────────────────────`,
    `Stations (registry):  ${STATIONS.length}`,
    `Live:                 ${liveCount} / ${STATIONS.length}`,
    `Loading:              ${loadingCount}`,
    `Errors:               ${errorCount}`,
    `─────────────────────────`,
    `API Connection:       ${state.mode}`,
    `Last successful fetch: ${state.lastSync ? new Date(state.lastSync).toLocaleTimeString() : 'Never'}`,
    `Next refresh in:      ${nextRefreshIn}s`,
    `Refresh interval:     ${refreshInterval}s`,
    `─────────────────────────`,
    `Stored observations:  ${totalStored} across ${storedKeys.length} stations`,
    `Collection span:      ${totalStored > 0 ? durationStr : 'N/A'}`,
    `History persistence:  ${localStorage.getItem("aws-history-v2") ? 'Present (V2)' : 'Missing'}`,
    `Anomalies detected:   ${state.anomalies.length}`
  ].join("\n");
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
    container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-tertiary);">All stations healthy — no anomalies detected</div>`;
    return;
  }

  container.innerHTML = topAnomalies.map(a => {
    const isCrit = a.severity === "CRITICAL";
    const label = a.isSynthetic ? `${a.anomalyType} [DEMO]` : a.anomalyType;
    return `
      <div class="attention-row" onclick="window.navigateTo('stations'); window.viewStation('${a.stationId}')">
        <span class="severity-dot ${isCrit ? "critical" : "warning"}"></span>
        <span class="attention-station">${a.stationId}</span>
        <span class="attention-sensor">${a.sensor}</span>
        <span class="attention-issue">${label}</span>
        <span class="attention-time" data-timestamp="${a.timestamp}"></span>
        <span class="attention-severity ${isCrit ? "critical" : "warning"}">${a.severity}</span>
      </div>
    `;
  }).join("");

  updateTimestamps();
}

function renderTicker() {
  updateTimestamps();

  const lastUpdateText = document.getElementById("lastUpdateText");

  if (!store.state.lastSync) {
    if (lastUpdateText) lastUpdateText.textContent = "Connecting...";
    return;
  }

  const msSince = Date.now() - new Date(store.state.lastSync).getTime();
  const secsSince = Math.floor(msSince / 1000);

  if (lastUpdateText) {
    if (store.state.mode === "LOADING") {
      lastUpdateText.textContent = "Refreshing...";
    } else {
      const nextRefreshIn = Math.max(0, store.state.settings.refreshInterval - secsSince);
      lastUpdateText.textContent = `Updated ${secsSince}s ago · Next in ${nextRefreshIn}s`;
    }
  }
}

function updateTimestamps() {
  document.querySelectorAll("[data-timestamp]").forEach(el => {
    const ts = el.dataset.timestamp;
    if (!ts) return;
    const ms = Date.now() - new Date(ts).getTime();
    if (isNaN(ms)) { el.textContent = "--"; return; }
    const mins = Math.floor(ms / 60000);
    if (mins < 1) el.textContent = "just now";
    else if (mins < 60) el.textContent = `${mins}m ago`;
    else el.textContent = `${Math.floor(mins / 60)}h ago`;
  });
}
