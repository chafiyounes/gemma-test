import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { renderAsync } from "docx-preview";
import { fetchDocumentFileBlob, fetchDocumentPreview } from "../services/api";
import { renderFormattedMessage } from "../lib/messageFormat";
import "./DocumentPreviewModal.css";

const MermaidDiagram = lazy(() => import("./MermaidDiagram"));

export default function DocumentPreviewModal({ name, categoryHint, onClose }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null);
  const [tab, setTab] = useState("docx");
  const docxContainerRef = useRef(null);

  const loadPreview = useCallback(async () => {
    setLoading(true);
    setError("");
    setPreview(null);
    try {
      const data = await fetchDocumentPreview({ name, category: categoryHint });
      setPreview(data);
      if (data.has_docx) {
        setTab("docx");
      } else if (data.has_md && (data.markdown || "").trim()) {
        setTab("markdown");
      } else if (data.has_logigramme) {
        setTab("logigramme");
      }
    } catch (err) {
      setError(err.message || "Document introuvable");
    } finally {
      setLoading(false);
    }
  }, [name, categoryHint]);

  useEffect(() => {
    loadPreview();
  }, [loadPreview]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (!preview?.has_docx || !preview.docx_url || tab !== "docx") return;
    const container = docxContainerRef.current;
    if (!container) return;

    let cancelled = false;
    container.innerHTML = "";

    (async () => {
      try {
        const blob = await fetchDocumentFileBlob(preview.docx_url);
        if (cancelled) return;
        await renderAsync(blob, container, null, {
          className: "docx-preview-page",
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
        });
      } catch (err) {
        if (!cancelled) {
          setError(err.message || "Impossible d'afficher le fichier Word");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [preview, tab]);

  const showDocxTab = preview?.has_docx;
  const showMdTab = preview?.has_md && (preview.markdown || "").trim();
  const showLogigrammeTab = preview?.has_logigramme && (preview.logigramme || "").trim();
  const showTabs = showDocxTab || showMdTab || showLogigrammeTab;

  return (
    <div
      className="doc-preview-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="doc-preview-title"
      onClick={onClose}
    >
      <div className="doc-preview-panel" onClick={(e) => e.stopPropagation()}>
        <header className="doc-preview-header">
          <h2 id="doc-preview-title" className="doc-preview-title">
            {preview?.title || name}
          </h2>
          <button type="button" className="doc-preview-close" onClick={onClose} aria-label="Fermer">
            ×
          </button>
        </header>

        {!loading && !error && preview && showTabs ? (
          <div className="doc-preview-tabs" role="tablist">
            {showDocxTab ? (
              <button
                type="button"
                role="tab"
                aria-selected={tab === "docx"}
                className={`doc-preview-tab ${tab === "docx" ? "active" : ""}`}
                onClick={() => setTab("docx")}
              >
                Word
              </button>
            ) : null}
            {showMdTab ? (
              <button
                type="button"
                role="tab"
                aria-selected={tab === "markdown"}
                className={`doc-preview-tab ${tab === "markdown" ? "active" : ""}`}
                onClick={() => setTab("markdown")}
              >
                Markdown
              </button>
            ) : null}
            {showLogigrammeTab ? (
              <button
                type="button"
                role="tab"
                aria-selected={tab === "logigramme"}
                className={`doc-preview-tab ${tab === "logigramme" ? "active" : ""}`}
                onClick={() => setTab("logigramme")}
              >
                Logigramme
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="doc-preview-body">
          {loading ? <p className="doc-preview-status">Chargement…</p> : null}
          {error ? <p className="doc-preview-status doc-preview-error">{error}</p> : null}
          {!loading && !error && preview ? (
            <>
              {tab === "docx" && showDocxTab ? (
                <div ref={docxContainerRef} className="doc-preview-docx" />
              ) : null}
              {tab === "markdown" && showMdTab ? (
                <div className="doc-preview-markdown msg-text">
                  {renderFormattedMessage(preview.markdown)}
                </div>
              ) : null}
              {tab === "logigramme" && showLogigrammeTab ? (
                <div className="doc-preview-logigramme">
                  <Suspense fallback={<p className="doc-preview-status">Chargement du diagramme…</p>}>
                    <MermaidDiagram code={preview.logigramme} />
                  </Suspense>
                </div>
              ) : null}
              {!showTabs ? (
                <p className="doc-preview-status">Aucun contenu disponible pour ce document.</p>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
