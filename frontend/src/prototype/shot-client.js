// 单镜头客户端只管理请求与版本；UI 和模型实现都不进入这一层。
export class ShotApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export class ShotClient {
  constructor({ baseUrl = "http://127.0.0.1:8000", fetchImpl = (...args) => globalThis.fetch(...args),
    onChange = () => {} } = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetch = fetchImpl;
    this.onChange = onChange;
    this.shot = null;
    this.busy = false;
  }

  async request(path, body) {
    const response = await this.fetch(`${this.baseUrl}/api/shots${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new ShotApiError(typeof data.detail === "string" ? data.detail : "请求参数无效，请检查输入", response.status);
    }
    return data;
  }

  async run(action) {
    if (this.busy) throw new Error("正在完成上一条指令，请稍候");
    this.busy = true;
    this.onChange(this);
    try {
      this.shot = await action();
      return this.shot;
    } finally {
      this.busy = false;
      this.onChange(this);
    }
  }

  create() { return this.run(() => this.request("", { title: "未命名镜头" })); }
  load(id) { return this.run(() => this.request(`/${encodeURIComponent(id)}`)); }

  change(action, instruction) {
    if (!this.shot) return Promise.reject(new Error("请先打开一个镜头"));
    const { id, version } = this.shot;
    return this.run(async () => {
      try {
        return await this.request(`/${encodeURIComponent(id)}/${action}`, {
          expectedVersion: version, ...(instruction === undefined ? {} : { instruction }),
        });
      } catch (error) {
        // 冲突只同步最新文档，不自动重复付费生成。
        if (error.status === 409) this.shot = await this.request(`/${encodeURIComponent(id)}`);
        throw error;
      }
    });
  }
}
