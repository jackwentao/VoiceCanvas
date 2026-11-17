import { ShotApiError } from "./shot-client.js";

// 编排和绘图共享一个忙碌锁；异步响应始终绑定稳定镜头 id，禁止串写。
export class StoryboardClient {
  constructor({ shots, onChange = () => {}, exportShot = async () => {}, fetchImpl = (...args) => globalThis.fetch(...args) }) {
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

  create() {
    return this.run(async () => {
      const board = await this.request("", { title: "未命名分镜" });
      this.pendingDelete = null;
      this.accept(board);
      return board;
    });
  }

  load(id) {
    return this.run(async () => {
      const board = await this.request(`/${encodeURIComponent(id)}`);
      this.pendingDelete = null;
      this.accept(board);
      return board;
    });
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
    // 画面修改之后只刷新同一项目；保留当次网络错误，调用方可稍后重试。
    this.accept(await this.request(`/${this.board.id}`));
  }

  cancelDelete() { this.pendingDelete = null; this.onChange(this); }

  confirmDelete() {
    return this.run(async () => {
      const pending = this.pendingDelete;
      if (!pending || pending.boardId !== this.board.id) throw new Error("当前没有待确认的删除操作");
      if (pending.version !== this.board.version) { this.pendingDelete = null; throw new Error("分镜已变化，请重新指定删除目标"); }
      return this.manageRequest({ action: "delete", targetId: pending.targetId, confirmed: true }, pending.version);
    });
  }

  execute(transcript, { allowDrawing = true } = {}) {
    return this.run(async () => {
      if (!this.board) throw new Error("请先打开分镜项目");
      const reply = await this.request(`/${this.board.id}/command`, { expectedVersion: this.board.version, transcript });
      const pending = this.pendingDelete;
      this.accept(reply.board);
      const currentNumber = () => this.board.shots.findIndex(s => s.id === this.board.activeId) + 1;
      if (reply.action === "cancel") { this.cancelDelete(); return "已取消删除"; }
      if (reply.action === "confirm") {
        if (!pending || pending.boardId !== this.board.id || pending.version !== this.board.version) {
          this.cancelDelete(); throw new Error("当前没有有效的删除确认，请重新指定镜头");
        }
        await this.manageRequest({ action: "delete", targetId: pending.targetId, confirmed: true }, pending.version);
        return `已删除镜头。可说“撤销分镜操作”恢复。当前第 ${currentNumber()} 镜头。`;
      }
      this.pendingDelete = null;
      if (reply.action === "request_delete") {
        const index = this.board.shots.findIndex(s => s.id === reply.targetId);
        const target = this.board.shots[index];
        this.pendingDelete = { boardId: this.board.id, version: this.board.version, targetId: target.id,
          message: `删除第 ${index + 1} 镜头“${target.title}”？说“确认删除”或“取消”。` };
        this.onChange(this);
        return this.pendingDelete.message;
      }
      if (reply.action === "new_project") {
        this.accept(await this.request("", { title: "未命名分镜" }));
        return "已新建分镜项目，当前是第一个镜头。";
      }
      if (reply.action === "export_png" || reply.action === "export_svg") {
        await this.exportShot(reply.action === "export_svg" ? "svg" : "png");
        return "已导出当前镜头。";
      }
      if (reply.action === "list") return `共 ${this.board.shots.length} 个镜头：${this.board.shots.map((s, i) => `${i + 1}，${s.title}`).join("；")}。当前第 ${currentNumber()} 镜头。`;
      if (reply.action === "draw") {
        if (!allowDrawing) throw new Error("文字预览尚未应用，请先应用或关闭编辑面板，再绘制画面");
        if (reply.targetId !== this.board.activeId) await this.manageRequest({ action: "switch", targetId: reply.targetId });
        await this.shots.change("generate", reply.instruction);
        await this.refresh();
        return `第 ${currentNumber()} 镜头已保存。`;
      }
      if (reply.action === "undo_shot" || reply.action === "redo_shot") {
        await this.shots.change(reply.action === "undo_shot" ? "undo" : "redo");
        await this.refresh();
        return `已${reply.action === "undo_shot" ? "撤销" : "重做"}当前镜头的画面修改。`;
      }
      return `已完成。共 ${this.board.shots.length} 个镜头，当前第 ${currentNumber()} 镜头“${this.board.shots[currentNumber() - 1].title}”。`;
    });
  }
}
