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
};

const el = {
  authGate: document.getElementById("authGate"),
  dashboardShell: document.getElementById("dashboardShell"),
  learningTab: document.getElementById("learningTab"),
  explorerTab: document.getElementById("explorerTab"),
  learningView: document.getElementById("learningView"),
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
  previewLearningButton: document.getElementById("previewLearningButton"),
  mappingStatus: document.getElementById("mappingStatus"),
  learningCandidates: document.getElementById("learningCandidates"),
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
  el.explorerView.classList.toggle("hidden", view !== "explorer");
  el.learningTab.classList.toggle("is-active", view === "learning");
  el.explorerTab.classList.toggle("is-active", view === "explorer");
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
    state.selectedLearningId = null;
    el.learningList.innerHTML = "";
    el.learningCount.textContent = "No queue loaded.";
    renderLearningDetail();
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

  el.resultsEmptyState.classList.toggle("hidden", columns.length > 0);
  el.resultsTableContainer.classList.toggle("hidden", columns.length === 0);

  if (!columns.length) {
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
  el.resultMeta.textContent = `${result.row_count} row(s) ${result.truncated ? "(truncated)" : ""}`;
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

  setStatus("Running query...", "loading");
  setConnectionStatus(`Executing read-only SQL against ${path}...`);
  el.queryInfo.textContent = "Query is running.";

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
  setStatus("Query completed", "success");
  el.queryInfo.textContent = `Source: ${data.source.name} | SQL: ${data.sql}`;
  setConnectionStatus(`Last query completed against ${data.source.resolved_path}`, "success");
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

  el.explorerTab.addEventListener("click", () => {
    switchView("explorer");
  });

  el.logoutButton.addEventListener("click", () => {
    logoutDashboard().catch(showError);
  });

  el.refreshLearningButton.addEventListener("click", () => {
    loadLearningQueue().catch(showError);
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
