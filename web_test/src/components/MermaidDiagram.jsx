import { useEffect, useRef, useState } from "react";
import "./MermaidDiagram.css";

let mermaidPromise;

function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import("mermaid").then((mod) => {
      const mermaid = mod.default;
      mermaid.initialize({
        startOnLoad: false,
        theme: "neutral",
        securityLevel: "strict",
        flowchart: { htmlLabels: true, curve: "basis" },
      });
      return mermaid;
    });
  }
  return mermaidPromise;
}

export default function MermaidDiagram({ code }) {
  const containerRef = useRef(null);
  const [error, setError] = useState("");
  const [svg, setSvg] = useState("");

  useEffect(() => {
    let cancelled = false;
    setError("");
    setSvg("");

    loadMermaid()
      .then(async (mermaid) => {
        if (cancelled || !containerRef.current) return;
        const id = `mmd-${Math.random().toString(36).slice(2)}`;
        const { svg: rendered } = await mermaid.render(id, code);
        if (!cancelled) setSvg(rendered);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.message || "Impossible de rendre le diagramme.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [code]);

  if (error) {
    return (
      <div className="msg-mermaid-wrap">
        <pre className="msg-mermaid-fallback">{code}</pre>
        <a
          className="msg-mermaid-link"
          href={`https://mermaid.live/edit#pako:${encodeURIComponent(code)}`}
          target="_blank"
          rel="noreferrer"
        >
          Ouvrir dans Mermaid Live
        </a>
      </div>
    );
  }

  return (
    <div className="msg-mermaid-wrap" ref={containerRef}>
      {svg ? (
        <div className="msg-mermaid-svg" dangerouslySetInnerHTML={{ __html: svg }} />
      ) : (
        <div className="msg-mermaid-loading">Chargement du diagramme…</div>
      )}
    </div>
  );
}
