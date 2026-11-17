import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  API_CONTRACT,
  COMMAND_BINDINGS,
  UI_BINDINGS,
  initialProject
} from "../fixtures/mock-data.js";
import { mergeElementPatch } from "../fixtures/element-patch.js";
import {
  sceneAtDisplayNumber,
  sceneDisplayNumber,
  visibleSceneEntries
} from "../../src/prototype/scene-numbering.js";
import { estimateTextUnits, fitTextFontSize } from "../../src/prototype/text-layout.js";
import { importProjectFile, sceneToSvg } from "../fixtures/export-service.js";
import { applyBackendEvent } from "../fixtures/state-sync.js";
import {
  isAmbientNoiseTranscript,
  isLikelyFeedbackEcho,
  VoiceSessionController,
  resolveClarificationOption
} from "../../src/prototype/voice-session.js";

const requiredEvents = [
  "TRANSCRIPT_PARTIAL",
  "TRANSCRIPT_FINAL",
  "STAGE_CHANGED",
  "PROGRESS",
  "CANVAS_PATCH_APPLIED",
  "EXPORT_COMPLETED",
  "CLARIFICATION_REQUESTED",
  "TURN_SUMMARY"
];

function testApiContract() {
  assert.equal(API_CONTRACT.orchestration.start.method, "POST");
  assert.equal(API_CONTRACT.orchestration.start.path, "/api/orchestrations");
  assert.equal(API_CONTRACT.orchestration.resume.path, "/api/orchestrations/:sessionId/resume");
  assert.equal(API_CONTRACT.orchestration.events.transport, "text/event-stream");
  assert.equal(API_CONTRACT.project.create.method, "POST");
  assert.equal(API_CONTRACT.project.create.path, "/api/projects");
  assert.equal(API_CONTRACT.project.export.path, "/api/projects/:projectId/export");
  assert.equal(API_CONTRACT.project.import.path, "/api/projects/import");
  assert.equal(API_CONTRACT.assets.catalog.method, "GET");
  assert.equal(API_CONTRACT.assets.catalog.path, "/api/assets/catalog");
  assert.equal(API_CONTRACT.userMemory.list.method, "GET");
  assert.equal(API_CONTRACT.userMemory.create.path, "/api/users/:userId/memories");
  assert.equal(API_CONTRACT.userMemory.update.method, "PATCH");
  assert.equal(API_CONTRACT.userMemory.delete.path, "/api/memories/:memoryId");

  for (const eventType of requiredEvents) {
    assert.ok(
      API_CONTRACT.orchestration.events.events.includes(eventType),
      `SSE 事件契约缺少 ${eventType}`
    );
  }
}

function testUiBindings() {
  assert.equal(UI_BINDINGS.length, 5);

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

  const memoryBinding = UI_BINDINGS.find((binding) => binding.area === "长期记忆管理面板");
  assert.ok(memoryBinding.writes.includes("UserMemoryCreateRequest"));
  assert.ok(memoryBinding.api.includes("PATCH /api/memories/:memoryId"));
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
      assert.ok(
        element.description === undefined || typeof element.description === "string",
        "元素 description 必须为空或字符串"
      );

      if (element.type === "text") {
        assert.ok(element.content?.text || element.text, "text 元素必须有可渲染文本");
      }

      if (element.type === "shape") {
        assert.ok(element.shape?.kind || element.shape, "shape 元素必须声明图形类型");
        assert.notEqual(element.content?.label, element.name, "shape 的画面标签不应依赖图层 name");
      }

      if (element.type === "connector") {
        if (element.from) assert.ok(elementIds.has(element.from.elementId));
        if (element.to) assert.ok(elementIds.has(element.to.elementId));
      }

      if (element.type === "generated_asset") {
        assert.ok(element.asset?.status, "generated_asset 必须声明生成状态");
        if (element.asset.status === "ready") {
          assert.ok(element.content?.assetId || element.content?.url, "ready 素材必须有资源引用");
        } else {
          assert.ok(element.placeholderStyle, "未完成素材必须有占位样式");
        }
      }
    }
  }
}

function testElementPatchMirrorSync() {
  const element = {
    id: "el_cat",
    type: "generated_asset",
    x: 10,
    y: 20,
    width: 120,
    height: 90,
    zIndex: 2,
    transform: { x: 10, y: 20, width: 120, height: 90 },
    layer: { zIndex: 2 },
    content: { alt: "猫" },
    asset: { kind: "character", status: "pending" },
    placeholderStyle: { fill: "#ffffff", stroke: "#1f8a5b", strokeWidth: 2 }
  };

  const legacyResize = mergeElementPatch(element, { width: 180, height: 135 });
  assert.equal(legacyResize.width, 180);
  assert.equal(legacyResize.height, 135);
  assert.equal(legacyResize.transform.width, 180);
  assert.equal(legacyResize.transform.height, 135);

  const structuredResize = mergeElementPatch(element, {
    transform: { width: 96, height: 72 },
    layer: { zIndex: 5 }
  });
  assert.equal(structuredResize.width, 96);
  assert.equal(structuredResize.height, 72);
  assert.equal(structuredResize.transform.width, 96);
  assert.equal(structuredResize.transform.height, 72);
  assert.equal(structuredResize.zIndex, 5);
  assert.equal(structuredResize.layer.zIndex, 5);
}

function testTextLayoutFontFit() {
  const compactFontSize = fitTextFontSize({
    text: "今天好开心的碰到了喜欢",
    baseFontSize: 14,
    transform: { width: 124, height: 30 }
  });
  assert.ok(compactFontSize < 14, "窄文本框内的长句必须自动缩小字号");
  assert.ok(compactFontSize >= 9, "字号适配必须保留可读下限");

  const roomyFontSize = fitTextFontSize({
    text: "开心",
    baseFontSize: 14,
    transform: { width: 124, height: 30 }
  });
  assert.equal(roomyFontSize, 14, "短文本不应被无谓缩小");
  assert.ok(estimateTextUnits("Hello 开心") > estimateTextUnits("开心"), "中英文混排必须参与宽度估算");
}

function testSceneDisplayNumberingUsesSortedVisibleIndex() {
  const scenes = [
    { id: "scene_backend_2", name: "镜头1", order: 2 },
    { id: "scene_backend_3", name: "镜头2", order: 3 },
    { id: "scene_backend_4", name: "镜头3", order: 4 }
  ];

  assert.deepEqual(
    visibleSceneEntries(scenes).map((entry) => ({
      sceneId: entry.scene.id,
      displayNumber: entry.displayNumber
    })),
    [
      { sceneId: "scene_backend_2", displayNumber: 1 },
      { sceneId: "scene_backend_3", displayNumber: 2 },
      { sceneId: "scene_backend_4", displayNumber: 3 }
    ],
    "用户可见镜头编号必须按排序后的列表从 1 开始"
  );
  assert.equal(sceneDisplayNumber(scenes, "scene_backend_2"), 1);
  assert.equal(sceneAtDisplayNumber(scenes, 2).id, "scene_backend_3");
}

function testSceneDeletePatchKeepsCanvasOnNearestScene() {
  const scene1 = {
    id: "scene_1",
    name: "主图",
    order: 1,
    description: "第一镜头",
    canvas: { width: 960, height: 540, background: { type: "solid", color: "#ffffff" } },
    elements: []
  };
  const scene2 = {
    id: "scene_2",
    name: "产品特写",
    order: 2,
    description: "第二镜头",
    canvas: { width: 960, height: 540, background: { type: "solid", color: "#ffffff" } },
    elements: []
  };
  const state = {
    project: {
      id: "project_scene_delete",
      title: "镜头删除测试",
      mode: "storyboard",
      activeSceneId: "scene_2",
      scenes: [scene1, scene2]
    },
    session: { id: "session_scene_delete", progress: {} },
    eventLog: [],
    voiceStatus: ""
  };

  applyBackendEvent(state, {
    type: "CANVAS_PATCH_APPLIED",
    sessionId: "session_scene_delete",
    commandId: "cmd_delete_scene",
    patch: {
      id: "patch_scene_deleted",
      type: "SCENE_DELETED",
      sceneId: "scene_2",
      scene: scene2,
      createdAt: "2026-06-14T00:00:00+00:00"
    }
  });

  assert.deepEqual(
    state.project.scenes.map((scene) => scene.id),
    ["scene_1"],
    "删除镜头事件必须移除左侧镜头列表中的目标镜头"
  );
  assert.equal(
    state.project.activeSceneId,
    "scene_1",
    "删除当前镜头后，中间画布必须立即切到最近可用镜头"
  );

  applyBackendEvent(state, {
    type: "CANVAS_PATCH_APPLIED",
    sessionId: "session_scene_delete",
    commandId: "cmd_undo_delete_scene",
    patch: {
      id: "patch_scene_created",
      type: "SCENE_CREATED",
      sceneId: "scene_2",
      scene: scene2,
      createdAt: "2026-06-14T00:00:01+00:00"
    }
  });
  applyBackendEvent(state, {
    type: "CANVAS_PATCH_APPLIED",
    sessionId: "session_scene_delete",
    commandId: "cmd_undo_delete_scene",
    patch: {
      id: "patch_active_scene_changed",
      type: "ACTIVE_SCENE_CHANGED",
      sceneId: "scene_2",
      createdAt: "2026-06-14T00:00:01+00:00"
    }
  });

  assert.equal(state.project.activeSceneId, "scene_2", "撤销删除镜头后必须恢复原 active 镜头");
  assert.ok(
    state.project.scenes.some((scene) => scene.id === "scene_2"),
    "撤销删除镜头必须把镜头重新投影回前端状态"
  );
}

function testBackendPatchUpdatesProjectTitleAndNarration() {
  const state = {
    project: {
      id: "project_patch_test",
      title: "旧项目名",
      mode: "storyboard",
      activeSceneId: "scene_1",
      scenes: [
        {
          id: "scene_1",
          name: "主图",
          order: 1,
          description: null,
          narration: null,
          canvas: { width: 960, height: 540, background: { type: "solid", color: "#ffffff" } },
          elements: []
        }
      ]
    },
    session: { id: "session_patch_test", progress: {} },
    eventLog: [],
    voiceStatus: ""
  };

  applyBackendEvent(state, {
    type: "CANVAS_PATCH_APPLIED",
    sessionId: "session_patch_test",
    commandId: "cmd_update_project",
    patch: {
      id: "patch_project_updated",
      type: "PROJECT_UPDATED",
      patch: { title: "低糖奶茶带货" },
      createdAt: "2026-06-14T00:00:00+00:00"
    }
  });
  applyBackendEvent(state, {
    type: "CANVAS_PATCH_APPLIED",
    sessionId: "session_patch_test",
    commandId: "cmd_update_narration",
    patch: {
      id: "patch_scene_updated",
      type: "SCENE_UPDATED",
      sceneId: "scene_1",
      patch: { narration: "快来买奶茶吧" },
      createdAt: "2026-06-14T00:00:01+00:00"
    }
  });

  assert.equal(state.project.title, "低糖奶茶带货");
  assert.equal(state.project.scenes[0].narration, "快来买奶茶吧");
}

async function testPrototypeHtml() {
  const root = new URL("../../src/prototype/", import.meta.url);
  const html = await readFile(new URL("workspace.html", root), "utf-8");
  const app = await readFile(new URL("svg-workspace.js", root), "utf-8");
  const css = await readFile(new URL("workspace.css", root), "utf-8");
  for (const id of ["voiceButton", "voiceInput", "canvasSurface", "sceneList", "undoButton",
    "redoButton", "clarificationCard", "exportButton", "textEditor", "retryButton"]) {
    assert.ok(html.includes(`id="${id}"`), `工作台缺少入口 ${id}`);
  }
  assert.ok(html.includes('src="./svg-workspace.js"'));
  for (const removed of ["memoryDialog", "memoryButton", "importButton", "backgroundColorInput", "workspace-entry.js"]) {
    assert.ok(!html.includes(removed), `工作台不应保留旧入口 ${removed}`);
  }
  assert.ok(app.includes("new StoryboardClient"));
  assert.ok(!app.includes('params.get("shot")'));
  assert.ok(!app.includes('import("./app.js")'));
  assert.ok(css.includes("prefers-reduced-motion"));
  assert.ok(css.includes("max-width:680px"));
}

class MockRecognition {
  constructor() {
    this.handlers = null;
    this.started = false;
    this.stopCount = 0;
  }

  isSupported() {
    return true;
  }

  start(handlers) {
    this.handlers = handlers;
    this.started = true;
  }

  stop() {
    this.stopCount += 1;
    this.started = false;
  }

  abort() {
    this.started = false;
  }

  emitFinal(text) {
    this.handlers.onFinal(text);
  }

  emitPartial(text) {
    this.handlers.onPartial(text);
  }
}

class MockFeedback {
  constructor() {
    this.messages = [];
    this.cancelCount = 0;
    this.readyToneCount = 0;
    this.pendingResolve = null;
    this.holdNext = false;
  }

  async say(text) {
    this.messages.push(text);
    if (!this.holdNext) return;
    this.holdNext = false;
    await new Promise((resolve) => {
      this.pendingResolve = resolve;
    });
  }

  cancel() {
    this.cancelCount += 1;
    this.pendingResolve?.();
    this.pendingResolve = null;
  }

  async playReadyTone() {
    this.readyToneCount += 1;
  }

  release() {
    this.pendingResolve?.();
    this.pendingResolve = null;
  }
}

async function testVoiceSessionController() {
  const recognition = new MockRecognition();
  const feedback = new MockFeedback();
  const submitted = [];
  const statuses = [];
  const controller = new VoiceSessionController({
    recognition,
    feedback,
    restartDelayMs: 1,
    submitTranscript: async (text) => {
      submitted.push(text);
      return { message: "已创建三个分镜" };
    },
    onStatusChange: (message) => statuses.push(message)
  });

  await controller.start();
  assert.equal(controller.isActive(), true);
  assert.equal(recognition.started, true);
  assert.equal(feedback.messages[0], "语音创作模式已开启，请说出你想绘制的内容。");
  assert.equal(feedback.readyToneCount, 1);

  await controller.handleFinalTranscript("创建一个三镜头奶茶广告分镜");
  assert.deepEqual(submitted, ["创建一个三镜头奶茶广告分镜"]);
  assert.ok(feedback.messages.includes("已创建三个分镜"));
  assert.equal(feedback.readyToneCount, 2);
  assert.equal(controller.isListening(), true);

  await controller.handleFinalTranscript("结束创作");
  assert.equal(controller.isActive(), false);
  assert.ok(statuses.includes("语音创作模式已结束"));
}

async function testVoiceSessionDoesNotListenDuringFeedback() {
  const recognition = new MockRecognition();
  const feedback = new MockFeedback();
  const submitted = [];
  const controller = new VoiceSessionController({
    recognition,
    feedback,
    restartDelayMs: 1,
    submitTranscript: async (text) => {
      submitted.push(text);
      return { message: text.includes("创建") ? "已创建三个分镜，请继续修改。" : "已撤销上一步。" };
    }
  });

  await controller.start();
  feedback.holdNext = true;
  const firstTurn = controller.handleFinalTranscript("创建一个三镜头奶茶广告分镜");
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(controller.isListening(), false, "系统播报期间必须关闭语音监听");
  assert.equal(recognition.started, false, "系统播报期间 recognition 不应保持 started");
  assert.deepEqual(submitted, ["创建一个三镜头奶茶广告分镜"]);

  feedback.release();
  await firstTurn;
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(feedback.readyToneCount, 2, "播报结束后必须播放可说话提示音");
  assert.equal(controller.isListening(), true, "提示音后必须恢复监听");

  await controller.handleFinalTranscript("撤销上一步");
  assert.deepEqual(submitted, ["创建一个三镜头奶茶广告分镜", "撤销上一步"]);
  assert.equal(feedback.cancelCount, 0, "播报期间不再通过打断监听取消系统播报");
}

async function testVoiceSessionDropsAmbientNoise() {
  const recognition = new MockRecognition();
  const feedback = new MockFeedback();
  const submitted = [];
  const statuses = [];
  const controller = new VoiceSessionController({
    recognition,
    feedback,
    restartDelayMs: 1,
    submitTranscript: async (text) => {
      submitted.push(text);
      return { message: "已处理" };
    },
    onStatusChange: (message) => statuses.push(message)
  });

  await controller.start();
  await controller.handleFinalTranscript("嗯");
  await controller.handleFinalTranscript("环境噪声");
  await controller.handleFinalTranscript("撤销上一步");

  assert.deepEqual(submitted, ["撤销上一步"]);
  assert.ok(statuses.includes("已忽略环境噪声"));
}

function testAmbientNoiseDetection() {
  assert.equal(isAmbientNoiseTranscript("嗯"), true);
  assert.equal(isAmbientNoiseTranscript("咳嗽"), true);
  assert.equal(isAmbientNoiseTranscript("环境噪声"), true);
  assert.equal(isAmbientNoiseTranscript("确认"), false);
  assert.equal(isAmbientNoiseTranscript("取消"), false);
  assert.equal(isAmbientNoiseTranscript("清空当前画布"), false);
  assert.equal(isAmbientNoiseTranscript("撤销"), false);
}

function testFeedbackEchoDetection() {
  assert.equal(isLikelyFeedbackEcho("已创建三个分镜请继续修改", "已创建三个分镜，请继续修改。"), true);
  assert.equal(isLikelyFeedbackEcho("已导出图片", "已导出图片。"), true);
  assert.equal(isLikelyFeedbackEcho("导出图片", "已导出图片。"), false);
  assert.equal(isLikelyFeedbackEcho("撤销", "已创建三个分镜，请继续修改。"), false);
}

function testClarificationOptionResolver() {
  const options = [
    {
      id: "cup_red",
      label: "红色杯子",
      value: "cup_red",
      bounds: { x: 100, y: 180, width: 80, height: 140 }
    },
    {
      id: "cup_blue",
      label: "蓝色杯子",
      value: "cup_blue",
      bounds: { x: 360, y: 180, width: 80, height: 140 }
    }
  ];

  assert.equal(resolveClarificationOption("左边那个", options).id, "cup_red");
  assert.equal(resolveClarificationOption("蓝色杯子", options).id, "cup_blue");
  assert.equal(resolveClarificationOption("第二个", options).id, "cup_blue");
}

async function testImportProjectFileValidation() {
  const validFile = {
    name: "demo.voicecanvas.json",
    type: "application/json",
    text: async () =>
      JSON.stringify({
        type: "voicecanvas.project",
        schemaVersion: 1,
        project: {
          id: "project_import_test",
          title: "导入测试",
          mode: "storyboard",
          scenes: [{ id: "scene_1", name: "空白画布", order: 1 }],
          activeSceneId: "scene_1"
        }
      })
  };
  const imported = await importProjectFile(validFile);
  assert.equal(imported.project.id, "project_import_test");

  await assert.rejects(
    () =>
      importProjectFile({
        name: "canvas.png",
        type: "image/png",
        text: async () => {
          throw new Error("不应读取非 JSON 文件内容");
        }
      }),
    /只能载入 JSON 项目文件/
  );

  await assert.rejects(
    () =>
      importProjectFile({
        name: "note.json",
        type: "application/json",
        text: async () => JSON.stringify({ hello: "world" })
      }),
    /项目文件格式不正确/
  );
}

function testSceneSvgExportsRenderedAssets() {
  const svg = sceneToSvg({
    id: "scene_export_assets",
    name: "导出图片测试",
    canvas: { width: 400, height: 240, background: { type: "solid", color: "#ffffff" } },
    elements: [
      {
        id: "el_photo",
        type: "image",
        name: "照片",
        x: 12,
        y: 16,
        width: 96,
        height: 80,
        zIndex: 1,
        content: { url: "https://cdn.example.test/photo.png", alt: "照片" }
      },
      {
        id: "el_ready_asset",
        type: "generated_asset",
        name: "已生成素材",
        x: 132,
        y: 16,
        width: 96,
        height: 80,
        zIndex: 2,
        content: { url: "data:image/png;base64,AAAA", alt: "已生成素材" },
        asset: { kind: "character", status: "ready" }
      },
      {
        id: "el_girl",
        type: "generated_asset",
        name: "小女孩",
        x: 244,
        y: 20,
        width: 90,
        height: 120,
        zIndex: 3,
        content: { alt: "小女孩" },
        asset: { kind: "character", status: "pending" },
        subject: { character: { gender: "女性" } },
        placeholderStyle: { fill: "#ffffff", stroke: "#243b53", strokeWidth: 2 }
      },
      {
        id: "el_bubble_tea",
        type: "generated_asset",
        name: "珍珠奶茶",
        x: 70,
        y: 132,
        width: 88,
        height: 88,
        zIndex: 4,
        content: { alt: "珍珠奶茶" },
        asset: { kind: "product", status: "pending" },
        metadata: {
          renderKey: "bubble-tea",
          assetPath: "catalog/commerce/food-drink/bubble-tea.png"
        },
        placeholderStyle: { fill: "#fff8dd", stroke: "#1f8a5b", strokeWidth: 2 }
      },
      {
        id: "el_arrow",
        type: "connector",
        name: "推荐箭头",
        x: 0,
        y: 0,
        width: 1,
        height: 1,
        zIndex: 5,
        connector: {
          kind: "line",
          from: { target: { type: "element", elementId: "el_girl" }, anchor: "left" },
          to: { target: { type: "element", elementId: "el_bubble_tea" }, anchor: "right" },
          routing: "straight"
        },
        content: { label: "推荐" },
        style: { stroke: "#f15b4a", strokeWidth: 4, arrowEnd: true }
      }
    ]
  });

  assert.ok(svg.includes('<image href="https://cdn.example.test/photo.png"'), "image 元素必须导出真实图片");
  assert.ok(svg.includes('<image href="data:image/png;base64,AAAA"'), "ready generated_asset 必须导出真实图片");
  assert.ok(
    svg.includes('<image href="/api/assets/catalog/raw?path=catalog%2Fcommerce%2Ffood-drink%2Fbubble-tea.png"'),
    "Catalog 素材必须导出后端代理图片"
  );
  assert.ok(svg.includes("character-illustration is-female"), "语义人物插画必须导出为真实 SVG");
  assert.ok(svg.includes("marker-end"), "连接线箭头必须导出 SVG marker");
  assert.ok(svg.includes(">推荐</text>"), "连接线标签必须随图片导出");
  assert.ok(!svg.includes(">小女孩</text>"), "可渲染语义素材不应退回占位文字");
}

testApiContract();
testUiBindings();
testCommandBindings();
testInitialProjectModel();
testElementPatchMirrorSync();
testTextLayoutFontFit();
testSceneDisplayNumberingUsesSortedVisibleIndex();
testSceneDeletePatchKeepsCanvasOnNearestScene();
testBackendPatchUpdatesProjectTitleAndNarration();
await testVoiceSessionController();
await testVoiceSessionDoesNotListenDuringFeedback();
await testVoiceSessionDropsAmbientNoise();
testAmbientNoiseDetection();
testFeedbackEchoDetection();
testClarificationOptionResolver();
await testImportProjectFileValidation();
testSceneSvgExportsRenderedAssets();
await testPrototypeHtml();

console.log("前端交互原型契约测试通过");
