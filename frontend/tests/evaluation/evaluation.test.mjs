import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { comparisonMismatch, countStatus, median, toolSteps, verdict } from "../../src/prototype/evaluation-data.js";

const archive = new URL("../../../docs/experiments/", import.meta.url);
const readJson = async path => JSON.parse(await readFile(new URL(path, archive), "utf8"));
const { batches } = await readJson("evaluations.json");
const first = batches.find(batch => batch.id === "evaluation-pilot-20261118");
const batchPath = `${first.id}/evidence`;
const meta = await readJson(`${batchPath}/metadata.json`);
const entries = await Promise.all(first.cases.map(async entry => ({
  ...entry,
  initial: await readJson(`${batchPath}/${entry.id}/initial.json`),
  result: await readJson(`${batchPath}/${entry.id}/result.json`),
})));

test("汇总指标与首轮证据一致，工具选择和执行结果独立计数", async () => {
  assert.deepEqual(entries.map(entry => verdict(entry.criteria)), ["fail", "fail"]);
  assert.equal(verdict([]), "review");
  assert.equal(verdict([{ status: "review" }]), "review");
  assert.equal(verdict([{ status: "pass" }]), "pass");
  const steps = entries.flatMap(toolSteps);
  assert.deepEqual(countStatus(steps.map(step => step.decision), "pass"), { passed: 16, total: 17, pending: 0 });
  assert.deepEqual(countStatus(steps.map(step => step.status), "succeeded"), { passed: 15, total: 17, pending: 0 });
  assert.equal(steps[8].status, "failed");
  assert.equal(steps[8].decision, "pass");
  assert.match(steps[9].note, /预算/);
  assert.equal(median(entries.map(entry => entry.result.timing.wallSeconds)).toFixed(1), "174.8");
  assert.equal(median([undefined, null, 0]), 0);
  for (const entry of entries) {
    const files = entry.result.board.shots.map((_, index) => `shot-0${index + 1}.png`);
    if (entry.beforeImage) files.push(entry.beforeImage);
    for (const name of files) {
      const png = await readFile(new URL(`${batchPath}/${entry.id}/${name}`, archive));
      assert.equal(png.toString("ascii", 1, 4), "PNG");
    }
  }
});

test("只对照同一需求、起点及口径，项目 ID 可因复跑而改变", () => {
  const batch = { ...first, meta };
  const previous = structuredClone(entries[1]);
  const current = entries[1];
  previous.initial.activeId = "new-shot-id";
  previous.initial.shots[0].id = "new-shot-id";
  assert.equal(comparisonMismatch(batch, current, batch, previous), "");
  assert.match(comparisonMismatch(batch, current, { ...batch, rubricVersion: "v2" }, previous), /验收标准/);
  assert.match(comparisonMismatch(batch, current, { ...batch, meta: { ...meta, model: "different" } }, previous), /模型/);
  previous.initial.shots[0].svg = "<svg/>";
  assert.match(comparisonMismatch(batch, current, batch, previous), /起始状态/);
  assert.match(comparisonMismatch(batch, current, batch, undefined), /没有此用例/);
});
