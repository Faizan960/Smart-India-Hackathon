const API_ROOT = "/api/weather/current";

export async function getWeatherData(location = "New Delhi", signal) {
  const response = await fetch(`${API_ROOT}?location=${encodeURIComponent(location)}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal
  });

  let payload = null;
  try { payload = await response.json(); } catch {}

  if (!response.ok) {
    throw new Error(payload?.message || payload?.error || `WeatherAPI HTTP ${response.status}`);
  }

  return payload;
}
