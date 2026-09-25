// Frontend live-pipeline tests — Node built-in runner, zero dependencies.
//
//   Run:  npm run test:frontend      (node --test tests/frontend/)
//
// These import the REAL browser ES modules (src/state/store.js,
// src/components/charts.js). Node auto-detects them as ES modules; we only stub
// the browser globals they touch at import time. No network is performed.
//
// Coverage maps to the live-pipeline spec:
//   A poll interval  B append        C same provider dt  D different dt
//   E no response    F source tags   G timestamp split   H synthetic guard
import { test } from "node:test";
import assert from "node:assert/strict";
import { pathToFileURL, fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// --- Minimal browser-global stubs (must exist BEFORE importing the modules) ---
const _ls = new Map();
globalThis.localStorage = {
  getItem: (k) => (_ls.has(k) ? _ls.get(k) : null),
  setItem: (k, v) => _ls.set(k, String(v)),
  removeItem: (k) => _ls.delete(k),
  clear: () => _ls.clear()
};
globalThis.window = {
  location: { hostname: "example.com" }, // non-dev by default
  addEventListener() {}, dispatchEvent() {}, appConfig: {}
};
globalThis.document = {
  documentElement: { getAttribute: () => "light" },
  getElementById: () => null, querySelectorAll: () => [], addEventListener() {}
};
globalThis.fetch = async () => { throw new Error("network disabled in tests"); };

// Resolve source relative to THIS file so cwd does not matter.
const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "../../src");
const charts = await import(pathToFileURL(resolve(SRC, "components/charts.js")).href);
const storeMod = await import(pathToFileURL(resolve(SRC, "state/store.js")).href);
const store = storeMod.store;

// A normalized live reading like store.fetchLiveData() would append.
function liveReading({ id = "DL-001", temperature = 28.4, humidity = 74, pressure = 1008.2, observedEpoch, receivedEpoch, isSynthetic = false } = {}) {
  return {
    id, temperature, humidity, pressure, windSpeed: 5,
    observedEpoch, observedAt: new Date(observedEpoch * 1000).toISOString(),
    receivedEpoch, receivedAt: new Date(receivedEpoch * 1000).toISOString(),
    lastUpdatedEpoch: observedEpoch, isSynthetic
  };
}
function resetHistory() { store.state.history = {}; }

// -- A: production poll interval is exactly 10 minutes --------------------------
test("A: production poll interval is exactly 10 minutes (not 1-min, not hourly)", () => {
  assert.equal(storeMod.PROD_POLL_INTERVAL_MS, 10 * 60 * 1000);
  assert.equal(storeMod.resolvePollIntervalMs(false), 600000);
  assert.notEqual(storeMod.resolvePollIntervalMs(false), 60 * 1000);      // not every 1 minute
  assert.notEqual(storeMod.resolvePollIntervalMs(false), 60 * 60 * 1000); // not hourly
  assert.equal(storeMod.resolvePollIntervalMs(true), storeMod.DEV_POLL_INTERVAL_MS); // dev keeps short cadence
});

// -- B: a successful OpenWeather response is appended ---------------------------
test("B: a successful response is appended to live history", () => {
  resetHistory();
  store.appendHistory(liveReading({ observedEpoch: 1758881220, receivedEpoch: 1758881400 }));
  const series = store.state.history["DL-001"];
  assert.equal(series.length, 1);
  assert.equal(series[0].temperature, 28.4);
  assert.equal(series[0].source, "live");
});

// -- C: identical provider dt across two polls → both kept, receivedEpoch distinct
test("C: two responses with identical provider dt are both kept; receivedEpoch stays distinct", () => {
  resetHistory();
  const dt = 1758881220; // provider observation time unchanged across both polls
  store.appendHistory(liveReading({ observedEpoch: dt, receivedEpoch: 1758881400 }));
  store.appendHistory(liveReading({ observedEpoch: dt, receivedEpoch: 1758882000 })); // +10 min
  const series = store.state.history["DL-001"];
  assert.equal(series.length, 2, "both successful responses are represented");
  assert.equal(series[0].observedEpoch, series[1].observedEpoch, "provider dt unchanged");
  assert.notEqual(series[0].receivedEpoch, series[1].receivedEpoch, "receivedEpoch distinct");
  // On the live chart the two samples land at distinct x positions (receivedEpoch).
  assert.notEqual(charts.getPointEpoch(series[0]), charts.getPointEpoch(series[1]));
  assert.equal(charts.getPointEpoch(series[1]), 1758882000);
});

// -- D: different provider dt → both represented --------------------------------
test("D: two responses with different provider dt are both represented", () => {
  resetHistory();
  store.appendHistory(liveReading({ observedEpoch: 1758881220, receivedEpoch: 1758881400 }));
  store.appendHistory(liveReading({ observedEpoch: 1758881820, receivedEpoch: 1758882000 }));
  const series = store.state.history["DL-001"];
  assert.equal(series.length, 2);
  assert.notEqual(series[0].observedEpoch, series[1].observedEpoch);
  assert.notEqual(series[0].receivedEpoch, series[1].receivedEpoch);
});

// -- E: no successful response → no fabricated point, no gap-filling ------------
test("E: a missing/null reading creates no point and no interpolation", () => {
  resetHistory();
  store.appendHistory(liveReading({ observedEpoch: 1758881220, receivedEpoch: 1758881400 }));
  // Failed/absent middle poll: temperature null → rejected outright, nothing stored.
  store.appendHistory(liveReading({ observedEpoch: 1758881820, receivedEpoch: 1758882000, temperature: null }));
  store.appendHistory(liveReading({ observedEpoch: 1758882420, receivedEpoch: 1758882600 }));
  const series = store.state.history["DL-001"];
  assert.equal(series.length, 2, "no synthetic point invented for the missing response");
  // The gap between the two real polls is left as-is (no forward-fill).
  assert.deepEqual(series.map(p => p.receivedEpoch), [1758881400, 1758882600]);
});

// -- F: provenance tags ---------------------------------------------------------
test("F: live points are source 'live'; historical points classify as 'historical'", () => {
  resetHistory();
  store.appendHistory(liveReading({ observedEpoch: 1758881220, receivedEpoch: 1758881400 }));
  assert.equal(store.state.history["DL-001"][0].source, "live");
  const hist = { source: "historical", observedEpoch: 1758790800, receivedEpoch: 1758790800, temperature: 25, isSynthetic: false };
  assert.equal(charts.classifyHistoryPoint(hist), "historical");
});

// -- G: timestamp separation (chart uses receivedEpoch, ML keeps observedEpoch) -
test("G: live axis = receivedEpoch; historical axis = observedEpoch; observedEpoch retained", () => {
  const live = { source: "live", observedEpoch: 1758881220, receivedEpoch: 1758881400, temperature: 28 };
  assert.equal(charts.getPointEpoch(live), 1758881400, "live timeline uses receivedEpoch");
  const hist = { source: "historical", observedEpoch: 1758790800, receivedEpoch: 1758790800, temperature: 25 };
  assert.equal(charts.getPointEpoch(hist), 1758790800, "historical timeline uses observedEpoch");
  // The appended live point still carries observedEpoch for ML temporal features.
  resetHistory();
  store.appendHistory(liveReading({ observedEpoch: 1758881220, receivedEpoch: 1758881400 }));
  const stored = store.state.history["DL-001"][0];
  assert.equal(stored.observedEpoch, 1758881220);
  assert.notEqual(stored.observedEpoch, stored.receivedEpoch);
});

// -- H: synthetic/demo never presented as real ----------------------------------
test("H: synthetic/demo data is never presented as real live data", () => {
  assert.equal(charts.classifyHistoryPoint({ isSynthetic: true, source: "live" }), "synthetic");
  const markers = charts.collectAnomalyMarkers(
    [
      { stationId: "DL-001", sensor: "Temperature", observed: 40, timestamp: 1758881400, isSynthetic: true },
      { stationId: "DL-001", sensor: "Temperature", observed: 41, timestamp: 1758881400, isSynthetic: false }
    ],
    "DL-001", 1758881000, 1758882000
  );
  assert.equal(markers.length, 1, "synthetic anomaly excluded; only the real one is plotted");
  assert.equal(markers[0].y, 41);
});

// -- Provider-observation staleness indicator (honest, non-fabricating) ---------
test("providerObservationStatus flags repeated provider dt without fabricating values", () => {
  const stale = charts.providerObservationStatus([
    { observedEpoch: 100, receivedEpoch: 1000, temperature: 28 },
    { observedEpoch: 100, receivedEpoch: 1600, temperature: 28 }
  ]);
  assert.equal(stale.stale, true);
  assert.equal(stale.repeated, 1);
  const fresh = charts.providerObservationStatus([
    { observedEpoch: 100, receivedEpoch: 1000, temperature: 28 },
    { observedEpoch: 200, receivedEpoch: 1600, temperature: 29 }
  ]);
  assert.equal(fresh.stale, false);
  assert.equal(fresh.repeated, 0);
});
