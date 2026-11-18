import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(process.env.VOICECANVAS_PLAYWRIGHT_PACKAGE || import.meta.url);
const { chromium } = require("playwright");
const browser = await chromium.launch({
  headless: true,
  ...(process.env.VOICECANVAS_BROWSER_PATH ? { executablePath: process.env.VOICECANVAS_BROWSER_PATH } : {}),
});
const ui = process.env.VOICECANVAS_E2E_UI_URL || "http://127.0.0.1:4178";
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", error => errors.push(error.message));

try {
  await page.goto(`${ui}/evaluation.html`);
  await page.locator("#dashboard").waitFor();
  assert.match(await page.locator("#metrics").innerText(), /16 \/ 17/);
  assert.match(await page.locator("#metrics").innerText(), /15 \/ 17/);
  await page.waitForFunction(() => document.images.length === 3 && [...document.images].every(img => img.naturalWidth === 1280));
  if (process.env.VOICECANVAS_E2E_OUTPUT) {
    await page.screenshot({ path: `${process.env.VOICECANVAS_E2E_OUTPUT}/evaluation-desktop.png`, fullPage: true });
  }
  const png = await page.request.get(await page.locator("figure a").first().getAttribute("href").then(path => new URL(path, ui).href));
  assert.equal(png.headers()["content-type"], "image/png");

  await page.getByRole("button", { name: "耗时与轨迹" }).click();
  await page.getByRole("checkbox", { name: "只看异常" }).check();
  assert.equal(await page.locator(".step-list details").count(), 2);
  await page.locator(".step-list summary").last().click();
  assert.match(await page.locator(".step-list details").last().innerText(), /绘图预算/);

  await page.getByRole("button", { name: /VC-02/ }).click();
  await page.getByRole("button", { name: "验收判据" }).click();
  assert.match(await page.locator("#case-detail").innerText(), /保留项/);
  await page.getByRole("button", { name: "产出与对照" }).click();
  await page.waitForFunction(() => document.images.length === 2 && [...document.images].every(img => img.naturalWidth === 1280));
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
  const image = await page.locator("figure img").first().boundingBox();
  assert.ok(Math.abs(image.width / image.height - 16 / 9) < 0.03);
  if (process.env.VOICECANVAS_E2E_OUTPUT) {
    await page.screenshot({ path: `${process.env.VOICECANVAS_E2E_OUTPUT}/evaluation-mobile.png`, fullPage: true });
  }
  await page.locator("#case-filter").selectOption("pass");
  assert.match(await page.locator("#case-list").innerText(), /没有符合条件/);
  await page.locator("#case-filter").selectOption("all");

  // 第二批仅在浏览器内使用，保留原始归档可复核。
  const originalId = "evaluation-pilot-20261118";
  const baselineId = "evaluation-comparison-fixture";
  await page.route("**/evaluation-data/index.json", async route => {
    const response = await route.fetch();
    const index = await response.json();
    const baseline = structuredClone(index.batches[0]);
    baseline.id = baselineId;
    baseline.label = "对照测试批次";
    baseline.cases[0].criteria[2].status = "pass";
    index.batches.push(baseline);
    await route.fulfill({ response, json: index });
  });
  await page.route(`**/evaluation-data/${baselineId}/**`, route =>
    route.continue({ url: route.request().url().replace(baselineId, originalId) }));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${ui}/evaluation.html?case=VC-01&compare=${baselineId}`);
  await page.getByRole("heading", { name: "与「对照测试批次」对照" }).waitFor();
  assert.match(await page.locator("#case-detail table").innerText(), /V1/);
  assert.deepEqual(errors, []);
  console.log("评测台浏览器验证通过。");
} finally {
  await browser.close();
}
