import { store } from "../state/store.js";

let currentSeverityFilter = "All";

export function initAnomalies() {
  store.subscribe(renderAnomalies);

  const filterSelect = document.getElementById("anomalySeverityFilter");
  if (filterSelect) {
    filterSelect.addEventListener("change", (e) => {
      currentSeverityFilter = e.target.value;
      renderAnomalies(store.state);
    });
  }

  // Drawer interactions
  const closeBtn = document.getElementById("drawerClose");
  const overlay = document.getElementById("drawerOverlay");

  if (closeBtn) closeBtn.addEventListener("click", closeAnomalyDrawer);
  if (overlay) overlay.addEventListener("click", closeAnomalyDrawer);
  
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeAnomalyDrawer();
  });
}

export function openAnomalyDrawer(anomaly) {
  const isCrit = anomaly.severity === "CRITICAL";
  
  document.getElementById("drawerTitle").textContent = anomaly.anomalyType || "Sensor Anomaly";
  
  const badge = document.getElementById("drawerSeverity");
  badge.textContent = anomaly.severity;
  badge.className = `drawer-severity-badge ${isCrit ? "critical" : "warning"}`;
  
  document.getElementById("drawerConfidence").textContent = `${(anomaly.confidence * 100).toFixed(0)}% confidence`;
  
  document.getElementById("drawerObserved").textContent = typeof anomaly.observed === "number" ? anomaly.observed.toFixed(1) : anomaly.observed;
  document.getElementById("drawerExpected").textContent = typeof anomaly.expected === "number" ? anomaly.expected.toFixed(1) : anomaly.expected;
  
  const dev = anomaly.deviation;
  const devEl = document.getElementById("drawerDeviation");
  devEl.textContent = dev > 0 ? `+${dev.toFixed(2)}` : dev.toFixed(2);
  devEl.style.color = isCrit ? "var(--critical)" : "var(--warning)";
  
  document.getElementById("drawerStation").textContent = `${anomaly.stationName} (${anomaly.stationId})`;
  document.getElementById("drawerTime").textContent = new Date(anomaly.timestamp).toLocaleString();
  document.getElementById("drawerReason").textContent = anomaly.evidence || anomaly.reason || "Deviation from historical baseline.";
  
  // Draw mini chart evidence if possible
  const canvas = document.getElementById("anomalyChart");
  if (canvas && store.state.history[anomaly.stationId]) {
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    
    const series = store.state.history[anomaly.stationId].slice(-60); // last 60 points for context
    if (series.length > 0) {
      const temps = series.map(p => p.temperature).filter(t => t !== null);
      if (temps.length > 1) {
        const min = Math.min(...temps) - 2;
        const max = Math.max(...temps) + 2;
        const range = max - min;
        const stepX = rect.width / (temps.length - 1);
        
        ctx.clearRect(0, 0, rect.width, rect.height);
        
        // Expected band
        ctx.fillStyle = "rgba(100, 100, 100, 0.1)";
        const expY = rect.height - ((anomaly.expected - min) / range) * rect.height;
        ctx.fillRect(0, expY - 10, rect.width, 20);
        
        // Line
        ctx.beginPath();
        ctx.strokeStyle = "var(--primary)";
        ctx.lineWidth = 2;
        temps.forEach((t, i) => {
          const x = i * stepX;
          const y = rect.height - ((t - min) / range) * rect.height;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
        
        // Anomaly point (the last point)
        const lastT = temps[temps.length - 1];
        const lastX = (temps.length - 1) * stepX;
        const lastY = rect.height - ((lastT - min) / range) * rect.height;
        ctx.beginPath();
        ctx.fillStyle = isCrit ? "var(--critical)" : "var(--warning)";
        ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
  
  document.getElementById("drawerOverlay").classList.add("active");
  document.getElementById("anomalyDrawer").classList.add("active");
}

export function closeAnomalyDrawer() {
  document.getElementById("drawerOverlay").classList.remove("active");
  document.getElementById("anomalyDrawer").classList.remove("active");
}

window.openAnomalyDrawer = openAnomalyDrawer;
window.closeAnomalyDrawer = closeAnomalyDrawer;

function renderAnomalies(state) {
  const container = document.getElementById("anomalyList");
  if (!container) return;

  const filtered = state.anomalies.filter(a => {
    if (currentSeverityFilter === "All") return true;
    return a.severity === currentSeverityFilter.toUpperCase();
  });

  document.getElementById("anomalyCount").textContent = `${filtered.length} anomalies`;

  if (filtered.length === 0) {
    container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-tertiary);">No active anomalies</div>`;
    return;
  }

  container.innerHTML = filtered.map(a => {
    const isCrit = a.severity === "CRITICAL";
    // We pass the stringified JSON anomaly object to openAnomalyDrawer by injecting it into onclick via a global lookup or inline.
    // However, it's safer to store it in a map or dataset. Let's use a global map for simplicity since it's a static vanilla app.
    
    if (!window.__anomalyMap) window.__anomalyMap = {};
    window.__anomalyMap[a.id] = a;

    return `
      <div class="anomaly-row" onclick="window.openAnomalyDrawer(window.__anomalyMap['${a.id}'])">
        <span class="severity-dot ${isCrit ? "critical" : "warning"}"></span>
        <span class="attention-station">${a.stationId}</span>
        <span class="attention-sensor">${a.sensor}</span>
        <span class="attention-issue">${a.anomalyType}</span>
        <span class="attention-time" data-timestamp="${a.timestamp}"></span>
        <span class="anomaly-confidence">${(a.confidence * 100).toFixed(0)}%</span>
      </div>
    `;
  }).join("");
}
