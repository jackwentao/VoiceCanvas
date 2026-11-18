// 需要现有 Playwright 和 Edge/Chromium；不安装依赖，不访问在线绘图模型。
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, readFile } from "node:fs/promises";

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
  const originalBoard = new URL(page.url()).searchParams.get("board");
  const otherBoard = await (await page.request.post(`${api}/api/storyboards`, {
    data: { title: "另一个分镜项目" },
  })).json();
  await page.reload();
  await page.locator("#projectSelect").locator(`option[value="${otherBoard.id}"]`).waitFor({ state: "attached" });
  await waitIdle();
  await page.locator("#voiceInput").fill("当前项目的指令草稿");
  await page.locator("#projectSelect").selectOption(otherBoard.id);
  await page.waitForURL(url => url.searchParams.get("board") === otherBoard.id);
  await waitIdle();
  assert.equal(await page.locator("#renameButton").textContent(), otherBoard.title);
  assert.equal(await page.locator("#voiceInput").inputValue(), "");
  await page.locator("#projectSelect").selectOption(originalBoard);
  await page.waitForURL(url => url.searchParams.get("board") === originalBoard);
  await waitIdle();
  assert.equal(await page.locator("#voiceInput").inputValue(), "当前项目的指令草稿");

  const listUrl = `${api}/api/storyboards`;
  await page.route(listUrl, route => route.fulfill({ status: 503, json: { detail: "最近项目暂时读不到" } }));
  await submit("新建两个镜头"); await count(3);
  assert.equal(await page.locator("#voiceInput").inputValue(), "");
  assert.match(await page.locator("#toast").textContent(), /项目列表暂时无法更新/);
  await page.unroute(listUrl);

  const manageUrl = `${listUrl}/${originalBoard}/manage`;
  await page.route(manageUrl, route => route.fulfill({ status: 503, json: { detail: "保存失败，请重试" } }));
  await page.locator("#renameButton").click();
  await page.locator("#nameInput").fill("雨夜分镜");
  await page.locator("#nameSubmit").click();
  await page.locator("#nameError").waitFor({ state: "visible" });
  assert.equal(await page.locator("#nameError").textContent(), "保存失败，请重试");
  assert.equal(await page.locator("#nameInput").inputValue(), "雨夜分镜");
  assert.equal(await page.locator("#errorBanner").isVisible(), false);
  await page.unroute(manageUrl);
  await page.locator("#nameSubmit").click();
  await page.locator("#nameDialog").waitFor({ state: "hidden" });
  assert.equal(await page.locator("#renameButton").textContent(), "雨夜分镜");

  await submit("切换到第一个镜头"); await submit("画一个雨夜镜头");
  await page.locator("#canvasSurface img").waitFor();
  await page.locator("#editTextToggle").click();
  await page.locator("#textContent").fill("我到家了。");
  await page.waitForFunction(() => !document.querySelector("#applyTextEdit").disabled);
  const textTarget = page.locator("#textTarget");
  const initialText = await textTarget.inputValue();
  const secondText = await textTarget.locator("option").nth(1).getAttribute("value");
  await textTarget.selectOption(secondText);
  assert.equal(await textTarget.inputValue(), initialText);
  assert.equal(await page.locator("#textContent").inputValue(), "我到家了。");
  for (const size of [{ width: 390, height: 844 }, { width: 1500, height: 1000 }]) {
    await page.setViewportSize(size);
    assert.equal(await page.locator("#textContent").inputValue(), "我到家了。");
    await page.locator("#applyTextEdit").click({ trial: true });
    const layout = await page.evaluate(() => {
      const stage = document.querySelector("#canvasStage").getBoundingClientRect();
      const panel = document.querySelector("#textEditor").getBoundingClientRect();
      const input = document.querySelector("#textContent").getBoundingClientRect();
      const saveButton = document.querySelector("#applyTextEdit");
      const save = saveButton.getBoundingClientRect();
      return {
        separated: stage.right <= panel.left + 1 || stage.bottom <= panel.top + 1,
        previewVisible: stage.width > 120 && stage.height > 60,
        inputBeforeSave: input.top >= panel.top && input.bottom <= save.top,
      };
    });
    if (out) {
      await mkdir(out, { recursive: true });
      await page.screenshot({ path: `${out}/text-draft-${size.width}.png` });
    }
    assert.ok(layout.separated && layout.previewVisible && layout.inputBeforeSave,
      `改字草稿、预览和应用按钮应在 ${size.width}px 下同时排列：${JSON.stringify(layout)}`);
  }
  await page.locator("#textFontSize").fill("1");
  assert.equal(await page.locator("#applyTextEdit").isDisabled(), true);
  assert.equal(await page.locator("#exportButton").isDisabled(), true);
  await page.locator("#addSvgScene").click();
  assert.match(await page.locator("#errorText").textContent(), /先应用/); await count(3);
  await page.locator("#textFontSize").fill("48");
  await page.waitForFunction(() => !document.querySelector("#applyTextEdit").disabled);
  await page.locator("#applyTextEdit").click(); await waitIdle();
  assert.match(await page.locator("#resultMessage").textContent(), /文字已保存/);
  await page.locator("#closeTextEditor").click();
  assert.equal(await page.locator("#exportButton").isDisabled(), false);
  await page.locator("#copySvgScene").click(); await count(4); await waitIdle();
  await submit("把第二个镜头移到第一位");
  const agentUrl = `${listUrl}/${originalBoard}/agent/runs`;
  await page.route(agentUrl, route => route.fulfill({ status: 503, json: { detail: "模型服务暂不可用" } }));
  const requestsBeforeDelete = requests.length;
  page.once("dialog", dialog => dialog.dismiss());
  await page.locator("#deleteSvgScene").click(); await waitIdle(); await count(4);
  assert.equal(requests.length, requestsBeforeDelete);
  page.once("dialog", async dialog => {
    assert.match(dialog.message(), /删除镜头/);
    await dialog.accept();
  });
  await page.locator("#deleteSvgScene").click(); await waitIdle(); await count(3);
  assert.deepEqual(requests.slice(requestsBeforeDelete), [manageUrl]);
  await page.unroute(agentUrl);
  await page.locator("#undoStructure").click(); await count(4); await waitIdle();
  await submit("删除当前镜头"); await count(4);
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
  await page.locator("#exportButton").click();
  const svgDownload = page.waitForEvent("download");
  await page.locator('[data-export="svg"]').click();
  const svg = await svgDownload;
  const chooser = page.waitForEvent("filechooser");
  await page.locator("#importSvgButton").click();
  await (await chooser).setFiles({
    name: "导回的镜头.svg", mimeType: "image/svg+xml", buffer: await readFile(await svg.path()),
  });
  await count(5);
  await waitIdle();
  assert.equal(await page.locator("#sceneName").textContent(), "导回的镜头");
  await page.locator("#editTextToggle").click();
  assert.ok(await page.locator("#textContent").inputValue());
  await page.locator("#closeTextEditor").click();
  await page.locator("#undoStructure").click();
  await count(4);
  await waitIdle();
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

  const missingId = "board_e2e_missing";
  await page.goto(`${ui}/workspace.html?apiBaseUrl=${encodeURIComponent(api)}&board=${missingId}`);
  await page.getByRole("button", { name: "打开可用项目" }).click();
  await page.waitForURL(url => url.searchParams.has("board") && url.searchParams.get("board") !== missingId);
  await waitIdle();
  assert.equal(await page.locator("#errorBanner").isVisible(), false);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${ui}/workspace.html?apiBaseUrl=${encodeURIComponent(api)}&board=${otherBoard.id}`);
  await waitIdle();
  const prompts = page.locator("[data-prompt]");
  assert.equal(await prompts.nth(0).isVisible(), true);
  assert.equal(await prompts.nth(1).isVisible(), true);
  await prompts.nth(1).click();
  assert.match(await page.locator("#voiceInput").inputValue(), /雨夜便利店/);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
  if (out) await page.screenshot({ path: `${out}/mobile-empty.png`, fullPage: true });

  assert.deepEqual(errors, []);
  console.log("工作台 E2E 通过：首页、项目切换、分镜管理、宽窄屏改字、语音、PNG 下载、SVG 导出与导入、失效链接。");
} finally { await browser.close(); }
