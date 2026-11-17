import assert from "node:assert/strict";
import { test } from "node:test";
import { ShotClient } from "../../src/prototype/shot-client.js";
import { StoryboardClient } from "../../src/prototype/storyboard-client.js";
import { VoiceSessionController } from "../../src/prototype/voice-session.js";
import { visualFeedback } from "../../src/prototype/shot-visual-feedback.js";

const response = (value, status = 200) => ({ ok: status < 400, status, json: async () => value });
const board = (version = 0, activeId = "a") => ({ id: "board_a", version, title: "故事", activeId,
  shots: [{ id: "a", title: "开场", version: 1, svg: "saved" }, { id: "b", title: "相遇", version: 0 }],
  activeShot: { id: activeId, version: activeId === "a" ? 1 : 0, svg: "saved SVG", revisions: [] } });
const reply = (status = "completed", extra = {}, current = board()) => response({ board: current,
  run: { id: "run_one", status, summary: "已处理相遇镜头", steps: [], clientActions: [], ...extra } });

function setup(answers) {
  const requests = [], exports = [], changes = [];
  const shots = new ShotClient({ baseUrl: "https://api.test" });
  const client = new StoryboardClient({ shots, pause: async () => {},
    exportShot: async (format, sid) => exports.push([format, sid]),
    onChange: c => changes.push(c.agent?.status),
    fetchImpl: async (url, options) => {
      requests.push({ url, method: options.method, body: options.body && JSON.parse(options.body) });
      const answer = answers.shift();
      assert.ok(answer, `未预期请求：${url}`);
      return typeof answer === "function" ? answer() : answer;
    },
  });
  client.accept(board());
  return { client, shots, requests, exports, changes };
}

test("完整复合需求原文交给Agent，逐次接受真实进展，不走命令路由", async () => {
  const { client, requests, changes } = setup([reply("running"), reply("running", {}, board(1)), reply("completed", {}, board(2, "b"))]);
  const request = "15秒三个镜头，雨中进店、递咖啡、优惠特写，请全部画好";
  assert.match(await client.execute(request), /已处理/);
  assert.deepEqual(requests[0].body, { request, expectedVersion: 0 });
  assert.match(requests[0].url, /\/agent\/runs$/);
  assert.deepEqual(requests.map(r => r.method), ["POST", "GET", "GET"]);
  assert.equal(requests.some(r => r.url.endsWith("/command")), false);
  assert.equal(client.shots.shot.id, "b");
  assert.ok(changes.includes("running"));
});

test("刷新恢复原任务，只查询不重放付费请求或历史下载", async () => {
  const { client, requests, exports } = setup([
    reply("running"), reply("completed", { clientActions: [{ shotId: "a", format: "svg" }] }),
  ]);
  await client.load("board_a");
  assert.equal(requests.every(r => r.method === "GET"), true);
  assert.deepEqual(exports, []);
  assert.equal(client.busy, false);
});

test("删除确认从持久化任务恢复，确认仍提交给Agent", async () => {
  const { client, requests } = setup([
    reply("needs_input", { pendingDelete: { shotId: "a", version: 0 } }), reply(),
  ]);
  await client.execute("删除第一个镜头");
  assert.equal(client.pendingDelete.targetId, "a");
  await client.confirmDelete();
  assert.equal(requests[1].body.request, "确认删除");
  assert.equal(client.pendingDelete, null);
  assert.equal(requests.some(r => r.url.endsWith("/manage")), false);
});

test("按稳定镜头id导出整组，同轮重复动作只发起一次", async () => {
  const { client, exports } = setup([reply("completed", { clientActions: [
    { shotId: "a", format: "svg" }, { shotId: "b", format: "png" }, { shotId: "a", format: "svg" },
  ] })]);
  assert.match(await client.execute("全部导出"), /2 个文件/);
  assert.deepEqual(exports, [["svg", "a"], ["png", "b"]]);
});

test("409同步项目，不重试任务", async () => {
  const { client, requests, shots } = setup([response({ detail: "分镜冲突" }, 409), response(board(3, "b"))]);
  await assert.rejects(client.execute("新建镜头"), /分镜冲突/);
  assert.equal(client.board.version, 3);
  assert.equal(shots.shot.id, "b");
  assert.deepEqual(requests.map(r => r.method), ["POST", "GET"]);
});

test("执行时拒绝重复请求，轮询失败后不重复POST，手动刷新继续查询", async () => {
  let fail;
  const { client, requests } = setup([reply("running"), () => new Promise((_, reject) => { fail = reject; }), reply()]);
  const pending = client.execute("完整故事");
  while (!fail) await new Promise(resolve => setImmediate(resolve));
  await assert.rejects(client.manage({ action: "add" }), /上一条/);
  fail(new TypeError("network"));
  await assert.rejects(pending, /network/);
  await client.refresh();
  assert.equal(client.busy, false);
  assert.equal(requests.filter(r => r.method === "POST").length, 1);
});

test("后端失败传播真实错误并保留画面，文字预览阻止任何提交", async () => {
  const { client, requests } = setup([reply("failed", { summary: "模型连接中断" })]);
  await assert.rejects(client.execute("改画"), /连接中断/);
  assert.equal(client.shots.shot.svg, "saved SVG");
  await assert.rejects(client.execute("改画", { allowDrawing: false }), /文字预览/);
  assert.equal(requests.length, 1);
});

test("语音最终转写走同一Agent，完成后恢复监听", async () => {
  let handlers, starts = 0;
  const spoken = [];
  const { client, requests } = setup([reply("completed", {}, board(1, "b"))]);
  const session = new VoiceSessionController({
    recognition: { isSupported: () => true, start: h => { handlers = h; starts++; }, stop() {}, abort() {} },
    feedback: { say: async text => spoken.push(text), playReadyTone: async () => {} },
    submitTranscript: text => client.execute(text),
  });
  await session.start();
  assert.ok(handlers.onFinal);
  await session.handleFinalTranscript("切换到第二镜然后改名相遇");
  assert.equal(client.board.activeId, "b");
  assert.ok(starts >= 2 && session.isListening());
  assert.equal(requests[0].body.request, "切换到第二镜然后改名相遇");
  assert.ok(spoken.some(s => s.includes("相遇")));
  await session.stop({ speak: false });
});

test("视觉记录绑定版本，旧评审不套用到新画面，也不把源码当成视觉评审", () => {
  const steps = [
    { call: { name: "review_shot" }, status: "succeeded", result: { shotId: "a", shotVersion: 1, previewUrl: "/image.png", review: "手离杯柄很远" } },
    { call: { name: "inspect_shot" }, status: "succeeded", result: { shotId: "a", svg: "<svg/>" } },
    { call: { name: "review_shot" }, status: "failed", result: { error: "不可用" } },
  ];
  const current = visualFeedback(board(), { steps });
  assert.equal(current.length, 1);
  assert.equal(current[0].current, true);
  assert.equal(current[0].previewUrl, "/image.png");
  const changed = board(); changed.shots[0].version = 2;
  const stale = visualFeedback(changed, { steps })[0];
  assert.equal(stale.current, false);
  assert.equal(stale.previewUrl, null);
  assert.match(stale.review, /离杯柄/);
});
