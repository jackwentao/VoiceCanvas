const $ = id => document.getElementById(id);
const endpoint = "/api/evaluation-cases";
const form = $("case-editor");
const criteria = $("criteria-rows");
const groups = ["结构", "画面", "目标修改", "保留项"];
let entries = [];
let current = null;
let dirty = false;
let busy = false;

async function request(path = "", method = "GET", body) {
  const response = await fetch(endpoint + path, {
    method, ...(body && { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "用例操作失败。");
  return data;
}

function feedback(message, error = false) {
  const status = $("editor-feedback");
  status.textContent = message;
  status.dataset.error = String(error);
}

function renderList() {
  const matched = entries.filter(entry => $("library-filter").value === "all" || entry.status === $("library-filter").value);
  $("library-list").replaceChildren(...matched.map(entry => {
    const button = document.createElement("button");
    const title = document.createElement("strong");
    const meta = document.createElement("span");
    button.type = "button";
    button.className = "case-button";
    button.setAttribute("aria-current", String(current?.id === entry.id));
    button.disabled = busy;
    title.textContent = entry.title;
    meta.className = "caption";
    meta.textContent = `${entry.id} · ${entry.kind} · r${entry.revision}${entry.status === "archived" ? " · 已归档" : ""}`;
    button.append(title, meta);
    button.addEventListener("click", () => choose(entry.id));
    return button;
  }));
  if (!matched.length) $("library-list").textContent = "没有符合条件的用例。";
}

function setBusy(value) {
  busy = value;
  for (const id of ["new-case", "save-case", "reset-case", "case-archive", "editor-fields"]) $(id).disabled = value;
  renderList();
}

function labeled(text, input) {
  const label = document.createElement("label");
  label.append(text, input);
  return label;
}

function addCriterion(row = { id: "", group: "画面", requirement: "", visual: true }) {
  const field = document.createElement("div");
  field.className = "criterion-row";
  const id = document.createElement("input");
  id.name = "criterionId";
  id.value = row.id;
  id.required = true;
  id.maxLength = 24;
  id.pattern = "[A-Za-z][A-Za-z0-9_-]*";
  const group = document.createElement("select");
  group.name = "criterionGroup";
  group.append(...groups.map(value => new Option(value, value)));
  group.value = row.group;
  const text = document.createElement("textarea");
  text.name = "criterionText";
  text.rows = 2;
  text.required = true;
  text.maxLength = 600;
  text.value = row.requirement;
  const visual = document.createElement("input");
  visual.name = "criterionVisual";
  visual.type = "checkbox";
  visual.checked = row.visual;
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "action";
  remove.textContent = "移除判据";
  remove.addEventListener("click", () => { field.remove(); dirty = true; });
  const fields = document.createElement("div");
  fields.className = "case-fields";
  fields.append(labeled("判据 ID", id), labeled("类别", group));
  const tools = document.createElement("div");
  tools.className = "criterion-tools";
  tools.append(labeled("DeepSeek 看图评分", visual), remove);
  field.append(fields, labeled("验收条件", text), tools);
  criteria.append(field);
}

function syncInitial() {
  const enabled = $("initial-mode").value === "svg";
  $("svg-initial").hidden = !enabled;
  for (const input of $("svg-initial").querySelectorAll("input, textarea")) {
    input.disabled = !enabled;
    if (input.type !== "file") input.required = enabled;
  }
}

function openEditor(entry) {
  current = entry;
  dirty = false;
  form.hidden = false;
  $("editor-title").textContent = entry.id ? "编辑用例" : "新建用例";
  $("case-revision").textContent = entry.id ? `${entry.id} · r${entry.revision}${entry.status === "archived" ? " · 已归档" : ""}` : "";
  $("case-archive").textContent = entry.status === "archived" ? "恢复用例" : "归档用例";
  $("case-archive").hidden = !entry.id;
  $("case-title").value = entry.title;
  $("case-kind").value = entry.kind;
  $("case-request").value = entry.request;
  $("initial-mode").value = entry.initial.mode;
  $("initial-title").value = entry.initial.title ?? "";
  $("initial-description").value = entry.initial.description ?? "";
  $("initial-camera").value = entry.initial.camera ?? "";
  $("initial-duration").value = entry.initial.durationSeconds ?? 5;
  $("initial-svg").value = entry.initial.svg ?? "";
  $("initial-file").value = "";
  $("case-operations").value = entry.operations.join("\n");
  criteria.replaceChildren();
  entry.criteria.forEach(addCriterion);
  syncInitial();
  renderList();
}

function emptyCase() {
  return { title: "", kind: "", request: "", status: "active", initial: { mode: "blank" },
    criteria: [{ id: "V1", group: "画面", requirement: "", visual: true }], operations: [] };
}

function mayLeave() {
  return !busy && (!dirty || window.confirm("放弃本次未保存的修改？"));
}

async function choose(id) {
  if (!mayLeave()) return;
  setBusy(true);
  feedback("");
  try { openEditor(id ? await request(`/${id}`) : emptyCase()); }
  catch (error) { $("library-status").textContent = error.message; }
  finally { setBusy(false); }
}

function editorValues() {
  const mode = $("initial-mode").value;
  return {
    title: $("case-title").value, kind: $("case-kind").value, request: $("case-request").value,
    initial: mode === "blank" ? { mode } : {
      mode, svg: $("initial-svg").value, title: $("initial-title").value,
      description: $("initial-description").value, camera: $("initial-camera").value,
      durationSeconds: $("initial-duration").valueAsNumber,
    },
    criteria: [...criteria.children].map(row => ({
      id: row.querySelector('[name="criterionId"]').value.trim(),
      group: row.querySelector('[name="criterionGroup"]').value,
      requirement: row.querySelector('[name="criterionText"]').value,
      visual: row.querySelector('[name="criterionVisual"]').checked,
    })),
    operations: $("case-operations").value.split("\n").map(line => line.trim()).filter(Boolean),
  };
}

async function save(values, status = current.status) {
  const id = current.id;
  setBusy(true);
  feedback("正在保存…");
  try {
    const saved = await request(id ? `/${id}` : "", id ? "PUT" : "POST", {
      ...values, status, revision: current.revision,
    });
    const summary = { id: saved.id, title: saved.title, kind: saved.kind, revision: saved.revision, status };
    entries = [...entries.filter(entry => entry.id !== saved.id), summary]
      .sort((a, b) => Number(a.id.slice(3)) - Number(b.id.slice(3)));
    $("library-status").textContent = `${entries.length} 条用例`;
    $("library-filter").value = status;
    openEditor(saved);
    feedback(`已保存 ${saved.id} · r${saved.revision}。`);
  } catch (error) {
    feedback(error.message, true);
  } finally {
    setBusy(false);
  }
}

$("new-case").addEventListener("click", () => choose());
$("reset-case").addEventListener("click", () => choose(current.id));
$("library-filter").addEventListener("change", renderList);
$("initial-mode").addEventListener("change", syncInitial);
$("add-criterion").addEventListener("click", () => { addCriterion(); dirty = true; });
$("initial-file").addEventListener("change", async event => {
  const [file] = event.target.files;
  if (!file) return;
  if (file.size > 1_000_000) {
    feedback("初始 SVG 超过 1 MB。", true);
    return;
  }
  const selected = current;
  try {
    const svg = await file.text();
    if (current === selected && !busy && $("initial-mode").value === "svg") {
      $("initial-svg").value = svg;
      dirty = true;
      feedback("");
    }
  } catch { feedback("无法读取 SVG 文件。", true); }
});
form.addEventListener("input", () => { dirty = true; });
form.addEventListener("submit", event => {
  event.preventDefault();
  if (!busy) void save(editorValues());
});
$("case-archive").addEventListener("click", () => {
  if (!mayLeave()) return;
  const status = current.status === "active" ? "archived" : "active";
  void save(current, status);
});
window.addEventListener("beforeunload", event => {
  if (dirty) { event.preventDefault(); event.returnValue = ""; }
});

try {
  ({ cases: entries } = await request());
  $("library-status").textContent = `${entries.length} 条用例`;
  await choose(entries.find(entry => entry.status === "active")?.id);
} catch (error) {
  $("library-status").textContent = error.message;
}
