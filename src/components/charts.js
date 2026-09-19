import { store } from "../state/store.js";

let chart = null;

function themeColors() {
  const dark = document.documentElement.classList.contains("dark");
  return {
    text: dark ? "#e9f1f6" : "#1d1d1f",
    grid: dark ? "#38383a" : "#e2e2e7",
    primary: dark ? "#0a84ff" : "#007aff",
    baseline: dark ? "rgba(255,255,255,.35)" : "rgba(0,0,0,.25)"
  };
}

export function initCharts() {
  const canvas = document.getElementById("stationChart");
  if (!canvas || typeof Chart === "undefined") return;

  chart = new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Observed", data: [], borderColor: themeColors().primary, borderWidth: 2, tension: .25, fill: false },
        { label: "Expected baseline", data: [], borderColor: themeColors().baseline, borderDash: [5,5], borderWidth: 1.5, tension: .25, fill: false }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: themeColors().text } } },
      scales: {
        x: { ticks: { color: themeColors().text }, grid: { color: themeColors().grid } },
        y: { ticks: { color: themeColors().text }, grid: { color: themeColors().grid } }
      }
    }
  });

  window.addEventListener("themeChanged", updateTheme);
  
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

  window.addEventListener("stationSelected", () => renderChart(store.state));
  store.subscribe(renderChart);
  renderChart(store.state);
}

function updateTheme() {
  if (!chart) return;
  const c = themeColors();
  chart.options.plugins.legend.labels.color = c.text;
  chart.options.scales.x.ticks.color = c.text;
  chart.options.scales.y.ticks.color = c.text;
  chart.options.scales.x.grid.color = c.grid;
  chart.options.scales.y.grid.color = c.grid;
  chart.data.datasets[0].borderColor = c.primary;
  chart.data.datasets[1].borderColor = c.baseline;
  chart.update("none");
}

function renderChart(state) {
  if (!chart) return;
  const station = state.selectedStation || state.data?.[0];
  const allPoints = station ? (state.history?.[station.id] || []) : [];
  
  const nowEpoch = Math.floor(Date.now() / 1000);
  const cutoff = nowEpoch - (window.currentChartRange || 24 * 60 * 60);
  
  // Filter by time range
  const points = allPoints.filter(p => (p.lastUpdatedEpoch || p.timestamp) >= cutoff);
  const subtitle = document.getElementById("chartSubtitle");
  
  if (points.length === 0) {
    if (subtitle) subtitle.textContent = "No observations collected yet in this window.";
    chart.data.labels = [];
    chart.data.datasets[0].data = [];
    chart.data.datasets[1].data = [];
  } else if (points.length === 1) {
    if (subtitle) subtitle.textContent = "Collecting time-series data... (1 point)";
    chart.data.labels = [new Date(points[0].lastUpdatedEpoch * 1000).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })];
    chart.data.datasets[0].data = [points[0].temperature];
    chart.data.datasets[1].data = [points[0].temperature];
  } else {
    if (subtitle) subtitle.textContent = `${points.length} observations within selected window`;
    chart.data.labels = points.map(p => {
      const ms = p.lastUpdatedEpoch ? p.lastUpdatedEpoch * 1000 : p.timestamp;
      return new Date(ms).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
    });
    chart.data.datasets[0].data = points.map(p => p.temperature);
  
    const values = points.map(p => p.temperature).filter(Number.isFinite);
    const baseline = values.length
      ? values.reduce((a,b) => a+b, 0) / values.length
      : null;
  
    chart.data.datasets[1].data = values.map(() => baseline);
  }
  chart.update("none");
}
