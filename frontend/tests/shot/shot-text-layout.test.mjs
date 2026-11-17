import assert from "node:assert/strict";
import { test } from "node:test";
import { centeredBaseline, chooseTextContainer, overlaps, recommendedTextSize,
  textReadability, textScale, wrapShotText } from "../../src/prototype/shot-text-layout.js";

const measure = text => Array.from(text).length * 10;

test("中文换行保留原字与标点，闭标点不落行首", () => {
  const content = "今天下雨了，我们一起回家。";
  const lines = wrapShotText(content, 50, measure);
  assert.equal(lines.join(""), content);
  assert.ok(lines.every(line => measure(line) <= 50));
  assert.ok(lines.every(line => !/^[，。]/.test(line)));
});

test("显式空行和英文空格保留，组合字符不被拆开", () => {
  const lines = wrapShotText("We go home.\n\n明天见👩‍👧！", 70, measure);
  assert.ok(lines.includes(""));
  assert.equal(lines.join("").replaceAll("\n", ""), "We go home.明天见👩‍👧！");
  assert.ok(lines.some(line => line.includes("👩‍👧")));
});

test("无法容纳单字和非法宽度明确失败", () => {
  assert.throws(() => wrapShotText("大", 5, measure), /容不下/);
  assert.throws(() => wrapShotText("字", NaN, measure), /有效/);
});

test("按实际预览和变换评估字号，不把源字号当显示字号", () => {
  assert.equal(textReadability(16, 1, 640).preview, 8);
  assert.match(textReadability(16, 1, 640).warning, /阅读偏小/);
  assert.equal(textReadability(16, 2, 640).warning, "");
});

test("放大建议只增加字号，保留已经清楚的文字大小", () => {
  assert.equal(recommendedTextSize(32, 1, 1038), 32);
  assert.equal(recommendedTextSize(16, 1, 640), 28);
  assert.equal(recommendedTextSize(16, 1, 320), 56);
});

test("非等比缩放按字高方向评估可读性", () => {
  assert.equal(textScale({ a: 2, b: 0, c: 0, d: 3 }), 3);
});

test("背景矩形不被误当文字气泡，文字保持原来的垂直位置", () => {
  const title = { x: 30, y: 25, right: 160, bottom: 50 };
  const background = { x: 0, y: 0, right: 1280, bottom: 720 };
  assert.equal(chooseTextContainer([background], title, 20), undefined);
  assert.equal(centeredBaseline(50, title, title), 50);
  const longer = { x: 30, y: 25, right: 160, bottom: 80 };
  assert.equal(centeredBaseline(50, title, longer), 35);
});

test("选择包住文字的最小合理底板，不选无关矩形", () => {
  const text = { x: 100, y: 100, right: 300, bottom: 140 };
  const bubble = { x: 80, y: 80, right: 340, bottom: 160 };
  const background = { x: 0, y: 0, right: 1280, bottom: 720 };
  assert.deepEqual(chooseTextContainer([background, bubble], text, 32), bubble);
});

test("只有实际相交才报文字碰撞，接触和微小包围盒余量忽略", () => {
  const a = { x: 0, y: 0, right: 100, bottom: 20 };
  assert.equal(overlaps(a, { x: 10, y: 10, right: 40, bottom: 50 }), true);
  assert.equal(overlaps(a, { x: 100, y: 0, right: 120, bottom: 20 }), false);
  assert.equal(overlaps(a, { x: 99, y: 0, right: 120, bottom: 20 }), false);
});
