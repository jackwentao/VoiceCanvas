import { randomUUID } from "node:crypto";
import { lstat, readFile, readdir, rename, unlink, writeFile } from "node:fs/promises";
import { join } from "node:path";

const caseId = /^VC-\d{2,8}$/;
const criterionId = /^[A-Za-z][A-Za-z0-9_-]{0,23}$/;
const groups = new Set(["结构", "画面", "目标修改", "保留项"]);

export class CaseError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function requiredText(value, name, limit) {
  if (typeof value !== "string" || !value.trim() || value.length > limit) {
    throw new CaseError(422, `${name}需要填写，长度不能超过 ${limit}。`);
  }
  return value.trim();
}

function validate(input) {
  if (!input || typeof input !== "object" || !["active", "archived"].includes(input.status)) {
    throw new CaseError(422, "用例状态无效。");
  }
  const { initial, criteria, operations } = input;
  if (!initial || !["blank", "svg"].includes(initial.mode)) throw new CaseError(422, "请选择初始状态。");
  if (initial.mode === "svg") {
    const svg = requiredText(initial.svg, "初始 SVG", 1_000_000);
    if (Buffer.byteLength(svg, "utf8") > 1_000_000) throw new CaseError(422, "初始 SVG 超过 1 MB。");
    if (!/^\s*(?:<\?xml[^?]*\?>\s*)?<svg(?:\s|>)/.test(svg)) {
      throw new CaseError(422, "初始 SVG 需要包含 svg 根元素。");
    }
    if (!Number.isFinite(initial.durationSeconds) || initial.durationSeconds <= 0 || initial.durationSeconds > 180) {
      throw new CaseError(422, "镜头时长必须大于 0 秒且不超过 180 秒。");
    }
  }
  if (!Array.isArray(criteria) || !criteria.length || criteria.length > 50 ||
      !criteria.every(row => row && typeof row.id === "string" && criterionId.test(row.id) && groups.has(row.group)
        && typeof row.visual === "boolean") ||
      new Set(criteria.map(row => row.id)).size !== criteria.length) {
    throw new CaseError(422, "请填写 1 至 50 条判据，判据 ID 须以字母开头、互不重复。");
  }
  if (!Array.isArray(operations) || operations.length > 40) throw new CaseError(422, "必要操作最多 40 条。");
  return {
    title: requiredText(input.title, "用例标题", 100),
    kind: requiredText(input.kind, "任务类型", 40),
    status: input.status,
    request: requiredText(input.request, "用户需求", 8000),
    initial: initial.mode === "blank" ? { mode: "blank" } : {
      mode: "svg",
      svg: initial.svg.trim(),
      title: requiredText(initial.title, "镜头标题", 100),
      description: requiredText(initial.description, "拍摄说明", 2000),
      camera: requiredText(initial.camera, "景别", 200),
      durationSeconds: initial.durationSeconds,
    },
    criteria: criteria.map(row => ({
      id: row.id, group: row.group, visual: row.visual,
      requirement: requiredText(row.requirement, `判据 ${row.id}`, 600),
    })),
    operations: operations.map(label => requiredText(label, "必要操作", 200)),
  };
}

export function createCaseStore(directory) {
  let pending = Promise.resolve();

  async function read(id) {
    if (!caseId.test(id)) throw new CaseError(404, "用例不存在。");
    const file = join(directory, `${id}.json`);
    try {
      if (!(await lstat(file)).isFile()) throw new CaseError(404, "用例不存在。");
      return JSON.parse(await readFile(file, "utf8"));
    } catch (error) {
      if (error.code === "ENOENT") throw new CaseError(404, "用例不存在。");
      throw error;
    }
  }

  async function list() {
    const entries = await readdir(directory, { withFileTypes: true });
    const cases = await Promise.all(entries
      .filter(entry => entry.isFile() && entry.name.endsWith(".json"))
      .map(entry => entry.name.slice(0, -5)).filter(id => caseId.test(id)).map(read));
    return cases.sort((a, b) => Number(a.id.slice(3)) - Number(b.id.slice(3)));
  }

  function save(input, id) {
    const job = pending.then(async () => {
      const fields = validate(input);
      const current = id ? await read(id) : null;
      if (current && input.revision !== current.revision) {
        throw new CaseError(409, "用例已在其他窗口更新，请重新加载当前版本。");
      }
      const nextId = id || `VC-${String(Math.max(0, ...(await list()).map(item => Number(item.id.slice(3)))) + 1).padStart(2, "0")}`;
      const next = {
        id: nextId, revision: (current?.revision ?? 0) + 1,
        ...fields, updatedAt: new Date().toISOString(),
      };
      const temp = join(directory, `.${nextId}-${randomUUID()}.tmp`);
      await writeFile(temp, JSON.stringify(next, null, 2) + "\n", { flag: "wx" });
      try {
        await rename(temp, join(directory, `${nextId}.json`));
      } catch (error) {
        await unlink(temp).catch(() => {});
        throw error;
      }
      return next;
    });
    pending = job.catch(() => {});
    return job;
  }

  return { read, list, save };
}
