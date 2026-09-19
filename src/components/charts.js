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
        { label: "Expected baseline", data: [], borderColor: themeColors().baseline, borderDash: [5,5], borderWidth: 1.5, tension: .25, fill: false, pointRadius: 0 }
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
            title: function(items) { return items[0]?.label || ""; },
            label: function(item) {
              return `${item.dataset.label}: ${item.parsed.y?.toFixed(1)}°C`;
            }
          }
        }
      },
      scales: {
        x: {
          ticks: { color: themeColors().text, maxTicksLimit: 12 },
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
  // Robust epoch extraction: try observedEpoch first, then lastUpdatedEpoch, then parse timestamp
  if (typeof p.observedEpoch === "number" && p.observedEpoch > 0) return p.observedEpoch;
  if (typeof p.lastUpdatedEpoch === "number" && p.lastUpdatedEpoch > 0) return p.lastUpdatedEpoch;
  if (p.timestamp) {
    const ms = new Date(p.timestamp).getTime();
    if (!isNaN(ms)) return Math.floor(ms / 1000);
  }
  return 0;
}

function renderChart(state) {
  // Only render when station detail is visible
  const detailView = document.getElementById("stationDetailView");
  if (!detailView || detailView.style.display === "none") return;

  // Try to create chart if not yet done (deferred until visible)
  if (!ensureChart()) return;

  const station = state.selectedStation || state.data?.[0];
  const stationId = station?.id;
  const allPoints = stationId ? (state.history?.[stationId] || []) : [];

  const nowEpoch = Math.floor(Date.now() / 1000);
  const rangeSeconds = window.currentChartRange || 24 * 60 * 60;
  const cutoff = nowEpoch - rangeSeconds;

  // Filter by time range, sort ascending
  const points = allPoints
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
      `Total history:    ${allPoints.length} points`,
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

  if (points.length === 0) {
    if (subtitle) subtitle.textContent = allPoints.length === 0
      ? "No observations collected yet"
      : `No observations in last ${rangeLabel} (${allPoints.length} total in history)`;
    chart.data.labels = [];
    chart.data.datasets[0].data = [];
    chart.data.datasets[1].data = [];
  } else if (points.length === 1) {
    if (subtitle) subtitle.textContent = "Collecting observations... (1 point)";
    const epoch = getPointEpoch(points[0]);
    chart.data.labels = [new Date(epoch * 1000).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })];
    chart.data.datasets[0].data = [points[0].temperature];
    chart.data.datasets[1].data = [points[0].temperature];
  } else {
    if (subtitle) subtitle.textContent = `${points.length} observations — ${rangeLabel}`;
    chart.data.labels = points.map(p => {
      const epoch = getPointEpoch(p);
      return new Date(epoch * 1000).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
    });
    chart.data.datasets[0].data = points.map(p => p.temperature);

    // Calculate baseline (mean of all points in window)
    const values = points.map(p => p.temperature).filter(Number.isFinite);
    if (values.length >= 6) {
      const baseline = values.reduce((a,b) => a+b, 0) / values.length;
      chart.data.datasets[1].data = values.map(() => baseline);
      chart.data.datasets[1].label = `Baseline (${baseline.toFixed(1)}°C)`;
    } else {
      chart.data.datasets[1].data = [];
      chart.data.datasets[1].label = "Baseline unavailable — collecting observations";
    }
  }

  chart.update("none");
  console.log(`[Chart] rendered ${points.length} points`);
}
