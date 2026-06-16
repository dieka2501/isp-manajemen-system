const STORAGE_KEYS = {
  token: "clientDashboard.token",
  expiresAt: "clientDashboard.expiresAt",
};

const state = {
  token: localStorage.getItem(STORAGE_KEYS.token) || "",
  expiresAt: Number(localStorage.getItem(STORAGE_KEYS.expiresAt) || 0),
  client: null,
  currentView: "overview",
  summary: null,
  customers: [],
  packages: [],
  billing: [],
  learningItems: [],
  learningIntents: [],
  selectedLearningId: null,
};

const el = {
  loginView: document.getElementById("loginView"),
  appShell: document.getElementById("appShell"),
  loginForm: document.getElementById("loginForm"),
  loginIdentifier: document.getElementById("loginIdentifier"),
  loginPassword: document.getElementById("loginPassword"),
  loginButton: document.getElementById("loginButton"),
  loginMessage: document.getElementById("loginMessage"),
  logoutButton: document.getElementById("logoutButton"),
  refreshButton: document.getElementById("refreshButton"),
  connectionStatus: document.getElementById("connectionStatus"),
  sidebarClientName: document.getElementById("sidebarClientName"),
  profileLine: document.getElementById("profileLine"),
  viewTitle: document.getElementById("viewTitle"),
  summaryGrid: document.getElementById("summaryGrid"),
  recentBilling: document.getElementById("recentBilling"),
  customerSearch: document.getElementById("customerSearch"),
  customerStatusFilter: document.getElementById("customerStatusFilter"),
  customerCount: document.getElementById("customerCount"),
  customersTable: document.getElementById("customersTable"),
  packageCount: document.getElementById("packageCount"),
  packagesTable: document.getElementById("packagesTable"),
  billingStatusFilter: document.getElementById("billingStatusFilter"),
  billingCount: document.getElementById("billingCount"),
  billingTable: document.getElementById("billingTable"),
  learningStatusFilter: document.getElementById("learningStatusFilter"),
  learningList: document.getElementById("learningList"),
  learningTitle: document.getElementById("learningTitle"),
  learningBadge: document.getElementById("learningBadge"),
  learningMessage: document.getElementById("learningMessage"),
  learningMeta: document.getElementById("learningMeta"),
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

const viewTitles = {
  overview: "Ringkasan",
  customers: "Customer",
  packages: "Paket",
  billing: "Billing",
  learning: "Learn Process",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatCurrency(value) {
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function setStatus(message, type = "idle") {
  el.connectionStatus.textContent = message;
  el.connectionStatus.className = `status status-${type}`;
}

function showLogin(message = "") {
  el.loginView.classList.remove("hidden");
  el.appShell.classList.add("hidden");
  if (message) {
    el.loginMessage.textContent = message;
  }
}

function showApp() {
  el.loginView.classList.add("hidden");
  el.appShell.classList.remove("hidden");
}

function persistToken(token, expiresAt) {
  state.token = token;
  state.expiresAt = Number(expiresAt || 0);
  localStorage.setItem(STORAGE_KEYS.token, state.token);
  localStorage.setItem(STORAGE_KEYS.expiresAt, String(state.expiresAt));
}

function clearToken() {
  state.token = "";
  state.expiresAt = 0;
  state.client = null;
  localStorage.removeItem(STORAGE_KEYS.token);
  localStorage.removeItem(STORAGE_KEYS.expiresAt);
}

async function dashboardApi(path, options = {}) {
  const response = await fetch(`/api/v1/client-dashboard${path}`, {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${state.token}`,
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      clearToken();
      showLogin("Sesi habis. Silakan login lagi.");
    }
    throw new Error(data.detail || `Request gagal (${response.status})`);
  }
  return data;
}

function renderProfile() {
  const client = state.client || {};
  el.sidebarClientName.textContent = client.name || "Client";
  el.profileLine.textContent = [
    client.email,
    client.pic_name ? `PIC ${client.pic_name}` : "",
    client.office_address,
  ]
    .filter(Boolean)
    .join(" | ");
}

function switchView(view) {
  state.currentView = view;
  document.querySelectorAll(".view").forEach((node) => {
    node.classList.toggle("hidden", node.id !== `${view}View`);
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === view);
  });
  el.viewTitle.textContent = viewTitles[view] || "Dashboard";
}

function metric(label, value, detail = "") {
  return `
    <div class="metric-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <p class="mt-2 text-sm text-slate-500">${escapeHtml(detail)}</p>
    </div>
  `;
}

function renderSummary() {
  const item = state.summary || {};
  el.summaryGrid.innerHTML = [
    metric("Customer aktif", item.active_customers || 0, `${item.total_customers || 0} total customer`),
    metric("Paket aktif", item.total_packages || 0, "Dari katalog paket client"),
    metric("Billing lunas", item.paid_count || 0, `${item.total_billing || 0} total billing`),
    metric("Tunggakan", formatCurrency(item.arrears_amount || 0), `${item.unpaid_count || 0} belum selesai`),
  ].join("");
  renderRecentBilling(item.recent_billing || []);
}

function renderRecentBilling(rows) {
  renderTable(el.recentBilling, [
    ["Customer", (row) => row.customer_name],
    ["Paket", (row) => row.package_name || "-"],
    ["Periode", (row) => row.billing_period || "-"],
    ["Tagihan", (row) => formatCurrency(row.amount)],
    ["Status", (row) => html(statusBadge(row.status))],
  ], rows);
}

function statusBadge(status) {
  const labelMap = {
    paid: "Lunas",
    unpaid: "Belum bayar",
    partial: "Sebagian",
    free: "Free",
    void: "Void",
    active: "Aktif",
    inactive: "Nonaktif",
    suspended: "Suspend",
    pending: "Pending",
    mapped: "Mapped",
    ignored: "Ignored",
  };
  const safeStatus = String(status || "idle").toLowerCase();
  return `<span class="badge badge-${escapeHtml(safeStatus)}">${escapeHtml(labelMap[safeStatus] || safeStatus)}</span>`;
}

function html(value) {
  return { __html: value };
}

function renderTable(container, columns, rows) {
  if (!rows.length) {
    container.innerHTML = `<div class="empty-state">Belum ada data.</div>`;
    return;
  }
  const head = columns.map(([label]) => `<th>${escapeHtml(label)}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map(([, render]) => {
          const value = render(row);
          return `<td>${value && typeof value === "object" && "__html" in value ? value.__html : escapeHtml(value)}</td>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  container.innerHTML = `<table class="data-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderCustomers() {
  el.customerCount.textContent = `${state.customers.length} data`;
  renderTable(el.customersTable, [
    ["Kode", (row) => row.customer_code || "-"],
    ["Nama", (row) => row.name],
    ["No HP", (row) => row.phone || "-"],
    ["Paket", (row) => row.package_name || "-"],
    ["PPPoE", (row) => row.pppoe_username || "-"],
    ["Alamat", (row) => row.address || "-"],
    ["Status", (row) => html(statusBadge(row.status))],
    ["Tunggakan", (row) => formatCurrency(row.total_arrears)],
  ], state.customers);
}

function renderPackages() {
  el.packageCount.textContent = `${state.packages.length} paket`;
  renderTable(el.packagesTable, [
    ["Kode", (row) => row.package_code],
    ["Nama paket", (row) => row.package_name],
    ["Speed", (row) => `${row.speed_mbps || 0} Mbps`],
    ["Harga", (row) => formatCurrency(row.monthly_price)],
    ["Device", (row) => row.device_name || row.device_identifier || "-"],
    ["Customer", (row) => row.customer_count || 0],
    ["Status", (row) => row.is_active ? "Aktif" : "Nonaktif"],
  ], state.packages);
}

function renderBilling() {
  el.billingCount.textContent = `${state.billing.length} data`;
  renderTable(el.billingTable, [
    ["Invoice", (row) => row.invoice_number],
    ["Customer", (row) => row.customer_name],
    ["Paket", (row) => row.package_name || "-"],
    ["Periode", (row) => row.billing_period || "-"],
    ["Tagihan", (row) => formatCurrency(row.amount)],
    ["Bayar", (row) => formatCurrency(row.paid_amount)],
    ["Tunggakan", (row) => formatCurrency(row.arrears_amount)],
    ["Status", (row) => html(statusBadge(row.status))],
    ["Tanggal", (row) => formatDate(row.payment_date)],
    ["Rekening", (row) => row.payment_account || "-"],
  ], state.billing);
}

function selectedLearningItem() {
  return state.learningItems.find((item) => item.id === state.selectedLearningId) || null;
}

function renderLearningIntents() {
  el.mappingIntentSelect.innerHTML = state.learningIntents.length
    ? state.learningIntents
        .map((intent) => `<option value="${escapeHtml(intent.intent_code)}">${escapeHtml(intent.intent_code)} - ${escapeHtml(intent.intent_name)}</option>`)
        .join("")
    : `<option value="">Belum ada intent</option>`;
}

function renderLearningList() {
  el.learningList.innerHTML = state.learningItems.length
    ? state.learningItems
        .map((item) => {
          const selected = item.id === state.selectedLearningId;
          return `
            <button class="learning-item ${selected ? "is-selected" : ""}" type="button" data-learning-id="${item.id}">
              <span class="text-sm font-semibold text-slate-950">${escapeHtml(item.message_text)}</span>
              <span class="text-xs text-slate-500">${escapeHtml(item.sender_name || item.sender_number || "Unknown")} | ${escapeHtml(item.created_at)}</span>
              <span>${statusBadge(item.status)}</span>
            </button>
          `;
        })
        .join("")
    : `<div class="empty-state">Queue kosong.</div>`;
}

function renderLearningDetail() {
  const item = selectedLearningItem();
  if (!item) {
    el.learningTitle.textContent = "Pilih pertanyaan";
    el.learningBadge.textContent = "Waiting";
    el.learningBadge.className = "status status-idle";
    el.learningMessage.textContent = "Belum ada pertanyaan dipilih.";
    el.learningMeta.innerHTML = "";
    el.mappingKeywordInput.value = "";
    el.mappingNormalizedInput.value = "";
    el.mappingNotesInput.value = "";
    el.mappingStatus.textContent = "Pilih pertanyaan dari queue.";
    el.learningCandidates.textContent = "Belum ada data.";
    return;
  }

  el.learningTitle.textContent = `Question #${item.id}`;
  el.learningBadge.textContent = item.status;
  el.learningBadge.className =
    "status " + (item.status === "pending" ? "status-loading" : item.status === "mapped" ? "status-success" : "status-idle");
  el.learningMessage.textContent = item.message_text;
  el.learningMeta.innerHTML = [
    ["Device", item.device_identifier || "-"],
    ["Detected", `${item.detected_intent_code || "unknown"} (${Math.round(Number(item.confidence || 0) * 100)}%)`],
    ["Reason", item.reason || "-"],
  ]
    .map(([label, value]) => `<div class="rounded-lg border border-slate-200 p-3"><p class="text-xs font-bold uppercase tracking-wide text-slate-500">${escapeHtml(label)}</p><p class="mt-1 text-sm text-slate-800">${escapeHtml(value)}</p></div>`)
    .join("");
  el.mappingKeywordInput.value = item.normalized_text || item.message_text || "";
  el.mappingNormalizedInput.value = item.normalized_text || "";
  el.mappingNotesInput.value = `Mapped dari question #${item.id}`;
  if (item.mapped_intent_code) {
    el.mappingIntentSelect.value = item.mapped_intent_code;
  }
  renderLearningCandidates(item);
  el.mappingStatus.textContent = "Pilih intent lalu simpan.";
}

function renderLearningCandidates(item) {
  const candidates = item.candidates || [];
  const entities = item.entities || [];
  const candidateRows = candidates.length
    ? candidates
        .map((candidate) => {
          const matched = (candidate.matched_keywords || []).join(", ") || "-";
          return `<tr><td>${escapeHtml(candidate.intent_code)}</td><td>${Math.round(Number(candidate.confidence || 0) * 100)}%</td><td>${escapeHtml(matched)}</td></tr>`;
        })
        .join("")
    : `<tr><td colspan="3">Tidak ada kandidat native.</td></tr>`;
  const entityHtml = entities.length
    ? `<div class="mt-4 flex flex-wrap gap-2">${entities
        .map((entity) => `<span class="badge status-idle">${escapeHtml(entity.entity_code)}: ${escapeHtml(entity.value)}</span>`)
        .join("")}</div>`
    : "";
  el.learningCandidates.innerHTML = `
    <table class="data-table min-w-full">
      <thead><tr><th>Intent</th><th>Confidence</th><th>Keyword</th></tr></thead>
      <tbody>${candidateRows}</tbody>
    </table>
    ${entityHtml}
  `;
}

async function login(event) {
  event.preventDefault();
  const identifier = el.loginIdentifier.value.trim();
  const password = el.loginPassword.value;
  if (!identifier || !password) {
    el.loginMessage.textContent = "Email/token dan password wajib diisi.";
    return;
  }

  el.loginButton.disabled = true;
  el.loginMessage.textContent = "Masuk...";
  try {
    const response = await fetch("/api/v1/client-dashboard/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier, password }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "Login gagal.");
    }
    persistToken(data.access_token, data.expires_at);
    state.client = data.client;
    el.loginPassword.value = "";
    await loadDashboard();
  } catch (error) {
    el.loginMessage.textContent = error.message || String(error);
  } finally {
    el.loginButton.disabled = false;
  }
}

async function loadDashboard() {
  if (!state.token || (state.expiresAt && state.expiresAt * 1000 < Date.now())) {
    clearToken();
    showLogin("Silakan login untuk membuka dashboard.");
    return;
  }

  showApp();
  setStatus("Memuat data...", "loading");
  const me = await dashboardApi("/auth/me");
  state.client = me.client;
  renderProfile();
  await Promise.all([
    loadSummary(),
    loadCustomers(),
    loadPackages(),
    loadBilling(),
    loadLearningIntents(),
    loadLearningQueue(),
  ]);
  switchView(state.currentView);
  setStatus("Data terbaru", "success");
}

async function loadSummary() {
  const data = await dashboardApi("/summary");
  state.summary = data.item || {};
  renderSummary();
}

async function loadCustomers() {
  const params = new URLSearchParams({
    status: el.customerStatusFilter.value || "all",
    limit: "500",
  });
  if (el.customerSearch.value.trim()) {
    params.set("query", el.customerSearch.value.trim());
  }
  const data = await dashboardApi(`/customers?${params.toString()}`);
  state.customers = data.items || [];
  renderCustomers();
}

async function loadPackages() {
  const data = await dashboardApi("/packages");
  state.packages = data.items || [];
  renderPackages();
}

async function loadBilling() {
  const params = new URLSearchParams({
    status: el.billingStatusFilter.value || "all",
    limit: "500",
  });
  const data = await dashboardApi(`/billing?${params.toString()}`);
  state.billing = data.items || [];
  renderBilling();
}

async function loadLearningIntents() {
  const data = await dashboardApi("/learning/intents");
  state.learningIntents = data.items || [];
  renderLearningIntents();
}

async function loadLearningQueue() {
  const params = new URLSearchParams({
    status: el.learningStatusFilter.value || "pending",
    limit: "100",
  });
  const data = await dashboardApi(`/learning/unprocessed?${params.toString()}`);
  state.learningItems = data.items || [];
  if (!state.learningItems.some((item) => item.id === state.selectedLearningId)) {
    state.selectedLearningId = state.learningItems[0]?.id || null;
  }
  renderLearningList();
  renderLearningDetail();
}

async function saveMapping() {
  const item = selectedLearningItem();
  if (!item) {
    el.mappingStatus.textContent = "Pilih pertanyaan dulu.";
    return;
  }
  const mappingType = el.mappingTypeSelect.value;
  const payload = {
    mapping_type: mappingType,
    intent_code: mappingType === "ignore" ? null : el.mappingIntentSelect.value,
    keyword: el.mappingKeywordInput.value.trim() || null,
    normalized_keyword: el.mappingNormalizedInput.value.trim() || null,
    weight: Number.parseInt(el.mappingWeightInput.value, 10) || 4,
    notes: el.mappingNotesInput.value.trim() || null,
  };
  el.saveMappingButton.disabled = true;
  el.mappingStatus.textContent = "Menyimpan...";
  try {
    const data = await dashboardApi(`/learning/unprocessed/${item.id}/map`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const updated = data.item;
    state.learningItems = state.learningItems.map((current) => (current.id === updated.id ? updated : current));
    renderLearningList();
    renderLearningDetail();
    el.mappingStatus.textContent = "Mapping tersimpan.";
  } finally {
    el.saveMappingButton.disabled = false;
  }
}

async function previewLearning() {
  const item = selectedLearningItem();
  if (!item) {
    el.mappingStatus.textContent = "Pilih pertanyaan dulu.";
    return;
  }
  el.mappingStatus.textContent = "Memuat preview...";
  const data = await dashboardApi("/agent/preview", {
    method: "POST",
    body: JSON.stringify({ message: item.message_text, device_id: item.device_id }),
  });
  el.learningCandidates.innerHTML = `<pre class="mono whitespace-pre-wrap">${escapeHtml(JSON.stringify(data.item || {}, null, 2))}</pre>`;
  el.mappingStatus.textContent = "Preview selesai.";
}

function bindEvents() {
  el.loginForm.addEventListener("submit", (event) => {
    login(event).catch(showFatalError);
  });

  el.logoutButton.addEventListener("click", () => {
    clearToken();
    showLogin("Anda sudah keluar.");
  });

  el.refreshButton.addEventListener("click", () => {
    loadDashboard().catch(showFatalError);
  });

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      switchView(button.dataset.view || "overview");
    });
  });

  let customerTimer = null;
  el.customerSearch.addEventListener("input", () => {
    window.clearTimeout(customerTimer);
    customerTimer = window.setTimeout(() => {
      loadCustomers().catch(showFatalError);
    }, 250);
  });
  el.customerStatusFilter.addEventListener("change", () => {
    loadCustomers().catch(showFatalError);
  });
  el.billingStatusFilter.addEventListener("change", () => {
    loadBilling().catch(showFatalError);
  });
  el.learningStatusFilter.addEventListener("change", () => {
    state.selectedLearningId = null;
    loadLearningQueue().catch(showFatalError);
  });
  el.learningList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-learning-id]");
    if (!button) return;
    state.selectedLearningId = Number.parseInt(button.dataset.learningId, 10);
    renderLearningList();
    renderLearningDetail();
  });
  el.saveMappingButton.addEventListener("click", () => {
    saveMapping().catch(showFatalError);
  });
  el.previewLearningButton.addEventListener("click", () => {
    previewLearning().catch(showFatalError);
  });
}

function showFatalError(error) {
  console.error(error);
  setStatus(error.message || String(error), "error");
}

async function bootstrap() {
  bindEvents();
  if (!state.token) {
    showLogin("Silakan login untuk membuka dashboard.");
    return;
  }
  try {
    await loadDashboard();
  } catch (error) {
    showFatalError(error);
  }
}

bootstrap();
