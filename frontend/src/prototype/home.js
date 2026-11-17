import { loadShowcase, createProjectState, resolveBackendUrl } from "./backend-client.js";
import { createHomeController, pageUrl } from "./home-controller.js";

const $ = selector => document.querySelector(selector);
const escape = value => String(value ?? "").replace(/[&<>"']/g, char =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
let heroLoaded = false;
let lastItems = null;
let lastCategories = null;
let artworks = new Map();
const dialog = $("#artworkDialog");
const controller = createHomeController(
  { showcase: loadShowcase, create: createProjectState }, render,
  url => { location.href = url; }, location.search
);

document.querySelectorAll(".workspace-link").forEach(link => {
  link.href = pageUrl("workspace.html", location.search);
});
document.querySelectorAll(".wordmark, .footer-brand").forEach(link => {
  link.href = pageUrl("index.html", location.search);
});

function preview(id) {
  const artwork = artworks.get(id);
  if (!artwork) return;
  $("#previewImage").src = resolveBackendUrl(artwork.imageUrl);
  $("#previewImage").alt = artwork.title;
  $("#previewCategory").textContent = artwork.categoryLabel;
  $("#previewTitle").textContent = artwork.title;
  $("#previewDescription").textContent = artwork.description;
  dialog.showModal();
}

function renderHero(items) {
  for (const slot of document.querySelectorAll("[data-hero]")) {
    const artwork = items.find(item => item.hero === slot.dataset.hero);
    slot.classList.remove("skeleton");
    if (!artwork) { slot.hidden = true; continue; }
    slot.hidden = false;
    slot.dataset.caption = artwork.note;
    slot.innerHTML = `<span class="${artwork.hero === "back" ? "pin" : "tape"}"></span>
      <button data-preview="${escape(artwork.id)}" aria-label="查看作品：${escape(artwork.title)}">
      <img src="${escape(resolveBackendUrl(artwork.imageUrl))}" alt="${escape(artwork.title)}" width="800" height="600" fetchpriority="high" /></button>`;
  }
  $("#heroGallery").setAttribute("aria-busy", "false");
}

function render(state) {
  const grid = $("#galleryGrid");
  grid.setAttribute("aria-busy", String(state.loading));
  $("#galleryError").hidden = !state.error;
  $("#galleryEmpty").hidden = !state.loaded || !!state.items.length || state.loading;
  $("#galleryCount").textContent = state.loading ? "正在挂上作品…" :
    state.loaded ? `${String(state.total).padStart(2, "0")} 幅小小灵感` : "画廊暂未连接";
  if (state.error && !state.loaded) {
    grid.replaceChildren();
    $("#heroGallery").setAttribute("aria-busy", "false");
    document.querySelectorAll("[data-hero]").forEach(slot => { slot.hidden = true; });
  }
  if (state.categories !== lastCategories || !$("#galleryFilters").children.length) {
    lastCategories = state.categories;
    $("#galleryFilters").innerHTML = [{ id: "", label: "全部灵感" }, ...state.categories].map(item =>
      `<button class="filter" data-category="${escape(item.id)}" aria-pressed="${item.id === state.category}">${escape(item.label)}</button>`).join("");
  }
  document.querySelectorAll("[data-category]").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.category === state.category));
  });
  if (state.loaded && state.items !== lastItems) {
    lastItems = state.items;
    state.items.forEach(item => artworks.set(item.id, item));
    if (!heroLoaded && !state.category) { renderHero(state.items); heroLoaded = true; }
    grid.innerHTML = state.items.map(item => `<article class="gallery-card">
      <button class="card-image" data-preview="${escape(item.id)}" aria-label="查看作品：${escape(item.title)}">
      <img src="${escape(resolveBackendUrl(item.imageUrl))}" alt="${escape(item.title)}" width="800" height="600" loading="lazy" />
      <span class="view-art" aria-hidden="true">↗</span></button>
      <div class="card-info"><div class="card-title-row"><h3>${escape(item.title)}</h3><span class="card-category">${escape(item.categoryLabel)}</span></div><p>${escape(item.note)}</p></div>
      </article>`).join("");
  }
  document.querySelectorAll("[data-create]").forEach(button => {
    button.disabled = state.creating;
    button.setAttribute("aria-busy", String(state.creating));
  });
  const status = $("#creationStatus");
  status.hidden = !state.creating && !state.creationError;
  status.classList.toggle("is-error", !!state.creationError);
  status.textContent = state.creationError ? "新画布暂时没能创建，请检查连接后再试一次。" :
    "正在为你铺开一张新画布…";
  // 原生 dialog 位于顶层，创建失败时直接在弹窗中显示可见状态。
  if (state.creationError && dialog.open) dialog.close();
}

document.addEventListener("click", event => {
  const button = event.target.closest("[data-preview], [data-category], [data-create]");
  if (!button) return;
  if (button.hasAttribute("data-preview")) preview(button.dataset.preview);
  if (button.hasAttribute("data-category")) controller.load(button.dataset.category);
  if (button.hasAttribute("data-create")) controller.create();
});
$("#closePreview").addEventListener("click", () => dialog.close());
dialog.addEventListener("click", event => { if (event.target === dialog) {
  const rect = dialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right ||
      event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
} });
$("#retryGallery").addEventListener("click", () => controller.load(controller.state.category));

// 兼容已分享的旧工作台链接；普通首页访问不会创建项目。
if (new URLSearchParams(location.search).has("projectId")) {
  location.replace(pageUrl("workspace.html", location.search,
    new URLSearchParams(location.search).get("projectId")));
} else {
  controller.load();
}
