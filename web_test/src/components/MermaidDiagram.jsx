import { useCallback, useEffect, useId, useRef, useState } from "react";
import { downloadSvgAsPng } from "../lib/downloadSvgAsPng";
import "./MermaidDiagram.css";

let mermaidModule = null;

const ZOOM_STEP = 1.25;
const ZOOM_MAX = 3;
const DBLCLICK_FACTOR = 2;

function getMermaidThemeConfig() {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  if (dark) {
    return {
      startOnLoad: false,
      securityLevel: "loose",
      theme: "dark",
      flowchart: {
        htmlLabels: true,
        useMaxWidth: false,
        wrappingWidth: 180,
      },
      themeVariables: {
        fontSize: "13px",
        fontFamily: "system-ui, Segoe UI, sans-serif",
        background: "#1a2332",
        primaryColor: "#2d3a4d",
        primaryTextColor: "#e8eaed",
        primaryBorderColor: "#3d4f66",
        lineColor: "#94a3b8",
        secondaryColor: "#151d28",
        tertiaryColor: "#0f1419",
      },
    };
  }
  return {
    startOnLoad: false,
    securityLevel: "loose",
    theme: "neutral",
    flowchart: {
      htmlLabels: true,
      useMaxWidth: false,
      wrappingWidth: 180,
    },
    themeVariables: {
      fontSize: "13px",
      fontFamily: "system-ui, Segoe UI, sans-serif",
    },
  };
}

async function loadMermaid() {
  const mod = await import("mermaid");
  mermaidModule = mod.default;
  mermaidModule.initialize(getMermaidThemeConfig());
  return mermaidModule;
}

function measureSvgNaturalSize(svg) {
  if (!svg) return { width: 800, height: 600 };
  const vb = svg.viewBox?.baseVal;
  if (vb && vb.width > 0 && vb.height > 0) {
    return { width: vb.width, height: vb.height };
  }
  try {
    const bb = svg.getBBox();
    if (bb.width > 0 && bb.height > 0) {
      return { width: bb.width, height: bb.height };
    }
  } catch {
    /* not laid out */
  }
  const rect = svg.getBoundingClientRect();
  return {
    width: rect.width > 0 ? rect.width : 800,
    height: rect.height > 0 ? rect.height : 600,
  };
}

export default function MermaidDiagram({
  code,
  compact = false,
  embedded = false,
  showDownload = false,
  showZoomControls = true,
  downloadFilename = "logigramme.png",
}) {
  const scrollRef = useRef(null);
  const canvasRef = useRef(null);
  const reactId = useId();
  const dimsRef = useRef({ baseWidth: 0, baseHeight: 0, fitScale: 1, currentScale: 1 });
  const panRef = useRef(null);

  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [zoomLabel, setZoomLabel] = useState("100%");
  const [scaleUi, setScaleUi] = useState({ fit: 1, current: 1 });
  const [themeKey, setThemeKey] = useState(
    () => document.documentElement.getAttribute("data-theme") || "light"
  );

  const updateZoomUi = useCallback(() => {
    const { fitScale, currentScale } = dimsRef.current;
    setZoomLabel(`${Math.round((currentScale / (fitScale || 1)) * 100)}%`);
    setScaleUi({ fit: fitScale || 1, current: currentScale || 1 });
  }, []);

  const applyDimensions = useCallback(() => {
    const canvas = canvasRef.current;
    const svg = canvas?.querySelector("svg");
    const { baseWidth, baseHeight, currentScale } = dimsRef.current;
    if (!canvas || !svg || !baseWidth) return;

    const w = baseWidth * currentScale;
    const h = baseHeight * currentScale;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    svg.style.width = `${baseWidth}px`;
    svg.style.height = `${baseHeight}px`;
    svg.style.maxWidth = "none";
    svg.style.display = "block";
    updateZoomUi();
  }, [updateZoomUi]);

  const computeFitScale = useCallback(() => {
    const scroll = scrollRef.current;
    const { baseWidth, baseHeight } = dimsRef.current;
    if (!scroll || !baseWidth) return 1;
    const pad = 16;
    const availW = Math.max(scroll.clientWidth - pad, 120);
    const availH = Math.max(scroll.clientHeight - pad, 80);
    return Math.min(1, availW / baseWidth, availH / baseHeight);
  }, []);

  const setZoom = useCallback(
    (scale, focalPoint, resetScroll = false) => {
      const fit = dimsRef.current.fitScale || computeFitScale();
      dimsRef.current.fitScale = fit;
      dimsRef.current.currentScale = Math.max(fit, Math.min(ZOOM_MAX, scale));
      applyDimensions();

      const scroll = scrollRef.current;
      if (scroll && focalPoint) {
        requestAnimationFrame(() => {
          scroll.scrollLeft = Math.max(0, focalPoint.x * dimsRef.current.currentScale - scroll.clientWidth / 2);
          scroll.scrollTop = Math.max(0, focalPoint.y * dimsRef.current.currentScale - scroll.clientHeight / 2);
        });
      } else if (resetScroll && scroll) {
        scroll.scrollLeft = 0;
        scroll.scrollTop = 0;
      }
    },
    [applyDimensions, computeFitScale]
  );

  const fitToView = useCallback(
    (resetScroll = true) => {
      const fit = computeFitScale();
      dimsRef.current.fitScale = fit;
      setZoom(fit, null, resetScroll);
    },
    [computeFitScale, setZoom]
  );

  const prepareSvgLayout = useCallback(() => {
    const svg = canvasRef.current?.querySelector("svg");
    if (!svg) return;
    const natural = measureSvgNaturalSize(svg);
    dimsRef.current.baseWidth = natural.width;
    dimsRef.current.baseHeight = natural.height;
    fitToView(true);
  }, [fitToView]);

  useEffect(() => {
    const observer = new MutationObserver(() => {
      const next = document.documentElement.getAttribute("data-theme") || "light";
      setThemeKey((prev) => (prev === next ? prev : next));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const src = (code || "").trim();
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (!src) {
      canvas.innerHTML = "";
      setError("");
      setReady(false);
      dimsRef.current = { baseWidth: 0, baseHeight: 0, fitScale: 1, currentScale: 1 };
      setZoomLabel("100%");
      return;
    }

    let cancelled = false;
    setReady(false);
    setError("");

    (async () => {
      try {
        const mermaid = await loadMermaid();
        if (cancelled) return;
        const renderId = `mmd-${reactId.replace(/:/g, "")}-${Date.now()}`;
        const { svg } = await mermaid.render(renderId, src);
        if (cancelled) return;
        canvas.innerHTML = `<div class="mermaid-diagram-viewport">${svg}</div>`;
        requestAnimationFrame(() => {
          if (!cancelled) {
            prepareSvgLayout();
            setReady(true);
          }
        });
      } catch (err) {
        if (!cancelled) {
          canvas.innerHTML = "";
          setError(err?.message || "Diagramme invalide");
          setReady(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code, reactId, themeKey, prepareSvgLayout]);

  const handleDownload = () => {
    const svg = canvasRef.current?.querySelector("svg");
    if (!svg) return;
    const wrap = scrollRef.current?.closest(".mermaid-diagram-wrap");
    const bg = wrap ? getComputedStyle(wrap).backgroundColor : "#ffffff";
    downloadSvgAsPng(svg, downloadFilename, { background: bg, scale: 2 });
  };

  const handleZoomIn = () => {
    setZoom((dimsRef.current.currentScale || 1) * ZOOM_STEP);
  };

  const handleZoomOut = () => {
    setZoom((dimsRef.current.currentScale || 1) / ZOOM_STEP);
  };

  const handleDblClick = (ev) => {
    if (!ready || error) return;
    const scroll = scrollRef.current;
    if (!scroll || !dimsRef.current.baseWidth) return;
    const fit = dimsRef.current.fitScale || computeFitScale();
    const atFit = Math.abs((dimsRef.current.currentScale || fit) - fit) < 0.02;
    if (!atFit) {
      fitToView(true);
      return;
    }
    const rect = scroll.getBoundingClientRect();
    const scale = dimsRef.current.currentScale || fit;
    const focal = {
      x: (ev.clientX - rect.left + scroll.scrollLeft) / scale,
      y: (ev.clientY - rect.top + scroll.scrollTop) / scale,
    };
    setZoom(fit * DBLCLICK_FACTOR, focal);
  };

  const handlePanStart = (ev) => {
    if (ev.button !== 0 || !scrollRef.current) return;
    panRef.current = {
      x: ev.clientX,
      y: ev.clientY,
      sl: scrollRef.current.scrollLeft,
      st: scrollRef.current.scrollTop,
    };
    scrollRef.current.classList.add("mermaid-diagram-scroll--panning");
  };

  const handlePanMove = (ev) => {
    if (!panRef.current || !scrollRef.current) return;
    scrollRef.current.scrollLeft = panRef.current.sl - (ev.clientX - panRef.current.x);
    scrollRef.current.scrollTop = panRef.current.st - (ev.clientY - panRef.current.y);
  };

  const handlePanEnd = () => {
    panRef.current = null;
    scrollRef.current?.classList.remove("mermaid-diagram-scroll--panning");
  };

  useEffect(() => {
    window.addEventListener("mousemove", handlePanMove);
    window.addEventListener("mouseup", handlePanEnd);
    return () => {
      window.removeEventListener("mousemove", handlePanMove);
      window.removeEventListener("mouseup", handlePanEnd);
    };
  });

  if (!(code || "").trim()) {
    return <p className="mermaid-diagram-empty">Aucun logigramme.</p>;
  }

  const wrapClass = [
    "mermaid-diagram-wrap",
    compact ? "mermaid-diagram-wrap--compact" : "",
    embedded ? "mermaid-diagram-wrap--embedded" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const fitScale = scaleUi.fit;
  const currentScale = scaleUi.current;

  return (
    <div className={wrapClass}>
      {showZoomControls || showDownload ? (
        <div className="mermaid-diagram-toolbar">
          {showZoomControls ? (
            <div className="mermaid-diagram-zoom">
              <button
                type="button"
                className="mermaid-diagram-zoom-btn"
                onClick={handleZoomOut}
                disabled={!ready || currentScale <= fitScale + 0.001}
                aria-label="Zoom arrière"
              >
                −
              </button>
              <span className="mermaid-diagram-zoom-label">{zoomLabel}</span>
              <button
                type="button"
                className="mermaid-diagram-zoom-btn"
                onClick={handleZoomIn}
                disabled={!ready || currentScale >= ZOOM_MAX - 0.001}
                aria-label="Zoom avant"
              >
                +
              </button>
              <button
                type="button"
                className="mermaid-diagram-zoom-btn mermaid-diagram-zoom-fit"
                onClick={() => fitToView(true)}
                disabled={!ready}
              >
                Ajuster
              </button>
            </div>
          ) : null}
          {showDownload ? (
            <button
              type="button"
              className="mermaid-diagram-download"
              onClick={handleDownload}
              disabled={!ready || Boolean(error)}
            >
              Télécharger PNG
            </button>
          ) : null}
        </div>
      ) : null}
      <div
        ref={scrollRef}
        className="mermaid-diagram-scroll"
        onDoubleClick={handleDblClick}
        onMouseDown={handlePanStart}
      >
        <div ref={canvasRef} className="mermaid-diagram-canvas" />
      </div>
      {error ? <pre className="mermaid-diagram-fallback">{code}</pre> : null}
    </div>
  );
}
