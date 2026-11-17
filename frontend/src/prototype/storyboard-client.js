import { ShotApiError } from "./shot-client.js";

// 编排和绘图共享一个忙碌锁；异步响应始终绑定稳定镜头 id，禁止串写。
export class StoryboardClient {
  constructor({ shots, onChange = () => {}, exportShot = async () => {}, fetchImpl = (...args) => globalThis.fetch(...args), pause = ms => new Promise(resolve => setTimeout(resolve, ms)) }) {
    this.pause = pause;
    this.agent = null;
    this.shots = shots;
    this.onChange = onChange;
    this.fetch = fetchImpl;
    this.exportShot = exportShot;
    this.board = null;
    this.busy = false;
    this.pendingDelete = null;
  }

  async request(path = "", body) {
    const response = await this.fetch(`${this.shots.baseUrl}/api/storyboards${path}`, {
      method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const result = await response.json();
    if (!response.ok) throw new ShotApiError(typeof result.detail === "string" ? result.detail : "分镜参数无效", response.status);
    return result;
  }

  accept(board) {
    this.board = board;
    this.shots.shot = board.activeShot;
    this.shots.onChange(this.shots);
    this.onChange(this);
  }

  async run(action) {
    if (this.busy || this.shots.busy) throw new Error("正在完成上一条指令，请稍候");
    this.busy = true;
    this.onChange(this);
    try { return await action(); }
    catch (error) {
      if (error.status === 409 && this.board) {
        this.pendingDelete = null;
        this.accept(await this.request(`/${this.board.id}`));
      }
      throw error;
    } finally { this.busy = false; this.onChange(this); }
  }

  create(title = "未命名分镜") {
    return this.run(async () => {
      const board = await this.request("", { title });
      this.pendingDelete = null;
      this.agent = null;
      this.accept(board);
      return board;
    });
  }

  load(id) {
    return this.run(async () => {
      const reply = await this.request(`/${encodeURIComponent(id)}/agent/run`);
      this.acceptRun(reply);
      if (this.agent?.status === "running") await this.follow();
      return this.board;
    });
  }

  acceptRun(reply) {
    this.agent = reply.run;
    const pending = this.agent?.pendingDelete;
    const target = reply.board.shots.find(s => s.id === pending?.shotId);
    this.pendingDelete = pending && target && pending.version === reply.board.version ? {
      boardId: reply.board.id, version: pending.version, targetId: pending.shotId,
      message: `删除镜头“${target.title}”？请确认删除或取消。`,
    } : null;
    this.accept(reply.board);
  }

  async follow() {
    const id = this.board.id;
    while (this.agent?.status === "running") {
      await this.pause(1200);
      const reply = await this.request(`/${id}/agent/run`);
      if (this.board.id !== id) throw new Error("当前项目已变化，请重新打开任务");
      this.acceptRun(reply);
    }
    if (["failed", "interrupted"].includes(this.agent?.status)) throw new Error(this.agent.summary);
  }

  async manageRequest(fields, version = this.board.version) {
    const board = await this.request(`/${this.board.id}/manage`, { ...fields, expectedVersion: version });
    this.pendingDelete = null;
    this.accept(board);
    return board;
  }

  manage(fields) { return this.run(() => this.manageRequest(fields)); }

  async refresh() {
    if (!this.board) return;
    const reply = await this.request(`/${this.board.id}/agent/run`);
    this.acceptRun(reply);
    if (this.agent?.status === "running") return this.run(() => this.follow());
  }

  cancelDelete() { return this.execute("取消删除"); }
  confirmDelete() { return this.execute("确认删除"); }

  execute(request, { allowDrawing = true } = {}) {
    return this.run(async () => {
      if (!this.board) throw new Error("请先打开分镜项目");
      if (!allowDrawing) throw new Error("文字预览尚未应用，请先应用或关闭编辑面板");
      const reply = await this.request(`/${this.board.id}/agent/runs`, {
        expectedVersion: this.board.version, request,
      });
      this.acceptRun(reply);
      await this.follow();
      let summary = this.agent?.summary || "任务已保存";
      // 只有本次主动提交才触发下载；刷新恢复不重复下载历史任务。
      const actions = this.agent?.clientActions || [];
      const seen = new Set();
      for (const action of actions) {
        const key = `${action.shotId}:${action.format}`;
        if (seen.has(key)) continue;
        seen.add(key);
        await this.exportShot(action.format, action.shotId);
      }
      if (seen.size) summary += `\n已向浏览器发起 ${seen.size} 个文件下载。`;
      return summary;
    });
  }
}
