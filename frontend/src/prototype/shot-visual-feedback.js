// 预览和评审绑定镜头版本；旧版本诊断保留为历史，不标记当前画面已通过。
export function visualFeedback(board, run) {
  return (run?.steps || []).filter(step =>
    ["render_shot", "review_shot"].includes(step.call.name) && step.status === "succeeded"
  ).map(step => {
    const result = step.result;
    const shot = board?.shots.find(s => s.id === result.shotId);
    const current = Boolean(shot && shot.version === result.shotVersion);
    return {
      title: shot?.title || "已移除镜头", version: result.shotVersion, current,
      previewUrl: current ? result.previewUrl : null,
      review: result.review || "真实 PNG 已渲染；这一步尚未完成专门的模型评审。",
      cached: Boolean(result.cached),
    };
  });
}
