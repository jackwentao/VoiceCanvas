// 纯文字排版规则，宽度测量由浏览器适配器注入，便于离线验证。
export function wrapShotText(content, maxWidth, measure) {
  if (!Number.isFinite(maxWidth) || maxWidth <= 0) throw new Error("请填写有效的换行宽度");
  const segmenter = typeof Intl.Segmenter === "function"
    ? new Intl.Segmenter("zh", { granularity: "grapheme" }) : null;
  const split = (value) => segmenter
    ? [...segmenter.segment(value)].map(part => part.segment) : Array.from(value);
  const closing = /^[，。！？：；、）》】”’.,!?;:)]$/;
  const opening = /^[（《【“‘([]$/;
  const lines = [];
  for (const paragraph of content.replace(/\r\n?/g, "\n").split("\n")) {
    const chars = split(paragraph);
    if (!chars.length) { lines.push(""); continue; }
    while (chars.length) {
      let end = 0;
      while (end < chars.length && measure(chars.slice(0, end + 1).join("")) <= maxWidth + 0.5) end++;
      if (!end) throw new Error("换行宽度容不下一个字，请增加宽度或减小字号");
      if (end < chars.length) {
        // 换行时避免把中文闭标点放到行首、开标点留在行尾。
        if (closing.test(chars[end]) && end > 1) end--;
        if (opening.test(chars[end - 1]) && end > 1) end--;
        const whitespace = chars.slice(0, end).lastIndexOf(" ");
        if (whitespace > end * 0.6) end = whitespace + 1;
      }
      lines.push(chars.splice(0, end).join(""));
      if (lines.length > 100) throw new Error("文字超过 100 行，请缩短内容或增加宽度");
    }
  }
  return lines;
}

export function textReadability(fontSize, scale, previewWidth) {
  const effective = fontSize * scale;
  const preview = effective * previewWidth / 1280;
  return {
    effective, preview,
    warning: preview < 12
      ? `当前预览约 ${preview.toFixed(1)} 像素，阅读偏小；可尝试增大字号。` : "",
  };
}

export function recommendedTextSize(current, scale, previewWidth) {
  return Math.min(160, Math.max(current, Math.ceil(14 * 1280 / previewWidth / scale)));
}

export function textScale(matrix) { return Math.hypot(matrix.c, matrix.d); }

export function chooseTextContainer(candidates, bounds, fontSize) {
  return candidates.filter(b => b.x <= bounds.x + 2 && b.y <= bounds.y + 2
    && b.right >= bounds.right - 2 && b.bottom >= bounds.bottom - 2
    && b.bottom - b.y <= Math.max(fontSize * 4, (bounds.bottom - bounds.y) * 3))
    .sort((a, b) => (a.right - a.x) * (a.bottom - a.y) - (b.right - b.x) * (b.bottom - b.y))[0];
}

export function centeredBaseline(baseline, original, current) {
  return baseline + (original.y + original.bottom - current.y - current.bottom) / 2;
}

export function overlaps(a, b, tolerance = 2) {
  return Math.min(a.right, b.right) - Math.max(a.x, b.x) > tolerance
    && Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y) > tolerance;
}
