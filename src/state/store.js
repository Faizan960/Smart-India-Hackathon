import { getAWSStation } from "../api/imd.js";
import { getWeatherData } from "../api/weather.js";
import { normalizeAWSData } from "../data/normalizer.js";

const CACHE_KEY = "aws-live-cache-v1";
const HISTORY_KEY = "aws-history-v1";
const DEFAULT_STATION = "NDL";

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
      mode === "LIVE" ? "CONNECTED" :
      mode === "CACHED" ? "CACHED" :
      mode === "ERROR" ? "ERROR" :
      mode === "DEMO" ? "DEMO MODE" : "CONNECTING";
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

  async fetchLiveStation(stationId = DEFAULT_STATION) {
    this.setMode("CONNECTING");
    this.notify();

    try {
      let payload;
      if (this.state.settings.provider === "weatherapi") {
        payload = await getWeatherData(stationId);
      } else {
        payload = await getAWSStation(stationId);
      }
      
      const station = normalizeAWSData(payload)[0];

      if (!station) throw new Error("API returned no observation for station " + stationId);

      this.state.stations = [station];
      this.state.data = this.state.stations;
      this.state.selectedStationId = station.id || stationId;
      this.state.selectedStation = station;
      this.state.lastSync = new Date().toISOString();

      this.appendHistory(station);
      this.state.anomalies = this.detectAnomalies(station);
      this.setMode("LIVE");

      try {
        localStorage.setItem(CACHE_KEY, JSON.stringify({
          station,
          savedAt: this.state.lastSync
        }));
      } catch {}

      this.notify();
      return station;
    } catch (error) {
      const cached = readJson(CACHE_KEY, null);

      if (cached?.station) {
        this.state.stations = [cached.station];
        this.state.data = this.state.stations;
        this.state.selectedStation = cached.station;
        this.state.selectedStationId = cached.station.id || stationId;
        this.state.lastSync = cached.savedAt || null;
        this.state.anomalies = this.detectAnomalies(cached.station);
        this.setMode("CACHED");
        this.notify();
        return cached.station;
      }

      this.setMode("ERROR");
      this.notify();
      throw error;
    }
  },

  async fetchLiveData() {
    return this.fetchLiveStation(DEFAULT_STATION);
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
