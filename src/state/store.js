import { getAWSStation } from "../api/imd.js";
import { getWeatherData } from "../api/weather.js";
import { normalizeAWSData } from "../data/normalizer.js";
import { STATIONS } from "../data/stations.js";
import { getDemoData } from "../data/demoData.js";

const CACHE_KEY = "aws-live-cache-v1";
const HISTORY_KEY = "aws-history-v1";
const DEFAULT_STATION = "DL-001";

function readJson(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback)); }
  catch { return fallback; }
}

export const store = {
  state: {
    mode: "CONNECTING",
    status: "CONNECTING",
    lastSync: null,
    selectedStationId: DEFAULT_STATION,
    stations: [],
    data: [],
    selectedStation: null,
    anomalies: [],
    history: readJson(HISTORY_KEY, {}),
    settings: { refreshInterval: 300, provider: "weatherapi" }
  },

  listeners: [],

  subscribe(listener) {
    this.listeners.push(listener);
    return () => { this.listeners = this.listeners.filter((l) => l !== listener); };
  },

  notify() { this.listeners.forEach((listener) => listener(this.state)); },

  setMode(mode) {
    this.state.mode = mode;
    this.state.status =
      mode === "LIVE" ? "Live WeatherAPI" :
      mode === "CACHED" ? "Cached Data" :
      mode === "ERROR" ? "Connection Error" :
      mode === "DEMO" ? "Demo Fallback" : "Connecting...";
  },

  appendHistory(station) {
    if (!station?.id || station.temperature === null) return;
    const series = Array.isArray(this.state.history[station.id])
      ? this.state.history[station.id]
      : [];

    const point = {
      timestamp: station.timestamp,
      temperature: station.temperature
    };

    const last = series[series.length - 1];
    if (!last || last.timestamp !== point.timestamp || last.temperature !== point.temperature) {
      series.push(point);
      this.state.history[station.id] = series.slice(-288);
      try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(this.state.history));
      } catch {}
    }
  },

  detectAnomalies(station) {
    if (!station || station.temperature === null) return [];

    const series = this.state.history[station.id] || [];
    const previous = series
      .slice(0, -1)
      .map((p) => p.temperature)
      .filter(Number.isFinite);

    if (previous.length < 6) return [];

    const mean = previous.reduce((a, b) => a + b, 0) / previous.length;
    const variance = previous.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / previous.length;
    const std = Math.sqrt(variance) || 0.1;
    const z = Math.abs((station.temperature - mean) / std);

    if (z < 3) return [];

    return [{
      id: `${station.id}-${station.timestamp}`,
      stationId: station.id,
      stationName: station.station || station.callSign || station.id,
      sensor: "Temperature",
      anomalyType: station.temperature > mean ? "SPIKE" : "DROP",
      severity: z >= 5 ? "CRITICAL" : "WARNING",
      observed: station.temperature,
      expected: mean,
      deviation: station.temperature - mean,
      confidence: Math.min(0.99, 0.50 + z / 10),
      timestamp: station.timestamp,
      evidence: `Temperature differs from the previous ${previous.length} collected observations by ${z.toFixed(1)} standard deviations.`,
      status: "NEW"
    }];
  },

  async fetchLiveData() {
    this.setMode("CONNECTING");
    this.notify();

    try {
      const promises = STATIONS.map(async (registryStation) => {
        let payload;
        if (this.state.settings.provider === "weatherapi") {
          payload = await getWeatherData(registryStation.locationQuery);
        } else {
          payload = await getAWSStation(registryStation.id);
        }
        const stationData = normalizeAWSData(payload)[0];
        if (!stationData) throw new Error("No data for " + registryStation.id);
        
        // Ensure ID matches registry for UI routing
        stationData.id = registryStation.id;
        // Keep coordinates from registry if weather API varies slightly
        stationData.latitude = registryStation.latitude;
        stationData.longitude = registryStation.longitude;
        stationData.station = registryStation.name;
        
        return stationData;
      });

      const results = await Promise.allSettled(promises);
      const liveStations = results
        .filter(r => r.status === "fulfilled")
        .map(r => r.value);

      if (liveStations.length === 0) {
        throw new Error("All live data requests failed.");
      }

      this.state.stations = liveStations;
      this.state.data = liveStations;
      
      if (!this.state.selectedStationId || !this.state.stations.find(s => s.id === this.state.selectedStationId)) {
        this.state.selectedStationId = this.state.stations[0].id;
      }
      this.state.selectedStation = this.state.stations.find(s => s.id === this.state.selectedStationId);
      this.state.lastSync = new Date().toISOString();

      let allAnomalies = [];
      liveStations.forEach(station => {
        this.appendHistory(station);
        allAnomalies = allAnomalies.concat(this.detectAnomalies(station));
      });
      this.state.anomalies = allAnomalies;
      this.setMode("LIVE");

      try {
        localStorage.setItem(CACHE_KEY, JSON.stringify({
          stations: liveStations,
          savedAt: this.state.lastSync
        }));
      } catch {}

      this.notify();
      return liveStations;
    } catch (error) {
      console.warn("Live fetch failed, attempting cache/demo fallback...", error);
      const cached = readJson(CACHE_KEY, null);

      if (cached?.stations?.length > 0) {
        this.state.stations = cached.stations;
        this.state.data = cached.stations;
        this.state.selectedStationId = this.state.selectedStationId || cached.stations[0].id;
        this.state.selectedStation = cached.stations.find(s => s.id === this.state.selectedStationId) || cached.stations[0];
        this.state.lastSync = cached.savedAt || null;
        
        let allAnomalies = [];
        this.state.stations.forEach(station => {
          allAnomalies = allAnomalies.concat(this.detectAnomalies(station));
        });
        this.state.anomalies = allAnomalies;
        
        this.setMode("CACHED");
        this.notify();
        return cached.stations;
      }

      // Final fallback to Demo Data
      console.warn("Falling back to Demo Mode.");
      const demoResult = getDemoData();
      this.state.stations = demoResult.data;
      this.state.data = demoResult.data;
      this.state.selectedStationId = this.state.selectedStationId || demoResult.data[0].id;
      this.state.selectedStation = demoResult.data.find(s => s.id === this.state.selectedStationId) || demoResult.data[0];
      this.state.lastSync = new Date().toISOString();
      
      let allAnomalies = [];
      this.state.stations.forEach(station => {
        allAnomalies = allAnomalies.concat(this.detectAnomalies(station));
      });
      this.state.anomalies = allAnomalies;
      
      this.setMode("DEMO");
      this.notify();
      return demoResult.data;
    }
  },

  setSelectedStation(stationId) {
    const station = this.state.stations.find((s) => s.id === stationId);
    if (!station) return;

    this.state.selectedStationId = stationId;
    this.state.selectedStation = station;
    this.state.anomalies = this.detectAnomalies(station);
    this.notify();
  }
};
