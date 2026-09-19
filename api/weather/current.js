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
    const location = req.query?.location || "New Delhi";
    const apiKey = process.env.WEATHERAPI_KEY;

    if (!apiKey) {
      throw new Error("WEATHERAPI_KEY is not configured on the server.");
    }

    const url = `https://api.weatherapi.com/v1/current.json?key=${encodeURIComponent(apiKey)}&q=${encodeURIComponent(location)}`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);

    let upstream;
    try {
      upstream = await fetch(url, { signal: controller.signal });
    } finally {
      clearTimeout(timeout);
    }

    const text = await upstream.text();
    let data;
    try { data = JSON.parse(text); }
    catch { data = { raw: text }; }

    res.statusCode = upstream.status;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Access-Control-Allow-Origin", "*");

    return res.end(JSON.stringify({
      source: "WeatherAPI",
      station: location,
      fetchedAt: new Date().toISOString(),
      data
    }));
  } catch (error) {
    res.statusCode = 502;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    return res.end(JSON.stringify({
      ok: false,
      provider: "WeatherAPI",
      error: error?.name === "AbortError" ? "WeatherAPI request timed out" : (error?.message || "Unknown error")
    }));
  }
};
