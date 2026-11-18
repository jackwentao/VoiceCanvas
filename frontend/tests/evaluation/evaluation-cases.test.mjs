import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { createCaseStore } from "../../scripts/evaluation-cases.mjs";

const draft = {
  title: "局部改画",
  kind: "编辑",
  request: "给第二镜添加标题",
  status: "active",
  initial: { mode: "blank" },
  criteria: [{ id: "V1", group: "画面", requirement: "标题可见", visual: true }],
  operations: ["添加标题"],
};

test("用例从独立 JSON 持久化，过期修订不能覆盖，归档后仍可恢复", async () => {
  const directory = await mkdtemp(join(tmpdir(), "voicecanvas-case-store-"));
  try {
    const store = createCaseStore(directory);
    const [first, second] = await Promise.all([store.save(draft), store.save(draft)]);
    assert.deepEqual([first.id, second.id], ["VC-01", "VC-02"]);
    assert.equal(first.revision, 1);
    const archived = await store.save({ ...first, title: "新版", status: "archived" }, first.id);
    assert.equal(archived.revision, 2);
    await assert.rejects(store.save(first, first.id), error => error.status === 409);
    const persisted = JSON.parse(await readFile(join(directory, "VC-01.json"), "utf8"));
    assert.equal(persisted.status, "archived");
    assert.equal(persisted.title, "新版");
    const reopened = createCaseStore(directory);
    await reopened.save({ ...persisted, status: "active" }, first.id);
    assert.equal((await reopened.list())[0].revision, 3);
    await assert.rejects(reopened.save({ ...draft, criteria: [draft.criteria[0], draft.criteria[0]] }),
      error => error.status === 422);
    await assert.rejects(reopened.save({ ...draft, criteria: [{ ...draft.criteria[0], id: undefined }] }),
      error => error.status === 422);
    await assert.rejects(reopened.read("../outside"), error => error.status === 404);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
