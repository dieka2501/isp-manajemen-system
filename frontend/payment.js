const token = decodeURIComponent(window.location.pathname.split("/").filter(Boolean).pop() || "");

const el = {
  form: document.getElementById("proofForm"),
  summary: document.getElementById("paymentSummary"),
  amountInput: document.getElementById("amountInput"),
  referenceInput: document.getElementById("referenceInput"),
  proofInput: document.getElementById("proofInput"),
  notesInput: document.getElementById("notesInput"),
  uploadButton: document.getElementById("uploadButton"),
  registrationLink: document.getElementById("registrationLink"),
  statusBox: document.getElementById("statusBox"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function rupiah(value) {
  const amount = Number.parseInt(value || 0, 10) || 0;
  return `Rp ${amount.toLocaleString("id-ID")}`;
}

function setStatus(message, kind = "idle") {
  el.statusBox.className = `status ${kind === "success" ? "success" : kind === "error" ? "error" : ""}`;
  el.statusBox.textContent = message;
}

async function api(path, options = {}) {
  const response = await fetch(`/api/v1/registrations${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Request gagal (${response.status})`);
  }
  return data;
}

function latestPayment(item) {
  const payments = item.payments || [];
  return payments[0] || null;
}

function renderPayment(item) {
  const payment = latestPayment(item);
  const amount = payment?.amount || 0;
  el.amountInput.value = amount;
  el.summary.innerHTML = `
    <div class="summary-row"><span>Status</span><strong>${escapeHtml(item.status)}</strong></div>
    <div class="summary-row"><span>ID Pelanggan</span><strong>${escapeHtml(item.customer_code || "-")}</strong></div>
    <div class="summary-row"><span>Nama</span><strong>${escapeHtml(item.name || "-")}</strong></div>
    <div class="summary-row"><span>Virtual Account</span><strong>${escapeHtml(item.virtual_account || "-")}</strong></div>
    <div class="summary-row"><span>Nominal</span><strong>${escapeHtml(rupiah(amount))}</strong></div>
    <div class="summary-row"><span>Bukti Terakhir</span><strong>${escapeHtml(payment?.status || "-")}</strong></div>
  `;
  if (item.registration_url) {
    el.registrationLink.href = item.registration_url;
    el.registrationLink.classList.remove("hidden");
  }

  const canUpload = ["registered", "approved"].includes(String(item.status || ""));
  el.uploadButton.disabled = !canUpload;
  [...el.form.elements].forEach((field) => {
    if (field !== el.uploadButton) {
      field.disabled = !canUpload;
    }
  });
  setStatus(
    canUpload
      ? "Bukti transfer bank bisa diupload dari form ini."
      : "Upload bukti tidak tersedia untuk status pembayaran saat ini.",
    canUpload ? "idle" : "success"
  );
}

async function loadPayment() {
  if (!token) {
    throw new Error("Token pembayaran tidak ditemukan.");
  }
  const data = await api(`/public/${encodeURIComponent(token)}/payment`);
  renderPayment(data.item || {});
}

async function uploadProof(event) {
  event.preventDefault();
  const file = el.proofInput.files?.[0];
  if (!file) {
    setStatus("Pilih file bukti pembayaran dulu.", "error");
    return;
  }
  el.uploadButton.disabled = true;
  setStatus("Mengunggah bukti pembayaran...");
  const formData = new FormData();
  formData.append("proof_file", file);
  formData.append("amount", el.amountInput.value || "0");
  formData.append("reference_number", el.referenceInput.value.trim());
  formData.append("notes", el.notesInput.value.trim());
  try {
    await api(`/public/${encodeURIComponent(token)}/payment-proof`, {
      method: "POST",
      body: formData,
    });
    setStatus("Bukti pembayaran terkirim dan menunggu verifikasi admin.", "success");
    el.form.reset();
    await loadPayment();
  } catch (error) {
    el.uploadButton.disabled = false;
    setStatus(error.message || String(error), "error");
  }
}

el.form.addEventListener("submit", uploadProof);

loadPayment().catch((error) => {
  setStatus(error.message || String(error), "error");
});
