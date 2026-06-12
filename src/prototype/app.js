import { COMMAND_BINDINGS, initialHistory, initialProject, initialSession } from "./mock-data.js";

const state = {
  project: structuredClone(initialProject),
  history: structuredClone(initialHistory),
  session: structuredClone(initialSession),
  eventLog: [],
  selectedElementId: null,
  voiceStatus: "等待语音输入",
  voiceRecording: null,
  voiceDraftReady: false,
  settingsOpen: false
};

const stageLabels = {
  listening: "监听中",
  understanding: "理解需求",
  planning: "拆解任务",
  calling_tool: "调用工具",
  executing: "执行命令",
  waiting_for_user: "等待确认",
  summarizing: "总结变更",
  completed: "已完成",
  failed: "执行失败"
};

const commandSummaries = {
  CREATE_SCENE: "创建镜头",
  UPDATE_SCENE: "更新镜头",
  DELETE_SCENE: "删除镜头",
  SWITCH_SCENE: "切换镜头",
  ADD_ELEMENT: "新增元素",
  UPDATE_ELEMENT: "修改元素",
  DELETE_ELEMENT: "删除元素",
  ARRANGE_LAYOUT: "调整布局",
  UPDATE_PROJECT_STYLE: "更新风格",
  EXPORT_PROJECT: "导出项目"
};

const $ = (selector) => document.querySelector(selector);

function nowIso() {
  return new Date().toISOString();
}

function makeId(prefix) {
  return `${prefix}_${Math.random().toString(36).slice(2, 8)}`;
}

function activeScene() {
  return state.project.scenes.find((scene) => scene.id === state.project.activeSceneId);
}

function pushEvent(event) {
  state.eventLog.unshift({
    id: makeId("event"),
    createdAt: nowIso(),
    ...event
  });
  state.eventLog = state.eventLog.slice(0, 14);
}

function pushHistory(command, patches, summary) {
  state.history.unshift({
    id: makeId("history"),
    command,
    patches,
    summary,
    status: "applied",
    createdAt: nowIso()
  });
}

function publishStage(stage, message) {
  state.session.stage = stage;
  pushEvent({
    type: "STAGE_CHANGED",
    sessionId: state.session.id,
    stage,
    message
  });
}

function publishPatch(patch, commandId) {
  pushEvent({
    type: "CANVAS_PATCH_APPLIED",
    sessionId: state.session.id,
    patch,
    commandId
  });
}

function executeCommand(command) {
  const patches = [];
  const timestamp = nowIso();

  if (command.type === "SWITCH_SCENE") {
    state.project.activeSceneId = command.payload.sceneId;
    patches.push({
      id: makeId("patch"),
      commandId: command.id,
      type: "ACTIVE_SCENE_CHANGED",
      sceneId: command.payload.sceneId,
      createdAt: timestamp
    });
  }

  if (command.type === "ADD_ELEMENT") {
    const targetScene = state.project.scenes.find((scene) => scene.id === command.payload.sceneId);
    const element = {
      id: makeId("el"),
      createdAt: timestamp,
      updatedAt: timestamp,
      ...command.payload.element
    };
    targetScene.elements.push(element);
    targetScene.updatedAt = timestamp;
    patches.push({
      id: makeId("patch"),
      commandId: command.id,
      type: "ELEMENT_ADDED",
      sceneId: targetScene.id,
      element,
      createdAt: timestamp
    });
  }

  if (command.type === "UPDATE_ELEMENT") {
    const targetScene = state.project.scenes.find((scene) => scene.id === command.payload.sceneId);
    const element = targetScene.elements.find((item) => item.id === command.payload.elementId);
    Object.assign(element, command.payload.patch, { updatedAt: timestamp });
    targetScene.updatedAt = timestamp;
    patches.push({
      id: makeId("patch"),
      commandId: command.id,
      type: "ELEMENT_UPDATED",
      sceneId: targetScene.id,
      elementId: element.id,
      patch: command.payload.patch,
      createdAt: timestamp
    });
  }

  if (command.type === "EXPORT_PROJECT") {
    state.project.metadata.lastExportedAt = timestamp;
    patches.push({
      id: makeId("patch"),
      commandId: command.id,
      type: "EXPORT_COMPLETED",
      result: {
        format: command.payload.format,
        data: command.payload.format === "json" ? state.project : undefined,
        url: command.payload.format !== "json" ? "local://prototype-export.png" : undefined,
        createdAt: timestamp
      },
      createdAt: timestamp
    });
  }

  patches.forEach((patch) => publishPatch(patch, command.id));
  pushHistory(command, patches, `${commandSummaries[command.type]}：${command.reason || "原型命令"}`);
}

function beginSession(userInput) {
  const sessionId = makeId("session");
  state.session = {
    id: sessionId,
    status: "RUNNING",
    stage: "listening",
    originalUserInput: userInput,
    currentUserInput: userInput,
    progress: {
      completedSteps: 0,
      totalSteps: 3,
      message: "收到语音输入"
    },
    taskPlan: null,
    pendingClarification: null,
    lastSummary: null
  };
  pushEvent({
    type: "TRANSCRIPT_FINAL",
    sessionId,
    text: userInput
  });
}

function submitVoiceDraft() {
  const input = $("#voiceInput").value.trim();
  if (!input) return;

  state.voiceDraftReady = false;
  state.voiceStatus = "已发送";
  runCustomInput();
}

async function playEvents(steps) {
  setBusy(true);
  for (const step of steps) {
    await wait(step.delay || 420);
    step.run();
    render();
  }
  setBusy(false);
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function setBusy(isBusy) {
  document.body.dataset.busy = String(isBusy);
  document.querySelectorAll("[data-run]").forEach((button) => {
    button.disabled = isBusy;
  });
}

function runStoryboardDemo() {
  const input = COMMAND_BINDINGS[0].userInput;
  beginSession(input);
  const commands = [
    {
      id: makeId("cmd"),
      type: "SWITCH_SCENE",
      source: "ai",
      reason: "先展示主图镜头",
      createdAt: nowIso(),
      payload: { sceneId: "scene_hook" }
    },
    {
      id: makeId("cmd"),
      type: "ADD_ELEMENT",
      source: "ai",
      reason: "补充新品上市标签",
      createdAt: nowIso(),
      payload: {
        sceneId: "scene_hook",
        element: {
          name: "新品上市标签",
          type: "text",
          text: "新品上市",
          x: 606,
          y: 88,
          width: 170,
          height: 52,
          zIndex: 5,
          style: {
            fontSize: 28,
            fontWeight: "bold",
            color: "#173b2c",
            align: "center",
            backgroundColor: "#f6c453"
          }
        }
      }
    },
    {
      id: makeId("cmd"),
      type: "SWITCH_SCENE",
      source: "ai",
      reason: "继续展示卖点镜头",
      createdAt: nowIso(),
      payload: { sceneId: "scene_product" }
    }
  ];

  playEvents([
    {
      run: () => publishStage("understanding", "识别到三镜头带货分镜")
    },
    {
      run: () => {
        state.session.taskPlan = {
          goal: "生成低糖奶茶带货分镜",
          tasks: [
            { id: "task_1", title: "确认主图钩子", status: "completed", relatedSceneId: "scene_hook" },
            { id: "task_2", title: "补充新品标签", status: "in_progress", relatedSceneId: "scene_hook" },
            { id: "task_3", title: "切到卖点镜头", status: "pending", relatedSceneId: "scene_product" }
          ]
        };
        state.session.progress = {
          completedSteps: 1,
          totalSteps: 3,
          message: "正在补充关键卖点"
        };
        publishStage("planning", "拆成镜头、元素、卖点三步");
        pushEvent({
          type: "PROGRESS",
          sessionId: state.session.id,
          progress: state.session.progress
        });
      }
    },
    {
      run: () => {
        publishStage("executing", "通过 CommandExecutor 执行画布命令");
        commands.slice(0, 2).forEach(executeCommand);
        state.session.progress = {
          completedSteps: 2,
          totalSteps: 3,
          message: "主图已补充新品标签"
        };
      }
    },
    {
      run: () => {
        executeCommand(commands[2]);
        state.session.progress = {
          completedSteps: 3,
          totalSteps: 3,
          message: "已切换到卖点镜头"
        };
        state.session.status = "COMPLETED";
        state.session.lastSummary = {
          userInput: input,
          completed: true,
          stage: "completed",
          changes: [
            {
              type: "updated",
              targetType: "scene",
              targetName: "主图",
              description: "补充新品上市标签"
            },
            {
              type: "updated",
              targetType: "scene",
              targetName: "卖点",
              description: "切换为当前编辑镜头"
            }
          ]
        };
        publishStage("completed", "本轮变更已完成");
        pushEvent({
          type: "TURN_SUMMARY",
          sessionId: state.session.id,
          summary: state.session.lastSummary
        });
      }
    }
  ]);
}

function runArrowDemo() {
  const input = COMMAND_BINDINGS[1].userInput;
  beginSession(input);
  const commands = [
    {
      id: makeId("cmd"),
      type: "SWITCH_SCENE",
      source: "ai",
      reason: "定位到第二镜头",
      createdAt: nowIso(),
      payload: { sceneId: "scene_product" }
    },
    {
      id: makeId("cmd"),
      type: "ADD_ELEMENT",
      source: "ai",
      reason: "从奶茶产品指向低糖标签",
      createdAt: nowIso(),
      payload: {
        sceneId: "scene_product",
        element: {
          name: "核心卖点箭头",
          type: "connector",
          connectorType: "arrow",
          from: { elementId: "el_product_cup", anchor: "right" },
          to: { elementId: "el_low_sugar_tag", anchor: "left" },
          text: "核心卖点",
          x: 555,
          y: 174,
          width: 118,
          height: 22,
          zIndex: 5,
          style: {
            stroke: "#f15b4a",
            strokeWidth: 4,
            arrowEnd: true
          }
        }
      }
    }
  ];

  playEvents([
    {
      run: () => publishStage("understanding", "目标元素已匹配：奶茶产品、低糖标签")
    },
    {
      run: () => {
        publishStage("executing", "执行 SWITCH_SCENE 和 ADD_ELEMENT");
        commands.forEach(executeCommand);
      }
    },
    {
      run: () => {
        state.session.status = "COMPLETED";
        state.session.lastSummary = {
          userInput: input,
          completed: true,
          stage: "completed",
          changes: [
            {
              type: "created",
              targetType: "element",
              targetName: "核心卖点箭头",
              description: "新增从奶茶产品到低糖标签的箭头"
            }
          ]
        };
        publishStage("completed", "箭头已添加");
        pushEvent({
          type: "TURN_SUMMARY",
          sessionId: state.session.id,
          summary: state.session.lastSummary
        });
      }
    }
  ]);
}

function runClarificationDemo() {
  const input = COMMAND_BINDINGS[2].userInput;
  beginSession(input);
  playEvents([
    {
      run: () => publishStage("understanding", "发现多个标题候选")
    },
    {
      run: () => {
        state.session.status = "WAITING_FOR_USER";
        state.session.stage = "waiting_for_user";
        state.session.pendingClarification = {
          id: makeId("clarification"),
          originalInput: input,
          question: "当前有主标题、低糖标签和优惠标签，你想移动哪一个？",
          expectedAnswerType: "element_selection",
          options: [
            { id: "el_title_hook", label: "主标题", value: "el_title_hook" },
            { id: "el_low_sugar_tag", label: "低糖标签", value: "el_low_sugar_tag" },
            { id: "el_offer", label: "优惠标签", value: "el_offer" }
          ],
          createdAt: nowIso()
        };
        pushEvent({
          type: "CLARIFICATION_REQUESTED",
          sessionId: state.session.id,
          question: state.session.pendingClarification.question,
          options: state.session.pendingClarification.options
        });
      }
    }
  ]);
}

function resumeClarification(elementId) {
  if (!state.session.pendingClarification) return;

  const targetScene = state.project.scenes.find((scene) => scene.elements.some((element) => element.id === elementId));
  const command = {
    id: makeId("cmd"),
    type: "UPDATE_ELEMENT",
    source: "ai",
    reason: "恢复澄清后移动目标标题",
    createdAt: nowIso(),
    payload: {
      sceneId: targetScene.id,
      elementId,
      patch: {
        y: 36,
        zIndex: 8
      }
    }
  };

  beginSession(`澄清回答：${elementId}`);
  playEvents([
    {
      run: () => publishStage("executing", "恢复原任务并执行 UPDATE_ELEMENT")
    },
    {
      run: () => {
        executeCommand({
          id: makeId("cmd"),
          type: "SWITCH_SCENE",
          source: "ai",
          reason: "定位到目标元素所在镜头",
          createdAt: nowIso(),
          payload: { sceneId: targetScene.id }
        });
        executeCommand(command);
        state.session.status = "COMPLETED";
        state.session.lastSummary = {
          userInput: "把标题放上面",
          completed: true,
          stage: "completed",
          changes: [
            {
              type: "updated",
              targetType: "element",
              targetName: targetScene.elements.find((element) => element.id === elementId).name,
              description: "已移动到画布顶部"
            }
          ]
        };
        publishStage("completed", "澄清任务已恢复完成");
        pushEvent({
          type: "TURN_SUMMARY",
          sessionId: state.session.id,
          summary: state.session.lastSummary
        });
      }
    }
  ]);
}

function runExportDemo() {
  const input = COMMAND_BINDINGS[3].userInput;
  beginSession(input);
  playEvents([
    {
      run: () => publishStage("executing", "调用 Exporter 导出 Project JSON")
    },
    {
      run: () => {
        executeCommand({
          id: makeId("cmd"),
          type: "EXPORT_PROJECT",
          source: "ai",
          reason: "导出项目结构化数据",
          createdAt: nowIso(),
          payload: {
            format: "json",
            scope: "project"
          }
        });
        state.session.status = "COMPLETED";
        state.session.lastSummary = {
          userInput: input,
          completed: true,
          stage: "completed",
          changes: [
            {
              type: "exported",
              targetType: "export",
              targetName: "Project JSON",
              description: "已导出结构化项目数据"
            }
          ]
        };
        publishStage("completed", "导出完成");
        pushEvent({
          type: "TURN_SUMMARY",
          sessionId: state.session.id,
          summary: state.session.lastSummary
        });
      }
    }
  ]);
}

function runProjectAction(action) {
  state.settingsOpen = false;

  if (action === "new") {
    const command = {
      id: makeId("cmd"),
      type: "CREATE_SCENE",
      source: "user_ui",
      reason: "新建项目入口已触发",
      createdAt: nowIso(),
      payload: {
        name: "新项目",
        activate: true
      }
    };
    pushHistory(command, [], "新建项目：原型中保留当前项目并展示入口反馈");
    state.voiceStatus = "已触发新建项目入口";
    pushEvent({
      type: "TURN_SUMMARY",
      sessionId: state.session.id,
      summary: {
        userInput: "新建项目",
        completed: true,
        stage: "completed",
        changes: [
          {
            type: "created",
            targetType: "project",
            targetName: "新项目",
            description: "真实实现将调用 POST /api/projects"
          }
        ]
      }
    });
  }

  if (action === "load") {
    state.voiceStatus = "已触发载入项目入口";
    pushHistory(
      {
        id: makeId("cmd"),
        type: "SWITCH_SCENE",
        source: "user_ui",
        reason: "载入项目入口已触发",
        createdAt: nowIso()
      },
      [],
      "载入项目：真实实现将打开项目列表"
    );
    pushEvent({
      type: "STAGE_CHANGED",
      sessionId: state.session.id,
      stage: "calling_tool",
      message: "真实实现将调用 GET /api/projects"
    });
  }

  if (action === "export-image") {
    beginSession("导出当前分镜图片");
    executeCommand({
      id: makeId("cmd"),
      type: "EXPORT_PROJECT",
      source: "user_ui",
      reason: "从设置菜单导出图片",
      createdAt: nowIso(),
      payload: {
        format: "png",
        scope: "active_scene"
      }
    });
    state.session.status = "COMPLETED";
    state.session.stage = "completed";
    state.session.lastSummary = {
      userInput: "导出当前分镜图片",
      completed: true,
      stage: "completed",
      changes: [
        {
          type: "exported",
          targetType: "export",
          targetName: "PNG 图片",
          description: "已触发当前镜头图片导出"
        }
      ]
    };
    pushEvent({
      type: "TURN_SUMMARY",
      sessionId: state.session.id,
      summary: state.session.lastSummary
    });
  }

  render();
}

function runCustomInput() {
  const input = $("#voiceInput").value.trim();
  if (!input) return;

  if (input.includes("箭头")) {
    runArrowDemo();
    return;
  }

  if (input.includes("标题") || input.includes("它")) {
    runClarificationDemo();
    return;
  }

  if (input.includes("导出")) {
    runExportDemo();
    return;
  }

  runStoryboardDemo();
}

function startVoiceRecording() {
  if (state.voiceRecording || document.body.dataset.busy === "true") return;

  const input = $("#voiceInput").value.trim() || COMMAND_BINDINGS[0].userInput;
  const sessionId = makeId("session");
  state.session = {
    id: sessionId,
    status: "RUNNING",
    stage: "listening",
    originalUserInput: input,
    currentUserInput: "",
    progress: {
      completedSteps: 0,
      totalSteps: 3,
      message: "正在听取语音"
    },
    taskPlan: null,
    pendingClarification: null,
    lastSummary: null
  };
  state.voiceStatus = "正在听取语音";
  state.voiceDraftReady = false;
  state.voiceRecording = {
    sessionId,
    input,
    partialTimer: window.setTimeout(() => {
      if (!state.voiceRecording || state.voiceRecording.sessionId !== sessionId) return;

      state.voiceStatus = "实时转写中";
      state.session.currentUserInput = input.slice(0, Math.max(8, Math.floor(input.length * 0.45)));
      $("#voiceInput").value = state.session.currentUserInput;
      pushEvent({
        type: "TRANSCRIPT_PARTIAL",
        sessionId,
        text: state.session.currentUserInput
      });
      render();
    }, 420)
  };
  pushEvent({
    type: "STAGE_CHANGED",
    sessionId,
    stage: "listening",
    message: "正在听取语音"
  });
  render();
}

function finishVoiceRecording() {
  if (!state.voiceRecording) return;

  const recording = state.voiceRecording;
  window.clearTimeout(recording.partialTimer);
  state.voiceRecording = null;
  state.voiceStatus = "识别完成，等待修改或发送";
  state.voiceDraftReady = true;
  state.session.currentUserInput = recording.input;
  $("#voiceInput").value = recording.input;
  pushEvent({
    type: "TRANSCRIPT_FINAL",
    sessionId: recording.sessionId,
    text: recording.input
  });
  publishStage("listening", "语音识别完成，等待修改或发送");
  render();
}

function runVoiceInputDemo() {
  if (state.voiceRecording) {
    finishVoiceRecording();
    return;
  }

  startVoiceRecording();
}

function switchScene(sceneId) {
  executeCommand({
    id: makeId("cmd"),
    type: "SWITCH_SCENE",
    source: "user_ui",
    reason: "用户从镜头历史区选择",
    createdAt: nowIso(),
    payload: { sceneId }
  });
  render();
}

function selectElement(elementId) {
  state.selectedElementId = elementId;
  render();
}

function render() {
  renderHeader();
  renderHistory();
  renderCanvas();
  renderAIPanel();
}

function renderHeader() {
  $("#projectTitle").textContent = state.project.title;
  $("#projectMeta").textContent = `${state.project.mode} · ${state.project.scenes.length} 个镜头 · ${stageLabels[state.session.stage] || state.session.stage}`;
  $("#settingsButton").setAttribute("aria-expanded", String(state.settingsOpen));
  $("#settingsMenu").hidden = !state.settingsOpen;
}

function renderHistory() {
  const sceneList = $("#sceneList");
  sceneList.innerHTML = state.project.scenes
    .map((scene) => {
      const active = scene.id === state.project.activeSceneId ? "is-active" : "";
      return `
        <button class="scene-row ${active}" data-scene="${scene.id}">
          <span class="scene-order">${scene.order}</span>
          <span>
            <strong>${scene.name}</strong>
            <small>${scene.description}</small>
          </span>
        </button>
      `;
    })
    .join("");

  const timeline = $("#operationTimeline");
  timeline.innerHTML = state.history
    .slice(0, 8)
    .map((entry) => `
      <li>
        <span>${commandSummaries[entry.command.type] || entry.command.type}</span>
        <strong>${entry.summary}</strong>
      </li>
    `)
    .join("");

  $("#undoState").textContent = state.history.length > 0 ? "可撤销上一条命令" : "暂无可撤销命令";
}

function renderCanvas() {
  const scene = activeScene();
  $("#activeSceneName").textContent = scene.name;
  $("#activeSceneDescription").textContent = scene.description;
  $("#activeSceneNarration").textContent = scene.narration;
  $("#sceneDuration").textContent = `${(scene.durationMs / 1000).toFixed(1)}s`;

  const canvas = $("#canvasSurface");
  canvas.style.background = scene.canvas.background.type === "solid" ? scene.canvas.background.color : "#ffffff";
  canvas.innerHTML = scene.elements
    .slice()
    .sort((left, right) => left.zIndex - right.zIndex)
    .map(renderElement)
    .join("");
}

function renderElement(element) {
  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const style = [
    `left:${scaleX(element.x)}%`,
    `top:${scaleY(element.y)}%`,
    `width:${scaleX(element.width)}%`,
    `height:${scaleY(element.height)}%`,
    `z-index:${element.zIndex}`
  ].join(";");

  if (element.type === "text") {
    const textStyle = [
      `font-size:${Math.max(12, element.style.fontSize * 0.42)}px`,
      `color:${element.style.color}`,
      `background:${element.style.backgroundColor || "transparent"}`,
      `font-weight:${element.style.fontWeight || "normal"}`,
      `text-align:${element.style.align || "left"}`
    ].join(";");
    return `<button class="canvas-element text-element ${selected}" data-element="${element.id}" style="${style};${textStyle}">${element.text}</button>`;
  }

  if (element.type === "shape") {
    const shapeStyle = [
      `background:${element.style.fill || "#ffffff"}`,
      `border:${element.style.strokeWidth || 1}px solid ${element.style.stroke || "#243b53"}`,
      `border-radius:${element.style.radius || 8}px`
    ].join(";");
    return `
      <button class="canvas-element shape-element ${selected}" data-element="${element.id}" style="${style};${shapeStyle}">
        <span>${element.name || element.shape}</span>
      </button>
    `;
  }

  if (element.type === "connector") {
    const connectorStyle = [
      `background:${element.style.stroke}`,
      `height:${Math.max(2, element.style.strokeWidth)}px`,
      `left:${scaleX(element.x)}%`,
      `top:${scaleY(element.y)}%`,
      `width:${scaleX(element.width)}%`,
      `z-index:${element.zIndex}`
    ].join(";");
    return `
      <button class="canvas-element connector-element ${selected}" data-element="${element.id}" style="${connectorStyle}">
        <span>${element.text || ""}</span>
      </button>
    `;
  }

  const placeholderStyle = [
    `background:${element.placeholderStyle.fill || "#ffffff"}`,
    `border:${element.placeholderStyle.strokeWidth || 1}px dashed ${element.placeholderStyle.stroke || "#243b53"}`,
    `border-radius:${element.placeholderStyle.radius || 8}px`
  ].join(";");
  return `
    <button class="canvas-element unknown-element ${selected}" data-element="${element.id}" style="${style};${placeholderStyle}">
      <span>${element.label}</span>
    </button>
  `;
}

function scaleX(value) {
  return (value / 960) * 100;
}

function scaleY(value) {
  return (value / 540) * 100;
}

function renderAIPanel() {
  $("#voiceStatus").textContent = state.voiceStatus;
  $("#voiceStatus").classList.toggle("is-ready", state.voiceDraftReady);
  const voiceButton = document.querySelector("[data-run='voice']");
  voiceButton?.setAttribute("aria-pressed", String(Boolean(state.voiceRecording)));
  const voiceButtonLabel = voiceButton?.querySelector("strong");
  if (voiceButtonLabel) {
    voiceButtonLabel.textContent = state.voiceRecording ? "结束识别" : "语音输入";
  }

  const stage = $("#stageIndicator");
  stage.dataset.stage = state.session.stage;
  stage.querySelector("strong").textContent = stageLabels[state.session.stage] || state.session.stage;
  stage.querySelector("span").textContent = state.session.progress?.message || "等待输入";

  const progress = state.session.progress || { completedSteps: 0, totalSteps: 0 };
  const percent = progress.totalSteps ? Math.round((progress.completedSteps / progress.totalSteps) * 100) : 0;
  $("#progressBar").style.width = `${percent}%`;
  $("#progressText").textContent = `${progress.completedSteps || 0}/${progress.totalSteps || 0}`;

  const clarification = $("#clarificationCard");
  if (state.session.pendingClarification) {
    clarification.hidden = false;
    clarification.querySelector("p").textContent = state.session.pendingClarification.question;
    clarification.querySelector(".option-list").innerHTML = state.session.pendingClarification.options
      .map((option) => `<button data-resume="${option.value}">${option.label}</button>`)
      .join("");
  } else {
    clarification.hidden = true;
  }

  const summary = $("#turnSummary");
  if (state.session.lastSummary?.changes?.length) {
    summary.innerHTML = state.session.lastSummary.changes
      .map((change) => `<li><span>${change.targetName || change.targetType}</span>${change.description}</li>`)
      .join("");
  } else {
    summary.innerHTML = "<li><span>待开始</span>暂无本轮变更</li>";
  }

  $("#eventLog").innerHTML = state.eventLog
    .map((event) => `
      <li>
        <span>${event.type}</span>
        <strong>${event.message || event.stage || event.question || event.patch?.type || event.text || "事件已接收"}</strong>
      </li>
    `)
    .join("");
}

function bindEvents() {
  const voiceButton = document.querySelector("[data-run='voice']");
  voiceButton?.setAttribute("data-bound", "true");
  voiceButton?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    state.settingsOpen = false;
    runVoiceInputDemo();
  });

  const sendButton = document.querySelector("[data-run='custom']");
  sendButton?.setAttribute("data-bound", "true");
  sendButton?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    submitVoiceDraft();
  });

  document.addEventListener("click", (event) => {
    const sceneButton = event.target.closest("[data-scene]");
    if (sceneButton) switchScene(sceneButton.dataset.scene);

    const elementButton = event.target.closest("[data-element]");
    if (elementButton) selectElement(elementButton.dataset.element);

    const resumeButton = event.target.closest("[data-resume]");
    if (resumeButton) resumeClarification(resumeButton.dataset.resume);

    const menuButton = event.target.closest("[data-menu-toggle='settings']");
    if (menuButton) {
      state.settingsOpen = !state.settingsOpen;
      renderHeader();
      return;
    }

    if (state.settingsOpen && !event.target.closest(".settings-menu")) {
      state.settingsOpen = false;
      renderHeader();
    }

    const projectActionButton = event.target.closest("[data-project-action]");
    if (projectActionButton) {
      runProjectAction(projectActionButton.dataset.projectAction);
      return;
    }

    const runButton = event.target.closest("[data-run]");
    if (runButton) {
      state.settingsOpen = false;
      if (runButton.dataset.run === "voice") runVoiceInputDemo();
      if (runButton.dataset.run === "storyboard") runStoryboardDemo();
      if (runButton.dataset.run === "arrow") runArrowDemo();
      if (runButton.dataset.run === "clarification") runClarificationDemo();
      if (runButton.dataset.run === "export") runExportDemo();
      if (runButton.dataset.run === "custom") submitVoiceDraft();
    }

  });

  $("#voiceInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") submitVoiceDraft();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.settingsOpen) {
      state.settingsOpen = false;
      renderHeader();
      return;
    }

    if (!isVoiceShortcut(event) || event.repeat) return;
    if (isTypingTarget(event.target)) return;

    event.preventDefault();
    state.settingsOpen = false;
    startVoiceRecording();
  });

  document.addEventListener("keyup", (event) => {
    if (!state.voiceRecording) return;
    if (event.code !== "KeyV" && event.key !== "Control") return;
    if (isTypingTarget(event.target)) return;

    event.preventDefault();
    finishVoiceRecording();
  });
}

function isVoiceShortcut(event) {
  return event.altKey && event.code === "KeyV";
}

function isTypingTarget(target) {
  const element = target instanceof HTMLElement ? target : null;
  if (!element) return false;

  return Boolean(element.closest("input, textarea, select, [contenteditable='true']"));
}

bindEvents();
render();
