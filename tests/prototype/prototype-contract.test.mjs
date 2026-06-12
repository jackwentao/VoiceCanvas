import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  API_CONTRACT,
  COMMAND_BINDINGS,
  UI_BINDINGS,
  initialProject
} from "../../src/prototype/mock-data.js";

const requiredEvents = [
  "TRANSCRIPT_PARTIAL",
  "TRANSCRIPT_FINAL",
  "STAGE_CHANGED",
  "PROGRESS",
  "CANVAS_PATCH_APPLIED",
  "CLARIFICATION_REQUESTED",
  "TURN_SUMMARY"
];

function testApiContract() {
  assert.equal(API_CONTRACT.orchestration.start.method, "POST");
  assert.equal(API_CONTRACT.orchestration.start.path, "/api/orchestrations");
  assert.equal(API_CONTRACT.orchestration.resume.path, "/api/orchestrations/:sessionId/resume");
  assert.equal(API_CONTRACT.orchestration.events.transport, "text/event-stream");
  assert.equal(API_CONTRACT.project.export.path, "/api/projects/:projectId/export");

  for (const eventType of requiredEvents) {
    assert.ok(
      API_CONTRACT.orchestration.events.events.includes(eventType),
      `SSE 事件契约缺少 ${eventType}`
    );
  }
}

function testUiBindings() {
  assert.equal(UI_BINDINGS.length, 4);

  for (const binding of UI_BINDINGS) {
    assert.ok(binding.area, "每个 UI 区域必须有名称");
    assert.ok(binding.components.length > 0, `${binding.area} 必须绑定组件`);
    assert.ok(binding.reads.length > 0, `${binding.area} 必须声明读取模型`);
    assert.ok(binding.api.length > 0, `${binding.area} 必须声明后端接口`);
  }

  const canvasBinding = UI_BINDINGS.find((binding) => binding.area === "中间结构化画布");
  assert.ok(canvasBinding.events.includes("CANVAS_PATCH_APPLIED"));
  assert.deepEqual(canvasBinding.writes, [], "结构化画布不能直接写 Project");

  const aiBinding = UI_BINDINGS.find((binding) => binding.area === "右侧 AI 交互栏");
  assert.ok(aiBinding.writes.includes("OrchestratorInput"));
  assert.ok(aiBinding.events.includes("CLARIFICATION_REQUESTED"));
}

function testCommandBindings() {
  assert.ok(COMMAND_BINDINGS.length >= 4);

  const clarification = COMMAND_BINDINGS.find((binding) => binding.firstAction === "ASK_CLARIFICATION");
  assert.ok(clarification, "必须覆盖可恢复澄清链路");
  assert.ok(clarification.events.includes("CLARIFICATION_REQUESTED"));
  assert.equal(clarification.commands.length, 0);

  const exportBinding = COMMAND_BINDINGS.find((binding) => binding.commands.includes("EXPORT_PROJECT"));
  assert.ok(exportBinding, "必须覆盖导出项目命令");

  for (const binding of COMMAND_BINDINGS) {
    assert.ok(binding.userInput.length > 0, `${binding.intent} 必须保留测试语料`);
    assert.ok(binding.endpoint.includes("/api/"), `${binding.intent} 必须绑定 API 入口`);
    assert.ok(binding.events.length > 0, `${binding.intent} 必须绑定运行事件`);
  }
}

function testInitialProjectModel() {
  assert.ok(initialProject.id.startsWith("project_"));
  assert.equal(initialProject.mode, "storyboard");
  assert.ok(initialProject.scenes.length >= 3);
  assert.ok(
    initialProject.scenes.some((scene) => scene.id === initialProject.activeSceneId),
    "activeSceneId 必须指向现有 Scene"
  );

  const orders = new Set(initialProject.scenes.map((scene) => scene.order));
  assert.equal(orders.size, initialProject.scenes.length, "Scene order 不能重复");

  for (const scene of initialProject.scenes) {
    assert.ok(scene.id.startsWith("scene_"));
    assert.ok(scene.canvas.width > 0);
    assert.ok(scene.canvas.height > 0);

    const elementIds = new Set(scene.elements.map((element) => element.id));

    for (const element of scene.elements) {
      assert.ok(element.id.startsWith("el_"));
      assert.ok(Number.isFinite(element.x));
      assert.ok(Number.isFinite(element.y));
      assert.ok(element.width > 0);
      assert.ok(element.height > 0);
      assert.ok(Number.isFinite(element.zIndex));

      if (element.type === "connector") {
        if (element.from) assert.ok(elementIds.has(element.from.elementId));
        if (element.to) assert.ok(elementIds.has(element.to.elementId));
      }
    }
  }
}

async function testPrototypeHtml() {
  const html = await readFile(new URL("../../src/prototype/index.html", import.meta.url), "utf-8");
  const app = await readFile(new URL("../../src/prototype/app.js", import.meta.url), "utf-8");
  const css = await readFile(new URL("../../src/prototype/styles.css", import.meta.url), "utf-8");

  assert.ok(html.includes('data-run="voice"'), "AI 交互栏必须提供语音输入按钮");
  assert.ok(html.includes('aria-label="开始语音输入"'), "语音按钮必须提供可访问名称");
  assert.ok(html.includes("voiceStatus"), "AI 交互栏必须展示语音识别状态");
  assert.ok(html.includes('data-menu-toggle="settings"'), "顶部必须提供设置菜单入口");
  assert.ok(html.includes('data-project-action="new"'), "设置菜单必须提供新建项目入口");
  assert.ok(html.includes('data-project-action="load"'), "设置菜单必须提供载入项目入口");
  assert.ok(html.includes('data-project-action="export-image"'), "设置菜单必须提供导出图片入口");
  assert.ok(!html.includes("contract-panel"), "开发契约面板不应出现在最终交互原型界面中");
  assert.ok(!app.includes("renderContractPanel"), "前端原型不应渲染底部契约调试面板");
  assert.ok(app.includes("isVoiceShortcut"), "原型必须封装语音快捷键判断");
  assert.ok(app.includes('event.altKey && event.code === "KeyV"'), "原型必须支持 Alt+V 语音快捷键");
  assert.ok(app.includes('runButton.dataset.run === "voice"'), "语音按钮必须保留点击触发");
  assert.ok(app.includes('voiceButton?.addEventListener("click"'), "语音按钮必须有直接点击监听");
  assert.ok(app.includes('sendButton?.addEventListener("click"'), "发送按钮必须有直接点击监听");
  assert.ok(app.includes('document.addEventListener("keyup"'), "快捷键必须支持松开发送");
  assert.ok(app.includes("submitVoiceDraft"), "语音转写后必须由用户手动发送");
  assert.ok(app.includes("识别完成，等待修改或发送"), "识别完成后必须停留在可编辑草稿状态");
  assert.ok(css.includes(".settings-popover[hidden]"), "设置菜单 hidden 状态必须真正隐藏");
}

testApiContract();
testUiBindings();
testCommandBindings();
testInitialProjectModel();
await testPrototypeHtml();

console.log("前端交互原型契约测试通过");
