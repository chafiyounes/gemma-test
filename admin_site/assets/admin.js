/** Theme (shared with chat — sendbot_theme). */
(function initSendbotTheme() {
  const KEY = "sendbot_theme";
  function getTheme() {
    try {
      const stored = localStorage.getItem(KEY);
      if (stored === "dark" || stored === "light") return stored;
    } catch {
      /* ignore */
    }
    return "light";
  }
  function applyTheme(theme) {
    const next = theme === "dark" ? "dark" : "light";
    const root = document.documentElement;
    root.setAttribute("data-theme", next);
    root.style.colorScheme = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
    const btn = document.getElementById("theme-toggle");
    if (btn) {
      const dark = next === "dark";
      btn.setAttribute("aria-label", dark ? "Mode clair" : "Mode sombre");
      btn.setAttribute("title", dark ? "Mode clair" : "Mode sombre");
      btn.innerHTML = dark
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    }
  }
  applyTheme(getTheme());
  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.addEventListener("click", () => {
        applyTheme(getTheme() === "dark" ? "light" : "dark");
      });
    }
  });
})();

/** Document admin JSON + multipart API (also under /admin/documents/* for compatibility). */
const DOCS_API_BASE = "/api/admin/documents";

const state = {
  session: null,
  items: [],
  selectedId: null,
  search: "",
  feedbackValue: "",
  feedbackReason: "",
  conversationCache: {},
  adminView: "interactions",
  docsOverview: null,
  docsDraft: null,
  docsDirty: false,
  docsPinnedExpandCategory: null,
  docsRevealScrollKeys: null,
  usersList: [],
};

const loginForm = document.getElementById("login-form");
const adminUsernameInput = document.getElementById("admin-username");
const passwordInput = document.getElementById("admin-password");
const loginError = document.getElementById("login-error");
const sessionCard = document.getElementById("session-card");
const sessionRole = document.getElementById("session-role");
const logoutButton = document.getElementById("logout-button");
const refreshButton = document.getElementById("refresh-button");
const gitRefreshButton = document.getElementById("git-refresh-button");
const ragReloadButton = document.getElementById("rag-reload-button");
const evalToggle = document.getElementById("eval-toggle");
const gatedContent = document.getElementById("gated-content");
const preAuthPanel = document.getElementById("admin-pre-auth");
const dashboardRoot = document.getElementById("admin-dashboard-root");
const searchInput = document.getElementById("search-input");
const feedbackFilter = document.getElementById("feedback-filter");
const reasonFilter = document.getElementById("reason-filter");
const interactionList = document.getElementById("interaction-list");
const interactionDetail = document.getElementById("interaction-detail");
const resultsCount = document.getElementById("results-count");
const interactionsView = document.getElementById("interactions-view");
const documentsView = document.getElementById("documents-view");
const viewInteractionsButton = document.getElementById("view-interactions-button");
const viewDocumentsButton = document.getElementById("view-documents-button");
const viewUsersButton = document.getElementById("view-users-button");
const usersView = document.getElementById("users-view");
const usersTableWrap = document.getElementById("users-table-wrap");
const usersError = document.getElementById("users-error");
const usersRefreshButton = document.getElementById("users-refresh-button");
const usersNewUsername = document.getElementById("users-new-username");
const usersNewPassword = document.getElementById("users-new-password");
const usersNewRole = document.getElementById("users-new-role");
const usersCreateButton = document.getElementById("users-create-button");
const documentsBudget = document.getElementById("documents-budget");
const documentsCategories = document.getElementById("documents-categories");
const docCategoryInput = document.getElementById("doc-category-input");
const docFileInput = document.getElementById("doc-file-input");
const docFolderInput = document.getElementById("doc-folder-input");
const docAddFolderButton = document.getElementById("doc-add-folder-button");
const docSaveButton = document.getElementById("doc-save-button");
const docDiscardButton = document.getElementById("doc-discard-button");
const docRefreshButton = document.getElementById("doc-refresh-button");
const docPendingSummary = document.getElementById("doc-pending-summary");
const docError = document.getElementById("doc-error");
const docReplaceInput = document.getElementById("doc-replace-input");
let activeToggleConfirmationCleanup = null;
let docReplaceTarget = null;

function roleRank(role) {
  const r = String(role || "").toLowerCase();
  if (r === "administrator" || r === "admin") return 3;
  if (r === "manager") return 2;
  if (r === "user") return 1;
  return 0;
}

function canUseStaffConsole(role) {
  return roleRank(role) >= 2;
}

function isAdministratorRole(role) {
  return roleRank(role) >= 3;
}

function setToggleLoading(button, loadingLabel, isLoading) {
  if (!button) return;

  if (isLoading) {
    if (button.dataset.loading === "true") return;

    button.classList.add("is-loading");
    button.dataset.loading = "true";
    button.dataset.previousText = button.textContent;
    button.dataset.previousDisabled = button.disabled ? "true" : "false";
    button.textContent = loadingLabel;
    button.disabled = true;
    return;
  }

  button.classList.remove("is-loading");
  if (button.dataset.loading !== "true") return;

  button.dataset.loading = "false";
  if (button.dataset.previousText) {
    button.textContent = button.dataset.previousText;
  }

  button.disabled = button.dataset.previousDisabled === "true";
  delete button.dataset.previousText;
  delete button.dataset.previousDisabled;
}

function clearToggleConfirmation() {
  if (activeToggleConfirmationCleanup) {
    activeToggleConfirmationCleanup();
    activeToggleConfirmationCleanup = null;
  }
}

function showToggleConfirmation(button, featureName, nextEnabled, onConfirm) {
  clearToggleConfirmation();

  const actionText = nextEnabled ? "Enable" : "Disable";
  const actionsContainer = button.parentElement;
  if (!actionsContainer) {
    onConfirm();
    return;
  }

  const controls = document.createElement("div");
  controls.className = "toggle-confirm-controls";

  const label = document.createElement("span");
  label.className = "toggle-confirm-label";
  label.textContent = `${actionText} ${featureName}?`;

  const confirmButton = document.createElement("button");
  confirmButton.type = "button";
  confirmButton.className = "toolbar-button toggle-confirm-yes";
  confirmButton.textContent = "Confirm";

  const cancelButton = document.createElement("button");
  cancelButton.type = "button";
  cancelButton.className = "toolbar-button toggle-confirm-no";
  cancelButton.textContent = "Cancel";

  controls.appendChild(label);
  controls.appendChild(confirmButton);
  controls.appendChild(cancelButton);

  button.disabled = true;
  button.classList.add("confirm-pending");
  actionsContainer.appendChild(controls);

  const cleanup = () => {
    controls.remove();
    button.classList.remove("confirm-pending");
    if (button.dataset.loading !== "true") {
      button.disabled = button.dataset.available !== "true";
    }
  };

  activeToggleConfirmationCleanup = cleanup;

  confirmButton.addEventListener("click", async () => {
    cleanup();
    activeToggleConfirmationCleanup = null;
    await onConfirm();
  });

  cancelButton.addEventListener("click", () => {
    cleanup();
    activeToggleConfirmationCleanup = null;
  });
}

async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    ...options,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    let msg = payload.detail || `HTTP ${response.status}`;
    if (response.status === 413) {
      msg =
        typeof msg === "string"
          ? msg
          : "Fichiers trop volumineux pour le serveur (413). Essayez moins de fichiers a la fois ou augmentez la limite du reverse-proxy.";
    }
    const error = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    error.status = response.status;
    throw error;
  }

  return response;
}

async function loadSession() {
  const response = await apiFetch("/auth/session");
  const session = await response.json();
  state.session = session.authenticated ? session : null;
  renderSession();
}

function renderSession() {
  const staff = canUseStaffConsole(state.session?.role);
  loginForm.classList.toggle("hidden", Boolean(staff));
  sessionCard.classList.toggle("hidden", !staff);
  if (preAuthPanel) preAuthPanel.classList.toggle("hidden", Boolean(staff));
  if (dashboardRoot) dashboardRoot.classList.toggle("hidden", !staff);
  document.body.classList.toggle("admin-console-manager", Boolean(staff && !isAdministratorRole(state.session?.role)));
  document.body.classList.toggle("admin-console-full", Boolean(staff && isAdministratorRole(state.session?.role)));
  if (staff) {
    sessionRole.textContent = isAdministratorRole(state.session.role) ? "Administrateur" : "Gestionnaire documents";
    if (!isAdministratorRole(state.session.role)) {
      state.adminView = "documents";
    }
    setAdminView(state.adminView || (isAdministratorRole(state.session.role) ? "interactions" : "documents"));
  }
  const userHint = document.getElementById("pre-auth-user-hint");
  if (userHint) {
    const showUserHint = Boolean(state.session?.authenticated && state.session?.role === "user");
    userHint.classList.toggle("hidden", !showUserHint);
  }
}

function setAdminView(view) {
  const mgrOnly = canUseStaffConsole(state.session?.role) && !isAdministratorRole(state.session?.role);
  if (mgrOnly) {
    state.adminView = "documents";
  } else if (view === "documents") {
    state.adminView = "documents";
  } else if (view === "users") {
    state.adminView = "users";
  } else {
    state.adminView = "interactions";
  }
  if (interactionsView) interactionsView.classList.toggle("hidden", state.adminView !== "interactions");
  if (documentsView) documentsView.classList.toggle("hidden", state.adminView !== "documents");
  if (usersView) usersView.classList.toggle("hidden", state.adminView !== "users");
  if (viewInteractionsButton) viewInteractionsButton.classList.toggle("active", state.adminView === "interactions");
  if (viewDocumentsButton) viewDocumentsButton.classList.toggle("active", state.adminView === "documents");
  if (viewUsersButton) viewUsersButton.classList.toggle("active", state.adminView === "users");
  const toolbarSub = document.querySelector(".toolbar-subtitle");
  if (toolbarSub) {
    if (state.adminView === "documents") {
      toolbarSub.textContent = "Corpus RAG, import et enregistrement sur le disque.";
    } else if (state.adminView === "users") {
      toolbarSub.textContent = "Gérer les comptes, rôles et mots de passe.";
    } else {
      toolbarSub.textContent = "Filtrer les interactions et consulter le détail.";
    }
  }
}

function showUsersError(message) {
  if (!usersError) return;
  usersError.textContent = message;
  usersError.classList.remove("hidden");
}

function clearUsersError() {
  if (!usersError) return;
  usersError.textContent = "";
  usersError.classList.add("hidden");
}

async function loadUsersList() {
  clearUsersError();
  if (!isAdministratorRole(state.session?.role)) return;
  try {
    const res = await apiFetch("/api/admin/users");
    const data = await res.json();
    state.usersList = data.users || [];
    renderUsersTable();
  } catch (error) {
    showUsersError(error.message || "Impossible de charger les utilisateurs.");
  }
}

function renderUsersTable() {
  if (!usersTableWrap) return;
  const users = state.usersList || [];
  const esc = (s) =>
    String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  if (!users.length) {
    usersTableWrap.innerHTML = '<p class="users-lead">Aucun compte.</p>';
    return;
  }
  let html =
    '<table class="users-table"><thead><tr><th>Identifiant</th><th>Rôle</th><th>Créé</th><th>Mot de passe</th></tr></thead><tbody>';
  for (const u of users) {
    const id = Number(u.id);
    html += `<tr data-user-id="${id}"><td>${esc(u.username)}</td><td>`;
    html += `<select class="users-field users-select js-user-role" data-user-id="${id}" aria-label="Rôle ${esc(u.username)}">`;
    const opts = [
      ["user", "Utilisateur"],
      ["manager", "Gestionnaire"],
      ["administrator", "Administrateur"],
    ];
    for (const [val, lab] of opts) {
      const sel = u.role === val ? " selected" : "";
      html += `<option value="${val}"${sel}>${lab}</option>`;
    }
    html += "</select></td>";
    html += `<td class="users-created-cell">${esc(u.created_at || "—")}</td>`;
    html += "<td><div class=\"users-pw-cell\">";
    html += `<input type="password" class="users-field js-user-pw" data-user-id="${id}" placeholder="Nouveau" autocomplete="new-password" />`;
    html += `<button type="button" class="toolbar-button secondary js-user-pw-save" data-user-id="${id}">Enregistrer</button>`;
    html += "</div></td></tr>";
  }
  html += "</tbody></table>";
  usersTableWrap.innerHTML = html;

  usersTableWrap.querySelectorAll(".js-user-role").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const uid = Number(sel.dataset.userId);
      const role = sel.value;
      clearUsersError();
      try {
        await apiFetch(`/api/admin/users/${uid}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role }),
        });
        await loadUsersList();
      } catch (error) {
        showUsersError(error.message || "Mise à jour du rôle impossible.");
        await loadUsersList();
      }
    });
  });

  usersTableWrap.querySelectorAll(".js-user-pw-save").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const uid = Number(btn.dataset.userId);
      const input = usersTableWrap.querySelector(`.js-user-pw[data-user-id="${uid}"]`);
      const pw = (input?.value || "").trim();
      if (pw.length < 4) {
        showUsersError("Mot de passe : au moins 4 caractères.");
        return;
      }
      clearUsersError();
      try {
        await apiFetch(`/api/admin/users/${uid}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password: pw }),
        });
        if (input) input.value = "";
        await loadUsersList();
      } catch (error) {
        showUsersError(error.message || "Mise à jour du mot de passe impossible.");
      }
    });
  });
}

async function handleLogin(event) {
  event.preventDefault();
  loginError.classList.add("hidden");

  try {
    const response = await apiFetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: (adminUsernameInput?.value || "").trim(),
        password: passwordInput.value,
      }),
    });
    const session = await response.json();
    if (!canUseStaffConsole(session.role)) {
      await handleLogout();
      throw new Error("Compte gestionnaire ou administrateur requis pour cette interface.");
    }
    if (adminUsernameInput) adminUsernameInput.value = "";
    passwordInput.value = "";
    state.session = session;
    renderSession();
    await Promise.allSettled([loadInteractions(), loadEvalStatus(), loadDocumentsOverview()]);
  } catch (error) {
    loginError.textContent = error.message;
    loginError.classList.remove("hidden");
  }
}

async function handleLogout() {
  await fetch("/auth/logout", {
    method: "POST",
    credentials: "include",
  });
  state.session = null;
  state.items = [];
  state.selectedId = null;
  state.docsOverview = null;
  state.usersList = [];
  if (usersTableWrap) usersTableWrap.innerHTML = "";
  clearUsersError();
  renderSession();
  renderList();
  renderDetail(null);
}

function buildListQuery() {
  const params = new URLSearchParams();
  params.set("limit", "40");
  if (state.search) params.set("search", state.search);
  if (state.feedbackValue) params.set("feedback_value", state.feedbackValue);
  if (state.feedbackReason) params.set("feedback_reason", state.feedbackReason);
  return params.toString();
}

function showDocError(message) {
  if (!docError) return;
  if (!message) {
    docError.textContent = "";
    docError.classList.add("hidden");
    docError.classList.remove("doc-flash-info");
    return;
  }
  docError.textContent = message;
  docError.classList.remove("doc-flash-info");
  docError.classList.remove("hidden");
}

function showDocInfo(message) {
  if (!docError) return;
  if (!message) {
    docError.textContent = "";
    docError.classList.add("hidden");
    docError.classList.remove("doc-flash-info");
    return;
  }
  docError.textContent = message;
  docError.classList.add("doc-flash-info");
  docError.classList.remove("hidden");
}

/** Single corpus: manual override or server default (RAG_DEFAULT_CATEGORY). */
function getCorpusCategory() {
  const manual = (docCategoryInput?.value || "").trim();
  if (manual) return manual;
  const fromServer = (state.docsOverview?.corpus?.default_category || "").trim();
  return fromServer || "procedures";
}

function isAllowedCorpusUpload(name) {
  const n = (name || "").toLowerCase();
  return n.endsWith(".docx") || n.endsWith(".txt") || n.endsWith(".md");
}

function inferStagedSourceFromFilename(filename) {
  const n = (filename || "").toLowerCase();
  if (n.endsWith(".txt")) return "txt";
  if (n.endsWith(".md")) return "md";
  return "docx";
}

function docFileKindLabel(filename) {
  const n = (filename || "").toLowerCase();
  if (n.endsWith(".docx")) return "DOCX";
  if (n.endsWith(".txt")) return "TXT";
  if (n.endsWith(".md")) return "MD";
  return "FILE";
}

async function addFilesToDraftFromFileList(fileList) {
  showDocError("");
  showDocInfo("");
  try {
    await ensureDocsReadyForEdits();
  } catch (error) {
    showDocError(error.message || "Chargez la vue Documents (ou reconnectez-vous).");
    return;
  }
  const category = getCorpusCategory();
  const raw = Array.from(fileList || []);
  let extSkipped = 0;
  const allowed = [];
  for (const f of raw) {
    if (isAllowedCorpusUpload(f.name)) allowed.push(f);
    else extSkipped += 1;
  }
  if (!allowed.length) {
    showDocError(
      extSkipped ? "Aucun fichier .docx, .txt ou .md dans la sélection." : "",
    );
    return;
  }
  const { modalQueue, anyAdded, draftConflictSkip, revealKeys } = stageIncomingFiles(allowed, category);
  applyDocsReveal(revealKeys);
  const msgParts = [];
  if (extSkipped) msgParts.push(`${extSkipped} ignoré(s) (extension).`);
  if (draftConflictSkip) {
    msgParts.push(
      `${draftConflictSkip} ignoré(s) (ce nom est déjà dans le brouillon pour un déplacement ou un autre remplacement).`,
    );
  }
  if (modalQueue.length) {
    openOverwriteConflictsModal(modalQueue);
  }
  if (msgParts.length) showDocError(msgParts.join(" "));
  else if (!modalQueue.length && anyAdded) showDocError("");
  renderDocuments();
}

async function processDocFileInputSelection() {
  await addFilesToDraftFromFileList(docFileInput?.files);
  if (docFileInput) docFileInput.value = "";
}

/** Draft is null until overview loads; adding files before that was a no-op. */
async function ensureDocsReadyForEdits() {
  if (!state.docsOverview || !state.docsDraft) {
    await loadDocumentsOverview();
  }
  if (!state.docsDraft) {
    throw new Error("Impossible d'initialiser le gestionnaire de documents.");
  }
}

function initDocsDraft() {
  const cats = (state.docsOverview?.categories || []).map((cat) => ({
    name: cat.name,
    active_source: cat.active_source,
    files: (cat.files || []).map((f) => ({
      name: f.name,
      source: f.source,
      chars: f.chars,
      isPending: false,
      pendingOp: "",
    })),
  }));
  state.docsDraft = {
    categories: cats,
    uploads: [],
    moves: [],
    deletes: [],
  };
  state.docsDirty = false;
  state.docsPinnedExpandCategory = null;
  state.docsRevealScrollKeys = null;
}

function ensureDraftCategory(name) {
  const n = String(name || "").trim();
  if (!n) return null;
  const existing = state.docsDraft.categories.find((c) => c.name === n);
  if (existing) return existing;
  const created = { name: n, active_source: "draft", files: [] };
  state.docsDraft.categories.push(created);
  return created;
}

function _setDirty(flag = true) {
  state.docsDirty = flag;
}

function updatePendingSummary() {
  if (!docPendingSummary || !state.docsDraft) return;
  const rep = state.docsDraft.uploads.filter((u) => u.replaceOf).length;
  const add = state.docsDraft.uploads.length - rep;
  const mv = state.docsDraft.moves.length;
  const delOnly = Math.max(0, state.docsDraft.deletes.length - rep);
  const total = state.docsDraft.uploads.length + state.docsDraft.moves.length + state.docsDraft.deletes.length;
  if (total === 0) {
    docPendingSummary.textContent =
      "Aucun changement en attente. Les modifications ci-dessous sont déjà sur le disque jusqu’à ce que vous enregistriez.";
  } else {
    const parts = [];
    if (add) parts.push(`${add} ajout`);
    if (rep) parts.push(`${rep} remplacement`);
    if (mv) parts.push(`${mv} déplacement`);
    if (delOnly) parts.push(`${delOnly} suppression`);
    docPendingSummary.textContent = `Brouillon : ${parts.join(" · ")} — cliquez « Enregistrer sur le disque » pour appliquer.`;
  }
  docPendingSummary.classList.toggle("doc-draft-status--dirty", total > 0);
  if (docSaveButton) docSaveButton.disabled = total === 0;
  if (docDiscardButton) docDiscardButton.disabled = total === 0;
}

function draftMoveFile(fromCategory, filename, sourceKind, targetCategory) {
  if (!state.docsDraft) return;
  const from = state.docsDraft.categories.find((c) => c.name === fromCategory);
  const to = ensureDraftCategory(targetCategory);
  if (!from || !to || fromCategory === targetCategory) return;
  const idx = from.files.findIndex((f) => f.name === filename && f.source === sourceKind);
  if (idx < 0) return;
  const [file] = from.files.splice(idx, 1);
  file.isPending = true;
  file.pendingOp = "move";
  to.files.push(file);
  state.docsDraft.moves.push({
    source_category: fromCategory,
    target_category: targetCategory,
    source_kind: sourceKind,
    filename,
  });
  _setDirty(true);
}

/** Restore a row from the last loaded server overview (draft-only mirror). */
function draftRowFromOverview(category, filename, sourceKind) {
  const liveCat = state.docsOverview?.categories?.find((c) => c.name === category);
  const f = liveCat?.files?.find((x) => x.name === filename && x.source === sourceKind);
  if (f) {
    return {
      name: f.name,
      source: f.source,
      chars: f.chars,
      isPending: false,
      pendingOp: "",
    };
  }
  return {
    name: filename,
    source: sourceKind,
    chars: "?",
    isPending: false,
    pendingOp: "",
  };
}

function draftDeleteFile(category, filename, sourceKind) {
  if (!state.docsDraft) return;
  const cat = state.docsDraft.categories.find((c) => c.name === category);
  if (!cat) return;
  const idx = cat.files.findIndex((f) => f.name === filename && f.source === sourceKind);
  if (idx < 0) return;
  const [row] = cat.files.splice(idx, 1);
  const op = row.pendingOp || "";

  if (op === "upload") {
    const ui = state.docsDraft.uploads.findIndex((u) => u.category === category && u.filename === filename);
    if (ui >= 0) state.docsDraft.uploads.splice(ui, 1);
    _setDirty(true);
    return;
  }

  if (op === "replace") {
    const ui = state.docsDraft.uploads.findIndex(
      (u) => u.category === category && u.filename === filename && u.replaceOf,
    );
    if (ui >= 0) {
      const u = state.docsDraft.uploads[ui];
      state.docsDraft.uploads.splice(ui, 1);
      const delEntry = state.docsDraft.deletes.find((d) => d.category === category && d.filename === u.replaceOf);
      if (delEntry) {
        state.docsDraft.deletes = state.docsDraft.deletes.filter((d) => d !== delEntry);
        cat.files.push(draftRowFromOverview(category, u.replaceOf, delEntry.source_kind));
      } else {
        const liveCat = state.docsOverview?.categories?.find((c) => c.name === category);
        const cand = liveCat?.files?.find((x) => x.name === u.replaceOf);
        cat.files.push(
          cand
            ? draftRowFromOverview(category, cand.name, cand.source)
            : draftRowFromOverview(category, u.replaceOf, "docx"),
        );
      }
    }
    _setDirty(true);
    return;
  }

  if (op === "move") {
    const mi = state.docsDraft.moves.findIndex(
      (m) =>
        m.target_category === category && m.filename === filename && m.source_kind === sourceKind,
    );
    if (mi >= 0) {
      const m = state.docsDraft.moves[mi];
      state.docsDraft.moves.splice(mi, 1);
      const fromCat = state.docsDraft.categories.find((c) => c.name === m.source_category);
      if (fromCat) {
        fromCat.files.push({
          name: row.name,
          source: row.source,
          chars: row.chars,
          isPending: false,
          pendingOp: "",
        });
      }
    }
    _setDirty(true);
    return;
  }

  state.docsDraft.deletes.push({ category, source_kind: sourceKind, filename });
  _setDirty(true);
}

function draftAddUpload(file, category) {
  if (!state.docsDraft) return;
  const cat = ensureDraftCategory(category);
  if (!cat) return;
  const source = inferStagedSourceFromFilename(file.name);
  cat.files.push({
    name: file.name,
    source,
    chars: "?",
    isPending: true,
    pendingOp: "upload",
  });
  state.docsDraft.uploads.push({ category, filename: file.name, file });
  _setDirty(true);
}

/** Replace the File object for a pending-only upload (same name). */
function draftSwapPendingUpload(category, filename, newFile) {
  const u = state.docsDraft.uploads.find((x) => x.category === category && x.filename === filename);
  if (!u) return;
  u.file = newFile;
  if (newFile.name !== filename) {
    u.filename = newFile.name;
    const cat = state.docsDraft.categories.find((c) => c.name === category);
    const r = cat?.files.find((f) => f.name === filename && f.pendingOp === "upload");
    if (r) {
      r.name = newFile.name;
      r.source = inferStagedSourceFromFilename(newFile.name);
    }
  }
  _setDirty(true);
}

/**
 * After staging files, expand the target category and scroll file rows into view.
 */
function applyDocsReveal(revealKeys) {
  if (!revealKeys?.length) return;
  state.docsPinnedExpandCategory = revealKeys[0].category;
  state.docsRevealScrollKeys = revealKeys.slice();
}

function findDocRowEl(category, name, source) {
  if (!documentsCategories) return null;
  for (const el of documentsCategories.querySelectorAll(".doc-file[data-doc-cat]")) {
    if (
      el.dataset.docCat === category &&
      el.dataset.docName === name &&
      el.dataset.docSrc === source
    ) {
      return el;
    }
  }
  return null;
}

function flushDocsRevealScroll() {
  const keys = state.docsRevealScrollKeys;
  if (!keys?.length) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const last = keys[keys.length - 1];
      const el = findDocRowEl(last.category, last.name, last.source);
      el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      state.docsRevealScrollKeys = null;
    });
  });
}

function duplicateLowerNamesForCategory(cat) {
  const counts = new Map();
  for (const f of cat.files || []) {
    const ln = String(f.name || "").toLowerCase();
    counts.set(ln, (counts.get(ln) || 0) + 1);
  }
  const dups = new Set();
  for (const [ln, c] of counts) {
    if (c > 1) dups.add(ln);
  }
  return dups;
}

/**
 * Stage new files: add non-conflicting; queue disk-backed name collisions for the modal.
 * @returns {{ modalQueue: Array<{file: File, row: object, category: string}>, anyAdded: boolean, draftConflictSkip: number, revealKeys: Array<{category: string, name: string, source: string}> }}
 */
function stageIncomingFiles(allowedFiles, category) {
  const modalQueue = [];
  const revealKeys = [];
  let anyAdded = false;
  let draftConflictSkip = 0;
  if (!state.docsDraft || !allowedFiles.length) {
    return { modalQueue, anyAdded, draftConflictSkip, revealKeys };
  }
  ensureDraftCategory(category);
  const cat = state.docsDraft.categories.find((c) => c.name === category);
  if (!cat) return { modalQueue, anyAdded, draftConflictSkip, revealKeys };

  for (const file of allowedFiles) {
    const row = cat.files.find((f) => f.name === file.name);
    if (!row) {
      draftAddUpload(file, category);
      anyAdded = true;
      revealKeys.push({
        category,
        name: file.name,
        source: inferStagedSourceFromFilename(file.name),
      });
      continue;
    }
    if (row.pendingOp === "upload") {
      draftSwapPendingUpload(category, file.name, file);
      anyAdded = true;
      revealKeys.push({
        category,
        name: file.name,
        source: inferStagedSourceFromFilename(file.name),
      });
      continue;
    }
    if (row.pendingOp) {
      draftConflictSkip += 1;
      continue;
    }
    row.nameCollisionPending = true;
    modalQueue.push({ file, row, category });
    revealKeys.push({ category, name: row.name, source: row.source });
  }
  return { modalQueue, anyAdded, draftConflictSkip, revealKeys };
}

function openOverwriteConflictsModal(items) {
  if (!items.length || !state.docsDraft) return;
  let overwriteCount = 0;
  let remaining = items.slice();

  const overlay = document.createElement("div");
  overlay.className = "doc-modal-backdrop";

  const dialog = document.createElement("div");
  dialog.className = "doc-modal doc-modal--conflicts";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-labelledby", "doc-conflict-title");

  const title = document.createElement("h3");
  title.id = "doc-conflict-title";
  title.className = "doc-modal-title";
  title.textContent = "Fichiers déjà présents";

  const intro = document.createElement("p");
  intro.className = "doc-modal-intro";
  intro.textContent = `Ces noms existent déjà dans ce corpus (sur le disque ou dans l’aperçu). Les autres fichiers de votre sélection sont déjà dans le brouillon. Choisissez par fichier, ou écrasez-les tous.`;

  const counter = document.createElement("p");
  counter.className = "doc-modal-counter";
  function refreshCounter() {
    counter.textContent = `Écrasements confirmés : ${overwriteCount}`;
  }
  refreshCounter();

  const listEl = document.createElement("div");
  listEl.className = "doc-conflict-list";

  const footer = document.createElement("div");
  footer.className = "doc-modal-footer";

  const btnAll = document.createElement("button");
  btnAll.type = "button";
  btnAll.className = "toolbar-button doc-btn-save";

  const btnClose = document.createElement("button");
  btnClose.type = "button";
  btnClose.className = "toolbar-button secondary";
  btnClose.textContent = "Fermer";

  const prevOverflow = document.body.style.overflow;

  function closeAll() {
    document.removeEventListener("keydown", onKey);
    document.body.style.overflow = prevOverflow;
    document.body.classList.remove("doc-modal-open");
    overlay.remove();
    if (overwriteCount > 0) {
      const hint = `${overwriteCount} fichier(s) marqué(s) pour écrasement — enregistrez sur le disque pour appliquer.`;
      if (docError && !docError.classList.contains("hidden") && (docError.textContent || "").trim()) {
        /* keep extension / brouillon warning visible */
      } else {
        showDocInfo(hint);
      }
    }
    renderDocuments();
    updatePendingSummary();
  }

  function onKey(ev) {
    if (ev.key === "Escape") {
      ev.preventDefault();
      closeAll();
    }
  }

  function applyOverwrite(entry) {
    delete entry.row.nameCollisionPending;
    const rev = draftReplaceFile(entry.category, entry.row.name, entry.row.source, entry.file);
    if (rev) applyDocsReveal([rev]);
    overwriteCount += 1;
    refreshCounter();
  }

  function renderList() {
    listEl.innerHTML = "";
    btnAll.textContent = `Tout écraser (${remaining.length})`;
    btnAll.disabled = remaining.length === 0;
    for (const entry of remaining) {
      const row = document.createElement("div");
      row.className = "doc-conflict-row";
      const nameEl = document.createElement("span");
      nameEl.className = "doc-conflict-name";
      nameEl.textContent = entry.file.name;
      const meta = document.createElement("span");
      meta.className = "doc-conflict-meta";
      meta.textContent = `existant · ${entry.row.source}`;
      const actions = document.createElement("div");
      actions.className = "doc-conflict-actions";
      const btnO = document.createElement("button");
      btnO.type = "button";
      btnO.className = "toolbar-button doc-modal-btn-primary";
      btnO.textContent = "Écraser";
      btnO.addEventListener("click", () => {
        applyOverwrite(entry);
        remaining = remaining.filter((x) => x !== entry);
        if (!remaining.length) {
          closeAll();
          return;
        }
        renderList();
      });
      const btnS = document.createElement("button");
      btnS.type = "button";
      btnS.className = "toolbar-button secondary";
      btnS.textContent = "Ignorer";
      btnS.addEventListener("click", () => {
        delete entry.row.nameCollisionPending;
        remaining = remaining.filter((x) => x !== entry);
        if (!remaining.length) {
          closeAll();
          return;
        }
        renderList();
      });
      row.appendChild(nameEl);
      row.appendChild(meta);
      row.appendChild(actions);
      actions.appendChild(btnO);
      actions.appendChild(btnS);
      listEl.appendChild(row);
    }
  }

  btnAll.addEventListener("click", () => {
    const batch = remaining.slice();
    for (const entry of batch) {
      applyOverwrite(entry);
    }
    remaining = [];
    closeAll();
  });

  btnClose.addEventListener("click", () => {
    closeAll();
  });

  document.addEventListener("keydown", onKey);
  document.body.classList.add("doc-modal-open");
  document.body.style.overflow = "hidden";

  footer.appendChild(btnAll);
  footer.appendChild(btnClose);

  dialog.appendChild(title);
  dialog.appendChild(intro);
  dialog.appendChild(counter);
  dialog.appendChild(listEl);
  dialog.appendChild(footer);
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);

  renderList();
}

function draftReplaceFile(category, filename, sourceKind, file) {
  if (!state.docsDraft) return null;
  const lower = file.name.toLowerCase();
  const cat = state.docsDraft.categories.find((c) => c.name === category);
  if (!cat) return null;
  const idx = cat.files.findIndex((f) => f.name === filename && f.source === sourceKind);
  if (idx < 0) return null;
  cat.files.splice(idx, 1);
  state.docsDraft.deletes.push({ category, source_kind: sourceKind, filename });
  const stem = filename.includes(".") ? filename.slice(0, filename.lastIndexOf(".")) : filename;
  let ext;
  let source;
  if (lower.endsWith(".txt")) {
    ext = ".txt";
    source = "txt";
  } else if (lower.endsWith(".md")) {
    ext = ".md";
    source = "md";
  } else if (lower.endsWith(".docx")) {
    ext = ".docx";
    source = "docx";
  } else {
    showDocError("Remplacement : choisir un fichier .docx, .txt ou .md.");
    return null;
  }
  const targetName = stem + ext;
  cat.files.push({
    name: targetName,
    source,
    chars: "?",
    isPending: true,
    pendingOp: "replace",
  });
  state.docsDraft.uploads.push({
    category,
    filename: targetName,
    file,
    replaceOf: filename,
  });
  _setDirty(true);
  return { category, name: targetName, source };
}

function renderDocuments() {
  const data = state.docsOverview;
  const draft = state.docsDraft;
  if (!data || !draft || !documentsCategories) return;

  const categories = draft.categories || [];

  if (documentsBudget) {
    const corp = data.corpus?.default_category || "";
    const corpBit = corp ? `Corpus par défaut serveur : ${corp}` : "Corpus par défaut : voir .env";
    documentsBudget.textContent = `${categories.length} catégorie(s). ${corpBit}.`;
  }

  if (!categories.length) {
    documentsCategories.innerHTML =
      '<div class="doc-platform-empty"><p class="doc-platform-empty-title">Aucun corpus pour l’instant</p><p class="doc-platform-empty-hint">Importez un premier fichier <code>.docx</code>, <code>.md</code> ou <code>.txt</code> (zone ci-dessus ou dossier), puis enregistrez sur le disque.</p></div>';
    updatePendingSummary();
    return;
  }

  const categoryOptions = categories
    .map((cat) => `<option value="${escapeHtml(cat.name)}">${escapeHtml(cat.name)}</option>`)
    .join("");

  documentsCategories.innerHTML = categories
    .map((cat) => {
      const expandCat = state.docsPinnedExpandCategory;
      const isExpanded = expandCat && cat.name === expandCat;
      const live = (state.docsOverview.categories || []).find((x) => x.name === cat.name);
      const sizePill = live
        ? `<span class="pill">${live.total_chars} chars (corpus)</span>`
        : `<span class="pill">nouvelle categorie</span>`;
      const dupLower = duplicateLowerNamesForCategory(cat);
      const files = (cat.files || [])
        .map((file) => {
          const kind = docFileKindLabel(file.name);
          const isDup =
            dupLower.has(String(file.name || "").toLowerCase()) || Boolean(file.nameCollisionPending);
          const dupPart = isDup ? " doc-file--dup" : "";
          const warn = isDup
            ? `<span class="doc-dup-icon" title="Conflit ou nom en double dans ce corpus" aria-hidden="true">⚠</span>`
            : "";
          return `
          <div class="doc-file ${file.isPending ? "pending" : ""}${dupPart}" data-doc-cat="${escapeHtml(cat.name)}" data-doc-name="${escapeHtml(file.name)}" data-doc-src="${escapeHtml(file.source)}">
            <span class="doc-file-kind" title="Type">${kind}</span>
            <div class="doc-file-info">
              ${warn}
              <span class="doc-file-title">${escapeHtml(file.name)}</span>
              <span class="doc-file-meta">
                <span class="pill">${escapeHtml(file.source)}</span>
                <span class="pill">${file.chars} car.</span>
                ${file.pendingOp ? `<span class="pill conv-pill">${escapeHtml(file.pendingOp)}</span>` : ""}
              </span>
            </div>
            <div class="doc-file-toolbar">
              <select class="doc-move-select" aria-label="Déplacer vers une catégorie" data-move-select data-from="${escapeHtml(cat.name)}" data-name="${escapeHtml(file.name)}" data-source="${escapeHtml(file.source)}">
                <option value="">Vers…</option>
                ${categoryOptions}
              </select>
              <button type="button" class="doc-file-btn doc-file-btn-warn" data-replace-button data-category="${escapeHtml(cat.name)}" data-name="${escapeHtml(file.name)}" data-source="${escapeHtml(file.source)}" title="Écraser ce fichier (même nom de base)">Remplacer</button>
              <button type="button" class="doc-file-btn doc-file-btn-danger" data-delete-button data-category="${escapeHtml(cat.name)}" data-name="${escapeHtml(file.name)}" data-source="${escapeHtml(file.source)}">Retirer</button>
            </div>
          </div>`;
        })
        .join("");

      return `
        <div class="doc-category ${isExpanded ? "expanded" : ""}">
          <div class="doc-category-head-wrap">
            <button type="button" class="doc-category-head" data-doc-toggle aria-expanded="${isExpanded}">
              <span class="doc-category-chevron" aria-hidden="true"></span>
              <div class="doc-category-head-text">
                <span class="doc-category-name">${escapeHtml(cat.name)}</span>
                <div class="doc-category-meta">
                  <span class="pill">source : ${escapeHtml(cat.active_source)}</span>
                  <span class="pill">${(cat.files || []).length} fichier(s)</span>
                  ${sizePill}
                </div>
              </div>
            </button>
            <button type="button" class="doc-cat-delete" data-delete-whole-category="${escapeHtml(cat.name)}" title="Supprimer toute cette catégorie sur le disque">Suppr. dossier</button>
          </div>
          <div class="doc-files">
            ${files || '<div class="doc-files-empty">Aucun fichier dans ce corpus.</div>'}
          </div>
        </div>
      `;
    })
    .join("");

  documentsCategories.querySelectorAll("[data-doc-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = btn.closest(".doc-category");
      row?.classList.toggle("expanded");
      const on = row?.classList.contains("expanded");
      btn.setAttribute("aria-expanded", on ? "true" : "false");
    });
  });

  documentsCategories.querySelectorAll("[data-delete-whole-category]").forEach((btn) => {
    btn.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const cat = btn.dataset.deleteWholeCategory || "";
      if (!cat) return;
      const ok = confirm(
        `Supprimer toute la categorie « ${cat} » sur le serveur ?\n` +
          "Tous les fichiers de ce dossier seront effaces (action immediate, pas seulement le brouillon).",
      );
      if (!ok) return;
      showDocError("");
      try {
        await apiFetch(`${DOCS_API_BASE}/delete-category`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category: cat }),
        });
        await loadDocumentsOverview();
      } catch (error) {
        showDocError(error.message || "Echec suppression categorie");
      }
    });
  });

  documentsCategories.querySelectorAll("select[data-move-select]").forEach((select) => {
    select.addEventListener("change", () => {
      const target = select.value || "";
      if (!target) return;
      const from = select.dataset.from;
      const filename = select.dataset.name;
      const source = select.dataset.source;
      if (target === from) {
        showDocError("La categorie cible doit etre differente.");
        select.value = "";
        return;
      }
      showDocError("");
      draftMoveFile(from, filename, source, target);
      renderDocuments();
    });
  });

  documentsCategories.querySelectorAll("[data-replace-button]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (!docReplaceInput) return;
      docReplaceTarget = {
        category: btn.dataset.category || "",
        filename: btn.dataset.name || "",
        sourceKind: btn.dataset.source || "",
      };
      docReplaceInput.click();
    });
  });

  documentsCategories.querySelectorAll("[data-delete-button]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const category = btn.dataset.category;
      const filename = btn.dataset.name;
      const source = btn.dataset.source;
      const cat = state.docsDraft?.categories.find((c) => c.name === category);
      const row = cat?.files?.find((f) => f.name === filename && f.source === source);
      const op = row?.pendingOp;
      const msg =
        op === "upload" || op === "replace" || op === "move"
          ? `Retirer ${filename} du brouillon ? (aucune suppression sur le disque pour l’instant.)`
          : `Supprimer ${filename} de ${category} ? Il sera effacé sur le disque à l’enregistrement.`;
      const ok = confirm(msg);
      if (!ok) return;
      showDocError("");
      draftDeleteFile(category, filename, source);
      renderDocuments();
    });
  });
  updatePendingSummary();
  flushDocsRevealScroll();
}

async function loadDocumentsOverview() {
  const response = await apiFetch(`${DOCS_API_BASE}/overview`);
  state.docsOverview = await response.json();
  const def = state.docsOverview?.corpus?.default_category;
  if (docCategoryInput && def && !(docCategoryInput.value || "").trim()) {
    docCategoryInput.value = def;
  }
  initDocsDraft();
  renderDocuments();
}


async function handleFolderSelection() {
  const files = Array.from(docFolderInput?.files || []);
  if (!files.length) return;
  try {
    await ensureDocsReadyForEdits();
  } catch (error) {
    showDocError(error.message || "Chargez la vue Documents.");
    return;
  }
  showDocError("");
  showDocInfo("");
  const corpus = getCorpusCategory();
  let extSkipped = 0;
  const allowed = [];
  for (const f of files) {
    if (isAllowedCorpusUpload(f.name)) allowed.push(f);
    else extSkipped += 1;
  }
  if (!allowed.length) {
    showDocError(
      extSkipped ? "Aucun fichier .docx, .txt ou .md dans ce dossier." : "",
    );
    if (docFolderInput) docFolderInput.value = "";
    return;
  }
  const { modalQueue, anyAdded, draftConflictSkip, revealKeys } = stageIncomingFiles(allowed, corpus);
  applyDocsReveal(revealKeys);
  const msgParts = [];
  if (extSkipped) msgParts.push(`${extSkipped} ignoré(s) (extension).`);
  if (draftConflictSkip) {
    msgParts.push(
      `${draftConflictSkip} ignoré(s) (ce nom est déjà dans le brouillon pour un déplacement ou un autre remplacement).`,
    );
  }
  if (modalQueue.length) {
    openOverwriteConflictsModal(modalQueue);
  }
  if (msgParts.length) showDocError(msgParts.join(" "));
  else if (!modalQueue.length && anyAdded) showDocError("");
  renderDocuments();
  if (docFolderInput) docFolderInput.value = "";
}

async function saveDraftChanges() {
  if (!state.docsDraft) return;
  showDocError("");
  const plan = {
    uploads: state.docsDraft.uploads.map((u) => ({
      filename: u.filename,
      ...(u.category ? { category: u.category } : {}),
    })),
    moves: state.docsDraft.moves,
    deletes: state.docsDraft.deletes,
  };
  const body = new FormData();
  body.append("plan_json", JSON.stringify(plan));
  for (const upload of state.docsDraft.uploads) {
    body.append("files", upload.file, upload.filename);
  }
  if (docSaveButton) docSaveButton.disabled = true;
  try {
    const response = await apiFetch(`${DOCS_API_BASE}/apply-plan`, { method: "POST", body });
    const data = await response.json().catch(() => ({}));
    if (Array.isArray(data.warnings) && data.warnings.length) {
      showDocError(`Attention : ${data.warnings.join(" ")}`);
    } else {
      showDocError("");
    }
    await loadDocumentsOverview();
  } catch (error) {
    showDocError(error.message || "Echec de sauvegarde");
  } finally {
    updatePendingSummary();
  }
}

async function loadInteractions() {
  const response = await apiFetch(`/admin/interactions?${buildListQuery()}`);
  const payload = await response.json();
  state.items = payload.items;
  resultsCount.textContent = `${payload.total ?? payload.count ?? 0} resultat(s)`;
  renderList();

  if (!state.selectedId && payload.items.length) {
    await loadInteractionDetail(payload.items[0].id);
  } else if (state.selectedId) {
    const stillExists = payload.items.some((item) => item.id === state.selectedId);
    if (stillExists) {
      await loadInteractionDetail(state.selectedId);
    } else {
      renderDetail(null);
    }
  }
}

function renderList() {
  if (!state.items.length) {
    interactionList.innerHTML = '<div class="detail-empty">Aucune interaction pour ce filtre.</div>';
    return;
  }

  // Group by session_id — preserve order of first occurrence
  const groups = [];
  const seen = new Map();
  for (const item of state.items) {
    const key = item.session_id || item.id; // fallback to id if no session
    if (!seen.has(key)) {
      const group = { session_id: item.session_id, items: [item] };
      seen.set(key, group);
      groups.push(group);
    } else {
      seen.get(key).items.push(item);
    }
  }

  interactionList.innerHTML = groups
    .map((group) => {
      if (!group.session_id || group.items.length === 1) {
        // Single interaction — render flat card
        return group.items.map((item) => renderInteractionCard(item)).join("");
      }
      // Multi-message conversation group
      const newest = group.items[0]; // items are sorted newest-first from API
      const count = group.items.length;
      const feedbacks = group.items.filter((i) => i.feedback);
      const disliked = feedbacks.some((i) => i.feedback?.value === "dislike");
      const feedbackPill = disliked
        ? '<span class="pill bad">has dislike</span>'
        : feedbacks.length
          ? '<span class="pill good">feedback</span>'
          : "";
      const isActive = group.items.some((i) => i.id === state.selectedId);
      return `
        <div class="conversation-group ${isActive ? "active" : ""}">
          <button type="button" class="conversation-header" data-session="${escapeHtml(group.session_id)}">
            <div class="interaction-meta">
              <span class="pill conv-pill">${count} messages</span>
              <span class="pill">${new Date(newest.created_at).toLocaleString()}</span>
              <span class="pill">${newest.user_id}</span>
              ${feedbackPill}
            </div>
            <div class="interaction-message">${escapeHtml(newest.message)}</div>
          </button>
          <div class="conversation-items">
            ${group.items.map((item) => renderInteractionCard(item, true)).join("")}
          </div>
        </div>`;
    })
    .join("");

  interactionList.querySelectorAll(".interaction-card").forEach((button) => {
    button.addEventListener("click", () => loadInteractionDetail(button.dataset.id));
  });

  interactionList.querySelectorAll(".conversation-header").forEach((header) => {
    header.addEventListener("click", () => {
      const group = header.closest(".conversation-group");
      group.classList.toggle("expanded");
    });
  });
}

function renderInteractionCard(item, nested = false) {
  const feedback = item.feedback
    ? `<span class="pill ${item.feedback.value === "dislike" ? "bad" : "good"}">${item.feedback.value}${item.feedback.reason ? ` · ${item.feedback.reason}` : ""}</span>`
    : "";
  return `
    <button type="button" class="interaction-card ${nested ? "nested" : ""} ${item.id === state.selectedId ? "active" : ""}" data-id="${item.id}">
      <div class="interaction-meta">
        <span class="pill">${new Date(item.created_at).toLocaleString()}</span>
        <span class="pill">${item.user_id}</span>
        ${feedback}
      </div>
      <div class="interaction-message">${escapeHtml(item.message)}</div>
    </button>`;
}

async function loadInteractionDetail(interactionId) {
  state.selectedId = interactionId;
  renderList();
  const response = await apiFetch(`/admin/interactions/${interactionId}`);
  const payload = await response.json();
  renderDetail(payload);

  // Load conversation context if session_id exists
  if (payload.session_id) {
    await loadConversation(payload.session_id, interactionId);
  }
}

async function loadConversation(sessionId, currentId) {
  if (state.conversationCache[sessionId]) {
    renderConversation(state.conversationCache[sessionId], currentId);
    return;
  }
  try {
    const resp = await apiFetch(`/admin/conversations/${sessionId}`);
    const data = await resp.json();
    state.conversationCache[sessionId] = data.items;
    renderConversation(data.items, currentId);
  } catch {
    const c = document.getElementById("conversation-context");
    if (c) {
      c.innerHTML =
        '<div class="detail-text">Impossible de charger la conversation.</div>';
    }
  }
}

function renderConversation(items, currentId) {
  const container = document.getElementById("conversation-context");
  if (!container) return;
  if (!items.length) {
    container.innerHTML =
      '<div class="detail-text">Aucun message pour cette session.</div>';
    return;
  }

  container.innerHTML = items
    .map((item) => {
      const isCurrent = item.id === currentId;
      return `
        <div class="conv-message ${isCurrent ? "conv-current" : ""}" ${!isCurrent ? `data-nav-id="${item.id}" style="cursor:pointer"` : ""}>
          <div class="conv-meta">
            <span class="pill">${new Date(item.created_at).toLocaleString()}</span>
            ${item.feedback ? `<span class="pill ${item.feedback.value === "dislike" ? "bad" : "good"}">${item.feedback.value}</span>` : ""}
            ${isCurrent ? '<span class="pill conv-pill">current</span>' : ""}
          </div>
          <div class="conv-prompt"><strong>User:</strong> ${escapeHtml(item.message)}</div>
          <div class="conv-response"><strong>Bot:</strong> ${escapeHtml(truncate(item.response, 200))}</div>
        </div>`;
    })
    .join("");

  container.querySelectorAll("[data-nav-id]").forEach((el) => {
    el.addEventListener("click", () => loadInteractionDetail(el.dataset.navId));
  });
}

function renderRagMetadata(item) {
  const meta = item.metadata || {};
  const rag = meta.rag || meta.rag_reconstructed || {};
  const cat = meta.category_used || rag.category || "—";
  const chars = rag.context_chars;
  const docs = rag.documents_in_prompt;
  const note = rag.note || rag.retrieval_error;
  const preview = rag.context_preview || "";
  const full = rag.context_full || "";
  const empty =
    (chars === 0 || chars === undefined) && !preview && !full && (note === undefined || note === null);

  if (empty) {
    return `<section class="detail-block">
      <div class="detail-label">RAG (contexte documents)</div>
      <div class="detail-text eval-warn">Aucun bloc DOCUMENTS injecté dans le prompt pour cet appel.</div>
      <div class="detail-text">Catégorie résolue : <strong>${escapeHtml(String(cat))}</strong></div>
    </section>`;
  }

  return `<section class="detail-block">
    <div class="detail-label">RAG (contexte documents)</div>
    <div class="detail-text">Catégorie : <strong>${escapeHtml(String(cat))}</strong> · caractères injectés : ${escapeHtml(String(chars ?? "—"))} · sections document : ${escapeHtml(String(docs ?? "—"))}</div>
    ${note ? `<div class="detail-text eval-warn">${escapeHtml(String(note))}</div>` : ""}
    ${full ? `<details class="rag-full-wrap" open><summary>Contexte complet injecté (${escapeHtml(String(full.length))} caractères)</summary><pre class="rag-preview rag-full">${escapeHtml(full)}</pre></details>` : ""}
    ${!full && preview ? `<pre class="rag-preview">${escapeHtml(preview)}</pre>` : ""}
  </section>`;
}

function truncate(text, max) {
  if (!text || text.length <= max) return text || "";
  return text.slice(0, max) + "…";
}

function renderDetail(item) {
  if (!item) {
    interactionDetail.innerHTML = '<div class="detail-empty">Selectionnez une interaction.</div>';
    return;
  }

  const feedbackBlock = item.feedback
    ? `<div class="detail-text"><strong>${item.feedback.value}</strong>${item.feedback.reason ? ` · ${item.feedback.reason}` : ""}</div>
       <div class="detail-text">${escapeHtml(item.feedback.comment || "Aucun commentaire")}</div>`
    : '<div class="detail-text">Aucun feedback</div>';

  const hasDislike = item.feedback?.value === "dislike";
  const hasEval = Boolean(item.metadata?.evaluation);
  const showEvalButton = hasDislike && !hasEval;

  interactionDetail.innerHTML = `
    <div class="detail-grid">
      <div class="detail-meta">
        <span class="pill">${new Date(item.created_at).toLocaleString()}</span>
        <span class="pill">${item.user_id}</span>
        <span class="pill">${item.session_id || "no-session"}</span>
        <span class="pill">${item.metadata?.detected_language || item.metadata?.lang || "—"}</span>
      </div>

      ${renderRagMetadata(item)}

      ${item.session_id ? `<section class="detail-block"><div class="detail-label">Conversation</div><div id="conversation-context" class="conversation-context"><div class="detail-text" style="color:var(--muted)">Loading…</div></div></section>` : ""}

      <section class="detail-block">
        <div class="detail-label">Prompt</div>
        <div class="detail-text">${escapeHtml(item.message)}</div>
      </section>

      <section class="detail-block">
        <div class="detail-label">Reponse</div>
        <div class="detail-text">${escapeHtml(item.response)}</div>
      </section>

      <section class="detail-block">
        <div class="detail-label">Feedback</div>
        ${feedbackBlock}
      </section>

      ${renderEvaluation(item)}
      ${showEvalButton ? `<button type="button" class="toolbar-button eval-run-button" data-eval-id="${item.id}">Run Evaluation</button>` : ""}
    </div>`;

  if (showEvalButton) {
    interactionDetail.querySelector(".eval-run-button").addEventListener("click", (e) => {
      handleRunEval(e.target.dataset.evalId);
    });
  }
}

async function handleRunEval(interactionId) {
  const button = interactionDetail.querySelector(".eval-run-button");
  if (button) {
    button.disabled = true;
    button.textContent = "Running…";
  }
  try {
    const response = await apiFetch(`/admin/eval-run/${interactionId}`, { method: "POST" });
    const data = await response.json();
    alert(data.reason || data.status || "Évaluation terminée.");
    await loadInteractionDetail(interactionId);
  } catch (error) {
    alert("Evaluation failed: " + error.message);
    if (button) {
      button.disabled = false;
      button.textContent = "Run Evaluation";
    }
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderEvaluation(item) {
  const evalData = item.metadata?.evaluation;
  if (!evalData) {
    return `<section class="detail-block">
      <div class="detail-label">Model Evaluation</div>
      <div class="detail-text eval-empty">No evaluation available</div>
    </section>`;
  }

  const verdictClass = {
    accurate: "eval-good",
    partial: "eval-warn",
    inaccurate: "eval-bad",
    no_context: "eval-neutral",
  }[evalData.verdict] || "eval-neutral";

  return `<section class="detail-block">
    <div class="detail-label">Model Evaluation</div>
    <div class="eval-card">
      <div class="eval-header">
        <span class="pill ${verdictClass}">${escapeHtml(evalData.verdict || "unknown")}</span>
        <span class="eval-confidence">Confidence: ${evalData.confidence ?? "N/A"}%</span>
      </div>
      <div class="eval-summary">${escapeHtml(evalData.summary || "")}</div>
      <div class="eval-reasoning">${escapeHtml(evalData.reasoning || "")}</div>
    </div>
  </section>`;
}

async function loadEvalStatus() {
  setToggleLoading(evalToggle, "Eval: LOADING...", true);
  try {
    const response = await apiFetch("/admin/eval-status");
    const data = await response.json();
    setToggleLoading(evalToggle, "Eval: LOADING...", false);

    evalToggle.dataset.available = data.available ? "true" : "false";
    evalToggle.textContent = data.available
      ? `Eval: ${data.enabled ? "ON" : "OFF"}`
      : "Eval: N/A";
    evalToggle.classList.toggle("active", data.enabled);
    evalToggle.disabled = !data.available;
  } catch {
    setToggleLoading(evalToggle, "Eval: LOADING...", false);
    evalToggle.dataset.available = "false";
    evalToggle.textContent = "Eval: N/A";
    evalToggle.disabled = true;
  }
}

async function handleEvalToggle() {
  if (evalToggle.disabled || evalToggle.dataset.available !== "true") return;

  const nextEnabled = !evalToggle.classList.contains("active");
  showToggleConfirmation(evalToggle, "evaluation", nextEnabled, async () => {
    setToggleLoading(evalToggle, "Eval: APPLYING...", true);
    try {
      const response = await apiFetch("/admin/eval-toggle", { method: "POST" });
      const data = await response.json();
      setToggleLoading(evalToggle, "Eval: APPLYING...", false);

      evalToggle.textContent = `Eval: ${data.enabled ? "ON" : "OFF"}`;
      evalToggle.classList.toggle("active", data.enabled);
      evalToggle.disabled = evalToggle.dataset.available !== "true";
    } catch (error) {
      setToggleLoading(evalToggle, "Eval: APPLYING...", false);
      evalToggle.disabled = evalToggle.dataset.available !== "true";
      alert("Failed to toggle evaluation: " + error.message);
    }
  });
}

function wireDocDropzone() {
  const dz = document.getElementById("doc-dropzone");
  if (!dz || !docFileInput) return;
  let depth = 0;
  dz.addEventListener("dragenter", (e) => {
    e.preventDefault();
    depth += 1;
    dz.classList.add("doc-dropzone-active");
  });
  dz.addEventListener("dragleave", (e) => {
    e.preventDefault();
    depth = Math.max(0, depth - 1);
    if (depth === 0) dz.classList.remove("doc-dropzone-active");
  });
  dz.addEventListener("dragover", (e) => e.preventDefault());
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    depth = 0;
    dz.classList.remove("doc-dropzone-active");
    const files = e.dataTransfer?.files;
    if (files && files.length) {
      addFilesToDraftFromFileList(files).catch((err) => showDocError(err.message));
    }
  });
  dz.addEventListener("click", () => docFileInput.click());
  dz.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      docFileInput.click();
    }
  });
}

if (docFileInput) {
  docFileInput.addEventListener("change", () => {
    processDocFileInputSelection().catch((e) => showDocError(e.message));
  });
}
wireDocDropzone();

if (loginForm) loginForm.addEventListener("submit", handleLogin);
if (logoutButton) logoutButton.addEventListener("click", handleLogout);
if (refreshButton) {
  refreshButton.addEventListener("click", () => {
    state.conversationCache = {};
    loadInteractions().catch(handleLoadError);
  });
}
if (viewInteractionsButton) {
  viewInteractionsButton.addEventListener("click", () => setAdminView("interactions"));
}
if (viewDocumentsButton) {
  viewDocumentsButton.addEventListener("click", () => {
    setAdminView("documents");
    loadDocumentsOverview().catch((error) => showDocError(error.message));
  });
}
if (viewUsersButton) {
  viewUsersButton.addEventListener("click", () => {
    setAdminView("users");
    loadUsersList().catch(() => {});
  });
}
if (usersRefreshButton) {
  usersRefreshButton.addEventListener("click", () => {
    loadUsersList().catch(() => {});
  });
}
if (usersCreateButton) {
  usersCreateButton.addEventListener("click", async () => {
    const username = (usersNewUsername?.value || "").trim();
    const password = usersNewPassword?.value || "";
    const role = usersNewRole?.value || "user";
    if (username.length < 2) {
      showUsersError("Identifiant trop court (min. 2).");
      return;
    }
    if (password.length < 4) {
      showUsersError("Mot de passe : au moins 4 caractères.");
      return;
    }
    clearUsersError();
    try {
      await apiFetch("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, role }),
      });
      if (usersNewUsername) usersNewUsername.value = "";
      if (usersNewPassword) usersNewPassword.value = "";
      if (usersNewRole) usersNewRole.value = "user";
      await loadUsersList();
    } catch (error) {
      showUsersError(error.message || "Création impossible.");
    }
  });
}
if (docAddFolderButton) {
  docAddFolderButton.addEventListener("click", () => docFolderInput?.click());
}
if (docFolderInput) {
  docFolderInput.addEventListener("change", () => {
    handleFolderSelection().catch((error) => showDocError(error.message));
  });
}
if (docReplaceInput) {
  docReplaceInput.addEventListener("change", () => {
    const f = docReplaceInput.files && docReplaceInput.files[0];
    const t = docReplaceTarget;
    docReplaceTarget = null;
    docReplaceInput.value = "";
    if (!f || !t || !t.category) return;
    ensureDocsReadyForEdits()
      .then(() => {
        showDocError("");
        const rev = draftReplaceFile(t.category, t.filename, t.sourceKind, f);
        if (rev) applyDocsReveal([rev]);
        renderDocuments();
      })
      .catch((error) => showDocError(error.message || "Chargez la vue Documents."));
  });
}
if (docSaveButton) {
  docSaveButton.addEventListener("click", () => {
    saveDraftChanges().catch((error) => showDocError(error.message));
  });
}
if (docDiscardButton) {
  docDiscardButton.addEventListener("click", () => {
    if (!state.docsDirty) return;
    const ok = confirm("Annuler tous les changements non sauvegardes ?");
    if (!ok) return;
    initDocsDraft();
    renderDocuments();
  });
}
if (docRefreshButton) {
  docRefreshButton.addEventListener("click", () => {
    loadDocumentsOverview().catch((error) => showDocError(error.message));
  });
}

if (gitRefreshButton) {
  gitRefreshButton.addEventListener("click", async () => {
    const ok = confirm(
      "Télécharger la dernière version depuis Git (origin) et reconstruire web_test/dist ?\n\n" +
        "Cela ne recharge pas l’index RAG seul — utilisez « Index RAG » après un changement de documents si besoin. " +
        "Un redémarrage API peut être nécessaire pour servir les nouveaux fichiers JS.",
    );
    if (!ok) return;
    setToggleLoading(gitRefreshButton, "Git...", true);
    try {
      const response = await apiFetch("/admin/git-refresh", { method: "POST" });
      const data = await response.json();
      alert(`Branche ${data.branch} @ ${data.commit}\n\n${data.note || "OK"}`);
    } catch (error) {
      alert("Échec Git / build web: " + error.message);
    } finally {
      setToggleLoading(gitRefreshButton, "Git...", false);
    }
  });
}

if (ragReloadButton) {
  ragReloadButton.addEventListener("click", async () => {
    setToggleLoading(ragReloadButton, "RAG...", true);
    try {
      const response = await apiFetch("/admin/rag-reload", { method: "POST" });
      const data = await response.json();
      const n = Array.isArray(data.rag_categories) ? data.rag_categories.length : 0;
      alert((data.note || "OK") + (n ? `\n\n${n} catégorie(s) dans l’index.` : ""));
      loadDocumentsOverview().catch((error) => showDocError(error.message));
    } catch (error) {
      alert("Échec rechargement index RAG: " + error.message);
    } finally {
      setToggleLoading(ragReloadButton, "RAG...", false);
    }
  });
}
if (evalToggle) evalToggle.addEventListener("click", handleEvalToggle);
if (searchInput) {
  searchInput.addEventListener("input", (event) => {
    state.search = event.target.value.trim();
    loadInteractions().catch(handleLoadError);
  });
}
if (feedbackFilter) {
  feedbackFilter.addEventListener("change", (event) => {
    state.feedbackValue = event.target.value;
    loadInteractions().catch(handleLoadError);
  });
}
if (reasonFilter) {
  reasonFilter.addEventListener("change", (event) => {
    state.feedbackReason = event.target.value;
    loadInteractions().catch(handleLoadError);
  });
}

function handleLoadError(error) {
  interactionList.innerHTML = `<div class="detail-empty">${escapeHtml(error.message || "Chargement impossible.")}</div>`;
  interactionDetail.innerHTML = '<div class="detail-empty">Verification necessaire.</div>';
}

loadSession()
  .then(() => {
    if (!canUseStaffConsole(state.session?.role)) return null;
    if (isAdministratorRole(state.session.role)) {
      return Promise.allSettled([loadInteractions(), loadEvalStatus(), loadDocumentsOverview()]);
    }
    return loadDocumentsOverview();
  })
  .catch(() => {
    renderSession();
  });