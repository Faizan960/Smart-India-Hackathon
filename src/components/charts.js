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
  const canvas = document.getElementById("anomalyChart");
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
  const points = station ? (state.history?.[station.id] || []) : [];

  chart.data.labels = points.map(p =>
    new Date(p.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
  );
  chart.data.datasets[0].data = points.map(p => p.temperature);

  const values = points.map(p => p.temperature).filter(Number.isFinite);
  const baseline = values.length
    ? values.reduce((a,b) => a+b, 0) / values.length
    : null;

  chart.data.datasets[1].data = values.map(() => baseline);
  chart.update("none");
}
