const state = {
  session: null,
  items: [],
  selectedId: null,
  search: "",
  feedbackValue: "",
  feedbackReason: "",
  conversationCache: {},
};

const loginForm = document.getElementById("login-form");
const passwordInput = document.getElementById("admin-password");
const loginError = document.getElementById("login-error");
const sessionCard = document.getElementById("session-card");
const sessionRole = document.getElementById("session-role");
const logoutButton = document.getElementById("logout-button");
const refreshButton = document.getElementById("refresh-button");
const evalToggle = document.getElementById("eval-toggle");
const darijaToggle = document.getElementById("darija-toggle");
const cacheFlushBtn = document.getElementById("cache-flush");
const gatedContent = document.getElementById("gated-content");
const searchInput = document.getElementById("search-input");
const feedbackFilter = document.getElementById("feedback-filter");
const reasonFilter = document.getElementById("reason-filter");
const interactionList = document.getElementById("interaction-list");
const interactionDetail = document.getElementById("interaction-detail");
const resultsCount = document.getElementById("results-count");
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
  gatedContent.classList.toggle("hidden", !isAdmin);
  if (isAdmin) {
    sessionRole.textContent = "Administrateur";
  }
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
    await loadDarijaStatus();
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

async function loadInteractions() {
  const response = await apiFetch(`/admin/interactions?${buildListQuery()}`);
  const payload = await response.json();
  state.items = payload.items;
  resultsCount.textContent = `${payload.total} resultat(s)`;
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
      <div class="interaction-meta">
        <span>${item.detected_language || "unknown"}</span>
        <span>${item.context_used ? "RAG" : "sans RAG"}</span>
        <span>${item.from_cache ? "cache" : "live"}</span>
      </div>
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
    // silently ignore — non-critical
  }
}

function renderConversation(items, currentId) {
  const container = document.getElementById("conversation-context");
  if (!container || items.length <= 1) return;

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
        <span class="pill">${item.detected_language || "unknown"}</span>
      </div>

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

      <section class="detail-block">
        <div class="detail-label">Metadata</div>
        <pre>${escapeHtml(JSON.stringify(item.metadata || {}, null, 2))}</pre>
      </section>

      <section class="detail-block">
        <div class="detail-label">RAG Debug</div>
        <pre>${escapeHtml(JSON.stringify(item.rag_debug || {}, null, 2))}</pre>
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
    await apiFetch(`/admin/eval-run/${interactionId}`, { method: "POST" });
    // Reload the detail to show the new eval
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

async function loadDarijaStatus() {
  setToggleLoading(darijaToggle, "Darija: LOADING...", true);
  try {
    const response = await apiFetch("/admin/darija-status");
    const data = await response.json();
    setToggleLoading(darijaToggle, "Darija: LOADING...", false);

    darijaToggle.dataset.available = data.available ? "true" : "false";
    if (data.available) {
      darijaToggle.textContent = `Darija: ${data.enabled ? "ON" : "OFF"}`;
      darijaToggle.title = "Toggle Darija language support";
    } else {
      darijaToggle.textContent = "Darija: UNAVAILABLE";
      darijaToggle.title = data.reason ? `Unavailable: ${data.reason}` : "Darija translation models are not loaded";
    }
    darijaToggle.classList.toggle("active", data.enabled);
    darijaToggle.disabled = !data.available;
  } catch {
    setToggleLoading(darijaToggle, "Darija: LOADING...", false);
    darijaToggle.dataset.available = "false";
    darijaToggle.textContent = "Darija: ERROR";
    darijaToggle.title = "Failed to fetch Darija status";
    darijaToggle.disabled = true;
  }
}

async function handleDarijaToggle() {
  if (darijaToggle.disabled || darijaToggle.dataset.available !== "true") return;

  const nextEnabled = !darijaToggle.classList.contains("active");
  showToggleConfirmation(darijaToggle, "Darija support", nextEnabled, async () => {
    setToggleLoading(darijaToggle, "Darija: APPLYING...", true);
    try {
      const response = await apiFetch("/admin/darija-toggle", { method: "POST" });
      const data = await response.json();
      setToggleLoading(darijaToggle, "Darija: APPLYING...", false);

      darijaToggle.dataset.available = "true";
      darijaToggle.textContent = `Darija: ${data.enabled ? "ON" : "OFF"}`;
      darijaToggle.title = "Toggle Darija language support";
      darijaToggle.classList.toggle("active", data.enabled);
      darijaToggle.disabled = false;
    } catch (error) {
      setToggleLoading(darijaToggle, "Darija: APPLYING...", false);
      darijaToggle.disabled = darijaToggle.dataset.available !== "true";
      alert("Failed to toggle Darija: " + error.message);
    }
  });
}

async function handleCacheFlush() {
  if (!cacheFlushBtn) return;
  if (!confirm("Vider le cache Redis du chatbot ?\nCette action supprime toutes les reponses mises en cache.")) {
    return;
  }
  const previousLabel = cacheFlushBtn.textContent;
  cacheFlushBtn.disabled = true;
  cacheFlushBtn.textContent = "Cache: VIDAGE...";
  try {
    const response = await apiFetch("/admin/cache-flush", { method: "POST" });
    const data = await response.json();
    cacheFlushBtn.textContent = `Cache vide (${data.deleted})`;
    setTimeout(() => {
      cacheFlushBtn.textContent = previousLabel;
      cacheFlushBtn.disabled = false;
    }, 2500);
  } catch (error) {
    cacheFlushBtn.textContent = previousLabel;
    cacheFlushBtn.disabled = false;
    alert("Echec du vidage du cache: " + (error.message || "erreur inconnue"));
  }
}

loginForm.addEventListener("submit", handleLogin);
logoutButton.addEventListener("click", handleLogout);
refreshButton.addEventListener("click", () => loadInteractions().catch(handleLoadError));
evalToggle.addEventListener("click", handleEvalToggle);
darijaToggle.addEventListener("click", handleDarijaToggle);
if (cacheFlushBtn) cacheFlushBtn.addEventListener("click", handleCacheFlush);
searchInput.addEventListener("input", (event) => {
  state.search = event.target.value.trim();
  loadInteractions().catch(handleLoadError);
});
feedbackFilter.addEventListener("change", (event) => {
  state.feedbackValue = event.target.value;
  loadInteractions().catch(handleLoadError);
});
reasonFilter.addEventListener("change", (event) => {
  state.feedbackReason = event.target.value;
  loadInteractions().catch(handleLoadError);
});

function handleLoadError(error) {
  interactionList.innerHTML = `<div class="detail-empty">${escapeHtml(error.message || "Chargement impossible.")}</div>`;
  interactionDetail.innerHTML = '<div class="detail-empty">Verification necessaire.</div>';
}

loadSession()
  .then(() => {
    if (state.session?.role === "admin") {
      return Promise.all([loadInteractions(), loadEvalStatus(), loadDarijaStatus()]);
    }
    return null;
  })
  .catch(() => {
    renderSession();
  });