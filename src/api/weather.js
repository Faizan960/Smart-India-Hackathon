const API_ROOT = "/api/weather/current";
const API_HISTORY = "/api/weather/history";

export async function getWeatherData(location = "New Delhi", signal) {
  const response = await fetch(`${API_ROOT}?location=${encodeURIComponent(location)}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal
  });

  let payload = null;
  try { payload = await response.json(); } catch {}

  if (!response.ok) {
    throw new Error(payload?.error || `WeatherAPI HTTP ${response.status}`);
  }

  return payload;
}

export async function getHistoricalData(station, signal) {
  // We need lat/lon and start/end epoch
  if (!station || !station.latitude || !station.longitude) {
    throw new Error("Station coordinates are required for historical data");
  }

  const end = Math.floor(Date.now() / 1000);
  const start = end - 30 * 24 * 60 * 60; // 30 days ago

  const url = `${API_HISTORY}?lat=${station.latitude}&lon=${station.longitude}&start=${start}&end=${end}&location=${encodeURIComponent(station.id || "Unknown")}`;

  const response = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal
  });

  let payload = null;
  try { payload = await response.json(); } catch {}

  if (!response.ok) {
    throw new Error(payload?.error || `Weather History API HTTP ${response.status}`);
  }

  return payload;
}
