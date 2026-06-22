import { ClientDashboardLayout } from "/client-dashboard-assets/client-dashboard/layouts/client-dashboard-layout.js";
import { clientNavigation } from "/client-dashboard-assets/client-dashboard/navigation/client-navigation.js";
import { clientPermissions } from "/client-dashboard-assets/client-dashboard/permissions/client-permissions.js";
import { clientRoutes, clientViewFromPath } from "/client-dashboard-assets/client-dashboard/routes/client-routes.js";

new ClientDashboardLayout({
  navigation: clientNavigation,
  permissions: clientPermissions,
  routes: clientRoutes,
}).mountNavigation(document.getElementById("clientNavigation"));

const STORAGE_KEYS = {
  expiresAt: "clientDashboard.expiresAt",
};

const SESSION_EXPIRED_MESSAGE = "Sesi habis setelah 2 jam. Silakan login lagi.";

const state = {
  expiresAt: Number(localStorage.getItem(STORAGE_KEYS.expiresAt) || 0),
  client: null,
  currentView: "overview",
  summary: null,
  customers: [],
  packages: [],
  billing: [],
  registrations: [],
  selectedRegistrationId: null,
  learningItems: [],
  learningIntents: [],
  selectedLearningId: null,
  sessionTimerId: null,
  runtime: null,
};

const el = {
  loginView: document.getElementById("loginView"),
  appShell: document.getElementById("appShell"),
  loginForm: document.getElementById("loginForm"),
  loginIdentifier: document.getElementById("loginIdentifier"),
  loginPassword: document.getElementById("loginPassword"),
  loginButton: document.getElementById("loginButton"),
  loginMessage: document.getElementById("loginMessage"),
  loginRuntimeVersion: document.getElementById("loginRuntimeVersion"),
  logoutButton: document.getElementById("logoutButton"),
  runtimeVersion: document.getElementById("runtimeVersion"),
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
  registrations: "Approval Registrasi",
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

function runtimeLabel(runtime) {
  if (!runtime) {
    return "Version unknown";
  }
  const version = runtime.version || "dev";
  const commit = runtime.build_commit_short || "";
  const branch = runtime.build_branch || "";
  const suffix = [commit, branch].filter(Boolean).join(" / ");
  return suffix ? `Version ${version} (${suffix})` : `Version ${version}`;
}

function renderRuntimeVersion() {
  const label = runtimeLabel(state.runtime);
  if (el.runtimeVersion) {
    el.runtimeVersion.textContent = label;
    el.runtimeVersion.title = JSON.stringify(state.runtime || {}, null, 2);
  }
  if (el.loginRuntimeVersion) {
    el.loginRuntimeVersion.textContent = label;
    el.loginRuntimeVersion.title = JSON.stringify(state.runtime || {}, null, 2);
  }
}

async function loadRuntimeVersion() {
  try {
    const response = await fetch("/health", { credentials: "same-origin" });
    state.runtime = await response.json();
  } catch (error) {
    state.runtime = null;
  }
  renderRuntimeVersion();
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

function persistSession(expiresAt) {
  state.expiresAt = Number(expiresAt || 0);
  localStorage.setItem(STORAGE_KEYS.expiresAt, String(state.expiresAt));
  localStorage.removeItem("clientDashboard.token");
  scheduleSessionExpiry();
}

function clearSessionState() {
  state.expiresAt = 0;
  state.client = null;
  if (state.sessionTimerId !== null) {
    window.clearTimeout(state.sessionTimerId);
    state.sessionTimerId = null;
  }
  localStorage.removeItem("clientDashboard.token");
  localStorage.removeItem(STORAGE_KEYS.expiresAt);
}

function resetDashboardState() {
  state.summary = null;
  state.customers = [];
  state.packages = [];
  state.billing = [];
  state.registrations = [];
  state.selectedRegistrationId = null;
  state.learningItems = [];
  state.learningIntents = [];
  state.selectedLearningId = null;
  el.summaryGrid.innerHTML = "";
  el.recentBilling.innerHTML = "";
  el.customersTable.innerHTML = "";
  el.packagesTable.innerHTML = "";
  el.billingTable.innerHTML = "";
  el.registrationsList.innerHTML = "";
  el.registrationsCount.textContent = "0 data";
  renderRegistrationDetail();
  el.learningList.innerHTML = "";
  el.mappingIntentSelect.innerHTML = "";
  renderLearningDetail();
}

function clearSession(message = "") {
  clearSessionState();
  resetDashboardState();
  showLogin(message);
}

function isSessionExpired() {
  return Boolean(state.expiresAt && state.expiresAt * 1000 <= Date.now());
}

function scheduleSessionExpiry() {
  if (state.sessionTimerId !== null) {
    window.clearTimeout(state.sessionTimerId);
    state.sessionTimerId = null;
  }
  if (!state.expiresAt) return;
  const delay = state.expiresAt * 1000 - Date.now();
  if (delay <= 0) {
    clearSession(SESSION_EXPIRED_MESSAGE);
    return;
  }
  state.sessionTimerId = window.setTimeout(() => {
    clearSession(SESSION_EXPIRED_MESSAGE);
  }, delay);
}

async function dashboardApi(path, options = {}) {
  if (isSessionExpired()) {
    clearSession(SESSION_EXPIRED_MESSAGE);
    throw new Error(SESSION_EXPIRED_MESSAGE);
  }
  const response = await fetch(`/api/v1/client${path}`, {
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
      clearSession(SESSION_EXPIRED_MESSAGE);
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

function switchView(view, { updateUrl = true } = {}) {
  state.currentView = view;
  document.querySelectorAll(".view").forEach((node) => {
    node.classList.toggle("hidden", node.id !== `${view}View`);
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === view);
  });
  el.viewTitle.textContent = viewTitles[view] || "Dashboard";
  if (updateUrl && window.location.pathname.startsWith("/client-dashboard")) {
    window.history.replaceState({}, "", clientRoutes[view] || clientRoutes.overview);
  }
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
    draft: "Draft",
    registered: "Registered",
    approved: "Approved",
    rejected: "Ditolak",
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

function selectedRegistration() {
  return state.registrations.find((item) => item.id === state.selectedRegistrationId) || null;
}

function setRegistrationActions(item) {
  el.approveRegistrationButton.disabled = !item || item.status !== "registered";
  el.cashPaymentButton.disabled = !item || item.status !== "approved";
  el.bankPaymentButton.disabled = !item || item.status !== "approved";
  el.activateRegistrationButton.disabled = !item || item.status !== "paid";
}

function renderRegistrations() {
  el.registrationsCount.textContent = `${state.registrations.length} data`;
  el.registrationsList.innerHTML = state.registrations.length
    ? state.registrations
        .map((item) => {
          const selected = item.id === state.selectedRegistrationId;
          return `
            <button class="registration-item ${selected ? "is-selected" : ""}" type="button" data-registration-id="${item.id}">
              <span class="registration-item-heading">
                <strong>${escapeHtml(item.name || item.default_name || item.sender_name || item.sender_number || "Tanpa nama")}</strong>
                ${statusBadge(item.status)}
              </span>
              <span>${escapeHtml(item.phone || item.default_phone || item.sender_number || "-")}</span>
              <small>${escapeHtml(item.customer_code || "Belum ada ID")} · ${escapeHtml(item.updated_at || "-")}</small>
            </button>
          `;
        })
        .join("")
    : `<div class="empty-state">Belum ada registrasi untuk filter ini.</div>`;
}

function renderRegistrationDetail() {
  const item = selectedRegistration();
  setRegistrationActions(item);
  if (!item) {
    el.registrationDetailTitle.textContent = "Pilih registrasi";
    el.registrationMeta.textContent = "Approval hanya berlaku untuk customer milik client ini.";
    el.registrationStatusBadge.textContent = "Menunggu";
    el.registrationStatusBadge.className = "status status-idle";
    el.registrationSummaryBox.textContent = "Belum ada registrasi dipilih.";
    el.registrationActionStatus.textContent = "Pilih registrasi untuk memulai.";
    el.approveAmountInput.value = 0;
    el.approveVirtualAccountInput.value = "";
    return;
  }

  const latestPayment = (item.payments || [])[0] || {};
  el.registrationDetailTitle.textContent = `Registrasi #${item.id}`;
  el.registrationMeta.textContent = `${item.device_identifier || "Device tidak diketahui"} · ${item.updated_at || "-"}`;
  el.registrationStatusBadge.textContent = item.status || "unknown";
  el.registrationStatusBadge.className =
    "status " + (item.status === "active" ? "status-success" : item.status === "registered" ? "status-loading" : "status-idle");
  el.registrationSummaryBox.innerHTML = `
    <div class="registration-summary-grid">
      <div><span>ID Customer</span><strong>${escapeHtml(item.customer_code || "-")}</strong></div>
      <div><span>Nama</span><strong>${escapeHtml(item.name || item.default_name || "-")}</strong></div>
      <div><span>WhatsApp</span><strong>${escapeHtml(item.phone || item.default_phone || item.sender_number || "-")}</strong></div>
      <div><span>Email</span><strong>${escapeHtml(item.email || "-")}</strong></div>
      <div class="registration-summary-wide"><span>Alamat</span><strong>${escapeHtml(item.address || "-")}</strong></div>
      <div class="registration-summary-wide"><span>Maps</span><strong>${escapeHtml(item.maps_link || "-")}</strong></div>
      <div><span>Virtual Account</span><strong>${escapeHtml(item.virtual_account || "-")}</strong></div>
      <div><span>Pembayaran Terakhir</span><strong>${escapeHtml(latestPayment.status || "-")} ${latestPayment.amount ? `· ${escapeHtml(formatCurrency(latestPayment.amount))}` : ""}</strong></div>
      <div class="registration-summary-wide"><span>URL Pembayaran</span><strong>${escapeHtml(item.payment_url || "-")}</strong></div>
    </div>
  `;
  el.approveVirtualAccountInput.value = item.virtual_account || "";
  el.approveAmountInput.value = latestPayment.amount || 0;
  if (item.payment_method) {
    el.approvePaymentMethodSelect.value = item.payment_method;
  }
  el.registrationActionStatus.textContent = "Pilih proses yang sesuai dengan status registrasi.";
}

async function loadRegistrations() {
  const params = new URLSearchParams({
    status: el.registrationStatusFilter.value || "registered",
    limit: String(Number.parseInt(el.registrationLimitInput.value, 10) || 100),
  });
  el.registrationActionStatus.textContent = "Memuat registrasi...";
  const data = await dashboardApi(`/registrations/items?${params.toString()}`);
  state.registrations = data.items || [];
  if (!state.registrations.some((item) => item.id === state.selectedRegistrationId)) {
    state.selectedRegistrationId = state.registrations[0]?.id || null;
  }
  renderRegistrations();
  renderRegistrationDetail();
}

function updateRegistrationInState(updated) {
  const exists = state.registrations.some((item) => item.id === updated.id);
  state.registrations = exists
    ? state.registrations.map((item) => (item.id === updated.id ? updated : item))
    : [updated, ...state.registrations];
  state.selectedRegistrationId = updated.id;
  renderRegistrations();
  renderRegistrationDetail();
}

async function approveSelectedRegistration() {
  const item = selectedRegistration();
  if (!item) return;
  el.registrationActionStatus.textContent = "Memproses approval...";
  const data = await dashboardApi(`/registrations/${item.id}/approve`, {
    method: "POST",
    body: JSON.stringify({
      amount: Number.parseInt(el.approveAmountInput.value, 10) || 0,
      payment_method: el.approvePaymentMethodSelect.value,
      virtual_account: el.approveVirtualAccountInput.value.trim() || null,
    }),
  });
  updateRegistrationInState(data.item);
  el.registrationActionStatus.textContent = "Registrasi berhasil di-approve dan notifikasi customer diproses.";
}

async function markSelectedRegistrationPaid(paymentMethod) {
  const item = selectedRegistration();
  if (!item) return;
  el.registrationActionStatus.textContent = "Mencatat pembayaran...";
  const data = await dashboardApi(`/registrations/${item.id}/payment`, {
    method: "POST",
    body: JSON.stringify({
      payment_method: paymentMethod,
      amount: Number.parseInt(el.approveAmountInput.value, 10) || 0,
      virtual_account: el.approveVirtualAccountInput.value.trim() || item.virtual_account || null,
    }),
  });
  updateRegistrationInState(data.item);
  el.registrationActionStatus.textContent = "Pembayaran tersimpan dan notifikasi teknisi diproses.";
}

async function activateSelectedRegistration() {
  const item = selectedRegistration();
  if (!item) return;
  el.registrationActionStatus.textContent = "Mengaktifkan customer...";
  const data = await dashboardApi(`/registrations/${item.id}/activate`, {
    method: "POST",
    body: JSON.stringify({ notes: "Pemasangan diselesaikan dari Client Dashboard." }),
  });
  updateRegistrationInState(data.item);
  el.registrationActionStatus.textContent = "Customer aktif dan notifikasi selesai diproses.";
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
    const response = await fetch("/api/v1/client/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier, password }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "Login gagal.");
    }
    persistSession(data.expires_at);
    state.client = data.client;
    el.loginPassword.value = "";
    window.location.replace("/client-dashboard");
  } catch (error) {
    el.loginMessage.textContent = error.message || String(error);
  } finally {
    el.loginButton.disabled = false;
  }
}

async function loadDashboard() {
  if (isSessionExpired()) {
    clearSession(SESSION_EXPIRED_MESSAGE);
    return;
  }

  showApp();
  scheduleSessionExpiry();
  setStatus("Memuat data...", "loading");
  const me = await dashboardApi("/auth/me");
  state.client = me.client;
  renderProfile();
  await Promise.all([
    loadSummary(),
    loadCustomers(),
    loadPackages(),
    loadBilling(),
    loadRegistrations(),
    loadLearningIntents(),
    loadLearningQueue(),
  ]);
  switchView(state.currentView, { updateUrl: true });
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
    dashboardApi("/auth/logout", { method: "POST" })
      .catch(() => {})
      .finally(() => {
        clearSessionState();
        window.location.replace("/login/client");
      });
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
  el.refreshRegistrationsButton.addEventListener("click", () => {
    loadRegistrations().catch(showFatalError);
  });
  el.registrationStatusFilter.addEventListener("change", () => {
    state.selectedRegistrationId = null;
    loadRegistrations().catch(showFatalError);
  });
  el.registrationLimitInput.addEventListener("change", () => {
    loadRegistrations().catch(showFatalError);
  });
  el.registrationsList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-registration-id]");
    if (!button) return;
    state.selectedRegistrationId = Number.parseInt(button.dataset.registrationId, 10);
    renderRegistrations();
    renderRegistrationDetail();
  });
  el.approveRegistrationButton.addEventListener("click", () => {
    approveSelectedRegistration().catch(showFatalError);
  });
  el.cashPaymentButton.addEventListener("click", () => {
    markSelectedRegistrationPaid("cash").catch(showFatalError);
  });
  el.bankPaymentButton.addEventListener("click", () => {
    markSelectedRegistrationPaid("bank_transfer").catch(showFatalError);
  });
  el.activateRegistrationButton.addEventListener("click", () => {
    activateSelectedRegistration().catch(showFatalError);
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
  await loadRuntimeVersion();
  state.currentView = clientViewFromPath(window.location.pathname);
  if (window.location.pathname === "/login/client") {
    try {
      await dashboardApi("/auth/me");
      window.location.replace("/client-dashboard");
      return;
    } catch (error) {
      showLogin("Silakan login untuk membuka dashboard.");
      return;
    }
  }
  try {
    await loadDashboard();
  } catch (error) {
    showFatalError(error);
  }
}

bootstrap();
