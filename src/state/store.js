import { getAWSStation } from "../api/imd.js";
import { getWeatherData, getHistoricalData } from "../api/weather.js";
import { normalizeAWSData } from "../data/normalizer.js";
import { STATIONS } from "../data/stations.js";
import { getDemoData } from "../data/demoData.js";

const CACHE_KEY = "aws-live-cache-v1";
const HISTORY_KEY = "aws-history-v1";
const DEFAULT_STATION = "DL-001";

// Development vs production polling
const IS_DEV = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

// Live polling cadence. Production polls every 10 minutes; a short dev cadence
// keeps local iteration fast. IMPORTANT: OpenWeather's observation time (`dt`)
// may NOT advance on every poll — we still poll on this cadence and place each
// successful response on the live chart by its receivedEpoch (see charts.js
// getPointEpoch). Polling every 10 minutes does not claim a new physical
// observation every 10 minutes. Kept as a pure resolver so the cadence is
// unit-testable without browser globals.
export const DEV_POLL_INTERVAL_MS = 5000;
export const PROD_POLL_INTERVAL_MS = 10 * 60 * 1000; // exactly 10 minutes
export function resolvePollIntervalMs(isDev) {
  return isDev ? DEV_POLL_INTERVAL_MS : PROD_POLL_INTERVAL_MS;
}
const LIVE_REFRESH_INTERVAL_MS = resolvePollIntervalMs(IS_DEV);

// Sentinel ML inference backend. Moved OFF the Vercel Python function onto a
// dedicated FastAPI service (Render). The URL is configurable, never hard-coded:
//   1. build-time VITE_SENTINEL_API_URL, if a bundler ever injects import.meta.env;
//   2. otherwise the runtime public config (window.appConfig.sentinelApiUrl,
//      populated from the VITE_SENTINEL_API_URL env var by /api/config/public) --
//      this is what works today, since the frontend ships as native ES modules
//      with no build step;
//   3. otherwise http://localhost:8000 in local dev.
// Returns null when nothing is configured so the caller uses the heuristic
// fallback rather than hitting a dead path.
function sentinelApiBase() {
  try {
    const env = (typeof import.meta !== "undefined" && import.meta.env) ? import.meta.env : null;
    if (env && env.VITE_SENTINEL_API_URL) return String(env.VITE_SENTINEL_API_URL).replace(/\/+$/, "");
  } catch { /* import.meta.env is unavailable without a bundler -- fall through */ }
  const cfg = (typeof window !== "undefined" && window.appConfig && window.appConfig.sentinelApiUrl) || "";
  if (cfg) return String(cfg).replace(/\/+$/, "");
  if (IS_DEV) return "http://localhost:8000";
  return null;
}

function sentinelInferenceUrl() {
  const base = sentinelApiBase();
  return base ? base + "/inference" : null;
}

// Concurrency control for API fetches
const MAX_CONCURRENT = 5;

function readJson(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback)); }
  catch { return fallback; }
}

function log(tag, ...args) {
  if (IS_DEV) console.log(`[${tag}]`, ...args);
}

export const store = {
  state: {
    mode: "LOADING",          // LOADING | CONNECTED | DEGRADED | ERROR | OFFLINE
    status: "Connecting...",
    lastSync: null,
    selectedStationId: DEFAULT_STATION,
    stations: [],             // Live data for stations that responded
    stationStatus: {},        // Per-station: { status: LOADING|LIVE|STALE|ERROR, error?: string }
    data: [],
    selectedStation: null,
    anomalies: [],
    history: readJson(HISTORY_KEY, {}),
    rawResponses: {},         // Latest raw API response per station (for Raw API viewer)
    settings: {
      refreshInterval: LIVE_REFRESH_INTERVAL_MS / 1000,
      provider: "openweathermap"
    }
  },

  _fetchInProgress: false,
  listeners: [],

  subscribe(listener) {
    this.listeners.push(listener);
    return () => { this.listeners = this.listeners.filter((l) => l !== listener); };
  },

  notify() { this.listeners.forEach((listener) => listener(this.state)); },

  setMode(mode) {
    this.state.mode = mode;
    this.state.status =
      mode === "CONNECTED" ? "Connected" :
      mode === "DEGRADED" ? "Degraded" :
      mode === "LOADING" ? "Connecting..." :
      mode === "ERROR" ? "Error" :
      mode === "OFFLINE" ? "Offline" :
      mode === "CACHED" ? "Cached" :
      mode === "DEMO" ? "Demo" : "Unknown";
  },

  appendHistory(station) {
    if (!station?.id || station.temperature === null) return;
    const series = Array.isArray(this.state.history[station.id])
      ? this.state.history[station.id]
      : [];

    const nowEpoch = Math.floor(Date.now() / 1000);
    const receivedEpoch = station.receivedEpoch || nowEpoch;
    
    // For live polling to build a historical chart, we MUST advance the timestamp 
    // even if the upstream provider (e.g. OpenWeatherMap) hasn't updated its own `dt`.
    const monotonicTimestamp = new Date(receivedEpoch * 1000).toISOString();

    const point = {
      timestamp: monotonicTimestamp,
      source: "live",            // provenance: /api/weather/current polling
      observedEpoch: station.observedEpoch,
      receivedEpoch: receivedEpoch,
      observedAt: station.observedAt,
      receivedAt: station.receivedAt || monotonicTimestamp,
      lastUpdatedEpoch: station.lastUpdatedEpoch || station.observedEpoch,
      temperature: station.temperature,
      humidity: station.humidity,
      pressure: station.pressure,
      windSpeed: station.windSpeed,
      isSynthetic: station.isSynthetic || false
    };

    const last = series[series.length - 1];
    
    // Deduplicate strictly by receivedEpoch to prevent double-render appends,
    // but ALLOW appending on every new poll cycle (where receivedEpoch advances).
    if (!last || point.receivedEpoch > last.receivedEpoch) {
      series.push(point);
      log("History", `observation accepted for ${station.id} (epoch=${receivedEpoch})`);
      // Keep the most recent 1440 live points (~10 days at the 10-minute cadence).
      this.state.history[station.id] = series.slice(-1440);
      try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(this.state.history));
      } catch {}
    } else {
      log("History", `observation deduplicated for ${station.id} (epoch=${receivedEpoch} <= ${last?.receivedEpoch})`);
    }
  },

  runHeuristicDetection(station, series) {
    if (!station || station.temperature === null) return [];
    log("Anomaly", `heuristic evaluation requested for ${station.id}`);

    const previous = series
      .slice(0, -1)
      .map((p) => p.temperature)
      .filter(Number.isFinite);

    if (previous.length < 6) return [];

    const anomalies = [];
    const mean = previous.reduce((a, b) => a + b, 0) / previous.length;
    const variance = previous.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / previous.length;
    const std = Math.sqrt(variance) || 0.1;

    // --- Temperature Z-score (spike/drop) ---
    const zTemp = Math.abs((station.temperature - mean) / std);
    if (zTemp >= 3) {
      const anomalyType = station.temperature > mean ? "SPIKE" : "DROP";
      const severity = zTemp >= 5 ? "CRITICAL" : "WARNING";

      // Multivariate evidence: check pressure & humidity consistency
      const prevPressures = series.slice(0, -1).map(p => p.pressure).filter(Number.isFinite);
      const prevHumidities = series.slice(0, -1).map(p => p.humidity).filter(Number.isFinite);

      let multivariateEvidence = "Insufficient data";
      let likelyCause = "Undetermined";

      if (prevPressures.length >= 6 && prevHumidities.length >= 6) {
        const pMean = prevPressures.reduce((a, b) => a + b, 0) / prevPressures.length;
        const pStd = Math.sqrt(prevPressures.reduce((a, b) => a + Math.pow(b - pMean, 2), 0) / prevPressures.length) || 0.1;
        const zPres = station.pressure !== null ? Math.abs((station.pressure - pMean) / pStd) : 0;

        const hMean = prevHumidities.reduce((a, b) => a + b, 0) / prevHumidities.length;
        const hStd = Math.sqrt(prevHumidities.reduce((a, b) => a + Math.pow(b - hMean, 2), 0) / prevHumidities.length) || 0.1;
        const zHum = station.humidity !== null ? Math.abs((station.humidity - hMean) / hStd) : 0;

        // If pressure and humidity also changed significantly → meteorological event
        // If only temperature changed → likely sensor fault
        if (zPres > 2 || zHum > 2) {
          multivariateEvidence = "Strong (correlated changes in P/RH)";
          likelyCause = "Likely meteorological event";
        } else {
          multivariateEvidence = "Weak (P/RH normal)";
          likelyCause = "Probable sensor fault";
        }
      }

      anomalies.push({
        id: `${station.id}-temp-${station.observedEpoch || station.lastUpdatedEpoch || Date.now()}`,
        stationId: station.id,
        stationName: station.station || station.callSign || station.id,
        sensor: "Temperature",
        anomalyType,
        severity,
        observed: station.temperature,
        expected: mean,
        deviation: station.temperature - mean,
        confidence: Math.min(0.99, 0.50 + zTemp / 10),
        timestamp: station.timestamp || station.observedAt,
        temporalEvidence: `Z-score ${zTemp.toFixed(1)} over ${previous.length} observations`,
        multivariateEvidence,
        spatialEvidence: "Normal (cross-station comparison not yet available)",
        likelyCause,
        evidence: `Temperature (${station.temperature.toFixed(1)}°C) differs from baseline (${mean.toFixed(1)}°C) by ${zTemp.toFixed(1)} σ. ${multivariateEvidence}. ${likelyCause}.`,
        status: "NEW",
        isSynthetic: station.isSynthetic || false
      });
    }

    // --- Freeze detection ---
    if (series.length >= 5) {
      const recentTemps = series.slice(-5).map(p => p.temperature).filter(Number.isFinite);
      if (recentTemps.length === 5 && recentTemps.every(v => v === recentTemps[0])) {
        anomalies.push({
          id: `${station.id}-freeze-${station.observedEpoch || Date.now()}`,
          stationId: station.id,
          stationName: station.station || station.callSign || station.id,
          sensor: "Temperature",
          anomalyType: "FREEZE",
          severity: "WARNING",
          observed: station.temperature,
          expected: station.temperature,
          deviation: 0,
          confidence: 0.85,
          timestamp: station.timestamp || station.observedAt,
          temporalEvidence: "5 consecutive identical readings",
          multivariateEvidence: "N/A",
          spatialEvidence: "N/A",
          likelyCause: "Probable sensor fault (stuck reading)",
          evidence: "Temperature sensor has not changed for 5 consecutive observations. Likely sensor malfunction.",
          status: "NEW",
          isSynthetic: station.isSynthetic || false
        });
      }
    }

    // --- Pressure anomaly ---
    if (station.pressure !== null) {
      const prevP = series.slice(0, -1).map(p => p.pressure).filter(Number.isFinite);
      if (prevP.length >= 6) {
        const pMean = prevP.reduce((a, b) => a + b, 0) / prevP.length;
        const pVar = prevP.reduce((a, b) => a + Math.pow(b - pMean, 2), 0) / prevP.length;
        const pStd = Math.sqrt(pVar) || 0.1;
        const zP = Math.abs((station.pressure - pMean) / pStd);
        if (zP >= 3) {
          anomalies.push({
            id: `${station.id}-pres-${station.observedEpoch || Date.now()}`,
            stationId: station.id,
            stationName: station.station || station.callSign || station.id,
            sensor: "Pressure",
            anomalyType: station.pressure > pMean ? "SPIKE" : "DROP",
            severity: zP >= 5 ? "CRITICAL" : "WARNING",
            observed: station.pressure,
            expected: pMean,
            deviation: station.pressure - pMean,
            confidence: Math.min(0.99, 0.50 + zP / 10),
            timestamp: station.timestamp || station.observedAt,
            temporalEvidence: `Z-score ${zP.toFixed(1)}`,
            multivariateEvidence: "Pressure-specific",
            spatialEvidence: "N/A",
            likelyCause: zP >= 5 ? "Probable sensor fault" : "Possible weather system",
            evidence: `Pressure (${station.pressure.toFixed(1)} hPa) deviates from baseline (${pMean.toFixed(1)} hPa) by ${zP.toFixed(1)} σ.`,
            status: "NEW",
            isSynthetic: station.isSynthetic || false
          });
        }
      }
    }

    // --- Humidity anomaly ---
    if (station.humidity !== null) {
      const prevH = series.slice(0, -1).map(p => p.humidity).filter(Number.isFinite);
      if (prevH.length >= 6) {
        const hMean = prevH.reduce((a, b) => a + b, 0) / prevH.length;
        const hVar = prevH.reduce((a, b) => a + Math.pow(b - hMean, 2), 0) / prevH.length;
        const hStd = Math.sqrt(hVar) || 0.1;
        const zH = Math.abs((station.humidity - hMean) / hStd);
        if (zH >= 3) {
          anomalies.push({
            id: `${station.id}-hum-${station.observedEpoch || Date.now()}`,
            stationId: station.id,
            stationName: station.station || station.callSign || station.id,
            sensor: "Humidity",
            anomalyType: station.humidity > hMean ? "SPIKE" : "DROP",
            severity: zH >= 5 ? "CRITICAL" : "WARNING",
            observed: station.humidity,
            expected: hMean,
            deviation: station.humidity - hMean,
            confidence: Math.min(0.99, 0.50 + zH / 10),
            timestamp: station.timestamp || station.observedAt,
            temporalEvidence: `Z-score ${zH.toFixed(1)}`,
            multivariateEvidence: "Humidity-specific",
            spatialEvidence: "N/A",
            likelyCause: zH >= 5 ? "Probable sensor fault" : "Possible weather event",
            evidence: `Humidity (${station.humidity.toFixed(0)}%) deviates from baseline (${hMean.toFixed(0)}%) by ${zH.toFixed(1)} σ.`,
            status: "NEW",
            isSynthetic: station.isSynthetic || false
          });
        }
      }
    }

    // --- Range violation ---
    const RANGES = {
      temperature: [-60, 60],
      humidity: [0, 100],
      pressure: [870, 1084]
    };
    for (const [sensor, [lo, hi]] of Object.entries(RANGES)) {
      const val = station[sensor];
      if (val !== null && val !== undefined && (val < lo || val > hi)) {
        anomalies.push({
          id: `${station.id}-range-${sensor}-${station.observedEpoch || Date.now()}`,
          stationId: station.id,
          stationName: station.station || station.callSign || station.id,
          sensor: sensor.charAt(0).toUpperCase() + sensor.slice(1),
          anomalyType: "RANGE_VIOLATION",
          severity: "CRITICAL",
          observed: val,
          expected: `${lo}–${hi}`,
          deviation: val < lo ? val - lo : val - hi,
          confidence: 0.99,
          timestamp: station.timestamp || station.observedAt,
          temporalEvidence: "Out of physical range",
          multivariateEvidence: "N/A",
          spatialEvidence: "N/A",
          likelyCause: "Sensor malfunction or data corruption",
          evidence: `${sensor} value ${val} is outside physical range [${lo}, ${hi}].`,
          status: "NEW",
          isSynthetic: station.isSynthetic || false
        });
      }
    }

    return anomalies;
  },

  async runMLInference(station) {
    if (!station || station.temperature === null) return [];
    const series = this.state.history[station.id] || [];
    if (series.length < 6) return []; // Need some history for temporal features

    // Send a wider rolling window: the Sentinel temporal features are wall-clock
    // based (3h / 24h windows, pressure tendency), so more history resolves them
    // better. The adapter bounds/keeps the last LIVE_HISTORY_ROWS server-side.
    // History points do NOT carry station_id/lat/lon, so pass those at top level.
    const inferenceSeries = series.slice(-300);

    // Resolve the Sentinel backend (Render FastAPI). If none is configured, skip
    // straight to the heuristic fallback rather than hitting a dead relative path.
    const inferenceUrl = sentinelInferenceUrl();
    if (!inferenceUrl) {
      log("ML", "No Sentinel API URL configured; using heuristic detection.");
      return this.runHeuristicDetection(station, series);
    }

    try {
      const response = await fetch(inferenceUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          history: inferenceSeries,
          station_id: station.id,
          latitude: station.latitude ?? null,
          longitude: station.longitude ?? null
        })
      });
      if (!response.ok) throw new Error('ML API failed');
      const result = await response.json();

      // Surface a fault card when the detector flags an anomaly OR the pipeline
      // typed a real fault (e.g. SENSOR_DROPOUT is is_anomaly=false but real).
      // The degraded / incomplete-data path returns fault_type=NORMAL, so an
      // unscoreable reading stays quiet rather than raising a phantom fault.
      const faultType = result.fault_type || "NORMAL";
      if (!result.is_anomaly && faultType === "NORMAL") return [];

      // anomaly_score may legitimately be null (incomplete latest reading — the
      // pipeline refuses to fabricate a score). NEVER call .toFixed() on null.
      const score = (typeof result.anomaly_score === "number") ? result.anomaly_score : null;
      const scoreText = score !== null ? score.toFixed(2) : "N/A (incomplete data)";

      // Prefer the pipeline's own severity (NORMAL/WARNING/CRITICAL); fall back
      // only when it is absent/UNKNOWN. Do NOT re-derive it from the raw score.
      const severity = (result.severity && result.severity !== "UNKNOWN")
        ? result.severity
        : (score !== null && score > 0.8 ? "CRITICAL" : "WARNING");

      const reasons = Array.isArray(result.reasons) ? result.reasons : [];
      const reasonText = reasons.length ? reasons.join("; ") : `Classified as ${faultType}.`;

      return [{
        id: `${station.id}-ml-${Date.now()}`,
        stationId: station.id,
        stationName: station.station || station.id,
        sensor: "Multiple",
        anomalyType: faultType,
        severity,
        observed: station.temperature,
        expected: "Model baseline",
        deviation: 0,
        // fault_confidence = confidence in the fault TYPE. This is NOT the anomaly
        // score and NOT a calibrated probability; kept numeric for the existing UI.
        confidence: (typeof result.confidence === "number") ? result.confidence : 0,
        timestamp: station.timestamp || station.observedAt,
        temporalEvidence: `Sentinel anomaly score: ${scoreText}`,
        multivariateEvidence: "AWS Sentinel (Isolation Forest + evidence fusion)",
        spatialEvidence: "N/A",
        likelyCause: faultType,
        evidence: `Sentinel ML assessment: ${reasonText} (anomaly score ${scoreText}).`,
        status: "NEW",
        isSynthetic: station.isSynthetic || false,
        // --- richer Sentinel fields (additive; the existing UI ignores unknown keys) ---
        source: "aws_sentinel",
        mlScore: score,
        fusedStatus: result.fused_status || null,
        faultConfidence: (typeof result.fault_confidence === "number") ? result.fault_confidence : null,
        reasons,
        explanation: result.explanation || null,
        layaDecision: result.laya_decision || null,
        verification: result.verification || null,
        health: result.health || null,
        baselineSource: result.baseline_source || null,
        dataComplete: result.data_complete !== false
      }];
    } catch (err) {
      log("ML", "Fallback to heuristic detection: " + err.message);
      return this.runHeuristicDetection(station, series);
    }
  },

  async loadHistoricalData(station) {
    if (!station || !station.id) return;
    const historyCacheKey = `weather-history-${station.id}`;
    
    // Check cache
    try {
      const cached = localStorage.getItem(historyCacheKey);
      if (cached) {
        const parsed = JSON.parse(cached);
        const ageHours = (Date.now() - new Date(parsed.fetchedAt).getTime()) / (1000 * 60 * 60);
        
        if (parsed.observations && parsed.observations.length > 0 && ageHours < 2) {
          log("History", `Loaded ${parsed.observations.length} historical records from cache for ${station.id}`);
          this._mergeHistoricalData(station.id, parsed.observations);
          return;
        }
      }
    } catch {}

    log("History", `Fetching 30-day historical data for ${station.id}...`);
    try {
      const payload = await getHistoricalData(station);
      if (payload && payload.data && payload.data.list) {
        // OpenWeatherMap historical response has a 'list' of hourly observations
        // map to our normalizer schema. Note: bulk API format differs slightly but we map it directly:
        const normalized = payload.data.list.map(item => {
          return {
            id: station.id,
            source: "historical",   // provenance: /api/weather/history backfill
            timestamp: new Date(item.dt * 1000).toISOString(),
            observedEpoch: item.dt,
            receivedEpoch: item.dt, // for historical, received is observed
            temperature: item.main.temp,
            humidity: item.main.humidity,
            pressure: item.main.pressure,
            windSpeed: item.wind?.speed ? item.wind.speed * 3.6 : 0,
            isSynthetic: false
          };
        });

        // Cache it
        try {
          localStorage.setItem(historyCacheKey, JSON.stringify({
            fetchedAt: new Date().toISOString(),
            observations: normalized
          }));
        } catch {}

        this._mergeHistoricalData(station.id, normalized);
      }
    } catch (err) {
      log("History", `Failed to fetch historical data for ${station.id}: ${err.message}`);
    }
  },

  _mergeHistoricalData(stationId, historicalObservations) {
    const series = Array.isArray(this.state.history[stationId]) ? this.state.history[stationId] : [];
    
    // Merge by receivedEpoch
    const merged = [...historicalObservations, ...series];
    
    // Deduplicate by receivedEpoch to preserve live polling points
    const map = new Map();
    for (const obs of merged) {
       map.set(obs.receivedEpoch, obs);
    }
    
    // Sort chronologically
    const finalSeries = Array.from(map.values()).sort((a, b) => a.receivedEpoch - b.receivedEpoch);
    
    // Cap at say 1440 points (actually 30 days of hourly is 720 points, so 2000 is plenty)
    this.state.history[stationId] = finalSeries.slice(-2000);
    this.notify();
  },

  async fetchLiveData() {
    // Prevent overlapping requests
    if (this._fetchInProgress) {
      log("API", "fetch skipped — already in progress");
      return this.state.stations;
    }
    this._fetchInProgress = true;
    log("API", "request started for all stations");

    this.setMode("LOADING");
    // Initialize per-station status
    STATIONS.forEach(s => {
      if (!this.state.stationStatus[s.id]) {
        this.state.stationStatus[s.id] = { status: "LOADING" };
      }
    });
    this.notify();

    try {
      // Controlled concurrency: fetch in batches of MAX_CONCURRENT
      const allResults = [];
      for (let i = 0; i < STATIONS.length; i += MAX_CONCURRENT) {
        const batch = STATIONS.slice(i, i + MAX_CONCURRENT);
        const batchPromises = batch.map(async (registryStation) => {
          log("API", `fetching ${registryStation.id} (${registryStation.locationQuery})`);
          this.state.stationStatus[registryStation.id] = { status: "LOADING" };

          try {
            let payload;
            if (this.state.settings.provider === "openweathermap") {
              payload = await getWeatherData(registryStation.locationQuery);
            } else {
              payload = await getAWSStation(registryStation.id);
            }

            log("API", `response received for ${registryStation.id}`);

            // Store raw response (strip any sensitive data)
            const rawForViewer = { ...payload };
            this.state.rawResponses[registryStation.id] = rawForViewer;

            // Demo fault injection logic
            if (window.__demoFaultInjectionEnabled && payload?.data?.main) {
              const targetStation = window.__demoStationId || "DL-001";
              if (registryStation.id === targetStation) {
                const faultType = window.__demoFaultType || "TEMPERATURE_SPIKE";
                if (faultType === "TEMPERATURE_SPIKE") payload.data.main.temp += 20.0;
                if (faultType === "TEMPERATURE_DROP") payload.data.main.temp -= 20.0;
                if (faultType === "SENSOR_FREEZE") payload.data.main.temp = window.__demoFreezeValue || payload.data.main.temp;
                if (faultType === "SENSOR_DRIFT") {
                    window.__demoDriftAccumulator = (window.__demoDriftAccumulator || 0) + 1.5;
                    payload.data.main.temp += window.__demoDriftAccumulator;
                }
                if (faultType === "PRESSURE_SPIKE") payload.data.main.pressure += 50;
                if (faultType === "HUMIDITY_SPIKE") payload.data.main.humidity = Math.min(100, payload.data.main.humidity + 40);
                if (faultType === "SENSOR_DROPOUT") {
                    payload.data.main.temp = null;
                    payload.data.main.humidity = null;
                }
                log("API", `DEMO FAULT INJECTED: ${faultType} on ${registryStation.id}`);
                payload._isSynthetic = true;
              }
            }

            const normalized = normalizeAWSData(payload);
            log("Normalizer", `normalized ${normalized.length} entries for ${registryStation.id}`);
            const stationData = normalized[0];
            if (!stationData) throw new Error("No data for " + registryStation.id);

            // Ensure ID matches registry for UI routing
            stationData.id = registryStation.id;
            stationData.latitude = registryStation.latitude;
            stationData.longitude = registryStation.longitude;
            stationData.station = registryStation.name;
            if (payload._isSynthetic) stationData.isSynthetic = true;

            this.state.stationStatus[registryStation.id] = { status: "LIVE" };
            return { status: "fulfilled", value: stationData };
          } catch (err) {
            log("API", `ERROR for ${registryStation.id}: ${err.message}`);
            this.state.stationStatus[registryStation.id] = { status: "ERROR", error: err.message };
            return { status: "rejected", reason: err };
          }
        });

        const batchResults = await Promise.all(batchPromises);
        allResults.push(...batchResults);
      }

      const liveStations = allResults
        .filter(r => r.status === "fulfilled")
        .map(r => r.value);

      const failedCount = allResults.length - liveStations.length;
      log("API", `completed: ${liveStations.length} success, ${failedCount} failed`);

      if (liveStations.length === 0) {
        this.setMode("ERROR");
        this._fetchInProgress = false;
        throw new Error("All live data requests failed.");
      } else if (failedCount > 0) {
        this.setMode("DEGRADED");
      } else {
        this.setMode("CONNECTED");
      }

      this.state.stations = liveStations;
      this.state.data = liveStations;

      if (!this.state.selectedStationId || !this.state.stations.find(s => s.id === this.state.selectedStationId)) {
        this.state.selectedStationId = this.state.stations[0].id;
      }
      this.state.selectedStation = this.state.stations.find(s => s.id === this.state.selectedStationId);
      this.state.lastSync = new Date().toISOString();

      let allAnomalies = [];
      // Synchronously append history for ALL stations first
      for (const station of liveStations) {
        this.appendHistory(station);
        log("Store", `station history updated: ${station.id}`);
      }
      
      // Concurrently run ML inference for all stations
      const inferencePromises = liveStations.map(station => this.runMLInference(station));
      const inferenceResults = await Promise.all(inferencePromises);
      
      for (const anomalies of inferenceResults) {
        allAnomalies = allAnomalies.concat(anomalies);
      }
      this.state.anomalies = allAnomalies;

      try {
        localStorage.setItem(CACHE_KEY, JSON.stringify({
          stations: liveStations,
          savedAt: this.state.lastSync
        }));
      } catch {}

      this._fetchInProgress = false;
      this.notify();
      return liveStations;
    } catch (error) {
      this._fetchInProgress = false;
      console.warn("Live fetch failed, attempting cache/demo fallback...", error);
      const cached = readJson(CACHE_KEY, null);

      if (cached?.stations?.length > 0) {
        this.state.stations = cached.stations;
        this.state.data = cached.stations;
        this.state.selectedStationId = this.state.selectedStationId || cached.stations[0].id;
        this.state.selectedStation = cached.stations.find(s => s.id === this.state.selectedStationId) || cached.stations[0];
        this.state.lastSync = cached.savedAt || null;

        let allAnomalies = [];
        const inferencePromises = this.state.stations.map(station => this.runMLInference(station));
        const inferenceResults = await Promise.all(inferencePromises);
        for (const anomalies of inferenceResults) {
          allAnomalies = allAnomalies.concat(anomalies);
        }
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
      const inferencePromises = this.state.stations.map(station => this.runMLInference(station));
      const inferenceResults = await Promise.all(inferencePromises);
      for (const anomalies of inferenceResults) {
        allAnomalies = allAnomalies.concat(anomalies);
      }
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
    // Do NOT overwrite all anomalies — just notify so chart re-renders
    this.notify();
  }
};
