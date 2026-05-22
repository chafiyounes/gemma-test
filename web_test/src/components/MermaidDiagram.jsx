import { useEffect, useId, useRef, useState } from "react";
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

export default function MermaidDiagram({ code }) {
  const containerRef = useRef(null);
  const reactId = useId();
  const [error, setError] = useState("");

  useEffect(() => {
    const src = (code || "").trim();
    const el = containerRef.current;
    if (!el) return;

    if (!src) {
      el.innerHTML = "";
      setError("");
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const mermaid = await loadMermaid();
        if (cancelled) return;
        const renderId = `mmd-${reactId.replace(/:/g, "")}-${Date.now()}`;
        const { svg } = await mermaid.render(renderId, src);
        if (cancelled) return;
        el.innerHTML = svg;
        setError("");
      } catch (err) {
        if (!cancelled) {
          el.innerHTML = "";
          setError(err?.message || "Diagramme invalide");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code, reactId]);

  if (!(code || "").trim()) {
    return <p className="mermaid-diagram-empty">Aucun logigramme.</p>;
  }

  return (
    <div className="mermaid-diagram-wrap">
      <div ref={containerRef} className="mermaid-diagram" />
      {error ? <pre className="mermaid-diagram-fallback">{code}</pre> : null}
    </div>
  );
}
