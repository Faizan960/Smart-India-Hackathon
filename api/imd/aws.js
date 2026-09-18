const IMD_AWS_URL = "https://api.imd.gov.in/api/v1/aws_data";

module.exports = async function handler(req, res) {
  if (req.method === "OPTIONS") {
    res.statusCode = 204;
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
    return res.end();
  }

  try {
    const station = typeof req.query?.station === "string"
      ? req.query.station.trim().toUpperCase()
      : "";

    let url = station
      ? IMD_AWS_URL + "?id=" + encodeURIComponent(station)
      : IMD_AWS_URL;
    
    if (process.env.IMD_API_KEY) {
      url += (url.includes("?") ? "&" : "?") + "key=" + encodeURIComponent(process.env.IMD_API_KEY);
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);

    let upstream;
    try {
      upstream = await fetch(url, {
        method: "GET",
        headers: {
          Accept: "application/json",
          "User-Agent": "AWS-Sentinel-SIH26073/1.0"
        },
        signal: controller.signal
      });
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
      source: "IMD AWS/ARG API",
      station: station || null,
      fetchedAt: new Date().toISOString(),
      data
    }));
  } catch (error) {
    res.statusCode = 502;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    return res.end(JSON.stringify({
      error: "Unable to reach IMD AWS API",
      message: error?.name === "AbortError" ? "IMD request timed out" : (error?.message || "Unknown error")
    }));
  }
};
