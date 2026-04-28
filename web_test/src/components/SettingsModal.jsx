import { useState, useEffect } from "react";
import { getApiUrl, setApiUrl, checkHealth, getDebugRag, setDebugRag } from "../services/api";
import "./SettingsModal.css";

export default function SettingsModal({ open, onClose }) {
  const [url, setUrl] = useState("");
  const [debugRag, setDebugRagState] = useState(false);
  const [health, setHealth] = useState(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (open) {
      setUrl(getApiUrl());
      setDebugRagState(getDebugRag());
    }
  }, [open]);

  const handleSave = () => {
    setApiUrl(url);
    setDebugRag(debugRag);
    onClose();
  };

  const handleTest = async () => {
    setApiUrl(url);
    setTesting(true);
    setHealth(null);
    try {
      const data = await checkHealth();
      setHealth(data);
    } catch (err) {
      setHealth({ status: "error", error: err.message });
    } finally {
      setTesting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Settings</h2>
          <button className="modal-close" onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="modal-body">
          <label className="field-label">RunPod API URL</label>
          <input
            className="field-input"
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="http://localhost:9000"
          />
          <p className="field-hint">
            Use http://localhost:9000 when you are connected through an SSH tunnel. Use a public RunPod URL only if you exposed the API directly.
          </p>

          <label className="toggle-row">
            <div>
              <span className="field-label toggle-label">Show RAG debug info</span>
              <p className="field-hint toggle-hint">
                Adds selected chunks, retrieval scores, and injected context to assistant messages.
              </p>
            </div>
            <input
              className="toggle-input"
              type="checkbox"
              checked={debugRag}
              onChange={(e) => setDebugRagState(e.target.checked)}
            />
          </label>

          <div className="modal-actions">
            <button className="btn-test" onClick={handleTest} disabled={!url || testing}>
              {testing ? "Testing..." : "Test connection"}
            </button>
            <button className="btn-save" onClick={handleSave} disabled={!url}>
              Save
            </button>
          </div>

          {health && (
            <div className={`health-panel ${health.status === "healthy" ? "ok" : "bad"}`}>
              {health.error ? (
                <div className="health-row">
                  <span>Connection</span>
                  <span className="val bad">Failed: {health.error}</span>
                </div>
              ) : (
                <>
                  <div className="health-row">
                    <span>Status</span>
                    <span className={`val ${health.status === "healthy" ? "ok" : "bad"}`}>
                      {health.status}
                    </span>
                  </div>
                  <div className="health-row">
                    <span>LLM Model</span>
                    <span className={`val ${health.model_loaded ? "ok" : "bad"}`}>
                      {health.model_loaded ? "✓ Loaded" : "✗ Not loaded"}
                    </span>
                  </div>
                  <div className="health-row">
                    <span>Vector DB</span>
                    <span className={`val ${health.vectordb_connected ? "ok" : "bad"}`}>
                      {health.vectordb_connected ? "✓ Connected" : "✗ Down"}
                    </span>
                  </div>
                  <div className="health-row">
                    <span>Redis Cache</span>
                    <span className={`val ${health.redis_connected ? "ok" : "bad"}`}>
                      {health.redis_connected ? "✓ Connected" : "✗ Down"}
                    </span>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
