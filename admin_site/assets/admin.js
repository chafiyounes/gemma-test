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
};

const loginForm = document.getElementById("login-form");
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
const docUploadButton = document.getElementById("doc-upload-button");
const docRefreshButton = document.getElementById("doc-refresh-button");
const docError = document.getElementById("doc-error");
let activeToggleConfirmationCleanup = null;

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
    const error = new Error(payload.detail || `HTTP ${response.status}`);
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
  const isAdmin = state.session?.role === "admin";
  loginForm.classList.toggle("hidden", Boolean(isAdmin));
  sessionCard.classList.toggle("hidden", !isAdmin);
  if (preAuthPanel) preAuthPanel.classList.toggle("hidden", Boolean(isAdmin));
  if (dashboardRoot) dashboardRoot.classList.toggle("hidden", !isAdmin);
  if (isAdmin) {
    sessionRole.textContent = "Administrateur";
    setAdminView(state.adminView || "interactions");
  }
  const userHint = document.getElementById("pre-auth-user-hint");
  if (userHint) {
    const showUserHint = Boolean(state.session?.authenticated && state.session?.role === "user");
    userHint.classList.toggle("hidden", !showUserHint);
  }
}

function setAdminView(view) {
  state.adminView = view === "documents" ? "documents" : "interactions";
  if (interactionsView) interactionsView.classList.toggle("hidden", state.adminView !== "interactions");
  if (documentsView) documentsView.classList.toggle("hidden", state.adminView !== "documents");
  if (viewInteractionsButton) viewInteractionsButton.classList.toggle("active", state.adminView === "interactions");
  if (viewDocumentsButton) viewDocumentsButton.classList.toggle("active", state.adminView === "documents");
}

async function handleLogin(event) {
  event.preventDefault();
  loginError.classList.add("hidden");

  try {
    const response = await apiFetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: passwordInput.value }),
    });
    const session = await response.json();
    if (session.role !== "admin") {
      await handleLogout();
      throw new Error("Le mot de passe admin est requis pour cette interface.");
    }
    passwordInput.value = "";
    state.session = session;
    renderSession();
    await loadInteractions();
    await loadEvalStatus();
    await loadDocumentsOverview();
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

function renderDocuments() {
  const data = state.docsOverview;
  if (!data || !documentsCategories) return;

  const budget = data.budget || {};
  const limit = budget.category_limit_chars ?? 0;
  const reserve = budget.history_reserve_chars ?? 0;
  const inject = budget.inject_cap_chars ?? 0;
  if (documentsBudget) {
    documentsBudget.textContent = `Budget categorie: ${limit} chars (reserve chat: ${reserve}, cap inject: ${inject})`;
  }

  const categories = data.categories || [];
  if (!categories.length) {
    documentsCategories.innerHTML = '<div class="detail-empty">Aucune categorie detectee. Creez-en une en uploadant un fichier.</div>';
    return;
  }

  const categoryOptions = categories
    .map((cat) => `<option value="${escapeHtml(cat.name)}">${escapeHtml(cat.name)}</option>`)
    .join("");

  documentsCategories.innerHTML = categories
    .map((cat, idx) => {
      const overflowPill = cat.overflow
        ? `<span class="pill bad">overflow (${cat.total_chars} / ${limit})</span>`
        : `<span class="pill good">${cat.total_chars} / ${limit}</span>`;
      const files = (cat.files || [])
        .map((file) => `
          <div class="doc-file">
            <div class="doc-file-name">${escapeHtml(file.name)} <span class="pill">${file.source}</span> <span class="pill">${file.chars} chars</span></div>
            <select class="doc-move-select" data-move-select data-from="${escapeHtml(cat.name)}" data-name="${escapeHtml(file.name)}" data-source="${escapeHtml(file.source)}">
              <option value="">Deplacer vers...</option>
              ${categoryOptions}
            </select>
            <button type="button" data-move-button data-from="${escapeHtml(cat.name)}" data-name="${escapeHtml(file.name)}" data-source="${escapeHtml(file.source)}">Deplacer</button>
            <button type="button" class="delete" data-delete-button data-category="${escapeHtml(cat.name)}" data-name="${escapeHtml(file.name)}" data-source="${escapeHtml(file.source)}">Supprimer</button>
          </div>
        `)
        .join("");

      return `
        <div class="doc-category ${cat.overflow ? "overflow" : ""} ${idx === 0 ? "expanded" : ""}">
          <button type="button" class="doc-category-head" data-doc-toggle>
            <div><strong>${escapeHtml(cat.name)}</strong></div>
            <div class="doc-category-meta">
              <span class="pill">source active: ${escapeHtml(cat.active_source)}</span>
              <span class="pill">${cat.file_count} fichier(s)</span>
              ${overflowPill}
            </div>
          </button>
          <div class="doc-files">
            ${files || '<div class="detail-empty">Aucun fichier actif dans cette categorie.</div>'}
          </div>
        </div>
      `;
    })
    .join("");

  documentsCategories.querySelectorAll("[data-doc-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.closest(".doc-category")?.classList.toggle("expanded");
    });
  });

  documentsCategories.querySelectorAll("[data-move-button]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const from = btn.dataset.from;
      const filename = btn.dataset.name;
      const source = btn.dataset.source;
      const select = btn.closest(".doc-file")?.querySelector("select[data-move-select]");
      const target = select?.value || "";
      if (!target) {
        showDocError("Choisissez d'abord une categorie cible.");
        return;
      }
      if (target === from) {
        showDocError("La categorie cible doit etre differente.");
        return;
      }
      showDocError("");
      try {
        await apiFetch("/admin/documents/move", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_category: from,
            target_category: target,
            source_kind: source,
            filename,
          }),
        });
        await loadDocumentsOverview();
      } catch (error) {
        showDocError(error.message);
      }
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
      try {
        await apiFetch("/admin/documents/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            category,
            source_kind: source,
            filename,
          }),
        });
        await loadDocumentsOverview();
      } catch (error) {
        showDocError(error.message);
      }
    });
  });
}

async function loadDocumentsOverview() {
  const response = await apiFetch("/admin/documents/overview");
  state.docsOverview = await response.json();
  renderDocuments();
}

async function handleUploadDocument() {
  showDocError("");
  const category = (docCategoryInput?.value || "").trim();
  const file = docFileInput?.files?.[0];
  if (!category) {
    showDocError("La categorie est obligatoire.");
    return;
  }
  if (!file) {
    showDocError("Choisissez un fichier .docx ou .txt.");
    return;
  }
  const lower = file.name.toLowerCase();
  if (!lower.endsWith(".docx") && !lower.endsWith(".txt")) {
    showDocError("Seuls les fichiers .docx et .txt sont autorises.");
    return;
  }

  const body = new FormData();
  body.append("category", category);
  body.append("file", file);
  docUploadButton.disabled = true;
  try {
    await apiFetch("/admin/documents/upload", {
      method: "POST",
      body,
    });
    if (docFileInput) docFileInput.value = "";
    await loadDocumentsOverview();
  } catch (error) {
    showDocError(error.message);
  } finally {
    docUploadButton.disabled = false;
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
    if (state.session?.role === "admin") {
      return Promise.all([loadInteractions(), loadEvalStatus(), loadDocumentsOverview()]);
    }
    return null;
  })
  .catch(() => {
    renderSession();
  });