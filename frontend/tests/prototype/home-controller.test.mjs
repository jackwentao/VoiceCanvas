import test from "node:test";
import assert from "node:assert/strict";
import { createHomeController, pageUrl } from "../../src/prototype/home-controller.js";

const gallery = (id = "original") => ({ items: [{ id }], categories: [{ id: "story", label: "故事" }], total: 1 });
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }

test("首页读取服务端作品，失败不伪造画廊或创建项目", async () => {
  let creates = 0;
  const controller = createHomeController({ showcase: async () => { throw new Error("offline"); }, create: () => { creates++; } });
  await controller.load();
  assert.deepEqual(controller.state.items, []);
  assert.equal(controller.state.loaded, false);
  assert.equal(controller.state.error.message, "offline");
  assert.equal(creates, 0);
});

test("分类透传给后端；较早请求迟到时不能覆盖最新分类", async () => {
  const first = deferred(), second = deferred(), calls = [];
  const controller = createHomeController({ showcase: category => { calls.push(category); return calls.length === 1 ? first.promise : second.promise; } });
  const a = controller.load("poster"), b = controller.load("story");
  second.resolve(gallery("cat")); await b;
  first.resolve(gallery("coffee")); await a;
  assert.deepEqual(calls, ["poster", "story"]);
  assert.equal(controller.state.category, "story");
  assert.deepEqual(controller.state.items, [{ id: "cat" }]);
});

test("分类失败保留上一份服务端结果，重试后清除错误", async () => {
  let fails = false;
  const controller = createHomeController({ showcase: async () => { if (fails) throw new Error("offline"); return gallery(); } });
  await controller.load(); fails = true; await controller.load("story");
  assert.equal(controller.state.category, "");
  assert.deepEqual(controller.state.items, gallery().items);
  assert.ok(controller.state.error); fails = false; await controller.load("story");
  assert.equal(controller.state.category, "story");
  assert.equal(controller.state.error, null);
});

test("新画布必须由后端创建；请求期间重复点击只创建一次", async () => {
  const pending = deferred(), destinations = []; let calls = 0;
  const controller = createHomeController({ create: () => { calls++; return pending.promise; } }, () => {}, url => destinations.push(url), "?apiBaseUrl=http%3A%2F%2F127.0.0.1%3A8018&projectId=old");
  const a = controller.create(); await controller.create();
  assert.equal(calls, 1); assert.equal(destinations.length, 0);
  pending.resolve({ id: "server-project" }); await a;
  assert.deepEqual(destinations, ["./workspace.html?apiBaseUrl=http%3A%2F%2F127.0.0.1%3A8018&board=server-project"]);
});

test("创建失败停留首页，允许显式重试", async () => {
  let fail = true; const destinations = [];
  const controller = createHomeController({ create: async () => { if (fail) throw new Error("offline"); return { id: "saved" }; } }, () => {}, url => destinations.push(url));
  await controller.create(); assert.equal(destinations.length, 0); assert.ok(controller.state.creationError);
  assert.equal(controller.state.creating, false); fail = false;
  await controller.create(); assert.deepEqual(destinations, ["./workspace.html?board=saved"]);
});

test("首页导航保留连接设置，返回首页时不携带旧项目定位", () => {
  assert.equal(pageUrl("index.html", "?projectId=old&userId=user_2&other=x"), "./index.html?userId=user_2");
  assert.equal(pageUrl("workspace.html"), "./workspace.html");
});

test("自由SVG创建使用分镜API返回的id，跳转保留board定位与连接参数", async () => {
  const destinations = [];
  const controller = createHomeController({ create: async () => ({ id: "board_server" }) },
    () => {}, url => destinations.push(url), "?apiBaseUrl=http%3A%2F%2F127.0.0.1%3A8013&projectId=old");
  await controller.create();
  assert.deepEqual(destinations, ["./workspace.html?apiBaseUrl=http%3A%2F%2F127.0.0.1%3A8013&board=board_server"]);
  assert.equal(pageUrl("index.html", "?board=old&shot=old&apiBaseUrl=x"), "./index.html?apiBaseUrl=x");
});
