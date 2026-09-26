try {
  require("dotenv").config({ path: require("path").resolve(process.cwd(), ".env.local") });
  require("dotenv").config();
} catch {}

module.exports = async function handler(req, res) {
  if (req.method === "OPTIONS") {
    res.statusCode = 204;
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
    return res.end();
  }

  try {
    const lat = req.query?.lat;
    const lon = req.query?.lon;
    const start = req.query?.start;
    const end = req.query?.end;
    const location = req.query?.location || "Unknown";
    
    if (!lat || !lon || !start || !end) {
      throw new Error("Missing required query parameters: lat, lon, start, end");
    }

    // Convert Unix epochs to ISO date strings for Open-Meteo
    const startDate = new Date(Number(start) * 1000).toISOString().split("T")[0];
    const endDate = new Date(Number(end) * 1000).toISOString().split("T")[0];

    // Use Open-Meteo Archive API (free, no API key required, real historical data).
    // timezone=UTC so the returned hour strings are UTC, not the location's local
    // time — otherwise they get read as UTC and every point is shifted by the
    // location's offset (e.g. IST +5:30), pushing recent hours into the future.
    const url = `https://archive-api.open-meteo.com/v1/archive?latitude=${lat}&longitude=${lon}&start_date=${startDate}&end_date=${endDate}&hourly=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m&timezone=UTC`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);

    let upstream;
    try {
      upstream = await fetch(url, { signal: controller.signal });
    } finally {
      clearTimeout(timeout);
    }

    const text = await upstream.text();
    let raw;
    try { raw = JSON.parse(text); }
    catch { raw = { raw: text }; }

    if (!upstream.ok) {
      res.statusCode = upstream.status;
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.setHeader("Access-Control-Allow-Origin", "*");
      return res.end(JSON.stringify({
        ok: false,
        provider: "Open-Meteo",
        error: raw?.reason || `Open-Meteo HTTP ${upstream.status}`
      }));
    }

    // Transform Open-Meteo response into the same shape the frontend expects:
    // { data: { list: [ { dt, main: { temp, humidity, pressure }, wind: { speed } } ] } }
    const hourly = raw.hourly || {};
    const times = hourly.time || [];
    const temps = hourly.temperature_2m || [];
    const humids = hourly.relative_humidity_2m || [];
    const pressures = hourly.surface_pressure || [];
    const winds = hourly.wind_speed_10m || [];

    const list = [];
    for (let i = 0; i < times.length; i++) {
      // Open-Meteo (timezone=UTC) returns naive strings like "2026-08-21T00:00"
      // with no offset; append "Z" so they parse as UTC on any runtime instead of
      // the server's local zone.
      const dt = Math.floor(new Date(times[i] + "Z").getTime() / 1000);
      if (isNaN(dt)) continue;
      // Skip entries where temperature is null (Open-Meteo returns null for future hours)
      if (temps[i] === null || temps[i] === undefined) continue;
      list.push({
        dt,
        main: {
          temp: temps[i],
          humidity: humids[i] ?? 0,
          pressure: pressures[i] ?? 0
        },
        wind: {
          // Open-Meteo wind_speed_10m is in km/h; our frontend converts m/s → km/h,
          // so we provide m/s here for consistency with the OWM format
          speed: winds[i] != null ? winds[i] / 3.6 : 0
        }
      });
    }

    res.statusCode = 200;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    // Cache for 1 hour — historical data doesn't change
    res.setHeader("Cache-Control", "public, max-age=3600, s-maxage=3600");
    res.setHeader("Access-Control-Allow-Origin", "*");

    return res.end(JSON.stringify({
      source: "Open-Meteo Historical",
      station: location,
      fetchedAt: new Date().toISOString(),
      data: {
        cnt: list.length,
        list
      }
    }));
  } catch (error) {
    res.statusCode = 502;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    return res.end(JSON.stringify({
      ok: false,
      provider: "Open-Meteo",
      error: error?.name === "AbortError" ? "Open-Meteo request timed out" : (error?.message || "Unknown error")
    }));
  }
};
