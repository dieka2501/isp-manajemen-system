const state = {
  sources: [],
  sourcePath: "",
  tables: [],
  selectedTable: "",
  query: `SELECT name, type FROM sqlite_master WHERE type IN ("table", "view") AND name NOT LIKE "sqlite_%" ORDER BY name;`,
  result: null,
  loading: false,
  authenticated: false,
  secretConfigured: false,
  activeView: "learning",
  learningItems: [],
  learningIntents: [],
  selectedLearningId: null,
  billingImportScopes: [],
  messageDumps: [],
  selectedDumpId: null,
  registrations: [],
  selectedRegistrationId: null,
};

const el = {
  authGate: document.getElementById("authGate"),
  dashboardShell: document.getElementById("dashboardShell"),
  learningTab: document.getElementById("learningTab"),
  dumpTab: document.getElementById("dumpTab"),
  registrationsTab: document.getElementById("registrationsTab"),
  explorerTab: document.getElementById("explorerTab"),
  learningView: document.getElementById("learningView"),
  messageDumpView: document.getElementById("messageDumpView"),
  registrationsView: document.getElementById("registrationsView"),
  explorerView: document.getElementById("explorerView"),
  loginForm: document.getElementById("loginForm"),
  passwordInput: document.getElementById("passwordInput"),
  loginMessage: document.getElementById("loginMessage"),
  loginButton: document.getElementById("loginButton"),
  sourceSelect: document.getElementById("sourceSelect"),
  pathInput: document.getElementById("pathInput"),
  loadButton: document.getElementById("loadButton"),
  refreshButton: document.getElementById("refreshButton"),
  tableFilter: document.getElementById("tableFilter"),
  tablesList: document.getElementById("tablesList"),
  tableCount: document.getElementById("tableCount"),
  sourceExistsBadge: document.getElementById("sourceExistsBadge"),
  sqlEditor: document.getElementById("sqlEditor"),
  limitInput: document.getElementById("limitInput"),
  runButton: document.getElementById("runButton"),
  resetButton: document.getElementById("resetButton"),
  queryStatus: document.getElementById("queryStatus"),
  queryInfo: document.getElementById("queryInfo"),
  resultMeta: document.getElementById("resultMeta"),
  resultsEmptyState: document.getElementById("resultsEmptyState"),
  resultsTableContainer: document.getElementById("resultsTableContainer"),
  connectionStatus: document.getElementById("connectionStatus"),
  logoutButton: document.getElementById("logoutButton"),
  refreshLearningButton: document.getElementById("refreshLearningButton"),
  learningStatusFilter: document.getElementById("learningStatusFilter"),
  learningLimitInput: document.getElementById("learningLimitInput"),
  learningList: document.getElementById("learningList"),
  learningCount: document.getElementById("learningCount"),
  learningDetailTitle: document.getElementById("learningDetailTitle"),
  learningDetailMeta: document.getElementById("learningDetailMeta"),
  learningStatusBadge: document.getElementById("learningStatusBadge"),
  learningMessageBox: document.getElementById("learningMessageBox"),
  learningReason: document.getElementById("learningReason"),
  learningDetected: document.getElementById("learningDetected"),
  learningSender: document.getElementById("learningSender"),
  mappingIntentSelect: document.getElementById("mappingIntentSelect"),
  mappingTypeSelect: document.getElementById("mappingTypeSelect"),
  mappingKeywordInput: document.getElementById("mappingKeywordInput"),
  mappingNormalizedInput: document.getElementById("mappingNormalizedInput"),
  mappingWeightInput: document.getElementById("mappingWeightInput"),
  mappingNotesInput: document.getElementById("mappingNotesInput"),
  saveMappingButton: document.getElementById("saveMappingButton"),
  suggestMappingButton: document.getElementById("suggestMappingButton"),
  previewLearningButton: document.getElementById("previewLearningButton"),
  mappingStatus: document.getElementById("mappingStatus"),
  learningCandidates: document.getElementById("learningCandidates"),
  billingImportClientSelect: document.getElementById("billingImportClientSelect"),
  billingImportDeviceSelect: document.getElementById("billingImportDeviceSelect"),
  billingImportFileInput: document.getElementById("billingImportFileInput"),
  billingImportButton: document.getElementById("billingImportButton"),
  billingImportStatus: document.getElementById("billingImportStatus"),
  billingImportSummary: document.getElementById("billingImportSummary"),
  refreshDumpButton: document.getElementById("refreshDumpButton"),
  dumpStatusFilter: document.getElementById("dumpStatusFilter"),
  dumpLimitInput: document.getElementById("dumpLimitInput"),
  dumpList: document.getElementById("dumpList"),
  dumpCount: document.getElementById("dumpCount"),
  dumpDetailTitle: document.getElementById("dumpDetailTitle"),
  dumpMeta: document.getElementById("dumpMeta"),
  dumpStatusBadge: document.getElementById("dumpStatusBadge"),
  dumpMessageBox: document.getElementById("dumpMessageBox"),
  dumpBotBox: document.getElementById("dumpBotBox"),
  dumpNotesInput: document.getElementById("dumpNotesInput"),
  markDumpReviewedButton: document.getElementById("markDumpReviewedButton"),
  markDumpIgnoredButton: document.getElementById("markDumpIgnoredButton"),
  dumpActionStatus: document.getElementById("dumpActionStatus"),
  refreshRegistrationsButton: document.getElementById("refreshRegistrationsButton"),
  registrationStatusFilter: document.getElementById("registrationStatusFilter"),
  registrationLimitInput: document.getElementById("registrationLimitInput"),
  registrationsList: document.getElementById("registrationsList"),
  registrationsCount: document.getElementById("registrationsCount"),
  registrationDetailTitle: document.getElementById("registrationDetailTitle"),
  registrationMeta: document.getElementById("registrationMeta"),
  registrationStatusBadge: document.getElementById("registrationStatusBadge"),
  registrationSummaryBox: document.getElementById("registrationSummaryBox"),
  approveAmountInput: document.getElementById("approveAmountInput"),
  approvePaymentMethodSelect: document.getElementById("approvePaymentMethodSelect"),
  approveVirtualAccountInput: document.getElementById("approveVirtualAccountInput"),
  approveRegistrationButton: document.getElementById("approveRegistrationButton"),
  cashPaymentButton: document.getElementById("cashPaymentButton"),
  bankPaymentButton: document.getElementById("bankPaymentButton"),
  activateRegistrationButton: document.getElementById("activateRegistrationButton"),
  registrationActionStatus: document.getElementById("registrationActionStatus"),
};

const STORAGE_KEYS = {
  sourcePath: "sqliteExplorer.sourcePath",
  query: "sqliteExplorer.query",
  limit: "sqliteExplorer.limit",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function quoteIdentifier(value) {
  return `"${String(value).replaceAll('"', '""')}"`;
}

function setStatus(label, variant = "idle") {
  el.queryStatus.className = `status-pill status-${variant}`;
  el.queryStatus.textContent = label;
}

function setConnectionStatus(message, kind = "idle") {
  el.connectionStatus.textContent = message;
  el.connectionStatus.className = "";
  el.connectionStatus.className =
    kind === "error"
      ? "mt-1 text-xs text-rose-200/90"
      : kind === "success"
        ? "mt-1 text-xs text-emerald-100/85"
        : "mt-1 text-xs text-emerald-100/80";
}

function persistPreferences() {
  localStorage.setItem(STORAGE_KEYS.sourcePath, el.pathInput.value.trim());
  localStorage.setItem(STORAGE_KEYS.query, el.sqlEditor.value);
  localStorage.setItem(STORAGE_KEYS.limit, el.limitInput.value);
}

function restorePreferences() {
  const savedPath = localStorage.getItem(STORAGE_KEYS.sourcePath);
  const savedQuery = localStorage.getItem(STORAGE_KEYS.query);
  const savedLimit = localStorage.getItem(STORAGE_KEYS.limit);

  if (savedPath) {
    el.pathInput.value = savedPath;
  }
  if (savedQuery) {
    el.sqlEditor.value = savedQuery;
    state.query = savedQuery;
  } else {
    el.sqlEditor.value = state.query;
  }
  if (savedLimit) {
    el.limitInput.value = savedLimit;
  }
}

async function api(path, options = {}) {
  const response = await fetch(`/api/v1/sqlite${path}`, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) {
      showAuthGate("Your session expired or login is required. Please sign in again.");
    }
    throw new Error(data.detail || `Request failed with status ${response.status}`);
  }
  return data;
}

async function uploadApi(path, formData) {
  const response = await fetch(`/api/v1/sqlite${path}`, {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      showAuthGate("Your session expired or login is required. Please sign in again.");
    }
    throw new Error(data.detail || `Request failed with status ${response.status}`);
  }
  return data;
}

async function chatApi(path, options = {}) {
  const response = await fetch(`/api/v1/chat${path}`, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      showAuthGate("Your session expired or login is required. Please sign in again.");
    }
    throw new Error(data.detail || `Request failed with status ${response.status}`);
  }
  return data;
}

async function registrationApi(path, options = {}) {
  const response = await fetch(`/api/v1/registrations${path}`, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      showAuthGate("Your session expired or login is required. Please sign in again.");
    }
    throw new Error(data.detail || `Request failed with status ${response.status}`);
  }
  return data;
}

function showAuthGate(message) {
  state.authenticated = false;
  el.authGate.classList.remove("hidden");
  el.dashboardShell.classList.add("hidden");
  if (message) {
    el.loginMessage.textContent = message;
  }
}

function showDashboard() {
  el.authGate.classList.add("hidden");
  el.dashboardShell.classList.remove("hidden");
}

function currentPath() {
  return el.pathInput.value.trim();
}

function setCurrentSource(path) {
  el.pathInput.value = path;
  persistPreferences();
}

function switchView(view) {
  state.activeView = view;
  el.learningView.classList.toggle("hidden", view !== "learning");
  el.messageDumpView.classList.toggle("hidden", view !== "dumps");
  el.registrationsView.classList.toggle("hidden", view !== "registrations");
  el.explorerView.classList.toggle("hidden", view !== "explorer");
  const tabs = [
    [el.learningTab, "learning"],
    [el.dumpTab, "dumps"],
    [el.registrationsTab, "registrations"],
    [el.explorerTab, "explorer"],
  ];
  tabs.forEach(([tab, tabView]) => {
    tab.classList.toggle("is-active", view === tabView);
    tab.classList.toggle("action-primary", view === tabView);
    tab.classList.toggle("action-secondary", view !== tabView);
    tab.setAttribute("aria-selected", view === tabView ? "true" : "false");
  });
  if (view === "dumps" && state.messageDumps.length === 0) {
    loadMessageDumps().catch(showError);
  }
  if (view === "registrations" && state.registrations.length === 0) {
    loadRegistrations().catch(showError);
  }
  if (view === "explorer" && state.billingImportScopes.length === 0) {
    loadBillingImportScopes().catch(showError);
  }
}

async function checkAuth() {
  el.loginMessage.textContent = "Checking login status...";
  const data = await api("/auth/status");
  state.authenticated = Boolean(data.authenticated);
  state.secretConfigured = Boolean(data.secret_configured);

  if (state.authenticated) {
    showDashboard();
    if (state.secretConfigured) {
      setConnectionStatus("Dashboard unlocked.", "success");
    } else {
      setConnectionStatus("Dashboard login is disabled in this environment.", "success");
    }
    return true;
  }

  showAuthGate("Enter the dashboard password to continue.");
  return false;
}

function selectedLearningItem() {
  return state.learningItems.find((item) => item.id === state.selectedLearningId) || null;
}

function renderLearningIntents() {
  el.mappingIntentSelect.innerHTML = state.learningIntents
    .map((intent) => {
      return `<option value="${escapeHtml(intent.intent_code)}">${escapeHtml(intent.intent_code)} - ${escapeHtml(intent.intent_name)}</option>`;
    })
    .join("");
}

function renderLearningList() {
  el.learningCount.textContent = `${state.learningItems.length} item(s)`;
  el.learningList.innerHTML = state.learningItems.length
    ? state.learningItems
        .map((item) => {
          const selected = item.id === state.selectedLearningId;
          const detected = item.detected_intent_code || "unknown";
          const confidence = Math.round(Number(item.confidence || 0) * 100);
          return `
            <button class="learning-card w-full text-left p-4 ${selected ? "is-selected" : ""}" data-learning-id="${item.id}">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="line-clamp-2 text-sm font-semibold text-white">${escapeHtml(item.message_text)}</div>
                  <div class="mt-2 text-xs text-slate-400">${escapeHtml(item.sender_name || item.sender_number || "Unknown sender")}</div>
                </div>
                <span class="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300">${escapeHtml(item.status)}</span>
              </div>
              <div class="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
                <span>${escapeHtml(item.reason)}</span>
                <span>${escapeHtml(detected)} ${confidence}%</span>
                <span>${escapeHtml(item.language)}</span>
              </div>
            </button>
          `;
        })
        .join("")
    : `<div class="p-5 text-sm text-slate-400">No questions found for this filter.</div>`;
}

function renderLearningDetail() {
  const item = selectedLearningItem();
  if (!item) {
    el.learningDetailTitle.textContent = "Select a question";
    el.learningDetailMeta.textContent = "Pick a pending customer question from the queue to map it into native intent data.";
    el.learningStatusBadge.textContent = "Waiting";
    el.learningStatusBadge.className = "status-pill status-idle";
    el.learningMessageBox.textContent = "No question selected.";
    el.learningReason.textContent = "-";
    el.learningDetected.textContent = "-";
    el.learningSender.textContent = "-";
    el.mappingKeywordInput.value = "";
    el.mappingNormalizedInput.value = "";
    el.mappingNotesInput.value = "";
    el.learningCandidates.textContent = "No candidates loaded.";
    el.mappingStatus.textContent = "Select a question to begin.";
    return;
  }

  el.learningDetailTitle.textContent = `Question #${item.id}`;
  el.learningDetailMeta.textContent = `${item.client_name} | ${item.device_identifier} | ${item.created_at}`;
  el.learningStatusBadge.textContent = item.status;
  el.learningStatusBadge.className =
    "status-pill " + (item.status === "pending" ? "status-loading" : item.status === "mapped" ? "status-success" : "status-idle");
  el.learningMessageBox.textContent = item.message_text;
  el.learningReason.textContent = item.reason;
  el.learningDetected.textContent = `${item.detected_intent_code || "unknown"} (${Math.round(Number(item.confidence || 0) * 100)}%)`;
  el.learningSender.textContent = item.sender_name || item.sender_number || "-";
  el.mappingKeywordInput.value = item.normalized_text || item.message_text;
  el.mappingNormalizedInput.value = item.normalized_text || "";
  el.mappingNotesInput.value = `Mapped from question #${item.id}`;
  if (item.mapped_intent_code) {
    el.mappingIntentSelect.value = item.mapped_intent_code;
  }
  renderLearningCandidates(item);
  el.mappingStatus.textContent = "Choose an intent and save mapping.";
}

function renderLearningCandidates(item) {
  const candidates = item.candidates || [];
  const entities = item.entities || [];
  const candidateHtml = candidates.length
    ? candidates
        .map((candidate) => {
          return `
            <div class="candidate-card">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div class="font-semibold text-white">${escapeHtml(candidate.intent_code)}</div>
                <span class="text-xs text-slate-400">${Math.round(Number(candidate.confidence || 0) * 100)}% | score ${escapeHtml(candidate.score)}</span>
              </div>
              <div class="mt-2 text-xs leading-5 text-slate-400">${escapeHtml((candidate.matched_keywords || []).join(", ") || "No keywords")}</div>
            </div>
          `;
        })
        .join("")
    : `<div class="text-sm text-slate-400">No native candidates were found.</div>`;
  const entityHtml = entities.length
    ? `<div class="mt-4 text-xs uppercase tracking-[0.22em] text-slate-500">Entities</div>
       <div class="mt-2 flex flex-wrap gap-2">${entities
         .map((entity) => `<span class="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">${escapeHtml(entity.entity_code)}: ${escapeHtml(entity.value)}</span>`)
         .join("")}</div>`
    : "";
  el.learningCandidates.innerHTML = `<div class="space-y-3">${candidateHtml}</div>${entityHtml}`;
}

function selectedDump() {
  return state.messageDumps.find((item) => item.id === state.selectedDumpId) || null;
}

function renderMessageDumps() {
  el.dumpCount.textContent = `${state.messageDumps.length} item(s)`;
  el.dumpList.innerHTML = state.messageDumps.length
    ? state.messageDumps
        .map((item) => {
          const selected = item.id === state.selectedDumpId;
          const confidence = Math.round(Number(item.confidence || 0) * 100);
          return `
            <button class="learning-card w-full text-left p-4 ${selected ? "is-selected" : ""}" data-dump-id="${item.id}">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="line-clamp-2 text-sm font-semibold text-white">${escapeHtml(item.message_text)}</div>
                  <div class="mt-2 text-xs text-slate-400">${escapeHtml(item.sender_name || item.sender_number || "Unknown sender")}</div>
                </div>
                <span class="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300">${escapeHtml(item.status)}</span>
              </div>
              <div class="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
                <span>${escapeHtml(item.reason)}</span>
                <span>${escapeHtml(item.detected_intent || "unknown")} ${confidence}%</span>
                <span>${escapeHtml(item.created_at)}</span>
              </div>
            </button>
          `;
        })
        .join("")
    : `<div class="p-5 text-sm text-slate-400">No message dumps found for this filter.</div>`;
}

function renderMessageDumpDetail() {
  const item = selectedDump();
  if (!item) {
    el.dumpDetailTitle.textContent = "Select a dump";
    el.dumpMeta.textContent = "Pick a message dump to review the customer text and bot reply.";
    el.dumpStatusBadge.textContent = "Waiting";
    el.dumpStatusBadge.className = "status-pill status-idle";
    el.dumpMessageBox.textContent = "No dump selected.";
    el.dumpBotBox.textContent = "No dump selected.";
    el.dumpNotesInput.value = "";
    el.dumpActionStatus.textContent = "Select a dump to begin.";
    return;
  }

  el.dumpDetailTitle.textContent = `Dump #${item.id}`;
  el.dumpMeta.textContent = `${item.client_name} | ${item.device_identifier} | ${item.created_at}`;
  el.dumpStatusBadge.textContent = item.status;
  el.dumpStatusBadge.className =
    "status-pill " + (item.status === "pending" ? "status-loading" : item.status === "reviewed" ? "status-success" : "status-idle");
  el.dumpMessageBox.textContent = item.message_text || "-";
  el.dumpBotBox.textContent = item.bot_response || "-";
  el.dumpNotesInput.value = item.reviewer_notes || "";
  el.dumpActionStatus.textContent = `${item.reason} | ${item.detected_intent || "unknown"} (${Math.round(Number(item.confidence || 0) * 100)}%)`;
}

async function loadMessageDumps() {
  const status = el.dumpStatusFilter.value || "pending";
  const limit = Number.parseInt(el.dumpLimitInput.value, 10) || 100;
  el.dumpActionStatus.textContent = "Loading message dumps...";
  const data = await registrationApi(`/admin/message-dumps?status=${encodeURIComponent(status)}&limit=${limit}`);
  state.messageDumps = data.items || [];
  if (!state.messageDumps.some((item) => item.id === state.selectedDumpId)) {
    state.selectedDumpId = state.messageDumps[0]?.id || null;
  }
  renderMessageDumps();
  renderMessageDumpDetail();
  el.dumpActionStatus.textContent = state.messageDumps.length ? "Message dumps loaded." : "No dumps for this filter.";
}

async function reviewSelectedDump(nextStatus) {
  const item = selectedDump();
  if (!item) {
    el.dumpActionStatus.textContent = "Select a dump first.";
    return;
  }
  el.dumpActionStatus.textContent = "Saving review...";
  const data = await registrationApi(`/admin/message-dumps/${item.id}`, {
    method: "POST",
    body: JSON.stringify({
      status: nextStatus,
      reviewer_notes: el.dumpNotesInput.value.trim() || null,
    }),
  });
  const updated = data.item;
  state.messageDumps = state.messageDumps.map((current) => (current.id === updated.id ? updated : current));
  renderMessageDumps();
  renderMessageDumpDetail();
  el.dumpActionStatus.textContent = "Review saved.";
}

function selectedRegistration() {
  return state.registrations.find((item) => item.id === state.selectedRegistrationId) || null;
}

function renderRegistrations() {
  el.registrationsCount.textContent = `${state.registrations.length} item(s)`;
  el.registrationsList.innerHTML = state.registrations.length
    ? state.registrations
        .map((item) => {
          const selected = item.id === state.selectedRegistrationId;
          return `
            <button class="learning-card w-full text-left p-4 ${selected ? "is-selected" : ""}" data-registration-id="${item.id}">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="line-clamp-2 text-sm font-semibold text-white">${escapeHtml(item.name || item.default_name || item.sender_name || item.sender_number)}</div>
                  <div class="mt-2 text-xs text-slate-400">${escapeHtml(item.phone || item.default_phone || item.sender_number || "-")}</div>
                </div>
                <span class="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300">${escapeHtml(item.status)}</span>
              </div>
              <div class="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
                <span>${escapeHtml(item.customer_code || "No ID")}</span>
                <span>${escapeHtml(item.client_name || "-")}</span>
                <span>${escapeHtml(item.updated_at)}</span>
              </div>
            </button>
          `;
        })
        .join("")
    : `<div class="p-5 text-sm text-slate-400">No registrations found for this filter.</div>`;
}

function renderRegistrationDetail() {
  const item = selectedRegistration();
  if (!item) {
    el.registrationDetailTitle.textContent = "Select a registration";
    el.registrationMeta.textContent = "Approve, mark paid, or activate a selected customer.";
    el.registrationStatusBadge.textContent = "Waiting";
    el.registrationStatusBadge.className = "status-pill status-idle";
    el.registrationSummaryBox.textContent = "No registration selected.";
    el.registrationActionStatus.textContent = "Select a registration to begin.";
    return;
  }

  const latestPayment = (item.payments || [])[0] || {};
  el.registrationDetailTitle.textContent = `Registration #${item.id}`;
  el.registrationMeta.textContent = `${item.client_name} | ${item.device_identifier} | ${item.updated_at}`;
  el.registrationStatusBadge.textContent = item.status;
  el.registrationStatusBadge.className =
    "status-pill " + (item.status === "active" ? "status-success" : item.status === "registered" ? "status-loading" : "status-idle");
  el.registrationSummaryBox.innerHTML = `
    <div class="grid gap-2 md:grid-cols-2">
      <div><span class="section-label">Customer ID</span><div>${escapeHtml(item.customer_code || "-")}</div></div>
      <div><span class="section-label">Name</span><div>${escapeHtml(item.name || item.default_name || "-")}</div></div>
      <div><span class="section-label">WA</span><div>${escapeHtml(item.phone || item.default_phone || item.sender_number || "-")}</div></div>
      <div><span class="section-label">Email</span><div>${escapeHtml(item.email || "-")}</div></div>
      <div class="md:col-span-2"><span class="section-label">Address</span><div>${escapeHtml(item.address || "-")}</div></div>
      <div class="md:col-span-2"><span class="section-label">Maps</span><div>${escapeHtml(item.maps_link || "-")}</div></div>
      <div><span class="section-label">Virtual Account</span><div>${escapeHtml(item.virtual_account || "-")}</div></div>
      <div><span class="section-label">Latest Payment</span><div>${escapeHtml(latestPayment.status || "-")} ${latestPayment.amount ? `| Rp ${Number(latestPayment.amount).toLocaleString("id-ID")}` : ""}</div></div>
      <div class="md:col-span-2"><span class="section-label">Payment URL</span><div>${escapeHtml(item.payment_url || "-")}</div></div>
    </div>
  `;
  el.approveVirtualAccountInput.value = item.virtual_account || "";
  if (latestPayment.amount) {
    el.approveAmountInput.value = latestPayment.amount;
  }
  if (item.payment_method) {
    el.approvePaymentMethodSelect.value = item.payment_method;
  }
  el.registrationActionStatus.textContent = "Choose an action for this registration.";
}

async function loadRegistrations() {
  const status = el.registrationStatusFilter.value || "registered";
  const limit = Number.parseInt(el.registrationLimitInput.value, 10) || 100;
  el.registrationActionStatus.textContent = "Loading registrations...";
  const data = await registrationApi(`/admin/items?status=${encodeURIComponent(status)}&limit=${limit}`);
  state.registrations = data.items || [];
  if (!state.registrations.some((item) => item.id === state.selectedRegistrationId)) {
    state.selectedRegistrationId = state.registrations[0]?.id || null;
  }
  renderRegistrations();
  renderRegistrationDetail();
  el.registrationActionStatus.textContent = state.registrations.length ? "Registrations loaded." : "No registrations for this filter.";
}

function updateRegistrationInState(updated) {
  const exists = state.registrations.some((item) => item.id === updated.id);
  state.registrations = exists
    ? state.registrations.map((current) => (current.id === updated.id ? updated : current))
    : [updated, ...state.registrations];
  state.selectedRegistrationId = updated.id;
  renderRegistrations();
  renderRegistrationDetail();
}

async function approveSelectedRegistration() {
  const item = selectedRegistration();
  if (!item) {
    el.registrationActionStatus.textContent = "Select a registration first.";
    return;
  }
  el.registrationActionStatus.textContent = "Approving registration...";
  const data = await registrationApi(`/admin/${item.id}/approve`, {
    method: "POST",
    body: JSON.stringify({
      amount: Number.parseInt(el.approveAmountInput.value, 10) || 0,
      payment_method: el.approvePaymentMethodSelect.value,
      virtual_account: el.approveVirtualAccountInput.value.trim() || null,
    }),
  });
  updateRegistrationInState(data.item);
  el.registrationActionStatus.textContent = "Registration approved.";
}

async function markSelectedRegistrationPaid(method) {
  const item = selectedRegistration();
  if (!item) {
    el.registrationActionStatus.textContent = "Select a registration first.";
    return;
  }
  el.registrationActionStatus.textContent = "Saving payment...";
  const data = await registrationApi(`/admin/${item.id}/payment`, {
    method: "POST",
    body: JSON.stringify({
      payment_method: method,
      amount: Number.parseInt(el.approveAmountInput.value, 10) || 0,
      virtual_account: el.approveVirtualAccountInput.value.trim() || item.virtual_account || null,
    }),
  });
  updateRegistrationInState(data.item);
  el.registrationActionStatus.textContent = "Payment saved and technician notification processed.";
}

async function activateSelectedRegistration() {
  const item = selectedRegistration();
  if (!item) {
    el.registrationActionStatus.textContent = "Select a registration first.";
    return;
  }
  el.registrationActionStatus.textContent = "Activating customer...";
  const data = await registrationApi(`/admin/${item.id}/activate`, {
    method: "POST",
    body: JSON.stringify({ notes: "Installation completed from SQLite Explorer." }),
  });
  updateRegistrationInState(data.item);
  el.registrationActionStatus.textContent = "Customer activated.";
}

function renderBillingImportScopes() {
  const selectedClientId = Number.parseInt(el.billingImportClientSelect.value, 10);
  const selectedClient =
    state.billingImportScopes.find((client) => client.id === selectedClientId) ||
    state.billingImportScopes[0] ||
    null;

  el.billingImportClientSelect.innerHTML = state.billingImportScopes.length
    ? state.billingImportScopes
        .map((client) => {
          const selected = selectedClient && client.id === selectedClient.id;
          const label = `${client.name}${client.email ? ` (${client.email})` : ""}`;
          return `<option value="${client.id}" ${selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
        })
        .join("")
    : `<option value="">No clients</option>`;

  const devices = selectedClient?.devices || [];
  el.billingImportDeviceSelect.innerHTML = devices.length
    ? devices
        .map((device, index) => {
          const label = device.device_name || device.device_identifier || `Device #${device.id}`;
          return `<option value="${device.id}" ${index === 0 ? "selected" : ""}>${escapeHtml(label)}</option>`;
        })
        .join("")
    : `<option value="">No devices</option>`;
}

async function loadBillingImportScopes() {
  const data = await api("/billing-import/scopes");
  state.billingImportScopes = data.items || [];
  renderBillingImportScopes();
}

function setBillingImportStatus(label, variant = "idle") {
  el.billingImportStatus.className = `status-pill status-${variant}`;
  el.billingImportStatus.textContent = label;
}

async function importBillingWorkbook() {
  const file = el.billingImportFileInput.files?.[0];
  if (!file) {
    el.billingImportSummary.textContent = "Choose a .xlsx billing file first.";
    setBillingImportStatus("File required", "error");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    el.billingImportSummary.textContent = "Only .xlsx files are supported.";
    setBillingImportStatus("Invalid file", "error");
    return;
  }

  const formData = new FormData();
  formData.append("billing_file", file);
  if (el.billingImportClientSelect.value) {
    formData.append("client_id", el.billingImportClientSelect.value);
  }
  if (el.billingImportDeviceSelect.value) {
    formData.append("device_id", el.billingImportDeviceSelect.value);
  }

  el.billingImportButton.disabled = true;
  setBillingImportStatus("Importing...", "loading");
  el.billingImportSummary.textContent = "Uploading workbook and importing rows into SQLite...";
  try {
    const data = await uploadApi("/billing-import", formData);
    const item = data.item || {};
    const clientName = item.client?.name || `Client #${item.client_id}`;
    const deviceName = item.device?.device_name || item.device?.device_identifier || `Device #${item.device_id}`;
    el.billingImportSummary.textContent =
      `${data.filename} imported for ${clientName} / ${deviceName}: ` +
      `${item.processed_rows || 0} row(s), ${item.customer_count || 0} customer(s), ` +
      `${item.billing_count || 0} billing record(s), ${item.package_count || 0} package(s). ` +
      `${item.skipped_rows || 0} row(s) skipped.`;
    setBillingImportStatus("Imported", "success");
    if (currentPath()) {
      await loadTables({ autoRunFirstTable: false });
    }
  } finally {
    el.billingImportButton.disabled = false;
  }
}

async function loadLearningIntents() {
  const data = await chatApi("/learning/intents");
  state.learningIntents = data.items || [];
  renderLearningIntents();
}

async function loadLearningQueue() {
  const status = el.learningStatusFilter.value || "pending";
  const limit = Number.parseInt(el.learningLimitInput.value, 10) || 50;
  el.mappingStatus.textContent = "Loading learning queue...";
  const data = await chatApi(`/learning/unprocessed?status=${encodeURIComponent(status)}&limit=${limit}`);
  state.learningItems = data.items || [];
  if (!state.learningItems.some((item) => item.id === state.selectedLearningId)) {
    state.selectedLearningId = state.learningItems[0]?.id || null;
  }
  renderLearningList();
  renderLearningDetail();
  el.mappingStatus.textContent = state.learningItems.length ? "Learning queue loaded." : "No items for this filter.";
}

async function saveLearningMapping() {
  const item = selectedLearningItem();
  if (!item) {
    el.mappingStatus.textContent = "Select a question first.";
    return;
  }
  const mappingType = el.mappingTypeSelect.value;
  const body = {
    mapping_type: mappingType,
    intent_code: mappingType === "ignore" ? null : el.mappingIntentSelect.value,
    keyword: el.mappingKeywordInput.value.trim() || null,
    normalized_keyword: el.mappingNormalizedInput.value.trim() || null,
    weight: Number.parseInt(el.mappingWeightInput.value, 10) || 4,
    notes: el.mappingNotesInput.value.trim() || null,
  };
  el.saveMappingButton.disabled = true;
  el.mappingStatus.textContent = "Saving mapping...";
  try {
    const data = await chatApi(`/learning/unprocessed/${item.id}/map`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const updated = data.item;
    state.learningItems = state.learningItems.map((current) => (current.id === updated.id ? updated : current));
    renderLearningList();
    renderLearningDetail();
    el.mappingStatus.textContent = "Mapping saved. Native intent data is updated in SQLite.";
  } finally {
    el.saveMappingButton.disabled = false;
  }
}

async function previewSelectedLearningItem() {
  const item = selectedLearningItem();
  if (!item) {
    el.mappingStatus.textContent = "Select a question first.";
    return;
  }
  el.mappingStatus.textContent = "Previewing selected question...";
  const data = await chatApi("/agent/preview", {
    method: "POST",
    body: JSON.stringify({ message: item.message_text }),
  });
  const analysis = data.item || {};
  el.learningCandidates.innerHTML = `<pre class="custom-scroll overflow-auto rounded-2xl bg-black/25 p-4 text-xs text-slate-200">${escapeHtml(JSON.stringify(analysis, null, 2))}</pre>`;
  el.mappingStatus.textContent = `Preview: ${analysis.intent?.intent_code || "unknown"}`;
}

async function suggestLearningMapping() {
  const item = selectedLearningItem();
  if (!item) {
    el.mappingStatus.textContent = "Select a question first.";
    return;
  }
  el.suggestMappingButton.disabled = true;
  el.mappingStatus.textContent = "Asking OpenAI for a reviewable suggestion...";
  try {
    const data = await chatApi(`/learning/unprocessed/${item.id}/suggest`, {
      method: "POST",
    });
    const suggestion = data.item || {};
    if (suggestion.intent_code) {
      el.mappingIntentSelect.value = suggestion.intent_code;
    }
    if (suggestion.mapping_type) {
      el.mappingTypeSelect.value = suggestion.mapping_type;
    }
    el.mappingKeywordInput.value = suggestion.keyword || item.message_text || "";
    el.mappingNormalizedInput.value = suggestion.normalized_keyword || "";
    el.mappingWeightInput.value = suggestion.weight || 4;
    el.mappingNotesInput.value = suggestion.reason || `OpenAI suggested mapping from question #${item.id}`;
    el.learningCandidates.innerHTML = `<pre class="custom-scroll overflow-auto rounded-2xl bg-black/25 p-4 text-xs text-slate-200">${escapeHtml(JSON.stringify(suggestion, null, 2))}</pre>`;
    el.mappingStatus.textContent = "OpenAI suggestion loaded. Review it before saving.";
  } finally {
    el.suggestMappingButton.disabled = false;
  }
}

async function loginDashboard(event) {
  event.preventDefault();
  const password = el.passwordInput.value.trim();
  if (!password) {
    el.loginMessage.textContent = "Please enter the dashboard password.";
    return;
  }

  el.loginButton.disabled = true;
  el.loginMessage.textContent = "Signing in...";

  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    state.authenticated = Boolean(data.authenticated);
    state.secretConfigured = Boolean(data.secret_configured);
    if (state.authenticated) {
      showDashboard();
      el.passwordInput.value = "";
      setConnectionStatus("Dashboard unlocked.", "success");
      switchView("learning");
      await loadLearningIntents();
      await loadLearningQueue();
      await loadSources();
      await loadBillingImportScopes();
      if (currentPath()) {
        await loadTables({ autoRunFirstTable: true });
      }
      return;
    }

    el.loginMessage.textContent = "Login failed. Please try again.";
  } catch (error) {
    el.loginMessage.textContent = error.message || String(error);
    showError(error);
  } finally {
    el.loginButton.disabled = false;
  }
}

async function logoutDashboard() {
  try {
    await api("/auth/logout", {
      method: "POST",
    });
  } finally {
    state.authenticated = false;
    state.sources = [];
    state.tables = [];
    state.selectedTable = "";
    state.sourcePath = "";
    state.result = null;
    el.sourceSelect.innerHTML = '<option value="">No configured sources</option>';
    el.tablesList.innerHTML = "";
    el.tableCount.textContent = "No database loaded.";
    el.sourceExistsBadge.textContent = "Waiting";
    el.sourceExistsBadge.className =
      "rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300";
    el.resultsEmptyState.classList.remove("hidden");
    el.resultsTableContainer.classList.add("hidden");
    el.resultsTableContainer.innerHTML = "";
    state.learningItems = [];
    state.learningIntents = [];
    state.billingImportScopes = [];
    state.messageDumps = [];
    state.registrations = [];
    state.selectedLearningId = null;
    state.selectedDumpId = null;
    state.selectedRegistrationId = null;
    el.learningList.innerHTML = "";
    el.learningCount.textContent = "No queue loaded.";
    renderLearningDetail();
    el.dumpList.innerHTML = "";
    el.dumpCount.textContent = "No dumps loaded.";
    renderMessageDumpDetail();
    el.registrationsList.innerHTML = "";
    el.registrationsCount.textContent = "No registrations loaded.";
    renderRegistrationDetail();
    renderBillingImportScopes();
    setStatus("Ready", "idle");
    setConnectionStatus("Signed out. Enter the dashboard password to continue.");
    showAuthGate("You have been signed out. Enter the dashboard password to continue.");
  }
}

function renderSources() {
  const customPath = currentPath();
  const sourceValues = new Set(state.sources.map((source) => source.path));
  const customOption =
    customPath && !sourceValues.has(customPath)
      ? `<option value="${escapeHtml(customPath)}" selected>Custom path: ${escapeHtml(customPath)}</option>`
      : "";
  const options = state.sources
    .map((source, index) => {
      const selected = source.path === currentPath() || (!currentPath() && index === 0);
      return `<option value="${escapeHtml(source.path)}" ${selected ? "selected" : ""}>${escapeHtml(source.name)}${source.exists ? "" : " (missing)"}</option>`;
    })
    .join("");
  el.sourceSelect.innerHTML = customOption + (options || `<option value="">No configured sources</option>`);
}

function applySelectedSourceFromDropdown() {
  const selected = state.sources.find((source) => source.path === el.sourceSelect.value);
  if (selected) {
    setCurrentSource(selected.path);
  }
}

function renderTables() {
  const filter = el.tableFilter.value.trim().toLowerCase();
  const visibleTables = state.tables.filter((table) => {
    if (!filter) return true;
    const columnNames = (table.columns || []).map((column) => column.name).join(" ");
    return `${table.name} ${columnNames}`.toLowerCase().includes(filter);
  });

  el.tableCount.textContent = `${visibleTables.length} table(s) visible`;
  el.tablesList.innerHTML = visibleTables.length
    ? visibleTables
        .map((table) => {
          const columns = (table.columns || []).map((column) => column.name).slice(0, 4).join(", ");
          return `
            <button
              class="table-card w-full text-left p-4 ${state.selectedTable === table.name ? "is-selected" : ""}"
              data-table="${escapeHtml(table.name)}"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-sm font-semibold text-white">${escapeHtml(table.name)}</div>
                  <div class="mt-1 text-xs uppercase tracking-[0.24em] text-slate-500">${escapeHtml(table.type)}</div>
                </div>
                <span class="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300">
                  ${table.row_count ?? "?"} rows
                </span>
              </div>
              <div class="mt-3 text-xs leading-5 text-slate-400">
                ${escapeHtml(columns || "No columns available")}
              </div>
            </button>
          `;
        })
        .join("")
    : `<div class="p-5 text-sm text-slate-400">No tables match the current filter.</div>`;

  el.sourceExistsBadge.textContent = state.sourcePath ? (state.sourceExists ? "File found" : "Missing file") : "Waiting";
  el.sourceExistsBadge.className =
    "rounded-full border px-3 py-1 text-xs " +
    (state.sourceExists
      ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-200"
      : "border-amber-400/20 bg-amber-400/10 text-amber-200");
}

function renderResultTable(result) {
  const columns = result.columns || [];
  const rows = result.rows || [];
  const isWriteResult = result.operation === "insert" || result.operation === "update";

  el.resultsEmptyState.classList.toggle("hidden", columns.length > 0);
  el.resultsTableContainer.classList.toggle("hidden", columns.length === 0);

  if (!columns.length) {
    if (isWriteResult) {
      el.resultsEmptyState.classList.add("hidden");
      el.resultsTableContainer.classList.remove("hidden");
      const operation = String(result.operation || "write").toUpperCase();
      const rowLabel = `${result.rows_affected ?? 0} row(s) affected`;
      const lastInsert = result.last_insert_rowid
        ? `<div><span>Last insert rowid</span><strong>${escapeHtml(result.last_insert_rowid)}</strong></div>`
        : "";
      el.resultsTableContainer.innerHTML = `
        <div class="write-summary">
          <div>
            <span>Operation</span>
            <strong>${escapeHtml(operation)}</strong>
          </div>
          <div>
            <span>Rows affected</span>
            <strong>${escapeHtml(result.rows_affected ?? 0)}</strong>
          </div>
          ${lastInsert}
        </div>
      `;
      el.resultMeta.textContent = rowLabel;
      return;
    }

    el.resultsTableContainer.innerHTML = "";
    el.resultMeta.textContent = "No columns returned";
    return;
  }

  const table = document.createElement("table");
  table.className = "data-table w-full";

  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  columns.forEach((column) => {
    const th = document.createElement("th");
    th.textContent = column;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);

  const tbody = document.createElement("tbody");
  if (rows.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = columns.length;
    td.className = "p-6 text-center text-sm text-slate-400";
    td.textContent = "Query returned no rows.";
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      columns.forEach((column) => {
        const td = document.createElement("td");
        const value = row[column];
        td.innerHTML =
          value === null || value === undefined || value === ""
            ? '<span class="text-slate-500">NULL</span>'
            : escapeHtml(value);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  table.appendChild(thead);
  table.appendChild(tbody);

  el.resultsTableContainer.innerHTML = "";
  el.resultsTableContainer.appendChild(table);
  const affectedText = isWriteResult ? ` | ${result.rows_affected ?? 0} affected` : "";
  el.resultMeta.textContent = `${result.row_count} row(s) ${result.truncated ? "(truncated)" : ""}${affectedText}`;
}

async function loadSources() {
  setStatus("Loading sources...", "loading");
  setConnectionStatus("Fetching configured SQLite sources...");
  const data = await api("/sources");
  state.sources = data.items || [];
  renderSources();

  const savedPath = localStorage.getItem(STORAGE_KEYS.sourcePath);
  const preferred =
    (savedPath ? state.sources.find((source) => source.path === savedPath) : null) ||
    data.default_source ||
    state.sources[0];
  if (savedPath) {
    setCurrentSource(savedPath);
  } else if (preferred) {
    setCurrentSource(preferred.path);
  }
  el.sourceSelect.value = currentPath();
  setConnectionStatus(`${state.sources.length} configured source(s) loaded.`, "success");
  setStatus("Ready", "success");
}

async function loadTables({ autoRunFirstTable = true } = {}) {
  const path = currentPath();
  if (!path) {
    setStatus("Choose a file first", "error");
    throw new Error("Please choose a SQLite file path first.");
  }

  state.sourcePath = path;
  setStatus("Loading tables...", "loading");
  setConnectionStatus(`Reading table list from ${path}...`);

  const data = await api(`/tables?path=${encodeURIComponent(path)}`);
  state.tables = data.tables || [];
  state.sourceExists = Boolean(data.source?.exists);
  state.selectedTable = "";
  renderTables();
  setStatus(`Loaded ${state.tables.length} table(s)`, "success");
  setConnectionStatus(
    state.sourceExists ? `Exploring ${data.source.resolved_path}` : `File not found: ${data.source.resolved_path}`,
    state.sourceExists ? "success" : "error"
  );

  if (autoRunFirstTable && state.tables.length > 0) {
    await loadTablePreview(state.tables[0].name);
  } else {
    el.queryInfo.textContent = state.tables.length
      ? "Click a table to inspect its rows."
      : "This database does not contain user tables yet.";
    el.resultsEmptyState.classList.remove("hidden");
    el.resultsTableContainer.classList.add("hidden");
    el.resultsTableContainer.innerHTML = "";
  }
}

async function loadTablePreview(tableName) {
  state.selectedTable = tableName;
  renderTables();
  const limit = Number.parseInt(el.limitInput.value, 10) || 250;
  const sql = `SELECT * FROM ${quoteIdentifier(tableName)} LIMIT ${limit};`;
  el.sqlEditor.value = sql;
  state.query = sql;
  persistPreferences();
  await runQuery();
}

async function runQuery() {
  const path = currentPath();
  const sql = el.sqlEditor.value.trim();
  const limit = Number.parseInt(el.limitInput.value, 10) || 250;

  if (!path) {
    throw new Error("Choose a SQLite file before running a query.");
  }
  if (!sql) {
    throw new Error("Query cannot be empty.");
  }

  setStatus("Running SQL...", "loading");
  setConnectionStatus(`Executing SQL against ${path}...`);
  el.queryInfo.textContent = "SQL is running.";

  const data = await api("/query", {
    method: "POST",
    body: JSON.stringify({
      path,
      sql,
      limit,
    }),
  });

  state.result = data;
  renderResultTable(data);
  const isWriteResult = data.operation === "insert" || data.operation === "update";
  const operation = isWriteResult ? String(data.operation).toUpperCase() : "Query";
  setStatus(`${operation} completed`, "success");
  el.queryInfo.textContent = isWriteResult
    ? `Source: ${data.source.name} | ${data.rows_affected ?? 0} row(s) affected | SQL: ${data.sql}`
    : `Source: ${data.source.name} | SQL: ${data.sql}`;
  setConnectionStatus(
    isWriteResult
      ? `Write completed against ${data.source.resolved_path}. Refresh tables to update row counts.`
      : `Last query completed against ${data.source.resolved_path}`,
    "success"
  );
  persistPreferences();
}

function bindEvents() {
  el.loginForm.addEventListener("submit", (event) => {
    loginDashboard(event).catch(showError);
  });

  el.learningTab.addEventListener("click", () => {
    switchView("learning");
    if (!state.learningIntents.length) {
      loadLearningIntents().catch(showError);
    }
    loadLearningQueue().catch(showError);
  });

  el.dumpTab.addEventListener("click", () => {
    switchView("dumps");
    loadMessageDumps().catch(showError);
  });

  el.registrationsTab.addEventListener("click", () => {
    switchView("registrations");
    loadRegistrations().catch(showError);
  });

  el.explorerTab.addEventListener("click", () => {
    switchView("explorer");
  });

  el.logoutButton.addEventListener("click", () => {
    logoutDashboard().catch(showError);
  });

  el.refreshLearningButton.addEventListener("click", () => {
    loadLearningQueue().catch(showError);
  });

  el.refreshDumpButton.addEventListener("click", () => {
    loadMessageDumps().catch(showError);
  });

  el.dumpStatusFilter.addEventListener("change", () => {
    state.selectedDumpId = null;
    loadMessageDumps().catch(showError);
  });

  el.dumpLimitInput.addEventListener("change", () => {
    loadMessageDumps().catch(showError);
  });

  el.dumpList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-dump-id]");
    if (!button) return;
    state.selectedDumpId = Number.parseInt(button.dataset.dumpId, 10);
    renderMessageDumps();
    renderMessageDumpDetail();
  });

  el.markDumpReviewedButton.addEventListener("click", () => {
    reviewSelectedDump("reviewed").catch(showError);
  });

  el.markDumpIgnoredButton.addEventListener("click", () => {
    reviewSelectedDump("ignored").catch(showError);
  });

  el.refreshRegistrationsButton.addEventListener("click", () => {
    loadRegistrations().catch(showError);
  });

  el.registrationStatusFilter.addEventListener("change", () => {
    state.selectedRegistrationId = null;
    loadRegistrations().catch(showError);
  });

  el.registrationLimitInput.addEventListener("change", () => {
    loadRegistrations().catch(showError);
  });

  el.registrationsList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-registration-id]");
    if (!button) return;
    state.selectedRegistrationId = Number.parseInt(button.dataset.registrationId, 10);
    renderRegistrations();
    renderRegistrationDetail();
  });

  el.approveRegistrationButton.addEventListener("click", () => {
    approveSelectedRegistration().catch(showError);
  });

  el.cashPaymentButton.addEventListener("click", () => {
    markSelectedRegistrationPaid("cash").catch(showError);
  });

  el.bankPaymentButton.addEventListener("click", () => {
    markSelectedRegistrationPaid("bank_transfer").catch(showError);
  });

  el.activateRegistrationButton.addEventListener("click", () => {
    activateSelectedRegistration().catch(showError);
  });

  el.billingImportClientSelect.addEventListener("change", renderBillingImportScopes);

  el.billingImportButton.addEventListener("click", () => {
    importBillingWorkbook().catch(showError);
  });

  el.learningStatusFilter.addEventListener("change", () => {
    state.selectedLearningId = null;
    loadLearningQueue().catch(showError);
  });

  el.learningLimitInput.addEventListener("change", () => {
    loadLearningQueue().catch(showError);
  });

  el.learningList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-learning-id]");
    if (!button) return;
    state.selectedLearningId = Number.parseInt(button.dataset.learningId, 10);
    renderLearningList();
    renderLearningDetail();
  });

  el.saveMappingButton.addEventListener("click", () => {
    saveLearningMapping().catch(showError);
  });

  el.suggestMappingButton.addEventListener("click", () => {
    suggestLearningMapping().catch(showError);
  });

  el.previewLearningButton.addEventListener("click", () => {
    previewSelectedLearningItem().catch(showError);
  });

  el.sourceSelect.addEventListener("change", () => {
    applySelectedSourceFromDropdown();
    loadTables({ autoRunFirstTable: true }).catch(showError);
  });

  el.loadButton.addEventListener("click", () => {
    setCurrentSource(el.pathInput.value.trim());
    loadTables({ autoRunFirstTable: true }).catch(showError);
  });

  el.refreshButton.addEventListener("click", () => {
    loadTables({ autoRunFirstTable: false }).catch(showError);
  });

  el.runButton.addEventListener("click", () => {
    runQuery().catch(showError);
  });

  el.resetButton.addEventListener("click", () => {
    el.sqlEditor.value = `SELECT name, type FROM sqlite_master WHERE type IN ("table", "view") AND name NOT LIKE "sqlite_%" ORDER BY name;`;
    persistPreferences();
  });

  el.tableFilter.addEventListener("input", renderTables);

  el.sqlEditor.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      runQuery().catch(showError);
    }
  });

  document.querySelectorAll(".quick-query").forEach((button) => {
    button.addEventListener("click", () => {
      el.sqlEditor.value = button.dataset.query || "";
      persistPreferences();
      runQuery().catch(showError);
    });
  });

  el.tablesList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-table]");
    if (!button) return;
    const tableName = button.dataset.table;
    if (!tableName) return;
    loadTablePreview(tableName).catch(showError);
  });
}

function showError(error) {
  console.error(error);
  setStatus("Error", "error");
  setConnectionStatus(error.message || String(error), "error");
  el.queryInfo.textContent = error.message || String(error);
}

async function bootstrap() {
  restorePreferences();
  bindEvents();
  try {
    const authenticated = await checkAuth();
    if (!authenticated) {
      return;
    }
    switchView("learning");
    await loadLearningIntents();
    await loadLearningQueue();
    await loadSources();
    await loadBillingImportScopes();
    if (currentPath()) {
      el.pathInput.value = currentPath();
      await loadTables({ autoRunFirstTable: true });
    }
  } catch (error) {
    showError(error);
  } finally {
    persistPreferences();
  }
}

bootstrap();
