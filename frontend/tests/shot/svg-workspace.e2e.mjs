// 需要现有 Playwright 和 Edge/Chromium；不安装依赖，不访问在线绘图模型。
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir } from "node:fs/promises";

const require = createRequire(process.env.VOICECANVAS_PLAYWRIGHT_PACKAGE || import.meta.url);
const { chromium } = require("playwright");
const browser = await chromium.launch({ headless: true,
  ...(process.env.VOICECANVAS_BROWSER_PATH ? { executablePath: process.env.VOICECANVAS_BROWSER_PATH } : {}) });
const ui = process.env.VOICECANVAS_E2E_UI_URL || "http://127.0.0.1:4178";
const api = process.env.VOICECANVAS_E2E_API_URL || "http://127.0.0.1:8015";
const out = process.env.VOICECANVAS_E2E_OUTPUT;
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
page.setDefaultTimeout(8000);
const errors = [], requests = [];
page.on("pageerror", e => errors.push(e.message));
page.on("request", r => { if (r.method() === "POST") requests.push(r.url()); });
await page.addInitScript(() => {
  // 只替换 ASR/TTS 边界，产品语音控制器与请求实际执行。
  window.SpeechRecognition = class {
    constructor() { window.__recognition = this; }
    start() { window.__listening = true; }
    stop() { window.__listening = false; this.onend?.(); }
    abort() { this.stop(); }
  };
  window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
  Object.defineProperty(window, "speechSynthesis", { value: { cancel() {}, speak(u) { setTimeout(() => u.onend?.(), 0); } } });
  window.AudioContext = undefined; window.webkitAudioContext = undefined;
});
const waitIdle = () => page.waitForFunction(() => document.querySelector("#saveStatus").dataset.busy === "false");
const count = async n => page.waitForFunction(n => document.querySelectorAll("[data-scene]").length === n, n);
const submit = async text => {
  await page.locator("#voiceInput").fill(text);
  await page.locator("#composerForm").evaluate(f => f.requestSubmit()); await waitIdle();
  assert.equal(await page.locator("#errorBanner").isVisible(), false, await page.locator("#errorText").textContent());
};
try {
  await page.goto(`${ui}/index.html?apiBaseUrl=${encodeURIComponent(api)}`);
  await page.locator("[data-create]").first().click();
  await page.waitForURL(/workspace.html.*board=/); await count(1);
  assert.ok(requests.some(url => url.endsWith("/api/storyboards")));
  assert.equal(requests.some(url => /\/api\/projects$/.test(url)), false);
  await submit("新建两个镜头"); await count(3);
  await submit("切换到第一个镜头"); await submit("画一个雨夜镜头");
  await page.locator("#canvasSurface img").waitFor();
  await page.locator("#editTextToggle").click();
  await page.locator("#textContent").fill("我到家了。");
  await page.waitForFunction(() => !document.querySelector("#applyTextEdit").disabled);
  assert.equal(await page.locator("#exportButton").isDisabled(), true);
  await page.locator("#addSvgScene").click();
  assert.match(await page.locator("#errorText").textContent(), /先应用/); await count(3);
  await page.locator("#applyTextEdit").click(); await waitIdle();
  assert.match(await page.locator("#resultMessage").textContent(), /文字已保存/);
  await page.locator("#closeTextEditor").click();
  assert.equal(await page.locator("#exportButton").isDisabled(), false);
  await page.locator("#copySvgScene").click(); await count(4); await waitIdle();
  await submit("把第二个镜头移到第一位");
  await page.locator("#deleteSvgScene").click(); await waitIdle(); await count(4);
  await page.locator('[data-delete-answer="确认删除"]').click(); await count(3); await waitIdle();
  await page.locator("#undoStructure").click(); await count(4); await waitIdle();
  await page.locator("#voiceButton").click(); await page.waitForFunction(() => window.__listening);
  await page.evaluate(() => window.__recognition.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: "切换到第二个镜头" }], { isFinal: true })] }));
  await page.waitForFunction(() => window.__listening && document.querySelector("#sceneDescription").textContent.startsWith("2 /"));
  await page.locator("#voiceButton").click();
  const savedUrl = page.url(); await page.reload(); await count(4);
  assert.equal(page.url(), savedUrl);
  await page.locator("#exportButton").click();
  const downloaded = page.waitForEvent("download"); await page.locator('[data-export="png"]').click();
  const download = await downloaded; assert.equal(await download.failure(), null); assert.match(download.suggestedFilename(), /\.png$/);
  if (out) { await mkdir(out, { recursive: true }); await page.screenshot({ path: `${out}/desktop.png`, fullPage: true }); }
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
  const frame = await page.locator("#canvasStage").boundingBox(); assert.ok(Math.abs(frame.width / frame.height - 16 / 9) < 0.02);
  if (out) await page.screenshot({ path: `${out}/mobile.png`, fullPage: true });
  await page.setViewportSize({ width: 1500, height: 1000 });
  const before = requests.length;
  await page.goto(`${ui}/index.html?apiBaseUrl=${encodeURIComponent(api)}&projectId=project_demo_voicecanvas`);
  await page.locator("[data-create]").first().waitFor();
  assert.equal(new URL(page.url()).pathname, "/index.html");
  assert.equal(requests.length, before, "首页不应因旧参数创建或迁移项目");
  await page.goto(`${ui}/workspace.html?apiBaseUrl=${encodeURIComponent(api)}&projectId=project_demo_voicecanvas`);
  await count(4);
  assert.equal(await page.locator("body").evaluate(e => e.classList.contains("svg-workspace")), true);
  assert.equal(new URL(page.url()).searchParams.has("projectId"), false);
  for (const selector of ["#importButton", "#memoryDialog", "#backgroundColorInput"]) assert.equal(await page.locator(selector).count(), 0);
  assert.equal((await page.request.get(`${ui}/shot.html`)).status(), 404);
  assert.deepEqual(errors, []);
  console.log("工作台 E2E 通过：首页API、分镜、改字、语音、导出、恢复、窄屏；无旧入口分流。");
} finally { await browser.close(); }
