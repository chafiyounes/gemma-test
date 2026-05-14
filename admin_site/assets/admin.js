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
const documentsBudget = document.getElementById("documents-budget");
const documentsCategories = document.getElementById("documents-categories");
const docCategoryInput = document.getElementById("doc-category-input");
const docFileInput = document.getElementById("doc-file-input");
const docFolderInput = document.getElementById("doc-folder-input");
const docUploadButton = document.getElementById("doc-upload-button");
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
  state.adminView = mgrOnly ? "documents" : view === "documents" ? "documents" : "interactions";
  if (interactionsView) interactionsView.classList.toggle("hidden", state.adminView !== "interactions");
  if (documentsView) documentsView.classList.toggle("hidden", state.adminView !== "documents");
  if (viewInteractionsButton) viewInteractionsButton.classList.toggle("active", state.adminView === "interactions");
  if (viewDocumentsButton) viewDocumentsButton.classList.toggle("active", state.adminView === "documents");
  const toolbarSub = document.querySelector(".toolbar-subtitle");
  if (toolbarSub) {
    toolbarSub.textContent =
      state.adminView === "documents"
        ? "Corpus RAG, import et enregistrement sur le disque."
        : "Filtrer les interactions et consulter le détail.";
  }
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
    return;
  }
  docError.textContent = message;
  docError.classList.remove("hidden");
}

/** Single corpus: manual override or server default (RAG_DEFAULT_CATEGORY). */
function getCorpusCategory() {
  const manual = (docCategoryInput?.value || "").trim();
  if (manual) return manual;
  const fromServer = (state.docsOverview?.corpus?.default_category || "").trim();
  return fromServer || "procedures";
}

function docFileKindLabel(filename) {
  const n = (filename || "").toLowerCase();
  if (n.endsWith(".docx")) return "DOCX";
  if (n.endsWith(".txt")) return "TXT";
  return "FILE";
}

async function addFilesToDraftFromFileList(fileList) {
  showDocError("");
  try {
    await ensureDocsReadyForEdits();
  } catch (error) {
    showDocError(error.message || "Chargez la vue Documents (ou reconnectez-vous).");
    return;
  }
  const category = getCorpusCategory();
  const list = Array.from(fileList || []);
  if (!list.length) {
    return;
  }
  let added = 0;
  let skipped = 0;
  for (const file of list) {
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".docx") && !lower.endsWith(".txt")) {
      skipped += 1;
      continue;
    }
    draftAddUpload(file, category);
    added += 1;
  }
  if (!added) {
    showDocError("Aucun fichier .docx ou .txt dans la sélection.");
    return;
  }
  if (skipped > 0) {
    showDocError(`${added} fichier(s) ajouté(s) au brouillon. ${skipped} ignoré(s) (extension).`);
  } else {
    showDocError("");
  }
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

function draftDeleteFile(category, filename, sourceKind) {
  if (!state.docsDraft) return;
  const cat = state.docsDraft.categories.find((c) => c.name === category);
  if (!cat) return;
  const idx = cat.files.findIndex((f) => f.name === filename && f.source === sourceKind);
  if (idx < 0) return;
  cat.files.splice(idx, 1);
  state.docsDraft.deletes.push({ category, source_kind: sourceKind, filename });
  _setDirty(true);
}

function draftAddUpload(file, category) {
  if (!state.docsDraft) return;
  const cat = ensureDraftCategory(category);
  if (!cat) return;
  const source = file.name.toLowerCase().endsWith(".txt") ? "txt" : "docx";
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

function draftReplaceFile(category, filename, sourceKind, file) {
  if (!state.docsDraft) return;
  const lower = file.name.toLowerCase();
  if (!lower.endsWith(".docx") && !lower.endsWith(".txt")) {
    showDocError("Remplacement : choisir un fichier .docx ou .txt.");
    return;
  }
  const cat = state.docsDraft.categories.find((c) => c.name === category);
  if (!cat) return;
  const idx = cat.files.findIndex((f) => f.name === filename && f.source === sourceKind);
  if (idx < 0) return;
  cat.files.splice(idx, 1);
  state.docsDraft.deletes.push({ category, source_kind: sourceKind, filename });
  const stem = filename.includes(".") ? filename.slice(0, filename.lastIndexOf(".")) : filename;
  const ext = lower.endsWith(".txt") ? ".txt" : ".docx";
  const targetName = stem + ext;
  const source = ext === ".txt" ? "txt" : "docx";
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
}

/** All .docx/.txt from a folder tree go to one corpus (no subfolder→category split). */
function assignFolderFilesToCategories(files, corpusCategory) {
  const assignments = [];
  const errors = [];
  const cat = (corpusCategory || "").trim() || "procedures";
  for (const file of files) {
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".docx") && !lower.endsWith(".txt")) continue;
    assignments.push({ file, category: cat });
  }
  return { assignments, errors };
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
      '<div class="doc-platform-empty"><p class="doc-platform-empty-title">Aucun corpus pour l’instant</p><p class="doc-platform-empty-hint">Importez un premier fichier <code>.docx</code> ou <code>.txt</code> pour créer une catégorie, ou saisissez un nom de corpus puis déposez des fichiers.</p></div>';
    updatePendingSummary();
    return;
  }

  const categoryOptions = categories
    .map((cat) => `<option value="${escapeHtml(cat.name)}">${escapeHtml(cat.name)}</option>`)
    .join("");

  documentsCategories.innerHTML = categories
    .map((cat, idx) => {
      const live = (state.docsOverview.categories || []).find((x) => x.name === cat.name);
      const sizePill = live
        ? `<span class="pill">${live.total_chars} chars (corpus)</span>`
        : `<span class="pill">nouvelle categorie</span>`;
      const files = (cat.files || [])
        .map((file) => {
          const kind = docFileKindLabel(file.name);
          return `
          <div class="doc-file ${file.isPending ? "pending" : ""}">
            <span class="doc-file-kind" title="Type">${kind}</span>
            <div class="doc-file-info">
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
        <div class="doc-category ${idx === 0 ? "expanded" : ""}">
          <div class="doc-category-head-wrap">
            <button type="button" class="doc-category-head" data-doc-toggle aria-expanded="${idx === 0}">
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
      const ok = confirm(`Supprimer ${filename} de ${category} ?`);
      if (!ok) return;
      showDocError("");
      draftDeleteFile(category, filename, source);
      renderDocuments();
    });
  });
  updatePendingSummary();
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


async function handleUploadDocument() {
  if (docFileInput) docFileInput.click();
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
  const corpus = getCorpusCategory();
  const { assignments, errors } = assignFolderFilesToCategories(files, corpus);
  for (const item of assignments) {
    draftAddUpload(item.file, item.category);
  }
  if (!assignments.length) {
    showDocError(errors[0] || "Aucun fichier .docx/.txt detecte dans ce dossier.");
  } else {
    showDocError(errors.length ? errors[0] : "");
    renderDocuments();
  }
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
if (docUploadButton) {
  docUploadButton.addEventListener("click", () => {
    handleUploadDocument().catch((error) => showDocError(error.message));
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
        draftReplaceFile(t.category, t.filename, t.sourceKind, f);
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
      "Télécharger la dernière version depuis Git (origin) et recharger l’index RAG ?\n\n" +
        "Les changements de documents seront pris en compte sans redémarrer l’API. " +
        "Les changements de code Python peuvent encore exiger un redémarrage du serveur (tmux).",
    );
    if (!ok) return;
    setToggleLoading(gitRefreshButton, "Git...", true);
    try {
      const response = await apiFetch("/admin/git-refresh", { method: "POST" });
      const data = await response.json();
      alert(`Branche ${data.branch} @ ${data.commit}\n\n${data.note || "OK"}`);
    } catch (error) {
      alert("Échec Git / RAG: " + error.message);
    } finally {
      setToggleLoading(gitRefreshButton, "Git...", false);
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