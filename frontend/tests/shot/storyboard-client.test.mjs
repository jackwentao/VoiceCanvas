import assert from "node:assert/strict";
import { test } from "node:test";
import { ShotClient } from "../../src/prototype/shot-client.js";
import { StoryboardClient } from "../../src/prototype/storyboard-client.js";
import { VoiceSessionController } from "../../src/prototype/voice-session.js";

const response = (value, status = 200) => ({ ok: status < 400, status, json: async () => value });
const board = (version = 0, activeId = "a") => ({ id: "board_a", version, title: "故事", activeId,
  shots: [{ id: "a", title: "开场", version: 1 }, { id: "b", title: "相遇", version: 0 }],
  activeShot: { id: activeId, version: activeId === "a" ? 1 : 0, svg: "saved SVG", revisions: [] } });

function setup(answers, shotFetch = async () => response({ id: "b", version: 1, svg: "drawn", revisions: [] })) {
  const requests = [];
  const shots = new ShotClient({ baseUrl: "https://api.test", fetchImpl: shotFetch });
  const client = new StoryboardClient({ shots, fetchImpl: async (url, options) => {
    requests.push({ url, method: options.method, body: options.body && JSON.parse(options.body) });
    const answer = answers.shift();
    return typeof answer === "function" ? answer() : answer;
  } });
  client.accept(board());
  return { client, shots, requests };
}

test("删除转写只建立确认，确认绑定稳定id和版本", async () => {
  const next = { ...board(1, "b"), shots: [board().shots[1]] };
  const { client, requests } = setup([
    response({ board: board(), action: "request_delete", targetId: "a" }),
    response({ board: board(), action: "confirm" }), response(next),
  ]);
  assert.match(await client.execute("删除第一个镜头"), /确认删除/);
  assert.equal(requests.length, 1);
  assert.equal(client.pendingDelete.targetId, "a");
  await client.execute("确认删除");
  assert.deepEqual(requests[2].body, { action: "delete", targetId: "a", confirmed: true, expectedVersion: 0 });
  assert.equal(client.board.shots.length, 1);
  assert.equal(client.pendingDelete, null);
});

test("其他操作清除待删除确认，不能删除后来切到的镜头", async () => {
  const { client, requests } = setup([
    response({ board: board(), action: "request_delete", targetId: "a" }),
    response({ board: board(1, "b"), action: "switch" }),
    response({ board: board(1, "b"), action: "confirm" }),
  ]);
  await client.execute("删除当前镜头");
  await client.execute("切换到第二个镜头");
  await assert.rejects(client.execute("确认删除"), /没有有效/);
  assert.equal(requests.filter(r => r.url.endsWith('/manage')).length, 0);
});

test("409同步项目与当前画面，不重试管理或付费绘制", async () => {
  const { client, requests, shots } = setup([response({ detail: "分镜冲突" }, 409), response(board(3, "b"))]);
  await assert.rejects(client.execute("新建镜头"), /分镜冲突/);
  assert.equal(client.board.version, 3);
  assert.equal(shots.shot.id, "b");
  assert.deepEqual(requests.map(r => r.method), ["POST", "GET"]);
  assert.equal(client.busy, false);
});

test("指定镜头绘图先切换，再使用该镜头自己的版本提交", async () => {
  const draws = [];
  const { client, shots } = setup([
    response({ board: board(), action: "draw", targetId: "b", instruction: "画雨夜" }),
    response(board(1, "b")), response({ ...board(1, "b"), activeShot: { id: "b", version: 1, svg: "drawn" } }),
  ], async (url, options) => { draws.push({ url, body: JSON.parse(options.body) }); return response({ id: "b", version: 1, svg: "drawn" }); });
  await client.execute("第二个镜头画雨夜");
  assert.match(draws[0].url, /\/b\/generate$/);
  assert.equal(draws[0].body.expectedVersion, 0);
  assert.equal(shots.shot.svg, "drawn");
});

test("执行期间拒绝第二条请求，网络失败后保留旧项目", async () => {
  let fail;
  const { client, requests } = setup([() => new Promise((_, reject) => { fail = reject; })]);
  const pending = client.execute("新建镜头");
  await assert.rejects(client.manage({ action: "add" }), /上一条/);
  fail(new TypeError("network"));
  await assert.rejects(pending, /network/);
  assert.equal(client.board.version, 0);
  assert.equal(client.busy, false);
  assert.equal(requests.length, 1);
});

test("持续语音会话执行最终转写后恢复监听，播报期间不重复执行", async () => {
  let handlers;
  const spoken = [];
  let startCount = 0;
  const { client } = setup([response({ board: board(1, "b"), action: "switch" })]);
  const recognition = { isSupported: () => true, start: h => { handlers = h; startCount++; }, stop() {}, abort() {} };
  const session = new VoiceSessionController({ recognition,
    feedback: { say: async text => { spoken.push(text); }, playReadyTone: async () => {} },
    submitTranscript: text => client.execute(text),
  });
  await session.start();
  assert.ok(handlers.onFinal);
  await session.handleFinalTranscript("切换到第二个镜头");
  assert.equal(client.board.activeId, "b");
  assert.ok(startCount >= 2 && session.isListening());
  assert.ok(spoken.some(text => text.includes("相遇")));
  await session.stop({ speak: false });
});

test("麦克风权限拒绝后停止会话，不无限重启识别", async () => {
  let handlers;
  const session = new VoiceSessionController({ recognition: { isSupported: () => true, start: h => { handlers = h; }, stop() {}, abort() {} },
    feedback: { say: async () => {}, playReadyTone: async () => {} }, submitTranscript: async () => { throw new Error("不应执行"); } });
  await session.start();
  handlers.onError(new Error("not-allowed"));
  assert.equal(session.isActive(), false);
});

test("语音取消不提交删除，导出使用当前画面，新项目不覆盖旧项目", async () => {
  const next = { ...board(), id: "board_new", shots: [board().shots[0]] };
  const { client, requests } = setup([
    response({ board: board(), action: "request_delete", targetId: "b" }),
    response({ board: board(), action: "cancel" }),
    response({ board: board(), action: "export_svg" }),
    response({ board: board(), action: "export_png" }),
    response({ board: board(), action: "new_project" }), response(next),
  ]);
  const exports = [];
  client.exportShot = async format => exports.push([format, client.shots.shot.id]);
  await client.execute("删除第二个镜头");
  await client.execute("取消");
  assert.equal(client.pendingDelete, null);
  await client.execute("导出SVG");
  await client.execute("导出当前镜头");
  assert.deepEqual(exports, [["svg", "a"], ["png", "a"]]);
  await client.execute("新建分镜项目");
  assert.equal(client.board.id, "board_new");
  assert.equal(requests.filter(r => r.url.endsWith("/manage")).length, 0);
  assert.deepEqual(requests.at(-1).body, { title: "未命名分镜" });
});
