import { comparisonMismatch, countStatus, median, toolSteps, verdict } from "./evaluation-data.js";

const $ = id => document.getElementById(id);
const dataRoot = "/evaluation-data";
const labels = { pass: "通过", fail: "未通过", review: "待复核" };
const execLabels = { succeeded: "执行成功", failed: "执行失败", running: "执行中" };
const seconds = n => Number.isFinite(n) ? `${n.toFixed(1)} 秒` : "—";
const pct = n => Number.isFinite(n) ? `${n.toFixed(1)}%` : "—";
const query = new URLSearchParams(location.search);
const batchCache = new Map();
let batches, active, baseline, selected, loadId = 0;
let tab = "assets";
let failedOnly = false;

function node(tag, text, attrs = {}) {
  const el = document.createElement(tag);
  if (text != null) el.textContent = text;
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

function container(tag, ...children) {
  const el = node(tag);
  el.append(...children);
  return el;
}

function badge(status, text = labels[status]) {
  return node("span", text, { class: "badge", "data-status": status });
}

function link(text, href) {
  return node("a", text, { href, target: "_blank", rel: "noopener" });
}

async function json(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`读取归档失败（HTTP ${response.status}）`);
  return response.json();
}

async function loadJudge(base, batch, result) {
  const response = await fetch(`${base}/judge.json`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`读取评分失败（HTTP ${response.status}）`);
  const score = await response.json();
  if (score.runId !== result.run.id || score.rubricVersion !== batch.rubricVersion) {
    throw new Error("评分记录与当前运行或判据版本不匹配。");
  }
  return score;
}

async function loadBatch(batch) {
  if (!batch) return null;
  if (!batchCache.has(batch.id)) {
    const archive = `${dataRoot}/${encodeURIComponent(batch.id)}/evidence`;
    const promise = Promise.all([
      json(`${archive}/metadata.json`),
      Promise.all(batch.cases.map(async entry => {
        const base = `${archive}/${encodeURIComponent(entry.id)}`;
        const [initial, result] = await Promise.all([json(`${base}/initial.json`), json(`${base}/result.json`)]);
        const judge = await loadJudge(base, batch, result);
        return { ...entry, base, initial, result, judge, verdict: verdict(entry.criteria) };
      })),
    ]).then(([meta, cases]) => ({ ...batch, meta, cases })).catch(error => {
      batchCache.delete(batch.id);
      throw error;
    });
    batchCache.set(batch.id, promise);
  }
  return batchCache.get(batch.id);
}

function metric(title, value, detail) {
  const term = node("dt", title);
  const valueNode = node("dd", value);
  valueNode.append(node("small", detail));
  const el = container("dl", term, valueNode);
  el.className = "metric";
  return el;
}

function ratio(count) {
  return count.total ? `${count.passed} / ${count.total}` : "—";
}

function renderMetrics() {
  const outcome = countStatus(active.cases.map(entry => entry.verdict), "pass");
  const steps = active.cases.flatMap(toolSteps);
  const decisions = countStatus(steps.map(step => step.decision), "pass");
  const execution = countStatus(steps.map(step => step.status), "succeeded", "running");
  const durations = active.cases.map(entry => entry.result.timing?.wallSeconds);
  $("metrics").replaceChildren(
    metric("严格通过", ratio(outcome), `待复核 ${outcome.pending} · 环境失败 ${active.environmentFailures ?? 0} 次`),
    metric("工具选择正确", ratio(decisions), `待复核 ${decisions.pending} 次`),
    metric("工具执行成功", ratio(execution), `执行失败 ${steps.filter(step => step.status === "failed").length} 次`),
    metric("任务耗时中位数", seconds(median(durations)), `服务端 · ${durations.filter(Number.isFinite).length} 次运行`),
  );
}

function updateUrl() {
  query.set("batch", active.id);
  if (selected) query.set("case", selected.id);
  else query.delete("case");
  if (baseline) query.set("compare", baseline.id);
  else query.delete("compare");
  history.replaceState(null, "", "?" + query);
}

function renderCases(wanted = selected?.id) {
  const filter = $("case-filter").value;
  const shown = active.cases.filter(entry => filter === "all" || entry.verdict === filter);
  selected = shown.find(entry => entry.id === wanted) ?? shown[0];
  const buttons = shown.map(entry => {
    const button = node("button", null, { type: "button", class: "case-button", "aria-current": String(entry === selected) });
    const meta = container("span", node("span", entry.id), badge(entry.verdict));
    meta.className = "case-meta caption";
    button.append(meta, node("span", entry.title, { class: "case-title" }),
      node("span", `${entry.kind} · ${seconds(entry.result.timing?.wallSeconds)}`, { class: "caption" }));
    button.addEventListener("click", () => {
      failedOnly = false;
      renderCases(entry.id);
      $("case-list").querySelector('[aria-current="true"]')?.focus();
    });
    return button;
  });
  $("case-list").replaceChildren(...(buttons.length ? buttons : [node("p", "没有符合条件的用例。", { class: "state" })]));
  renderDetail();
  updateUrl();
}

function table(headings, rows) {
  const header = container("thead", container("tr", ...headings.map(value => node("th", value, { scope: "col" }))));
  const body = container("tbody", ...rows.map(row => container("tr", ...row.map(value =>
    value instanceof Node ? container("td", value) : node("td", value)))));
  const wrap = container("div", container("table", header, body));
  wrap.className = "data-table";
  return wrap;
}

function imageFigure(base, file, title, caption = "") {
  const url = `${base}/${encodeURIComponent(file)}`;
  const img = node("img", null, { src: url, alt: title, loading: "lazy", width: "1280", height: "720" });
  const download = link("", url);
  download.setAttribute("aria-label", `${title}，查看原图`);
  download.append(img);
  const label = container("figcaption", node("strong", title), node("span", caption, { class: "caption" }));
  label.className = "asset-caption";
  return container("figure", download, label);
}

function renderAssets(entry) {
  const failures = entry.criteria.filter(item => item.status === "fail");
  const pending = entry.criteria.filter(item => item.status === "review");
  const notes = [...failures, ...pending];
  const gallery = node("div", null, { class: "gallery", "data-two": String(Boolean(entry.beforeImage)) });
  const figures = entry.result.board.shots.flatMap((shot, index) => {
    const title = entry.beforeImage ? `修改后 · ${shot.title}` : shot.title;
    const meta = [Number.isFinite(shot.durationSeconds) ? `${shot.durationSeconds} 秒` : "", `v${shot.version}`].filter(Boolean).join(" · ");
    return shot.svg ? [imageFigure(entry.base, `shot-${String(index + 1).padStart(2, "0")}.png`, title, meta)] : [];
  });
  if (entry.beforeImage) gallery.append(imageFigure(entry.base, entry.beforeImage, "修改前"));
  gallery.append(...figures);
  const resultLinks = container("div", link("初始快照 JSON", `${entry.base}/initial.json`), link("运行记录 JSON", `${entry.base}/result.json`));
  resultLinks.className = "raw-links";
  const prompt = container("details", node("summary", "用户需求"), node("p", entry.result.run.request, { class: "request" }));
  const overview = [];
  if (notes.length) {
    const message = container("div", node("h3", "关键验收问题"),
      container("ul", ...notes.map(item => node("li", `${item.id} · ${item.note}`))));
    message.className = "findings";
    overview.push(message);
  }
  if (gallery.childElementCount) overview.push(gallery);
  else overview.push(node("p", "本次运行没有保存画面。", { class: "state" }));
  if (baseline) overview.push(renderComparison(entry));
  return [...overview, resultLinks, prompt];
}

function renderComparison(entry) {
  const previous = baseline.cases.find(item => item.id === entry.id);
  const mismatch = comparisonMismatch(active, entry, baseline, previous);
  const section = container("section", node("h3", `与「${baseline.label}」对照`));
  if (mismatch) {
    section.append(node("p", mismatch, { class: "caption" }));
    return section;
  }
  const a = previous.result.timing?.wallSeconds;
  const b = entry.result.timing?.wallSeconds;
  const delta = Number.isFinite(a) && Number.isFinite(b) ? `${b > a ? "+" : ""}${seconds(b - a)}` : "—";
  const status = item => labels[item.status];
  const earlier = new Map(previous.criteria.map(item => [item.id, item]));
  const changes = entry.criteria.filter(item => earlier.get(item.id).status !== item.status);
  const selectedTools = item => countStatus(toolSteps(item).map(step => step.decision), "pass");
  const successRate = count => count.total && count.pending === 0 ? count.passed * 100 / count.total : null;
  const before = successRate(selectedTools(previous));
  const after = successRate(selectedTools(entry));
  section.append(table(["指标", "对照", "当前", "差异"], [
    ["最终验收", labels[previous.verdict], labels[entry.verdict], previous.verdict === entry.verdict ? "无变化" : "结论变化"],
    ["任务耗时", seconds(a), seconds(b), delta],
    ["工具选择正确率", pct(before), pct(after),
      Number.isFinite(before) && Number.isFinite(after) ? `${(after - before).toFixed(1)} 个百分点` : "—"],
    ...changes.map(item => [`${item.id} · ${item.requirement}`, status(earlier.get(item.id)), status(item), item.note]),
  ]));
  return section;
}

function renderRubric(entry) {
  const operationCount = countStatus(entry.operations.map(item => item.status), "pass");
  const modelScores = new Map(entry.judge?.criteria.map(item => [item.id, item]));
  const rows = entry.criteria.map(item => {
    const review = container("div", badge(item.status), node("p", item.note));
    const row = [`${item.id} · ${item.group}`, node("span", item.requirement, { class: "criterion" }), review];
    if (entry.judge) {
      const score = modelScores.get(item.id);
      const evaluation = score ? container("div", badge(score.status), node("p", score.note)) : node("span", "—");
      if (score && score.status !== item.status) evaluation.append(node("small", "与首轮核验有分歧", { class: "caption" }));
      row.push(evaluation);
    }
    return row;
  });
  const headers = ["判据", "验收条件", "归档核验"];
  const details = [];
  if (entry.judge) {
    headers.push("DeepSeek 评分");
    const count = countStatus(entry.judge.criteria.map(item => item.status), "pass");
    const meta = container("p", document.createTextNode(
      `${entry.judge.model} · ${ratio(count)} 画面判据通过 · ${seconds(entry.judge.elapsedSeconds)} · `),
    link("评分 JSON", `${entry.base}/judge.json`));
    meta.className = "caption";
    details.push(meta);
  } else {
    details.push(node("p", "暂无模型评分。", { class: "caption" }));
  }
  return [
    ...details,
    table(headers, rows),
    node("h3", `必要操作 · ${ratio(operationCount)}`),
    table(["操作", "结果"], entry.operations.map(item => [item.label, badge(item.status)])),
  ];
}

function renderTrace(entry) {
  const { timing, run } = entry.result;
  const timings = container("dl", ...[
    ["首次保存", timing?.firstSaveSeconds],
    ["最后保存", timing?.lastSaveSeconds],
    ["任务结束", timing?.wallSeconds],
  ].map(([key, value]) => container("div", node("dt", key), node("dd", seconds(value)))));
  timings.className = "timings";
  const steps = toolSteps(entry);
  const max = Math.max(1, ...steps.map(step => step.result?.elapsedSeconds ?? 0));
  const title = container("div", node("h3", "工具轨迹"));
  title.className = "section-title";
  const toggle = node("input", null, { type: "checkbox" });
  toggle.checked = failedOnly;
  toggle.addEventListener("change", () => {
    failedOnly = toggle.checked;
    renderDetail();
    $("case-detail").querySelector('input[type="checkbox"]')?.focus();
  });
  title.append(container("label", toggle, " 只看异常"));
  const list = node("div", null, { class: "step-list" });
  const filtered = steps.filter(step => !failedOnly || step.status === "failed" || step.decision === "fail");
  if (!filtered.length) list.append(node("p", "没有符合条件的工具记录。", { class: "state" }));
  for (const step of filtered) {
    const time = step.result?.elapsedSeconds;
    const target = step.target || "项目";
    const execStatus = step.status === "succeeded" ? "pass" : step.status === "failed" ? "fail" : "review";
    const label = container("span", node("code", `${step.index}. ${step.call.name}`),
      node("span", target, { class: "target" }),
      badge(execStatus, execLabels[step.status] || step.status),
      node("span", seconds(time), { class: "step-time" }));
    const content = container("details", container("summary", label));
    const note = step.note || step.result?.error;
    content.append(badge(step.decision, `选择${labels[step.decision]}`));
    if (note) content.append(node("p", note, { class: "step-note" }));
    if (Number.isFinite(time)) {
      const bar = node("div", null, { class: "bar", "aria-hidden": "true" });
      bar.append(node("span", null, { style: `width:${Math.min(100, Math.max(0, time / max * 100))}%` }));
      content.append(bar);
    }
    content.append(node("pre", JSON.stringify({ 参数: step.call.arguments, 返回: step.result }, null, 2)));
    list.append(content);
  }
  return [
    timings,
    node("p", "服务端墙钟时间与单次工具耗时分别记录。并行调用存在重叠，模型决策暂无独立计时。", { class: "caption" }),
    title,
    list,
    container("details", node("summary", `Agent 最终记录 · ${run.status}`), node("p", run.summary, { class: "request" })),
  ];
}

function renderDetail() {
  const detail = $("case-detail");
  if (!selected) { detail.replaceChildren(); return; }
  const head = container("div",
    container("div", node("p", `${selected.id} · ${selected.kind}`, { class: "caption" }), node("h2", selected.title)),
    badge(selected.verdict));
  head.className = "detail-heading";
  const tabs = node("div", null, { class: "tabbar", role: "group", "aria-label": "详情视图" });
  for (const [key, name] of [["assets", "产出与对照"], ["rubric", "验收判据"], ["trace", "耗时与轨迹"]]) {
    const button = node("button", name, { type: "button", "aria-pressed": String(tab === key) });
    button.addEventListener("click", () => {
      tab = key;
      renderDetail();
      detail.querySelector('.tabbar [aria-pressed="true"]').focus();
    });
    tabs.append(button);
  }
  const renderer = { assets: renderAssets, rubric: renderRubric, trace: renderTrace }[tab];
  const panel = container("div", ...renderer(selected));
  panel.className = "panel";
  detail.replaceChildren(head, tabs, panel);
}

async function showBatch(wanted) {
  const requestId = ++loadId;
  const id = $("batch-select").value;
  const compareId = $("baseline-select").value;
  $("dashboard").hidden = true;
  $("loading").hidden = false;
  $("loading").textContent = "正在读取评测归档…";
  try {
    const [next, reference] = await Promise.all([
      loadBatch(batches.find(batch => batch.id === id)),
      loadBatch(batches.find(batch => compareId !== id && batch.id === compareId)),
    ]);
    if (requestId !== loadId) return;
    active = next;
    baseline = reference;
    renderMetrics();
    renderCases(wanted);
    $("batch-meta").textContent = `${active.date} · ${active.meta.commit.slice(0, 7)} · ${active.meta.model}`;
    $("loading").hidden = true;
    $("dashboard").hidden = false;
  } catch (error) {
    if (requestId === loadId) showError(error, () => showBatch(wanted));
  }
}

function showError(error, retry) {
  const button = node("button", "重试", { type: "button" });
  button.addEventListener("click", retry);
  $("loading").replaceChildren(document.createTextNode(`${error.message} `), button);
}

async function start() {
  try {
    ({ batches } = await json(`${dataRoot}/index.json`));
    if (!batches.length) {
      $("loading").textContent = "暂无评测批次。";
      return;
    }
    const options = batches.map(batch => new Option(batch.label, batch.id));
    $("batch-select").replaceChildren(...options);
    const batchId = query.get("batch");
    if (batches.some(batch => batch.id === batchId)) $("batch-select").value = batchId;
    updateBaselineOptions(query.get("compare"));
    $("batch-select").disabled = false;
    $("batch-select").addEventListener("change", () => {
      updateBaselineOptions($("baseline-select").value);
      void showBatch(selected?.id);
    });
    $("baseline-select").addEventListener("change", () => { void showBatch(selected?.id); });
    $("case-filter").addEventListener("change", () => renderCases());
    await showBatch(query.get("case"));
  } catch (error) {
    showError(error, start);
  }
}

function updateBaselineOptions(compareId) {
  const alternatives = batches.filter(batch => batch.id !== $("batch-select").value);
  $("baseline-select").replaceChildren(new Option(alternatives.length ? "无" : "暂无其他批次", ""),
    ...alternatives.map(batch => new Option(batch.label, batch.id)));
  $("baseline-select").disabled = alternatives.length === 0;
  if (alternatives.some(batch => batch.id === compareId)) $("baseline-select").value = compareId;
}

await start();
