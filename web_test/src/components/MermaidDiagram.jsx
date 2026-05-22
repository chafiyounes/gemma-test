import { useEffect, useId, useRef, useState } from "react";
import { downloadSvgAsPng } from "../lib/downloadSvgAsPng";
import "./MermaidDiagram.css";

let mermaidModule = null;

const MERMAID_CONFIG = {
  startOnLoad: false,
  securityLevel: "loose",
  theme: "neutral",
  flowchart: {
    htmlLabels: true,
    useMaxWidth: false,
    wrappingWidth: 200,
  },
  themeVariables: {
    fontSize: "15px",
    fontFamily: "system-ui, Segoe UI, sans-serif",
  },
};

async function loadMermaid() {
  if (mermaidModule) return mermaidModule;
  const mod = await import("mermaid");
  mermaidModule = mod.default;
  mermaidModule.initialize(MERMAID_CONFIG);
  return mermaidModule;
}

export default function MermaidDiagram({
  code,
  compact = false,
  showDownload = false,
  downloadFilename = "logigramme.png",
}) {
  const containerRef = useRef(null);
  const reactId = useId();
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const src = (code || "").trim();
    const el = containerRef.current;
    if (!el) return;

    if (!src) {
      el.innerHTML = "";
      setError("");
      setReady(false);
      return;
    }

    let cancelled = false;
    setReady(false);

    (async () => {
      try {
        const mermaid = await loadMermaid();
        if (cancelled) return;
        const renderId = `mmd-${reactId.replace(/:/g, "")}-${Date.now()}`;
        const { svg } = await mermaid.render(renderId, src);
        if (cancelled) return;
        el.innerHTML = svg;
        setError("");
        setReady(true);
      } catch (err) {
        if (!cancelled) {
          el.innerHTML = "";
          setError(err?.message || "Diagramme invalide");
          setReady(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code, reactId]);

  const handleDownload = () => {
    const svg = containerRef.current?.querySelector("svg");
    if (!svg) return;
    const wrap = containerRef.current?.closest(".mermaid-diagram-wrap");
    const bg = wrap ? getComputedStyle(wrap).backgroundColor : "#ffffff";
    downloadSvgAsPng(svg, downloadFilename, { background: bg, scale: 2 });
  };

  if (!(code || "").trim()) {
    return <p className="mermaid-diagram-empty">Aucun logigramme.</p>;
  }

  const wrapClass = [
    "mermaid-diagram-wrap",
    compact ? "mermaid-diagram-wrap--compact" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={wrapClass}>
      {showDownload ? (
        <div className="mermaid-diagram-toolbar">
          <button
            type="button"
            className="mermaid-diagram-download"
            onClick={handleDownload}
            disabled={!ready || Boolean(error)}
          >
            Télécharger PNG
          </button>
        </div>
      ) : null}
      <div ref={containerRef} className="mermaid-diagram" />
      {error ? <pre className="mermaid-diagram-fallback">{code}</pre> : null}
    </div>
  );
}
