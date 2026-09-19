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
    cartoBasemapKey: process.env.CARTO_BASEMAP_KEY || ""
  }));
};
