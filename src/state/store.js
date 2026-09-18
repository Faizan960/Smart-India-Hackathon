import { getAWSStation } from "../api/imd.js";
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
    lastSync: null,
    selectedStationId: DEFAULT_STATION,
    stations: [],
    selectedStation: null,
    anomalies: [],
    history: readJson(HISTORY_KEY, {})
  },
  listeners: [],

  subscribe(listener) {
    this.listeners.push(listener);
    return () => { this.listeners = this.listeners.filter((l) => l !== listener); };
  },

  notify() { this.listeners.forEach((listener) => listener(this.state)); },

  appendHistory(station) {
    if (!station?.id || station.temperature === null) return;
    const key = station.id;
    const series = Array.isArray(this.state.history[key]) ? this.state.history[key] : [];
    const point = { timestamp: station.timestamp, temperature: station.temperature };
    const last = series[series.length - 1];

    if (!last || last.timestamp !== point.timestamp || last.temperature !== point.temperature) {
      series.push(point);
      this.state.history[key] = series.slice(-288);
      try { localStorage.setItem(HISTORY_KEY, JSON.stringify(this.state.history)); } catch {}
    }
  },

  detectAnomalies(station) {
    if (!station || station.temperature === null) return [];
    const series = this.state.history[station.id] || [];
    const previous = series.slice(0, -1).map(p => p.temperature).filter(Number.isFinite);
    if (previous.length < 6) return [];

    const mean = previous.reduce((a,b) => a+b, 0) / previous.length;
    const variance = previous.reduce((a,b) => a + Math.pow(b - mean, 2), 0) / previous.length;
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
    this.state.mode = "CONNECTING";
    this.notify();

    try {
      const payload = await getAWSStation(stationId);
      const station = normalizeAWSData(payload)[0];
      if (!station) throw new Error("IMD returned no observation for station " + stationId);

      this.state.stations = [station];
      this.state.selectedStationId = station.id || stationId;
      this.state.selectedStation = station;
      this.state.mode = "LIVE";
      this.state.lastSync = new Date().toISOString();

      this.appendHistory(station);
      this.state.anomalies = this.detectAnomalies(station);

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
        this.state.selectedStation = cached.station;
        this.state.selectedStationId = cached.station.id || stationId;
        this.state.mode = "CACHED";
        this.state.lastSync = cached.savedAt || null;
        this.state.anomalies = this.detectAnomalies(cached.station);
        this.notify();
        return cached.station;
      }

      this.state.mode = "ERROR";
      this.notify();
      throw error;
    }
  },

  setSelectedStation(stationId) {
    const station = this.state.stations.find(s => s.id === stationId);
    if (!station) return;
    this.state.selectedStationId = stationId;
    this.state.selectedStation = station;
    this.state.anomalies = this.detectAnomalies(station);
    this.notify();
  }
};
