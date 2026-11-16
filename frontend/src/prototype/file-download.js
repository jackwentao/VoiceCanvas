/** 仅将后端授权的导出结果呈现为浏览器下载，不生成项目包或决定导出业务规则。 */
import { resolveBackendUrl } from "./backend-client.js";

function asDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("导出图片读取失败"));
    reader.readAsDataURL(blob);
  });
}

async function embedImages(root) {
  await Promise.all([...root.querySelectorAll("image, img")].map(async node => {
    const source = node.getAttribute("href") || node.getAttribute("src");
    if (!source || source.startsWith("data:")) return;
    const response = await fetch(resolveBackendUrl(source));
    if (!response.ok) throw new Error("素材加载失败，暂时无法导出完整图片");
    const data = await asDataUrl(await response.blob());
    node.setAttribute(node.tagName.toLowerCase() === "img" ? "src" : "href", data);
  }));
}

async function sceneSvg(element, width, height) {
  if (!element) throw new Error("当前镜头尚未显示，请等待加载后重试");
  await document.fonts?.ready;
  const clone = element.cloneNode(true);
  const originals = [element, ...element.querySelectorAll("*")];
  [clone, ...clone.querySelectorAll("*")].forEach((node, index) => {
    const computed = getComputedStyle(originals[index]);
    node.setAttribute("style", [...computed].map(key => `${key}:${computed.getPropertyValue(key)}`).join(";"));
    node.classList.remove("is-selected", "is-candidate", "is-changed");
    node.style.outline = "none";
    node.style.boxShadow = "none";
    node.style.animation = "none";
    node.style.transition = "none";
  });
  clone.style.transform = "none";
  clone.style.position = "relative";
  clone.style.width = `${width}px`;
  clone.style.height = `${height}px`;
  await embedImages(clone);
  clone.setAttribute("xmlns", "http://www.w3.org/1999/xhtml");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><foreignObject width="100%" height="100%">${new XMLSerializer().serializeToString(clone)}</foreignObject></svg>`;
}

async function pngBlob(svg, width, height) {
  const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
  if (doc.querySelector("parsererror")) throw new Error("导出图片格式有误");
  await embedImages(doc);
  const serialized = new XMLSerializer().serializeToString(doc.documentElement);
  const image = new Image();
  await new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = () => reject(new Error("图片渲染失败，请重试或先导出项目 JSON"));
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(serialized)}`;
  });
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("当前浏览器无法生成图片");
  context.drawImage(image, 0, 0, width, height);
  return new Promise((resolve, reject) => canvas.toBlob(blob =>
    blob ? resolve(blob) : reject(new Error("PNG 图片生成失败")), "image/png"));
}

export async function downloadBackendExport(result, { project, element } = {}) {
  if (!result?.filename) throw new Error("后端没有返回可下载的导出文件");
  let blob;
  if (result.format === "png") {
    const scene = project?.scenes.find(item => item.id === result.sceneId);
    if (!scene) throw new Error("后端指定的导出镜头尚未同步，请重新连接");
    const { width, height } = scene.canvas;
    const svg = result.renderMode === "client_scene"
      ? await sceneSvg(element, width, height) : result.content;
    blob = await pngBlob(svg, width, height);
  } else {
    if (typeof result.content !== "string" || !result.content) {
      throw new Error("后端没有返回文件内容");
    }
    blob = new Blob([result.content], { type: result.mimeType });
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = result.filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
