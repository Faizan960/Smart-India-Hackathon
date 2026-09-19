const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = 3000;
const MIME_TYPES = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".json": "application/json"
};

const server = http.createServer(async (req, res) => {
  const urlPath = req.url.split("?")[0];

  // API routes — emulate Vercel serverless functions
  if (urlPath === "/api/weather/current") {
    req.query = Object.fromEntries(new URLSearchParams(req.url.split("?")[1]));
    const handler = require("./api/weather/current.js");
    return handler(req, res);
  }

  if (urlPath === "/api/config/public") {
    req.query = Object.fromEntries(new URLSearchParams(req.url.split("?")[1]));
    const handler = require("./api/config/public.js");
    return handler(req, res);
  }

  // Static file serving
  let filePath = "." + urlPath;
  if (filePath === "./") filePath = "./index.html";

  const extname = path.extname(filePath);
  const contentType = MIME_TYPES[extname] || "text/plain";

  try {
    const content = await fs.promises.readFile(filePath);
    res.writeHead(200, { "Content-Type": contentType });
    res.end(content, "utf-8");
  } catch (error) {
    if (error.code === "ENOENT") {
      res.writeHead(404);
      res.end("404 Not Found");
    } else {
      res.writeHead(500);
      res.end("500 Internal Error");
    }
  }
});

server.listen(PORT, () => console.log(`AWS Sentinel dev server running at http://localhost:${PORT}`));
