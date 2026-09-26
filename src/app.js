import { initCharts } from "./components/charts.js";
import { initMap } from "./components/map.js";
import { store } from "./state/store.js";
import { initNavigation } from "./ui/navigation.js";
import { initOverview } from "./ui/overview.js";
import { initStations } from "./ui/stations.js";
import { initAnomalies } from "./ui/anomalies.js";

function initTheme() {
  // Theme toggle via menu
  const themeBtn = document.getElementById("themeBtn");
  const themeMenu = document.getElementById("themeMenu");

  if (themeBtn && themeMenu) {
    themeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      themeMenu.classList.toggle("active");
    });

    themeMenu.querySelectorAll("[data-theme-choice]").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const choice = e.target.dataset.themeChoice;
        localStorage.setItem("sentinel-theme", choice);
        applyTheme(choice);
        themeMenu.classList.remove("active");
        themeMenu.querySelectorAll("button").forEach(b => b.classList.remove("selected"));
        e.target.classList.add("selected");
      });
    });

    // Close menu when clicking outside
    document.addEventListener("click", () => themeMenu.classList.remove("active"));
  }
}

function applyTheme(choice) {
  let theme = choice;
  if (choice === "system") {
    theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  if (theme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  window.dispatchEvent(new Event("themeChanged"));
}

async function initUI() {
  await initMap("mapContainer");
  initCharts();
  initNavigation();
  initOverview();
  initStations();
  initAnomalies();

  // Connection status display
  store.subscribe(state => {
    const statusText = document.getElementById("statusText");
    const statusDot = document.getElementById("statusDot");

    if (statusText && statusDot) {
      switch (state.mode) {
        case "LOADING":
          statusText.textContent = "Connecting";
          statusDot.className = "dot connecting";
          break;
        case "CONNECTED":
          statusText.textContent = "Connected";
          statusDot.className = "dot";
          statusDot.style.background = "var(--success)";
          break;
        case "DEGRADED":
          statusText.textContent = "Degraded";
          statusDot.className = "dot";
          statusDot.style.background = "var(--warning)";
          break;
        case "ERROR":
          statusText.textContent = "Error";
          statusDot.className = "dot error";
          statusDot.style.background = "";
          break;
        case "OFFLINE":
          statusText.textContent = "Offline";
          statusDot.className = "dot error";
          statusDot.style.background = "";
          break;
        case "CACHED":
          statusText.textContent = "Cached";
          statusDot.className = "dot";
          statusDot.style.background = "var(--accent)";
          break;
        case "DEMO":
          statusText.textContent = "Demo";
          statusDot.className = "dot demo";
          statusDot.style.background = "";
          break;
        default:
          statusText.textContent = "Unknown";
          statusDot.className = "dot connecting";
      }
    }
  });

  // Search overlay
  const searchBtn = document.getElementById("searchBtn");
  const searchOverlay = document.getElementById("searchOverlay");
  const searchInput = document.getElementById("searchInput");

  if (searchBtn && searchOverlay) {
    searchBtn.addEventListener("click", () => {
      searchOverlay.classList.add("active");
      searchInput?.focus();
    });
    searchOverlay.addEventListener("click", (e) => {
      if (e.target === searchOverlay) searchOverlay.classList.remove("active");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") searchOverlay.classList.remove("active");
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        searchOverlay.classList.add("active");
        searchInput?.focus();
      }
    });
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  initTheme();

  // Fetch public config (map key, etc.)
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

  // One-time migration: drop pre-v2 persisted history and per-station caches.
  // Older builds stored Open-Meteo points under a +5:30 timezone bug whose epochs
  // the merge dedup could never replace, contaminating the chart. Removing them
  // also reclaims localStorage before the fresh corrected data is written, so the
  // ~5MB quota isn't exhausted by dead per-station caches.
  try {
    localStorage.removeItem("aws-history-v1");
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith("weather-history-") && !k.startsWith("weather-history-v2-")) {
        localStorage.removeItem(k);
      }
    }
  } catch {}

  // Load persisted history into memory
  try {
    const saved = localStorage.getItem("aws-history-v2");
    if (saved) {
      const parsed = JSON.parse(saved);
      if (parsed && typeof parsed === "object") {
        store.state.history = parsed;
        store.notify();
      }
    }
  } catch {}

  // Initial fetch
  console.log("[App] Starting initial live data fetch...");
  store.fetchLiveData().catch(err => console.error("[App] Initial live fetch failed:", err));

  // Polling engine — single instance, checks elapsed time
  const POLL_CHECK_INTERVAL = 1000; // Check every second
  setInterval(() => {
    // Notify subscribers periodically (for relative timestamps and countdowns)
    window.dispatchEvent(new Event("tick"));

    if (store.state.mode === "LOADING") return;

    if (store.state.lastSync) {
      const msSince = Date.now() - new Date(store.state.lastSync).getTime();
      const intervalMs = store.state.settings.refreshInterval * 1000;
      if (msSince >= intervalMs) {
        console.log("[App] Polling triggered — fetching live data...");
        store.fetchLiveData().catch(err => console.error("[App] Live refresh failed:", err));
      }
    }
  }, POLL_CHECK_INTERVAL);

  // Manual refresh wiring
  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      if (store.state.mode === "LOADING") return;
      refreshBtn.textContent = "Refreshing...";
      refreshBtn.disabled = true;
      store.fetchLiveData()
        .then(() => {
          refreshBtn.textContent = "Refresh";
          refreshBtn.disabled = false;
        })
        .catch(() => {
          refreshBtn.textContent = "Refresh";
          refreshBtn.disabled = false;
        });
    });
  }
  
  // Wire up Demo UI
  const demoPanel = document.getElementById("demoControlPanel");
  const injectBtn = document.getElementById("injectDemoBtn");
  const resetBtn = document.getElementById("resetDemoBtn");
  const stationSel = document.getElementById("demoStationSelect");
  const scenarioSel = document.getElementById("demoScenarioSelect");
  
  // Expose a global way to enable demo mode for testing without console
  window.enableDemoMode = () => {
    window.__demoMode = true;
    if (demoPanel) demoPanel.style.display = 'flex';
  };
  
  // You can automatically show demo UI if we are in Demo mode (or always show it for SIH)
  // For the SIH judging, we want it available. We can just show it.
  window.enableDemoMode();

  if (injectBtn) {
    injectBtn.addEventListener("click", () => {
      window.__demoFaultInjectionEnabled = true;
      window.__demoStationId = stationSel.value;
      window.__demoFaultType = scenarioSel.value;
      if (scenarioSel.value === "SENSOR_FREEZE") {
          const current = store.state.stations.find(s => s.id === stationSel.value);
          window.__demoFreezeValue = current ? current.temperature : 25.0;
      }
      window.__demoDriftAccumulator = 0;
      
      console.log(`[Demo] Scheduled injection: ${scenarioSel.value} on ${stationSel.value}`);
      // Force an immediate refresh to apply the anomaly
      store.fetchLiveData();
    });
  }
  
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      window.__demoFaultInjectionEnabled = false;
      window.__demoStationId = null;
      window.__demoFaultType = null;
      window.__demoFreezeValue = null;
      window.__demoDriftAccumulator = 0;
      
      console.log("[Demo] Resetting anomalies...");
      // Optional: clear local anomaly history for the UI
      store.state.anomalies = store.state.anomalies.filter(a => !a.isSynthetic);
      store.notify();
      store.fetchLiveData();
    });
  }
});
