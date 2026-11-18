import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { CaseError, createCaseStore } from "./evaluation-cases.mjs";

const root = fileURLToPath(new URL("../src/evaluation/", import.meta.url));
const archive = fileURLToPath(new URL("../../docs/experiments/", import.meta.url));
const port = Number(process.env.VOICECANVAS_EVALUATION_PORT || 4180);
const caseDirectory = process.env.VOICECANVAS_EVALUATION_CASE_DIR ||
  fileURLToPath(new URL("../../backend/evaluation/cases/", import.meta.url));
const cases = createCaseStore(caseDirectory);
const contentTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
};

function assetFor(pathname) {
  if (pathname === "/") return resolve(root, "evaluation.html");
  if (/^\/(?:evaluation(?:\.html|\.css|(?:-data)?\.js)|cases\.(?:html|css|js))$/.test(pathname)) {
    return resolve(root, pathname.slice(1));
  }
  if (pathname === "/evaluation-data/index.json") return resolve(archive, "evaluations.json");
  const prefix = "/evaluation-data/";
  if (!pathname.startsWith(prefix)) return null;
  const asset = pathname.slice(prefix.length);
  return /^evaluation-[a-z0-9-]+\/evidence\/(?:metadata\.json|[A-Z]+-\d+\/(?:case\.json|initial\.json|result\.json|judge\.json|before\.png|shot-\d+\.png))$/.test(asset)
    ? resolve(archive, asset)
    : null;
}

function sendJson(response, status, body) {
  response.writeHead(status, {
    "content-type": contentTypes[".json"], "cache-control": "no-store",
  }).end(JSON.stringify(body));
}

async function readCaseBody(request) {
  const host = request.headers.host ?? "";
  if (!/^(?:127\.0\.0\.1|localhost)(?::\d+)?$/.test(host) ||
      (request.headers.origin && request.headers.origin !== `http://${host}`)) {
    throw new CaseError(403, "只能从本地评测台保存用例。");
  }
  if (request.headers["content-type"]?.split(";")[0] !== "application/json") {
    throw new CaseError(415, "用例请求必须使用 JSON。");
  }
  let size = 0;
  const chunks = [];
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 2_000_000) throw new CaseError(413, "用例数据过大。");
    chunks.push(chunk);
  }
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8")); }
  catch { throw new CaseError(400, "用例 JSON 无法解析。"); }
}

async function serveCases(request, response, id) {
  if (request.method === "GET") {
    const body = id ? await cases.read(id) : { cases: (await cases.list()).map(
      ({ id, title, kind, revision, status }) => ({ id, title, kind, revision, status }),
    ) };
    sendJson(response, 200, body);
  } else if (request.method === (id ? "PUT" : "POST")) {
    const saved = await cases.save(await readCaseBody(request), id);
    sendJson(response, id ? 200 : 201, saved);
  } else {
    response.writeHead(405, { Allow: id ? "GET, PUT" : "GET, POST" }).end();
  }
}

createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
    const caseRoute = /^\/api\/evaluation-cases(?:\/(VC-\d{2,8}))?$/.exec(pathname);
    if (caseRoute) {
      await serveCases(request, response, caseRoute[1]);
      return;
    }
    if (request.method !== "GET" && request.method !== "HEAD") {
      response.writeHead(405, { Allow: "GET, HEAD" }).end();
      return;
    }
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
    if (error instanceof CaseError) {
      sendJson(response, error.status, { error: error.message });
      return;
    }
    if (error.code !== "ENOENT" && !(error instanceof URIError)) {
      sendJson(response, 500, { error: "评测服务读取或保存失败。" });
      return;
    }
  }
  response.writeHead(404).end();
}).listen(port, "127.0.0.1", () => {
  console.log(`VoiceCanvas 评测台 · http://127.0.0.1:${port}/`);
});
