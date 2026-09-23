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

  res.statusCode = 200;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "s-maxage=3600, stale-while-revalidate");
  res.setHeader("Access-Control-Allow-Origin", "*");

  return res.end(JSON.stringify({
    cartoBasemapKey: process.env.CARTO_BASEMAP_KEY || "",
    // Sentinel ML inference backend (FastAPI on Render). Surfaced to the browser at
    // runtime because the frontend ships as native ES modules with no Vite build,
    // so build-time import.meta.env substitution is unavailable. Set the
    // VITE_SENTINEL_API_URL env var on Vercel to the Render service origin
    // (e.g. https://<service>.onrender.com); empty -> frontend falls back.
    sentinelApiUrl: process.env.VITE_SENTINEL_API_URL || process.env.SENTINEL_API_URL || ""
  }));
};
