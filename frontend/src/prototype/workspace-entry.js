// 已分享的结构化项目使用原控制器；普通入口与自由分镜使用新 API。
const params = new URLSearchParams(location.search);
if (params.has("projectId") && !params.has("board") && !params.has("shot")) {
  await import("./app.js");
} else {
  await import("./svg-workspace.js");
}
