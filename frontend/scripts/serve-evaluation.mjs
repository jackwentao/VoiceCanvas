import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src/evaluation/", import.meta.url));
const archive = fileURLToPath(new URL("../../docs/experiments/", import.meta.url));
const port = Number(process.env.VOICECANVAS_EVALUATION_PORT || 4180);
const contentTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
};

function assetFor(pathname) {
  if (pathname === "/") return resolve(root, "evaluation.html");
  if (/^\/evaluation(?:\.html|\.css|(?:-data)?\.js)$/.test(pathname)) {
    return resolve(root, pathname.slice(1));
  }
  if (pathname === "/evaluation-data/index.json") return resolve(archive, "evaluations.json");
  const prefix = "/evaluation-data/";
  if (!pathname.startsWith(prefix)) return null;
  const asset = pathname.slice(prefix.length);
  return /^evaluation-[a-z0-9-]+\/evidence\/(?:metadata\.json|[A-Z]+-\d+\/(?:initial\.json|result\.json|judge\.json|before\.png|shot-\d+\.png))$/.test(asset)
    ? resolve(archive, asset)
    : null;
}

createServer(async (request, response) => {
  if (request.method !== "GET" && request.method !== "HEAD") {
    response.writeHead(405, { Allow: "GET, HEAD" }).end();
    return;
  }
  try {
    const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
    const file = assetFor(pathname);
    if (file) {
      const body = await readFile(file);
      response.writeHead(200, {
        "content-type": contentTypes[extname(file)],
        "cache-control": "no-store",
      }).end(request.method === "HEAD" ? undefined : body);
      return;
    }
  } catch (error) {
    if (error.code !== "ENOENT" && !(error instanceof URIError)) {
      response.writeHead(500).end();
      return;
    }
  }
  response.writeHead(404).end();
}).listen(port, "127.0.0.1", () => {
  console.log(`VoiceCanvas 评测台 · http://127.0.0.1:${port}/`);
});
