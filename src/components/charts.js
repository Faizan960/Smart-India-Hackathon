import { store } from "../state/store.js";

let chart = null;
let chartInitialized = false;

function themeColors() {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  return {
    text: dark ? "#e9f1f6" : "#1d1d1f",
    grid: dark ? "#38383a" : "#e2e2e7",
    primary: dark ? "#0a84ff" : "#007aff",
    baseline: dark ? "rgba(255,255,255,.35)" : "rgba(0,0,0,.25)"
  };
}

function ensureChart() {
  if (chart) return true;

  const canvas = document.getElementById("stationChart");
  if (!canvas || typeof Chart === "undefined") return false;

  // Check if canvas is actually visible (non-zero dimensions)
  const wrap = canvas.closest(".chart-canvas-wrap");
  if (wrap && wrap.offsetHeight === 0) return false;

  const ctx = canvas.getContext("2d");
  if (!ctx) return false;

  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Observed", data: [], borderColor: themeColors().primary, borderWidth: 2, tension: .25, fill: false, pointRadius: 3, pointHoverRadius: 5 },
        { label: "Historical baseline", data: [], borderColor: themeColors().baseline, borderDash: [5,5], borderWidth: 1.5, tension: .25, fill: false, pointRadius: 0 },
        { label: "Sentinel anomaly", data: [], showLine: false, pointStyle: "rectRot", pointRadius: 7, pointHoverRadius: 9, borderColor: "#ff3b30", backgroundColor: "#ff3b30", borderWidth: 2 }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: themeColors().text } },
        tooltip: {
          callbacks: {
            title: function(items) { 
              const val = items[0]?.parsed?.x;
              if (val) return new Date(val * 1000).toLocaleString("en-IN");
              return items[0]?.label || ""; 
            },
            label: function(item) {
              return `${item.dataset.label}: ${item.parsed.y?.toFixed(1)}°C`;
            }
          }
        }
      },
      scales: {
        x: {
          type: "linear",
          ticks: { 
            color: themeColors().text, 
            maxTicksLimit: 12,
            callback: function(value) {
              return new Date(value * 1000).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
            }
          },
          grid: { color: themeColors().grid }
        },
        y: {
          ticks: { color: themeColors().text },
          grid: { color: themeColors().grid },
          title: { display: true, text: "Temperature (°C)", color: themeColors().text }
        }
      }
    }
  });
  chartInitialized = true;
  console.log("[Chart] initialized");
  return true;
}

export function initCharts() {
  // Expose function to trigger re-render with specific time range
  window.currentChartRange = 24 * 60 * 60; // 24 hours in seconds

  document.getElementById("chartControls")?.addEventListener("click", (e) => {
    if (e.target.tagName === "BUTTON") {
      document.querySelectorAll(".chart-control-btn").forEach(b => b.classList.remove("active"));
      e.target.classList.add("active");
      const range = e.target.dataset.range;
      if (range === "24h") window.currentChartRange = 24 * 60 * 60;
      if (range === "7d") window.currentChartRange = 7 * 24 * 60 * 60;
      if (range === "30d") window.currentChartRange = 30 * 24 * 60 * 60;
      renderChart(store.state);
    }
  });

  window.addEventListener("stationSelected", () => {
    // When station detail becomes visible, try to create chart
    requestAnimationFrame(() => {
      renderChart(store.state);
    });
  });

  window.addEventListener("themeChanged", updateTheme);
  store.subscribe(renderChart);
}

function updateTheme() {
  if (!chart) return;
  const c = themeColors();
  chart.options.plugins.legend.labels.color = c.text;
  chart.options.scales.x.ticks.color = c.text;
  chart.options.scales.y.ticks.color = c.text;
  chart.options.scales.x.grid.color = c.grid;
  chart.options.scales.y.grid.color = c.grid;
  chart.options.scales.y.title.color = c.text;
  chart.data.datasets[0].borderColor = c.primary;
  chart.data.datasets[1].borderColor = c.baseline;
  chart.update("none");
}

function getPointEpoch(p) {
  // Use monotonic timestamp (polling time) for the x-axis to separate duplicate observations
  if (p.timestamp) {
    const ms = new Date(p.timestamp).getTime();
    if (!isNaN(ms)) return Math.floor(ms / 1000);
  }
  if (typeof p.receivedEpoch === "number" && p.receivedEpoch > 0) return p.receivedEpoch;
  if (typeof p.observedEpoch === "number" && p.observedEpoch > 0) return p.observedEpoch;
  return 0;
}

// --- Observation provenance -------------------------------------------------
// state.history[stationId] mixes two provenance classes in one array:
//   • historical — backfilled from /api/weather/history (provider observation
//     times; receivedEpoch === observedEpoch; no receivedAt). See store.js
//     loadHistoricalData / _mergeHistoricalData.
//   • live — appended each poll from /api/weather/current (monotonic
//     receivedEpoch, always carries receivedAt). See store.js appendHistory.
// Fault-injected demo readings are flagged isSynthetic and must NEVER be shown
// as real observations while the dashboard is live.
export function classifyHistoryPoint(p) {
  if (!p || p.isSynthetic) return "synthetic";
  if (p.source === "historical") return "historical";
  if (p.source === "live") return "live";
  // Legacy points persisted before source tagging: infer from timestamp shape.
  if (p.receivedAt == null && Number.isFinite(p.observedEpoch) && p.observedEpoch === p.receivedEpoch) {
    return "historical";
  }
  return "live";
}

// Hour-of-day climatological baseline computed ONLY from real historical
// provider observations. Returns null when there is too little history — we
// never fall back to averaging the currently plotted points.
export function computeHistoricalBaseline(historicalPoints) {
  const temps = historicalPoints.map(p => p.temperature).filter(Number.isFinite);
  if (temps.length < 6) return null;
  const overall = temps.reduce((a, b) => a + b, 0) / temps.length;
  const sums = new Array(24).fill(0);
  const counts = new Array(24).fill(0);
  for (const p of historicalPoints) {
    if (!Number.isFinite(p.temperature)) continue;
    const hr = new Date(getPointEpoch(p) * 1000).getHours();
    sums[hr] += p.temperature;
    counts[hr] += 1;
  }
  const byHour = sums.map((s, h) => (counts[h] ? s / counts[h] : null));
  return { overall, byHour, sampleSize: temps.length };
}

// Prefer a real model/climatological baseline if the frontend state already
// provides a NUMERIC one; otherwise use the historical baseline. A historical
// average is never labelled as the Sentinel / Isolation Forest baseline.
export function resolveBaseline(state, stationId, historicalPoints) {
  const station = state.selectedStation;
  const candidates = [];
  if (station && station.id === stationId) {
    candidates.push(station.modelBaseline, station.baselineTemp);
  }
  // The Sentinel anomaly currently reports expected:"Model baseline" (a label,
  // not a value); this branch stays inert until a real numeric baseline exists.
  const anomaly = (state.anomalies || []).find(a => a.stationId === stationId && a.source === "aws_sentinel");
  if (anomaly) candidates.push(anomaly.baseline, anomaly.expected);
  const modelValue = candidates.find(v => Number.isFinite(v));
  if (Number.isFinite(modelValue)) {
    return { kind: "sentinel", label: "Sentinel baseline", flat: modelValue };
  }
  const bl = computeHistoricalBaseline(historicalPoints);
  if (bl) return { kind: "historical", label: "Historical baseline", byHour: bl.byHour, overall: bl.overall };
  return { kind: "none", label: "Baseline unavailable" };
}

function anomalyEpochOf(a) {
  if (!a) return 0;
  if (typeof a.timestamp === "number") return a.timestamp > 1e12 ? Math.floor(a.timestamp / 1000) : a.timestamp;
  if (a.timestamp) {
    const ms = new Date(a.timestamp).getTime();
    if (!isNaN(ms)) return Math.floor(ms / 1000);
  }
  return 0;
}

// Temperature-axis anomaly markers taken directly from the existing Sentinel
// anomaly state — no invented points. Synthetic (demo-injected) anomalies are
// excluded so nothing synthetic is shown as a real event in live mode.
export function collectAnomalyMarkers(anomalies, stationId, cutoff, nowEpoch) {
  return (anomalies || [])
    .filter(a => a.stationId === stationId && !a.isSynthetic)
    .filter(a => a.sensor === "Temperature" || a.sensor === "Multiple")
    .filter(a => Number.isFinite(a.observed))
    .map(a => ({ x: anomalyEpochOf(a), y: a.observed }))
    .filter(m => m.x >= cutoff && m.x <= nowEpoch);
}

function renderChart(state) {
  // Only render when station detail is visible
  const detailView = document.getElementById("stationDetailView");
  if (!detailView || detailView.style.display === "none") return;

  // Try to create chart if not yet done (deferred until visible)
  if (!ensureChart()) return;

  const station = state.selectedStation || state.data?.[0];
  const stationId = station?.id;
  const rawPoints = stationId ? (state.history?.[stationId] || []) : [];

  // Never treat synthetic/demo-injected readings as real observations.
  const realPoints = rawPoints.filter(p => classifyHistoryPoint(p) !== "synthetic");
  const syntheticCount = rawPoints.length - realPoints.length;
  // Full historical (provider) set drives the baseline, independent of window.
  const historicalPoints = realPoints.filter(p => classifyHistoryPoint(p) === "historical");

  const nowEpoch = Math.floor(Date.now() / 1000);
  const rangeSeconds = window.currentChartRange || 24 * 60 * 60;
  const cutoff = nowEpoch - rangeSeconds;

  // Observed series = real historical + live observations within the window, sorted.
  const allPoints = realPoints; // diagnostics/messaging use real observations only
  const points = realPoints
    .filter(p => getPointEpoch(p) >= cutoff)
    .sort((a, b) => getPointEpoch(a) - getPointEpoch(b));

  const subtitle = document.getElementById("chartSubtitle");
  const rangeLabel = rangeSeconds <= 86400 ? "24 hours" : rangeSeconds <= 604800 ? "7 days" : "30 days";

  // Diagnostics
  const debugEl = document.getElementById("debugContent");
  const canvas = document.getElementById("stationChart");

  console.log(`[Chart] render requested: station=${stationId}, totalPoints=${allPoints.length}, filteredPoints=${points.length}, range=${rangeLabel}`);

  if (debugEl) {
    const diagLines = [
      `Chart Diagnostics`,
      `─────────────────`,
      `Selected station: ${stationId || "none"}`,
      `Selected range:   ${rangeLabel}`,
      `Total history:    ${allPoints.length} real points`,
      `  historical:     ${historicalPoints.length} (provider /api/weather/history)`,
      `  synthetic excl: ${syntheticCount}`,
      `Filtered points:  ${points.length}`,
      `Canvas:           ${canvas ? `${canvas.width}×${canvas.height}` : "NOT FOUND"}`,
    ];
    if (points.length > 0) {
      const first = points[0];
      const last = points[points.length - 1];
      diagLines.push(`First point:      T=${first.temperature}°C at ${new Date(getPointEpoch(first) * 1000).toLocaleString()}`);
      diagLines.push(`Last point:       T=${last.temperature}°C at ${new Date(getPointEpoch(last) * 1000).toLocaleString()}`);
    } else {
      diagLines.push(`Reason empty:     ${allPoints.length === 0 ? "No history for this station yet" : "All points outside selected time range"}`);
    }
    debugEl.textContent = diagLines.join("\n");
  }

  // Enforce x-axis time window anchored to NOW
  chart.options.scales.x.min = cutoff;
  chart.options.scales.x.max = nowEpoch;

  // ---- Baseline: model → historical → unavailable. Never mean-of-visible. ----
  const baseline = resolveBaseline(state, stationId, historicalPoints);
  const markers = collectAnomalyMarkers(state.anomalies, stationId, cutoff, nowEpoch);

  if (points.length === 0) {
    if (subtitle) subtitle.textContent = allPoints.length === 0
      ? "No observations collected yet"
      : `No observations in last ${rangeLabel} (${allPoints.length} in history)`;
    chart.data.labels = [];
    chart.data.datasets[0].data = [];
    chart.data.datasets[1].data = [];
    chart.data.datasets[2].data = [];
  } else {
    // Observed = real historical + live temperatures within the window.
    const chartData = points.map(p => ({ x: getPointEpoch(p), y: p.temperature }));
    chart.data.datasets[0].data = chartData;

    // Baseline series (dashed) — from historical data or a model, not visible points.
    let baselineData = [];
    let baselineLabel;
    if (baseline.kind === "sentinel") {
      baselineData = chartData.map(p => ({ x: p.x, y: baseline.flat }));
      baselineLabel = `Sentinel baseline (${baseline.flat.toFixed(1)}°C)`;
    } else if (baseline.kind === "historical") {
      baselineData = chartData.map(p => {
        const hr = new Date(p.x * 1000).getHours();
        const y = Number.isFinite(baseline.byHour[hr]) ? baseline.byHour[hr] : baseline.overall;
        return { x: p.x, y };
      });
      baselineLabel = `Historical baseline (${baseline.overall.toFixed(1)}°C avg)`;
    } else {
      baselineLabel = "Baseline unavailable — loading historical data";
    }
    chart.data.datasets[1].data = baselineData;
    chart.data.datasets[1].label = baselineLabel;

    // Sentinel anomaly markers (from existing anomaly state only).
    chart.data.datasets[2].data = markers;

    // ---- Informative subtitle ----
    const histInWindow = points.filter(p => classifyHistoryPoint(p) === "historical").length;
    const liveInWindow = points.length - histInWindow;
    const cadence = liveInWindow === 0 && histInWindow > 0 ? "hourly " : "";
    const baselineChip = baseline.kind === "sentinel" ? "Sentinel baseline"
      : baseline.kind === "historical" ? "Historical baseline"
      : "baseline unavailable";
    let text = `${points.length} ${cadence}observation${points.length === 1 ? "" : "s"} · ${baselineChip}`;
    if (markers.length) text += ` · ${markers.length} Sentinel anomal${markers.length === 1 ? "y" : "ies"}`;
    if (subtitle) subtitle.textContent = text;
  }

  chart.update("none");
  console.log(`[Chart] rendered ${points.length} points`);
}
