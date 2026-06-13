export function visibleSceneEntries(scenes) {
  return (Array.isArray(scenes) ? scenes : [])
    .map((scene, index) => ({ scene, sourceIndex: index }))
    .sort((left, right) => {
      const leftOrder = Number.isFinite(left.scene?.order) ? left.scene.order : Number.MAX_SAFE_INTEGER;
      const rightOrder = Number.isFinite(right.scene?.order) ? right.scene.order : Number.MAX_SAFE_INTEGER;
      if (leftOrder !== rightOrder) return leftOrder - rightOrder;
      return left.sourceIndex - right.sourceIndex;
    })
    .map(({ scene }, index) => ({
      scene,
      displayNumber: index + 1
    }));
}

export function sceneDisplayNumber(scenes, sceneId) {
  return visibleSceneEntries(scenes).find((entry) => entry.scene?.id === sceneId)?.displayNumber ?? null;
}

export function sceneAtDisplayNumber(scenes, displayNumber) {
  const targetNumber = Number(displayNumber);
  if (!Number.isInteger(targetNumber) || targetNumber < 1) return null;
  return visibleSceneEntries(scenes).find((entry) => entry.displayNumber === targetNumber)?.scene ?? null;
}
