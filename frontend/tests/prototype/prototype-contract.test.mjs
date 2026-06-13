import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  API_CONTRACT,
  COMMAND_BINDINGS,
  UI_BINDINGS,
  initialProject
} from "../../src/prototype/mock-data.js";
import { mergeElementPatch } from "../../src/prototype/element-patch.js";

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

async function testPrototypeHtml() {
  const html = await readFile(new URL("../../src/prototype/index.html", import.meta.url), "utf-8");
  const app = await readFile(new URL("../../src/prototype/app.js", import.meta.url), "utf-8");
  const css = await readFile(new URL("../../src/prototype/styles.css", import.meta.url), "utf-8");
  const renderCatalog = JSON.parse(
    await readFile(new URL("../../src/prototype/render-catalog.json", import.meta.url), "utf-8")
  );
  const backendClient = await readFile(
    new URL("../../src/prototype/backend-client.js", import.meta.url),
    "utf-8"
  );
  const stateSync = await readFile(
    new URL("../../src/prototype/state-sync.js", import.meta.url),
    "utf-8"
  );

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
  assert.ok(app.includes("hydrateBackendState"), "原型启动时必须拉取后端 Project State");
  assert.ok(app.includes("runBackendInput"), "AI 指令必须统一进入后端编排入口");
  assert.ok(app.includes("applyBackendResponse"), "后端响应必须统一归并到页面状态");
  assert.ok(app.includes("renderConnectorLayer"), "画布必须提供独立 SVG 连接层");
  assert.ok(app.includes("createElementLayoutIndex"), "连接线必须依赖元素布局索引计算端点");
  assert.ok(app.includes("<path"), "连接线必须使用 SVG path 渲染");
  assert.ok(app.includes("marker-end"), "箭头必须使用 SVG marker 渲染");
  assert.ok(app.includes("renderGeneratedAssetElement"), "画布必须支持生成素材渲染");
  assert.ok(app.includes("hydrateRenderCatalog"), "前端必须加载 Render Catalog");
  assert.ok(app.includes("renderCatalogState"), "前端必须建立 Render Catalog 索引");
  assert.ok(app.includes("getIllustrationRenderer"), "前端必须通过 renderer registry 分发语义插画");
  assert.ok(app.includes("metadata.renderKey"), "前端必须优先使用后端显式 renderKey");
  assert.ok(app.includes("renderSemanticIllustrationElement"), "画布必须支持语义对象插画渲染");
  assert.ok(app.includes("characterIllustrationSvg"), "画布必须使用通用人物插画渲染器");
  assert.ok(app.includes("renderVariant"), "画布必须支持后端传入的人物渲染变体");
  assert.ok(app.includes('data-variant="${spec.variant || ""}"'), "人物渲染变体必须落到 DOM 便于视觉 QA");
  assert.ok(app.includes("catIllustrationSvg"), "画布必须能把猫渲染成专门插画");
  assert.ok(app.includes("tableIllustrationSvg"), "画布必须能把桌子渲染成专门插画");
  assert.ok(app.includes("metadata?.renderHint"), "前端必须优先使用后端显式渲染提示");
  assert.ok(app.includes("semanticSpecFromSubject"), "前端必须支持 subject 结构化主体识别");
  assert.ok(!app.includes('|| "girl"'), "人物识别不能把未知 character 默认画成女生");
  assert.ok(!app.includes("asset?.prompt ||"), "前端不能根据 prompt 场景词决定插画主体");
  assert.ok(app.indexOf('text.includes("男生")') < app.indexOf('text.includes("女生")'), "男生主体识别必须在通用人物识别前处理");
  assert.ok(!app.includes("element.name || element.shape"), "shape 不应把图层 name 当画面内容渲染");
  assert.ok(css.includes(".connector-layer"), "CSS 必须定义连接层样式");
  assert.ok(css.includes(".illustration-element"), "CSS 必须定义语义插画元素样式");
  assert.ok(css.includes(".character-shirt"), "CSS 必须定义人物上衣样式");
  assert.ok(css.includes(".character-dress"), "CSS 必须定义女性人物裙装样式");
  assert.ok(css.includes(".character-pants"), "CSS 必须定义男性人物裤装样式");
  assert.ok(css.includes(".cat-body"), "CSS 必须定义猫插画样式");
  assert.ok(css.includes(".table-top"), "CSS 必须定义桌子插画样式");
  assert.ok(backendClient.includes("/api/orchestrations"), "前端客户端必须绑定编排 API");
  assert.ok(backendClient.includes("/api/projects/"), "前端客户端必须绑定项目状态 API");
  assert.ok(stateSync.includes("CANVAS_PATCH_APPLIED"), "状态归并层必须保留画布事件投影能力");
  assert.ok(stateSync.includes("CLARIFICATION_REQUESTED"), "状态归并层必须保留澄清事件投影能力");
  assert.ok(css.includes(".settings-popover[hidden]"), "设置菜单 hidden 状态必须真正隐藏");

  const catalogItems = new Map(renderCatalog.items.map((item) => [item.renderKey, item]));
  assert.equal(renderCatalog.version, 1, "Render Catalog 必须有版本");
  assert.equal(catalogItems.get("character")?.directRender, true, "人物必须声明本地 direct renderer");
  assert.equal(catalogItems.get("dog")?.directRender, false, "未接入 renderer 的对象必须走 placeholder");
  assert.ok(
    catalogItems.get("character")?.variants?.some((variant) => variant.key === "male"),
    "人物 catalog 必须声明 male variant"
  );
}

testApiContract();
testUiBindings();
testCommandBindings();
testInitialProjectModel();
testElementPatchMirrorSync();
await testPrototypeHtml();

console.log("前端交互原型契约测试通过");
