/**
 * Export an SVG element to a PNG file download.
 * @param {SVGElement} svg
 * @param {string} filename
 * @param {{ background?: string, scale?: number }} [options]
 */
export function downloadSvgAsPng(svg, filename, options = {}) {
  if (!svg) return;

  const { background = "#ffffff", scale = 2 } = options;
  const vb = svg.viewBox?.baseVal;
  const rect = svg.getBoundingClientRect();
  const baseW = vb?.width || rect.width || 800;
  const baseH = vb?.height || rect.height || 600;

  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(baseW * scale);
  canvas.height = Math.ceil(baseH * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.fillStyle = background;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const svgStr = new XMLSerializer().serializeToString(svg);
  const blob = new Blob([svgStr], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const img = new Image();

  img.onload = () => {
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(url);
    canvas.toBlob((pngBlob) => {
      if (!pngBlob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(pngBlob);
      a.download = filename || "diagramme.png";
      a.click();
      URL.revokeObjectURL(a.href);
    }, "image/png");
  };
  img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
}
