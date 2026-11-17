import assert from "node:assert/strict";
import { test } from "node:test";
import { createWorkspaceController } from "../../src/prototype/workspace-controller.js";
import { renderSceneMarkup, renderSceneThumbnailMarkup } from "../../src/prototype/canvas-renderer.js";

function fixture() {
  let snapshot = {
    project: {id:"server-project",title:"后端项目",activeSceneId:"scene_1",scenes:[{
      id:"scene_1",name:"镜头一",order:1,canvas:{width:1280,height:720,background:{color:"#ffffff"}},
      elements:[]
    }]}, history:[],undoRedo:{canUndo:false,canRedo:false},pending:null
  };
  const calls = [];
  const api = {
    workspace: async id => { calls.push(["workspace",id]); return structuredClone(snapshot); },
    projects: async () => ({projects:[{id:"server-project",title:"后端项目"}]}),
    create: async () => structuredClone(snapshot),
    action: async (id,payload) => { calls.push(["action",id,payload]); return structuredClone(snapshot); },
    orchestrate: async (id,text) => { calls.push(["orchestrate",id,text]); return {status:"COMPLETED",summary:{message:"完成"}}; },
    resume: async (id,session,text) => { calls.push(["resume",id,session,text]); snapshot.pending=null; return {status:"COMPLETED"}; },
    import: async payload => { calls.push(["import",payload]); return structuredClone(snapshot); },
    export: async (id,payload) => { calls.push(["export",id,payload]); return {export:{filename:"backend.json",content:"后端内容"}}; }
  };
  return {api,calls,get snapshot(){return snapshot;},set snapshot(value){snapshot=value;}};
}

test("首次连接失败时没有本地项目，也不允许提交业务", async () => {
  const f=fixture();
  f.api.workspace=async()=>{throw new Error("网络断开");};
  const model=createWorkspaceController(f.api);
  await model.load("server-project");
  assert.equal(model.state.snapshot,null);
  assert.equal(model.state.error,"网络断开");
  await model.submit("创建三镜头");
  assert.equal(f.calls.some(call=>call[0]==="orchestrate"),false);
});

test("按钮只发送固定动作；界面接受后端结果而不乐观改写数据", async () => {
  const f=fixture();const model=createWorkspaceController(f.api);await model.load("server-project");
  const before=structuredClone(model.state.snapshot);
  await model.action({action:"set_background",sceneId:"scene_1",color:"#abcdef"});
  assert.deepEqual(f.calls.find(call=>call[0]==="action"),["action","server-project",{action:"set_background",sceneId:"scene_1",color:"#abcdef"}]);
  assert.deepEqual(model.state.snapshot,before);
});

test("SSE 只展示进度；最终画面以服务端重新读取的快照为准", async () => {
  const f=fixture();const model=createWorkspaceController(f.api);await model.load("server-project");
  f.api.orchestrate=async(id,text,handlers)=>{
    handlers.onEvent({type:"CANVAS_PATCH_APPLIED",patch:{type:"SCENE_DELETED",sceneId:"scene_1"}});
    assert.equal(model.state.snapshot.project.scenes.length,1);
    f.snapshot.project.title="服务端真实结果";
    return {status:"COMPLETED",project:{title:"不完整快照"},summary:{message:"完成"}};
  };
  await model.submit("改变标题");
  assert.equal(model.state.snapshot.project.title,"服务端真实结果");
  assert.equal(model.state.busy,false);
});

test("断流后重新读取服务器，不执行本地兜底或自动重发", async () => {
  const f=fixture();const model=createWorkspaceController(f.api);await model.load("server-project");
  let requests=0;
  f.api.orchestrate=async()=>{requests++;f.snapshot.project.title="已在服务器完成";throw new Error("连接中断");};
  await model.submit("修改标题");
  assert.equal(requests,1);
  assert.equal(model.state.snapshot.project.title,"已在服务器完成");
  assert.equal(model.state.error,"连接中断");
});

test("澄清原样交给后端挂起会话，刷新后仍能回答", async () => {
  const f=fixture();f.snapshot.pending={sessionId:"backend-session",nextAction:{question:"选哪个？",options:[]}};
  const model=createWorkspaceController(f.api);await model.load("server-project");
  await model.submit("左边那个");
  assert.deepEqual(f.calls.find(call=>call[0]==="resume"),["resume","server-project","backend-session","左边那个"]);
  assert.equal(model.state.snapshot.pending,null);
  assert.equal(f.calls.some(call=>call[0]==="orchestrate"),false);
});

test("请求进行时阻止重复操作，后端失败不展示成功", async () => {
  const f=fixture();const model=createWorkspaceController(f.api);await model.load("server-project");
  let finish;let count=0;
  f.api.orchestrate=()=>{count++;return new Promise(resolve=>{finish=resolve;});};
  const first=model.submit("第一次");
  assert.equal(await model.submit("重复"),null);
  assert.equal(await model.action({action:"undo"}),null);
  finish({status:"FAILED",summary:{message:"目标不存在"}});
  await first;
  assert.equal(count,1);
  assert.equal(model.state.error,"目标不存在");
  assert.equal(model.state.stage,"failed");
});

test("导出只返回后端内容；项目文件原样交由后端校验", async () => {
  const f=fixture();const model=createWorkspaceController(f.api);await model.load("server-project");
  assert.deepEqual(await model.export("json"),{filename:"backend.json",content:"后端内容"});
  assert.deepEqual(f.calls.find(call=>call[0]==="export"),["export","server-project",{format:"json",scope:"project"}]);
  const payload={invalid:"交由后端校验"};await model.import(payload);
  assert.deepEqual(f.calls.find(call=>call[0]==="import"),["import",payload]);
});

test("渲染可编辑文本和几何形状，不修改后端快照，不从文案猜测素材", () => {
  const f=fixture();const scene=f.snapshot.project.scenes[0];
  scene.elements=[{id:'title"id',type:"text",text:"<测试标题>",transform:{x:10,y:20,width:300,height:80},layer:{zIndex:1},style:{fontSize:36}}];
  const before=structuredClone(f.snapshot.project);
  const markup=renderSceneMarkup(f.snapshot.project,scene);
  assert.ok(markup.includes("&lt;测试标题&gt;"));
  assert.ok(markup.includes('data-element="title&quot;id"'));
  assert.deepEqual(f.snapshot.project,before);
  const thumbnail=renderSceneThumbnailMarkup(f.snapshot.project,scene);
  assert.ok(!thumbnail.includes("<button "));
  assert.ok(thumbnail.includes("&lt;测试标题&gt;"));
});

test("切换失败后，后续动作仍提交给屏幕上最后成功加载的项目", async () => {
  const f=fixture();const model=createWorkspaceController(f.api);await model.load("server-project");
  f.api.workspace=async id=>{if(id==="unavailable")throw new Error("项目加载失败");return structuredClone(f.snapshot);};
  await model.load("unavailable");
  assert.equal(model.state.snapshot.project.id,"server-project");
  await model.action({action:"undo"});
  assert.equal(f.calls.find(call=>call[0]==="action")[1],"server-project");
});
