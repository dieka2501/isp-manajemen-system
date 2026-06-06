const state = {
  sources: [],
  sourcePath: "",
  tables: [],
  selectedTable: "",
  query: `SELECT name, type FROM sqlite_master WHERE type IN ("table", "view") AND name NOT LIKE "sqlite_%" ORDER BY name;`,
  result: null,
  loading: false,
};

const el = {
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
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Request failed with status ${response.status}`);
  }
  return data;
}

function currentPath() {
  return el.pathInput.value.trim();
}

function setCurrentSource(path) {
  el.pathInput.value = path;
  persistPreferences();
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
