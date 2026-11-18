import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src/prototype/", import.meta.url));
const archive = fileURLToPath(new URL("../../docs/experiments/", import.meta.url));
const port = Number(process.env.PORT || 4178);

const contentTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png"
};

function resolveRequestPath(url) {
  const pathname = decodeURIComponent(new URL(url, `http://127.0.0.1:${port}`).pathname);
  if (pathname === "/evaluation-data/index.json") return resolve(archive, "evaluations.json");
  if (pathname.startsWith("/evaluation-data/")) {
    const asset = pathname.slice("/evaluation-data/".length);
    return /^evaluation-[a-z0-9-]+\/evidence\/(?:metadata\.json|[A-Z]+-\d+\/(?:initial\.json|result\.json|before\.png|shot-\d+\.png))$/.test(asset)
      ? resolve(archive, asset)
      : null;
  }
  const file = resolve(root, "." + (pathname === "/" ? "/index.html" : pathname));
  const rel = relative(root, file);
  return rel && rel !== ".." && !rel.startsWith(".." + sep) && !isAbsolute(rel) ? file : null;
}

const server = createServer(async (request, response) => {
  let filePath;
  try { filePath = resolveRequestPath(request.url || "/"); }
  catch { filePath = null; }

  if (!filePath) {
    response.writeHead(403, { "content-type": "text/plain; charset=utf-8" });
    response.end("Forbidden");
    return;
  }

  try {
    const body = await readFile(filePath);
    response.writeHead(200, {
      "cache-control": "no-store",
      "content-type": contentTypes[extname(filePath)] || "application/octet-stream"
    });
    response.end(body);
  } catch {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not Found");
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(`VoiceCanvas prototype: http://127.0.0.1:${port}/index.html`);
});
