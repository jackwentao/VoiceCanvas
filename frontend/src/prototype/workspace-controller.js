/** 工作台视图模型。业务快照只接受后端响应，页面只持有请求与展示状态。 */
export function createWorkspaceController(api, notify = () => {}) {
  const state = {
    snapshot: null, projects: [], busy: false, stage: "idle", message: "连接工作台…",
    error: null, lastInput: "", summary: null, events: [], highlights: []
  };
  let projectId = null;
  const emit = () => notify(state);

  async function synchronize() {
    const snapshot = await api.workspace(projectId);
    if (!snapshot?.project?.id) throw new Error("后端没有返回完整的项目快照，请重新连接");
    state.snapshot = snapshot;
    projectId = snapshot.project.id;
    state.projects = (await api.projects()).projects;
  }

  async function perform(operation) {
    if (state.busy) return null;
    state.busy = true;
    state.error = null;
    state.stage = "working";
    state.message = "正在处理…";
    emit();
    try {
      const result = await operation();
      state.stage = state.snapshot?.pending ? "waiting" : "idle";
      return result;
    } catch (error) {
      state.error = error?.message || "请求失败，请检查后端服务后重新连接";
      state.stage = "failed";
      // 切换失败时继续指向屏幕上最后一次成功加载的项目。
      projectId = state.snapshot?.project.id || projectId;
      // 请求可能已经在服务端完成。只重新读取事实，不在浏览器执行或重发命令。
      if (projectId) {
        try { await synchronize(); } catch { /* 保留最后一次后端快照供查看。 */ }
      }
      return null;
    } finally {
      state.busy = false;
      emit();
    }
  }

  return {
    state,
    load(id) {
      return perform(async () => {
        projectId = id || projectId;
        if (!projectId) {
          const list = (await api.projects()).projects;
          projectId = list[0]?.id || (await api.create({})).project.id;
        }
        await synchronize();
        state.message = "所有修改由后端保存";
        state.summary = null;
        state.lastInput = "";
        state.events = [];
        state.highlights = [];
        return state.snapshot;
      });
    },
    submit(text, displayText = text) {
      const input = String(text || "").trim();
      if (!input || !state.snapshot) return Promise.resolve(null);
      return perform(async () => {
        state.lastInput = String(displayText || input);
        state.summary = null;
        state.events = [];
        state.highlights = [];
        emit();
        const pending = state.snapshot.pending;
        const result = pending
          ? await api.resume(projectId, pending.sessionId, input)
          : await api.orchestrate(projectId, input, {
              onEvent(event) {
                state.events = [...state.events, event].slice(-30);
                if (event.type === "STAGE_CHANGED") {
                  state.message = event.message || "正在处理…";
                }
                emit();
              }
            });
        if (!result) throw new Error("连接提前结束，请重新连接以确认执行结果");
        await synchronize();
        state.summary = result.summary;
        state.message = result.summary?.message || "已更新画布";
        state.highlights = (result.patches || []).flatMap(patch =>
          [patch.elementId, patch.element?.id].filter(Boolean));
        if (result.status === "FAILED") throw new Error(state.message);
        return result;
      });
    },
    action(payload) {
      if (!state.snapshot) return Promise.resolve(null);
      return perform(async () => {
        const response = await api.action(projectId, payload);
        state.snapshot = response;
        state.projects = (await api.projects()).projects;
        state.message = "修改已由后端保存";
        return response;
      });
    },
    create(title) {
      return perform(async () => {
        const response = await api.create({ title });
        projectId = response.project.id;
        await synchronize();
        state.summary = null;
        state.lastInput = "";
        state.events = [];
        state.highlights = [];
        state.message = "新项目已创建，描述你的第一个画面吧";
        return state.snapshot;
      });
    },
    import(payload) {
      return perform(async () => {
        const response = await api.import(payload);
        projectId = response.project.id;
        await synchronize();
        state.summary = null;
        state.lastInput = "";
        state.events = [];
        state.highlights = [];
        state.message = "项目已由后端校验并保存";
        return state.snapshot;
      });
    },
    export(format) {
      if (!state.snapshot) return Promise.resolve(null);
      return perform(async () => {
        const response = await api.export(projectId, {
          format, scope: format === "json" ? "project" : "active_scene"
        });
        state.message = "导出文件已准备好";
        return response.export;
      });
    }
  };
}
