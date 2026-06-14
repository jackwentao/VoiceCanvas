export const API_CONTRACT = {
  orchestration: {
    start: {
      method: "POST",
      path: "/api/orchestrations",
      request: ["projectId", "userInput"],
      response: ["sessionId", "status"]
    },
    resume: {
      method: "POST",
      path: "/api/orchestrations/:sessionId/resume",
      request: ["answer"],
      response: ["sessionId", "status"]
    },
    cancel: {
      method: "POST",
      path: "/api/orchestrations/:sessionId/cancel",
      request: [],
      response: ["sessionId", "status"]
    },
    events: {
      method: "GET",
      path: "/api/orchestrations/:sessionId/events",
      transport: "text/event-stream",
      events: [
        "TRANSCRIPT_PARTIAL",
        "TRANSCRIPT_FINAL",
        "STAGE_CHANGED",
        "PROGRESS",
        "CANVAS_PATCH_APPLIED",
        "CLARIFICATION_REQUESTED",
        "TURN_SUMMARY"
      ]
    }
  },
  project: {
    load: {
      method: "GET",
      path: "/api/projects/:projectId",
      response: ["Project", "HistoryEntry[]", "OrchestrationEvent[]"]
    },
    save: {
      method: "PUT",
      path: "/api/projects/:projectId",
      request: ["Project"],
      response: ["Project"]
    },
    export: {
      method: "POST",
      path: "/api/projects/:projectId/export",
      request: ["format", "scope", "sceneId?"],
      response: ["ExportResult"]
    }
  },
  assets: {
    upload: {
      method: "POST",
      path: "/api/assets/upload",
      request: ["file", "sceneId?"],
      response: ["AssetRef"]
    }
  },
  userMemory: {
    list: {
      method: "GET",
      path: "/api/users/:userId/memories",
      response: ["UserMemoryItem[]"]
    },
    create: {
      method: "POST",
      path: "/api/users/:userId/memories",
      request: ["kind", "content", "scope"],
      response: ["UserMemoryItem"]
    },
    update: {
      method: "PATCH",
      path: "/api/memories/:memoryId",
      request: ["kind?", "content?", "scope?", "confidence?", "status?"],
      response: ["UserMemoryItem"]
    },
    delete: {
      method: "DELETE",
      path: "/api/memories/:memoryId",
      request: [],
      response: []
    }
  }
};

export const UI_BINDINGS = [
  {
    area: "左侧画布历史区",
    components: ["SceneHistoryList", "OperationTimeline", "UndoRedoStatus"],
    reads: ["CanvasHistoryViewModel", "HistoryEntry[]", "CanvasPatch[]"],
    writes: [],
    events: ["CANVAS_PATCH_APPLIED"],
    api: ["GET /api/projects/:projectId"]
  },
  {
    area: "中间结构化画布",
    components: ["CanvasRenderer", "StoryboardStrip", "ElementLayer"],
    reads: ["Project", "Scene", "CanvasElement[]"],
    writes: [],
    events: ["CANVAS_PATCH_APPLIED"],
    api: ["GET /api/projects/:projectId", "GET /api/orchestrations/:sessionId/events"]
  },
  {
    area: "右侧 AI 交互栏",
    components: ["VoiceControl", "StageIndicator", "ClarificationCard", "TurnSummaryCard"],
    reads: ["OrchestrationSession", "OrchestrationEvent", "TurnSummary"],
    writes: ["OrchestratorInput", "ClarificationAnswer"],
    events: ["TRANSCRIPT_PARTIAL", "TRANSCRIPT_FINAL", "STAGE_CHANGED", "PROGRESS", "CLARIFICATION_REQUESTED", "TURN_SUMMARY"],
    api: ["POST /api/orchestrations", "POST /api/orchestrations/:sessionId/resume", "POST /api/orchestrations/:sessionId/cancel"]
  },
  {
    area: "导出面板",
    components: ["ExportPanel", "ExportStatus"],
    reads: ["Project", "ExportResult"],
    writes: ["ExportRequest"],
    events: ["CANVAS_PATCH_APPLIED", "TURN_SUMMARY"],
    api: ["POST /api/projects/:projectId/export"]
  },
  {
    area: "长期记忆管理面板",
    components: ["MemoryCreateForm", "MemoryList", "MemoryEditRow"],
    reads: ["UserMemoryItem[]"],
    writes: ["UserMemoryCreateRequest", "UserMemoryUpdateRequest"],
    events: [],
    api: [
      "GET /api/users/:userId/memories",
      "POST /api/users/:userId/memories",
      "PATCH /api/memories/:memoryId",
      "DELETE /api/memories/:memoryId"
    ]
  }
];

export const COMMAND_BINDINGS = [
  {
    intent: "创建三镜头带货分镜",
    userInput: "创建一个三镜头的珍珠奶茶带货分镜，主打低糖和新品上市。",
    endpoint: "POST /api/orchestrations",
    firstAction: "PLAN_TASKS",
    commands: ["CREATE_SCENE", "ADD_ELEMENT", "SWITCH_SCENE"],
    events: ["STAGE_CHANGED", "PROGRESS", "CANVAS_PATCH_APPLIED", "TURN_SUMMARY"]
  },
  {
    intent: "添加指向卖点的箭头",
    userInput: "给第二镜头加一个箭头，指向低糖标签，写上核心卖点。",
    endpoint: "POST /api/orchestrations",
    firstAction: "EXECUTE_COMMANDS",
    commands: ["SWITCH_SCENE", "ADD_ELEMENT"],
    events: ["STAGE_CHANGED", "CANVAS_PATCH_APPLIED", "TURN_SUMMARY"]
  },
  {
    intent: "指代不清进入澄清",
    userInput: "把标题放上面。",
    endpoint: "POST /api/orchestrations",
    firstAction: "ASK_CLARIFICATION",
    commands: [],
    events: ["STAGE_CHANGED", "CLARIFICATION_REQUESTED"]
  },
  {
    intent: "导出项目 JSON",
    userInput: "导出项目数据。",
    endpoint: "POST /api/projects/:projectId/export",
    firstAction: "EXECUTE_COMMANDS",
    commands: ["EXPORT_PROJECT"],
    events: ["STAGE_CHANGED", "CANVAS_PATCH_APPLIED", "TURN_SUMMARY"]
  }
];

export const initialProject = {
  id: "project_demo_voicecanvas",
  title: "珍珠奶茶带货分镜",
  mode: "storyboard",
  activeSceneId: "scene_hook",
  globalStyle: {
    theme: "promotion",
    backgroundColor: "#f6fbf6",
    fontFamily: "system-ui",
    colorPalette: ["#1f8a5b", "#f6c453", "#f15b4a", "#243b53"]
  },
  metadata: {
    source: "demo",
    version: 1
  },
  createdAt: "2026-06-12T09:00:00.000Z",
  updatedAt: "2026-06-12T09:00:00.000Z",
  scenes: [
    {
      id: "scene_hook",
      name: "主图",
      order: 1,
      description: "用痛点钩子吸引用户，强调想喝奶茶又怕糖高。",
      narration: "想喝奶茶，又怕太甜？",
      durationMs: 2500,
      canvas: {
        width: 960,
        height: 540,
        background: {
          type: "solid",
          color: "#effaf1"
        }
      },
      elements: [
        {
          id: "el_title_hook",
          name: "主标题",
          type: "text",
          text: "低糖也好喝",
          x: 90,
          y: 62,
          width: 360,
          height: 72,
          zIndex: 4,
          style: {
            fontSize: 42,
            fontWeight: "bold",
            color: "#173b2c",
            align: "left"
          },
          createdAt: "2026-06-12T09:00:00.000Z",
          updatedAt: "2026-06-12T09:00:00.000Z"
        },
        {
          id: "el_person_hook",
          name: "犹豫的顾客",
          type: "generated_asset",
          content: {
            alt: "犹豫看着奶茶的年轻顾客"
          },
          asset: {
            kind: "character",
            status: "pending",
            prompt: "年轻顾客看着奶茶，表情犹豫，清爽电商插画风格",
            provider: "mock"
          },
          subject: {
            character: {
              role: "顾客",
              pose: "站立思考",
              expression: "犹豫"
            }
          },
          x: 116,
          y: 184,
          width: 170,
          height: 230,
          zIndex: 2,
          placeholderStyle: {
            fill: "#ffffff",
            stroke: "#1f8a5b",
            strokeWidth: 3,
            radius: 8
          },
          createdAt: "2026-06-12T09:00:00.000Z",
          updatedAt: "2026-06-12T09:00:00.000Z"
        },
        {
          id: "el_product_hook",
          name: "奶茶产品",
          type: "shape",
          content: {
            label: "奶茶"
          },
          shape: "rounded_rectangle",
          x: 560,
          y: 138,
          width: 210,
          height: 290,
          zIndex: 3,
          style: {
            fill: "#ffffff",
            stroke: "#1f8a5b",
            strokeWidth: 4,
            radius: 16
          },
          createdAt: "2026-06-12T09:00:00.000Z",
          updatedAt: "2026-06-12T09:00:00.000Z"
        }
      ],
      createdAt: "2026-06-12T09:00:00.000Z",
      updatedAt: "2026-06-12T09:00:00.000Z"
    },
    {
      id: "scene_product",
      name: "卖点",
      order: 2,
      description: "产品特写展示低糖、新品和口感卖点。",
      narration: "新品低糖配方，清爽不腻。",
      durationMs: 3000,
      canvas: {
        width: 960,
        height: 540,
        background: {
          type: "solid",
          color: "#f7fbff"
        }
      },
      elements: [
        {
          id: "el_product_cup",
          name: "奶茶产品",
          type: "shape",
          shape: "rounded_rectangle",
          x: 352,
          y: 104,
          width: 240,
          height: 330,
          zIndex: 2,
          style: {
            fill: "#ffffff",
            stroke: "#1f8a5b",
            strokeWidth: 5,
            radius: 18
          },
          semanticTags: ["product", "milk_tea"],
          createdAt: "2026-06-12T09:00:00.000Z",
          updatedAt: "2026-06-12T09:00:00.000Z"
        },
        {
          id: "el_low_sugar_tag",
          name: "低糖标签",
          type: "text",
          text: "低糖 30%",
          x: 650,
          y: 156,
          width: 160,
          height: 52,
          zIndex: 4,
          style: {
            fontSize: 28,
            fontWeight: "bold",
            color: "#ffffff",
            align: "center",
            backgroundColor: "#1f8a5b"
          },
          semanticTags: ["selling_point"],
          createdAt: "2026-06-12T09:00:00.000Z",
          updatedAt: "2026-06-12T09:00:00.000Z"
        }
      ],
      createdAt: "2026-06-12T09:00:00.000Z",
      updatedAt: "2026-06-12T09:00:00.000Z"
    },
    {
      id: "scene_conversion",
      name: "转化",
      order: 3,
      description: "限时优惠和立即下单按钮推动转化。",
      narration: "今天下单，第二杯半价。",
      durationMs: 3000,
      canvas: {
        width: 960,
        height: 540,
        background: {
          type: "solid",
          color: "#fff8ef"
        }
      },
      elements: [
        {
          id: "el_offer",
          name: "限时优惠标签",
          type: "text",
          text: "第二杯半价",
          x: 114,
          y: 126,
          width: 240,
          height: 74,
          zIndex: 3,
          style: {
            fontSize: 34,
            fontWeight: "bold",
            color: "#ffffff",
            align: "center",
            backgroundColor: "#f15b4a"
          },
          createdAt: "2026-06-12T09:00:00.000Z",
          updatedAt: "2026-06-12T09:00:00.000Z"
        },
        {
          id: "el_cta",
          name: "下单按钮",
          type: "text",
          text: "马上下单",
          x: 600,
          y: 350,
          width: 210,
          height: 66,
          zIndex: 4,
          style: {
            fontSize: 30,
            fontWeight: "bold",
            color: "#173b2c",
            align: "center",
            backgroundColor: "#f6c453"
          },
          createdAt: "2026-06-12T09:00:00.000Z",
          updatedAt: "2026-06-12T09:00:00.000Z"
        }
      ],
      createdAt: "2026-06-12T09:00:00.000Z",
      updatedAt: "2026-06-12T09:00:00.000Z"
    }
  ]
};

export const initialHistory = [
  {
    id: "history_001",
    summary: "创建主图镜头并添加标题、顾客和奶茶产品",
    status: "applied",
    command: {
      id: "cmd_seed_001",
      type: "CREATE_SCENE"
    },
    patches: [],
    createdAt: "2026-06-12T09:00:00.000Z"
  },
  {
    id: "history_002",
    summary: "创建卖点镜头并添加低糖标签",
    status: "applied",
    command: {
      id: "cmd_seed_002",
      type: "ADD_ELEMENT"
    },
    patches: [],
    createdAt: "2026-06-12T09:00:01.000Z"
  },
  {
    id: "history_003",
    summary: "创建转化镜头并添加优惠与下单按钮",
    status: "applied",
    command: {
      id: "cmd_seed_003",
      type: "ADD_ELEMENT"
    },
    patches: [],
    createdAt: "2026-06-12T09:00:02.000Z"
  }
];

export const initialSession = {
  id: "session_idle",
  status: "COMPLETED",
  stage: "completed",
  originalUserInput: "",
  progress: {
    completedSteps: 0,
    totalSteps: 0,
    message: "等待语音输入"
  },
  taskPlan: null,
  pendingClarification: null,
  lastSummary: {
    userInput: "",
    completed: true,
    stage: "completed",
    changes: []
  }
};
