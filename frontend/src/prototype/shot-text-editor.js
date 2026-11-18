import { centeredBaseline, chooseTextContainer, overlaps, recommendedTextSize,
  textReadability, textScale, wrapShotText } from "./shot-text-layout.js";

const NS = "http://www.w3.org/2000/svg";
const box = (b) => ({ x: b.x, y: b.y, right: b.x + b.width, bottom: b.y + b.height });
const union = (items) => ({ x: Math.min(...items.map(b => b.x)), y: Math.min(...items.map(b => b.y)),
  right: Math.max(...items.map(b => b.right)), bottom: Math.max(...items.map(b => b.bottom)) });

function transformedBounds(element, inverse = null) {
  const b = element.getBBox();
  let matrix = element.getCTM();
  if (inverse) matrix = inverse.multiply(matrix);
  const points = [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]]
    .map(([x, y]) => new DOMPoint(x, y).matrixTransform(matrix));
  return { x: Math.min(...points.map(p => p.x)), y: Math.min(...points.map(p => p.y)),
    right: Math.max(...points.map(p => p.x)), bottom: Math.max(...points.map(p => p.y)) };
}

// 测量在禁止脚本和外部资源的 iframe 中进行；画面预览仍使用隔离的 img。
export class ShotTextEditor {
  constructor({ root = document, preview, save, frame }) {
    this.$ = id => root.getElementById(id);
    this.preview = preview;
    this.save = save;
    this.frame = frame;
    this.state = null;
    this.versionKey = null;
    this.previewSvg = null;
    this.candidate = null;
    this.hasDraft = false;
    this.measureHost = document.createElement("iframe");
    this.measureHost.className = "text-measure-host";
    this.measureHost.setAttribute("sandbox", "allow-same-origin");
    this.measureHost.setAttribute("aria-hidden", "true");
    this.measureHost.title = "文字排版测量";
    this.measureHost.tabIndex = -1;
    this.ready = new Promise(resolve => this.measureHost.addEventListener("load", resolve, { once: true }));
    this.measureHost.src = new URL("./shot-text-measure.html", import.meta.url).href;
    document.body.append(this.measureHost);
    this.$("editTextToggle").addEventListener("click", () => this.open());
    this.$("closeTextEditor").addEventListener("click", () => this.close());
    this.$("textTarget").addEventListener("change", () => {
      if (!this.hasDraft) {
        this.select();
        return;
      }
      this.$("textTarget").value = String(this.info.block.index);
      this.$("textEditFeedback").textContent = "请应用改字或重置草稿，再选择其他文字。";
    });
    for (const id of ["textContent", "textFontSize", "textWrapWidth"]) {
      this.$(id).addEventListener("input", () => this.draft());
    }
    this.$("resetTextDraft").addEventListener("click", () => this.select());
    this.$("applyTextEdit").addEventListener("click", async () => {
      if (this.candidate) await this.save(this.candidate);
    });
    this.$("recommendedTextSize").addEventListener("click", () => {
      const scale = textScale(this.info.matrix);
      const width = this.frame.clientWidth || 640;
      this.$("textFontSize").value = recommendedTextSize(Number(this.$("textFontSize").value), scale, width);
      this.draft();
    });
    this.observer = new ResizeObserver(() => {
      if (this.info && !this.$("textEditor").hidden) {
        this.showReadability(Number(this.$("textFontSize").value));
        if (this.previewSvg) this.draft();
      }
    });
    this.observer.observe(frame);
  }

  setState(state, busy) {
    this.state = state;
    this.busy = busy;
    this.$("editTextToggle").disabled = busy || !state?.texts?.length;
    const key = state ? `${state.id}:${state.version}` : null;
    if (key !== this.versionKey) {
      this.versionKey = key;
      this.previewSvg = null;
      this.candidate = null;
      this.hasDraft = false;
      this.info = null;
      if (!this.$("textEditor").hidden) this.populate();
    }
    for (const id of ["textTarget", "textContent", "textFontSize", "textWrapWidth", "resetTextDraft", "recommendedTextSize"]) {
      this.$(id).disabled = busy || (id !== "textTarget" && !this.info);
    }
    this.$("applyTextEdit").disabled = busy || !this.candidate;
  }

  async open() {
    if (!this.$("textEditor").hidden) {
      this.$(this.hasDraft ? "textContent" : "textTarget").focus();
      return;
    }
    this.$("textEditor").hidden = false;
    await this.ready;
    if (this.$("textEditor").hidden) return;
    this.populate();
    const target = this.info ? "textContent" : "textTarget";
    this.$(target).focus();
  }

  close() {
    if (this.busy || (this.hasDraft && !window.confirm("舍弃尚未保存的改字草稿？"))) return;
    this.previewSvg = null;
    this.candidate = null;
    this.hasDraft = false;
    this.$("textEditor").hidden = true;
    this.preview(this.state?.svg);
    this.$("editTextToggle").focus();
  }

  populate() {
    const select = this.$("textTarget");
    const oldIndex = select.value;
    select.replaceChildren();
    for (const text of this.state?.texts || []) {
      const option = document.createElement("option");
      option.value = text.index;
      option.textContent = text.text.replace(/\s+/g, " ").slice(0, 60) || "（空文字）";
      option.disabled = !text.editable;
      if (!text.editable) option.textContent += ` · ${text.reason}`;
      select.append(option);
    }
    const options = [...select.options];
    select.value = options.find(o => !o.disabled && o.value === oldIndex)?.value
      ?? options.find(o => !o.disabled)?.value ?? "";
    this.select();
  }

  mount(source) {
    const documentSvg = new DOMParser().parseFromString(source, "image/svg+xml");
    const targetDocument = this.measureHost.contentDocument;
    const svg = targetDocument.importNode(documentSvg.documentElement, true);
    targetDocument.body.replaceChildren(svg);
    svg.setAttribute("width", "1280");
    svg.setAttribute("height", "720");
    return svg;
  }

  select() {
    this.previewSvg = null;
    this.candidate = null;
    this.hasDraft = false;
    this.info = null;
    this.$("applyTextEdit").disabled = true;
    const block = this.state?.texts?.find(t => String(t.index) === this.$("textTarget").value);
    if (!block || !block.editable) {
      this.$("textContent").value = "";
      this.$("textEditFeedback").textContent = "当前没有可直接编辑的文字。复杂字形仍可通过自然语言修改。";
      this.$("textReadability").textContent = "";
      this.preview(this.state?.svg);
      this.setState(this.state, this.busy);
      return;
    }
    try {
      const svg = this.mount(this.state.svg);
      const texts = [...svg.querySelectorAll("text")];
      const nodes = block.indices.map(index => texts[index]);
      const first = nodes[0];
      const inverse = first.getCTM().inverse();
      const bounds = union(nodes.map(node => transformedBounds(node, inverse)));
      const style = getComputedStyle(first);
      const fontSize = parseFloat(style.fontSize);
      const container = chooseTextContainer([...first.parentElement.children]
        .filter(el => el.localName === "rect").map(el => transformedBounds(el, inverse)), bounds, fontSize);
      const baseline = parseFloat(first.querySelector("tspan[y]")?.getAttribute("y") || first.getAttribute("y") || "0");
      const anchorX = first.firstElementChild?.getAttribute("x") || first.getAttribute("x") || "0";
      this.info = { block, bounds, container, fontSize, baseline, anchorX, matrix: first.getCTM() };
      this.$("textContent").value = block.text;
      this.$("textFontSize").value = Math.round(fontSize * 10) / 10;
      this.$("textWrapWidth").value = Math.max(20, Math.round(container
        ? container.right - container.x - 24 : bounds.right - bounds.x + 4));
      this.$("textEditFeedback").textContent = "修改后会在画面中预览，点击“应用改字”保存。";
      this.preview(this.state.svg);
      this.showReadability(fontSize);
      this.setState(this.state, this.busy);
    } catch {
      this.info = null;
      this.$("textEditFeedback").textContent = "这段文字使用特殊布局，请通过自然语言修改。";
      this.preview(this.state?.svg);
      this.setState(this.state, this.busy);
    }
  }

  showReadability(fontSize) {
    if (!this.info) return;
    const scale = textScale(this.info.matrix);
    const reading = textReadability(fontSize, scale, this.frame.clientWidth || 640);
    this.$("textReadability").textContent = reading.warning || `当前预览约 ${reading.preview.toFixed(1)} 像素。`;
  }

  draft() {
    if (!this.info || this.busy) return;
    this.hasDraft = true;
    this.candidate = null;
    this.$("applyTextEdit").disabled = true;
    try {
      const content = this.$("textContent").value;
      const fontSize = Number(this.$("textFontSize").value);
      const width = Number(this.$("textWrapWidth").value);
      if (!content.trim() || content.length > 2000) throw new Error("请输入 1–2000 字的内容");
      if (!Number.isFinite(fontSize) || fontSize < 8 || fontSize > 160) throw new Error("字号范围为 8–160");
      if (!Number.isFinite(width) || width < 20 || width > 1280) throw new Error("换行宽度范围为 20–1280");
      const svg = this.mount(this.state.svg);
      const all = [...svg.querySelectorAll("text")];
      const { block, container, bounds, baseline, anchorX } = this.info;
      const first = all[block.index];
      // 测量与最终文字使用同一 SVG 字体、字距和变换，避免 Canvas 字体估算漂移。
      first.replaceChildren();
      first.style.removeProperty("font-size");
      first.setAttribute("font-size", fontSize);
      const measure = text => { first.textContent = text; return first.getComputedTextLength(); };
      const lines = wrapShotText(content, width, measure);
      const x = anchorX;
      first.setAttribute("x", x);
      first.replaceChildren();
      first.setAttribute("y", baseline);
      lines.forEach((line, index) => {
        const span = document.createElementNS(NS, "tspan");
        span.setAttribute("x", x);
        span.setAttribute("dy", index ? fontSize * 1.35 : 0);
        span.textContent = line;
        first.append(span);
      });
      for (const index of block.indices.slice(1)) all[index].remove();
      // 保持原文字块的垂直中心，避免长句只向下生长。
      const current = box(first.getBBox());
      const y = centeredBaseline(baseline, bounds, current);
      first.setAttribute("y", y);
      const local = box(first.getBBox());
      const global = transformedBounds(first);
      const messages = [];
      let blocked = false;
      if (global.x < 0 || global.y < 0 || global.right > 1280 || global.bottom > 720) {
        messages.push("文字超出画布，请缩短内容或调整字号、换行宽度。"); blocked = true;
      }
      if (container && (local.x < container.x - 1 || local.y < container.y - 1
        || local.right > container.right + 1 || local.bottom > container.bottom + 1)) {
        messages.push("文字超出原气泡或底板，请缩短、减小字号，或用自然语言扩大气泡。"); blocked = true;
      }
      const otherText = [...svg.querySelectorAll("text")].filter(el => el !== first && el.getBBox().width > 0);
      if (otherText.some(el => overlaps(global, transformedBounds(el)))) {
        messages.push("文字与其他文字重叠，请调整字号或换行宽度。"); blocked = true;
      }
      this.previewSvg = new XMLSerializer().serializeToString(svg);
      this.preview(this.previewSvg);
      this.$("textEditFeedback").textContent = messages.join(" ") || `已预览 ${lines.length} 行；应用后保存为一个可撤销版本。`;
      this.showReadability(fontSize);
      if (!blocked) this.candidate = { index: block.index, lines, fontSize, lineHeight: 1.35, y };
      this.$("applyTextEdit").disabled = blocked;
    } catch (error) {
      this.previewSvg = null;
      this.preview(this.state.svg);
      this.$("textEditFeedback").textContent = error.message;
    }
  }
}
