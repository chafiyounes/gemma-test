import { useState, useEffect } from "react";
import {
  getApiUrl,
  setApiUrl,
  checkHealth,
  fetchAdminUsers,
  createAdminUser,
  updateAdminUser,
  sessionRoleLabel,
  isAdministrator,
} from "../services/api";
import "./SettingsModal.css";

const TABS_API = "api";
const TABS_USERS = "users";

export default function SettingsModal({ open, onClose, session }) {
  const [activeTab, setActiveTab] = useState(TABS_API);
  const [url, setUrl] = useState("");
  const [health, setHealth] = useState(null);
  const [testing, setTesting] = useState(false);

  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersError, setUsersError] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [busyUserId, setBusyUserId] = useState(null);
  const [pwEdits, setPwEdits] = useState({});

  const showAdminTab = isAdministrator(session?.role);

  useEffect(() => {
    if (open) {
      setUrl(getApiUrl());
      setHealth(null);
      setUsersError("");
    }
  }, [open]);

  useEffect(() => {
    if (!open || activeTab !== TABS_USERS || !showAdminTab) return;
    let cancelled = false;
    (async () => {
      setUsersLoading(true);
      setUsersError("");
      try {
        const data = await fetchAdminUsers();
        if (!cancelled) setUsers(data.users || []);
      } catch (e) {
        if (!cancelled) setUsersError(e.message || "Chargement impossible");
      } finally {
        if (!cancelled) setUsersLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, activeTab, showAdminTab]);

  const handleSave = () => {
    setApiUrl(url);
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

  const loadUsers = async () => {
    setUsersLoading(true);
    setUsersError("");
    try {
      const data = await fetchAdminUsers();
      setUsers(data.users || []);
    } catch (e) {
      setUsersError(e.message || "Erreur");
    } finally {
      setUsersLoading(false);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setUsersError("");
    try {
      await createAdminUser({
        username: newUsername.trim(),
        password: newPassword,
        role: newRole,
      });
      setNewUsername("");
      setNewPassword("");
      setNewRole("user");
      await loadUsers();
    } catch (err) {
      setUsersError(err.message || "Création impossible");
    }
  };

  const handlePasswordSave = async (uid) => {
    const pw = (pwEdits[uid] || "").trim();
    if (pw.length < 4) {
      setUsersError("Mot de passe : 4 caractères minimum");
      return;
    }
    setBusyUserId(uid);
    setUsersError("");
    try {
      await updateAdminUser(uid, { password: pw });
      setPwEdits((prev) => ({ ...prev, [uid]: "" }));
      await loadUsers();
    } catch (err) {
      setUsersError(err.message || "Mise à jour impossible");
    } finally {
      setBusyUserId(null);
    }
  };

  const handleRoleChange = async (uid, role) => {
    setBusyUserId(uid);
    setUsersError("");
    try {
      await updateAdminUser(uid, { role });
      await loadUsers();
    } catch (err) {
      setUsersError(err.message || "Rôle impossible");
    } finally {
      setBusyUserId(null);
    }
  };

  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className={`modal-card ${activeTab === TABS_USERS ? "modal-card-wide" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>Réglages</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Fermer">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="modal-tabs">
          <button
            type="button"
            className={`modal-tab ${activeTab === TABS_API ? "active" : ""}`}
            onClick={() => setActiveTab(TABS_API)}
          >
            API
          </button>
          {showAdminTab && (
            <button
              type="button"
              className={`modal-tab ${activeTab === TABS_USERS ? "active" : ""}`}
              onClick={() => setActiveTab(TABS_USERS)}
            >
              Utilisateurs
            </button>
          )}
        </div>

        <div className="modal-body">
          {activeTab === TABS_API && (
            <>
              <label className="field-label">URL de l&apos;API RunPod</label>
              <input
                className="field-input"
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="http://localhost:9000"
              />
              <p className="field-hint">
                Utilisez http://localhost:9000 avec un tunnel SSH. Une URL publique RunPod seulement si
                l&apos;API est exposée.
              </p>

              <div className="modal-actions">
                <button type="button" className="btn-test" onClick={handleTest} disabled={!url || testing}>
                  {testing ? "Test..." : "Tester"}
                </button>
                <button type="button" className="btn-save" onClick={handleSave} disabled={!url}>
                  Enregistrer
                </button>
              </div>

              {health && (
                <div className={`health-panel ${health.status === "ok" ? "ok" : "bad"}`}>
                  {health.error ? (
                    <div className="health-row">
                      <span>Connexion</span>
                      <span className="val bad">Échec : {health.error}</span>
                    </div>
                  ) : (
                    <>
                      <div className="health-row">
                        <span>Statut</span>
                        <span className={`val ${health.status === "ok" ? "ok" : "bad"}`}>{health.status}</span>
                      </div>
                      <div className="health-row">
                        <span>Modèle</span>
                        <span className={`val ${health.model_available ? "ok" : "bad"}`}>
                          {health.model_available ? `✓ ${health.model_name}` : "✗ Indisponible"}
                        </span>
                      </div>
                      <div className="health-row">
                        <span>vLLM</span>
                        <span className="val ok">{health.vllm_url}</span>
                      </div>
                    </>
                  )}
                </div>
              )}
            </>
          )}

          {activeTab === TABS_USERS && showAdminTab && (
            <div className="admin-users">
              {usersError && <div className="admin-users-error">{usersError}</div>}
              {usersLoading ? (
                <p className="field-hint">Chargement…</p>
              ) : (
                <div className="admin-users-table-wrap">
                  <table className="admin-users-table">
                    <thead>
                      <tr>
                        <th>Utilisateur</th>
                        <th>Rôle</th>
                        <th>Créé</th>
                        <th>Mot de passe</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((u) => (
                        <tr key={u.id}>
                          <td>{u.username}</td>
                          <td>
                            <select
                              className="field-input admin-role-select"
                              value={u.role}
                              disabled={busyUserId === u.id}
                              onChange={(e) => handleRoleChange(u.id, e.target.value)}
                            >
                              <option value="user">Utilisateur</option>
                              <option value="manager">Gestionnaire</option>
                              <option value="administrator">Administrateur</option>
                            </select>
                          </td>
                          <td className="admin-users-date">{u.created_at || "—"}</td>
                          <td>
                            <div className="admin-pw-row">
                              <input
                                type="password"
                                className="field-input"
                                placeholder="Nouveau"
                                autoComplete="new-password"
                                value={pwEdits[u.id] || ""}
                                onChange={(e) =>
                                  setPwEdits((prev) => ({ ...prev, [u.id]: e.target.value }))
                                }
                              />
                              <button
                                type="button"
                                className="btn-test"
                                disabled={busyUserId === u.id}
                                onClick={() => handlePasswordSave(u.id)}
                              >
                                OK
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <h3 className="admin-users-subtitle">Nouvel utilisateur</h3>
              <form className="admin-create-form" onSubmit={handleCreateUser}>
                <input
                  className="field-input"
                  placeholder="Nom d&apos;utilisateur"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  minLength={2}
                  required
                />
                <input
                  type="password"
                  className="field-input"
                  placeholder="Mot de passe (min. 4)"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  minLength={4}
                  required
                  autoComplete="new-password"
                />
                <select
                  className="field-input"
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                >
                  <option value="user">Utilisateur</option>
                  <option value="manager">Gestionnaire</option>
                  <option value="administrator">Administrateur</option>
                </select>
                <button type="submit" className="btn-save" style={{ flex: "0 0 auto" }}>
                  Créer
                </button>
              </form>
              <p className="field-hint">
                Rôles affichés : {sessionRoleLabel("user")}, {sessionRoleLabel("manager")},{" "}
                {sessionRoleLabel("administrator")}.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
