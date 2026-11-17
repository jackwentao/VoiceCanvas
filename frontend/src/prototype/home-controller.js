/** 首页只编排读取与跳转，不生成作品数据或本地项目。 */
export function pageUrl(page, search = "", boardId) {
  const source = new URLSearchParams(search);
  const target = new URLSearchParams();
  for (const key of ["apiBaseUrl", "userId", "streamStepDelayMs"]) {
    if (source.has(key)) target.set(key, source.get(key));
  }
  if (boardId) target.set("board", boardId);
  return `./${page}${target.size ? `?${target}` : ""}`;
}

export function createHomeController(api, notify = () => {}, navigate = () => {}, search = "") {
  const state = { items: [], categories: [], category: "", total: 0, loading: false,
    loaded: false, error: null, creating: false, creationError: null };
  let requestNumber = 0;
  async function load(category = "") {
    const current = ++requestNumber;
    state.loading = true;
    state.error = null;
    notify(state);
    try {
      const result = await api.showcase(category);
      if (current !== requestNumber) return;
      Object.assign(state, { items: result.items, categories: result.categories,
        total: result.total, category, loaded: true });
    } catch (error) {
      if (current === requestNumber) state.error = error;
    } finally {
      if (current === requestNumber) { state.loading = false; notify(state); }
    }
  }
  async function create() {
    if (state.creating) return;
    state.creating = true;
    state.creationError = null;
    notify(state);
    try {
      const response = await api.create();
      const id = response.id;
      if (!id) throw new Error("新画布没有创建成功，请重试。");
      navigate(pageUrl("workspace.html", search, id));
    } catch (error) {
      state.creationError = error;
    } finally {
      state.creating = false;
      notify(state);
    }
  }
  return { state, load, create };
}
