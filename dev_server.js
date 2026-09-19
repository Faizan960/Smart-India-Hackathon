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
  if (req.url.startsWith("/api/weather/current")) {
    // Emulate Vercel function
    req.query = Object.fromEntries(new URLSearchParams(req.url.split("?")[1]));
    const handler = require("./api/weather/current.js");
    return handler(req, res);
  }

  // Static file serving
  let filePath = "." + req.url.split("?")[0];
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

server.listen(PORT, () => console.log(`Test server running on port ${PORT}`));
