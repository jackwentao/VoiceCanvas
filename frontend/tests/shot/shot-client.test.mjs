import assert from "node:assert/strict";
import { test } from "node:test";
import { ShotClient, ShotApiError } from "../../src/prototype/shot-client.js";

const state = (version = 0, svg = null) => ({ id: "shot_a", version, svg, revisions: [], cursor: -1 });
const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });

test("默认 fetch 使用全局接收对象，兼容浏览器原生方法", async () => {
  const savedFetch = globalThis.fetch;
  globalThis.fetch = function () {
    assert.equal(this, globalThis);
    return Promise.resolve(response(state()));
  };
  try {
    const client = new ShotClient();
    await client.create();
    assert.equal(client.shot.id, "shot_a");
  } finally { globalThis.fetch = savedFetch; }
});

test("创建、生成、修改、撤销、重做携带服务端版本", async () => {
  const calls = [];
  const answers = [state(), state(1, "<svg/>"), state(2, "<svg/>"), state(3), state(4, "<svg/>")];
  const client = new ShotClient({ baseUrl: "https://api.test/", fetchImpl: async (url, options) => {
    calls.push({ url, ...options });
    return response(answers.shift());
  } });
  await client.create();
  await client.change("generate", "雨夜");
  await client.change("generate", "只改雨衣");
  await client.change("undo");
  await client.change("redo");
  assert.equal(calls[0].url, "https://api.test/api/shots");
  assert.deepEqual(calls.slice(1).map(c => JSON.parse(c.body).expectedVersion), [0, 1, 2, 3]);
  assert.equal(JSON.parse(calls[2].body).instruction, "只改雨衣");
  assert.equal(client.shot.version, 4);
});

test("刷新恢复读取现有镜头，不自动生成", async () => {
  const calls = [];
  const client = new ShotClient({ fetchImpl: async (url, options) => {
    calls.push({ url, options });
    return response(state(2, "saved svg"));
  } });
  await client.load("shot_a");
  assert.equal(client.shot.svg, "saved svg");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.method, "GET");
});

test("生成失败保留上一画面并释放忙碌状态", async () => {
  const events = [];
  const client = new ShotClient({ fetchImpl: async () => response({ detail: "输出预算不足" }, 502),
    onChange: c => events.push(c.busy) });
  client.shot = state(1, "last good svg");
  await assert.rejects(client.change("generate", "edit"), /输出预算不足/);
  assert.equal(client.shot.svg, "last good svg");
  assert.equal(client.busy, false);
  assert.deepEqual(events, [true, false]);
});

test("409 同步服务端最新状态，保留错误，不自动重试模型", async () => {
  const calls = [];
  const client = new ShotClient({ fetchImpl: async (url, options) => {
    calls.push(options.method);
    return options.method === "POST" ? response({ detail: "版本冲突" }, 409) : response(state(3, "newer svg"));
  } });
  client.shot = state(1, "old svg");
  await assert.rejects(client.change("generate", "edit"), ShotApiError);
  assert.deepEqual(calls, ["POST", "GET"]);
  assert.equal(client.shot.svg, "newer svg");
});

test("阻止重复提交；网络中断后可重新操作", async () => {
  let reject;
  let calls = 0;
  const client = new ShotClient({ fetchImpl: () => {
    calls++;
    return new Promise((_, fail) => { reject = fail; });
  } });
  client.shot = state(1, "saved");
  const pending = client.change("generate", "edit");
  await assert.rejects(client.change("generate", "duplicate"), /上一条/);
  assert.equal(calls, 1);
  reject(new TypeError("network"));
  await assert.rejects(pending, /network/);
  assert.equal(client.busy, false);
  assert.equal(client.shot.svg, "saved");
});
