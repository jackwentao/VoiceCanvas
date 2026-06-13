export function fitTextFontSize({ text, baseFontSize, transform }) {
  const textUnits = estimateTextUnits(text);
  if (!textUnits) return roundCssNumber(baseFontSize);

  const width = Math.max(8, transform?.width || 1);
  const height = Math.max(8, transform?.height || 1);
  const maxLines = Math.max(1, Math.floor(height / (baseFontSize * 1.1)));
  const unitsPerLine = Math.ceil(textUnits / maxLines);
  const widthLimitedSize = width / Math.max(1, unitsPerLine);
  const heightLimitedSize = height / (maxLines * 1.1);
  const fittedSize = Math.min(baseFontSize, widthLimitedSize, heightLimitedSize);

  return roundCssNumber(Math.max(9, fittedSize));
}

export function estimateTextUnits(text) {
  return Array.from(String(text || "").trim()).reduce((total, char) => {
    if (/\s/.test(char)) return total + 0.35;
    if (/[\u4e00-\u9fff\u3040-\u30ff\uff00-\uffef]/u.test(char)) return total + 1;
    if (/[A-Z0-9]/.test(char)) return total + 0.72;
    if (/[a-z]/.test(char)) return total + 0.58;
    return total + 0.5;
  }, 0);
}

function roundCssNumber(value) {
  return Number(value.toFixed(2));
}
