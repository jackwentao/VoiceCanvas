export function verdict(criteria) {
  if (criteria.some(item => item.status === "fail")) return "fail";
  return criteria.length && criteria.every(item => item.status === "pass") ? "pass" : "review";
}

export function toolSteps(entry) {
  const titles = new Map(entry.result.board.shots.map(shot => [shot.id, shot.title]));
  return entry.result.run.steps.map((step, index) => {
    const review = entry.toolReview?.overrides?.[index + 1];
    return {
      ...step,
      index: index + 1,
      decision: review?.status ?? entry.toolReview?.default ?? "review",
      note: review?.note,
      target: titles.get(step.call.arguments?.shotId) ?? step.call.arguments?.shotId,
    };
  });
}

export function countStatus(items, passed, pending = "review") {
  return {
    passed: items.filter(status => status === passed).length,
    total: items.length,
    pending: items.filter(status => status === pending).length,
  };
}

export function comparisonMismatch(batch, current, baseline, previous) {
  if (!previous) return "对照批次没有此用例。";
  const configKeys = [
    "model", "endpointHost", "reasoningEffort", "drawingSkill", "maxTokens", "timeoutSeconds",
  ];
  if (configKeys.some(key => !Object.hasOwn(batch.meta, key) || !Object.hasOwn(baseline.meta, key)
    || batch.meta[key] !== baseline.meta[key])) return "模型配置不同或缺失。";
  if (batch.rubricVersion !== baseline.rubricVersion) return "验收标准版本不同。";
  if (current.result.run.request !== previous.result.run.request) return "用户需求不同。";
  const criteria = entry => entry.criteria.map(({ id, group, requirement }) => [id, group, requirement]);
  if (JSON.stringify(criteria(current)) !== JSON.stringify(criteria(previous))) return "验收条目不同。";
  const start = ({ initial }) => JSON.stringify([
    initial.context,
    initial.shots.findIndex(shot => shot.id === initial.activeId),
    initial.shots.map(({ title, description, durationSeconds, camera, svg }) =>
      [title, description, durationSeconds, camera, svg]),
  ]);
  if (start(current) !== start(previous)) return "用例起始状态不同。";
  return "";
}

export function median(values) {
  const measured = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!measured.length) return null;
  return (measured[Math.floor((measured.length - 1) / 2)]
    + measured[Math.floor(measured.length / 2)]) / 2;
}
