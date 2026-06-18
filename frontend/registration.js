const token = decodeURIComponent(window.location.pathname.split("/").filter(Boolean).pop() || "");

const el = {
  form: document.getElementById("registrationForm"),
  summary: document.getElementById("registrationSummary"),
  nameInput: document.getElementById("nameInput"),
  phoneInput: document.getElementById("phoneInput"),
  emailInput: document.getElementById("emailInput"),
  addressInput: document.getElementById("addressInput"),
  mapsInput: document.getElementById("mapsInput"),
  submitButton: document.getElementById("submitButton"),
  paymentLink: document.getElementById("paymentLink"),
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

function setStatus(message, kind = "idle") {
  el.statusBox.className = `status ${kind === "success" ? "success" : kind === "error" ? "error" : ""}`;
  el.statusBox.textContent = message;
}

async function api(path, options = {}) {
  const response = await fetch(`/api/v1/registrations${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Request gagal (${response.status})`);
  }
  return data;
}

function renderSummary(item) {
  el.summary.classList.remove("hidden");
  el.summary.innerHTML = `
    <div class="summary-row"><span>Status</span><strong>${escapeHtml(item.status)}</strong></div>
    <div class="summary-row"><span>Client</span><strong>${escapeHtml(item.client_name || "-")}</strong></div>
    <div class="summary-row"><span>ID Pelanggan</span><strong>${escapeHtml(item.customer_code || "-")}</strong></div>
  `;
  if (item.payment_url) {
    el.paymentLink.href = item.payment_url;
    el.paymentLink.classList.remove("hidden");
  }
}

function fillForm(item) {
  el.nameInput.value = item.name || item.default_name || "";
  el.phoneInput.value = item.phone || item.default_phone || item.sender_number || "";
  el.emailInput.value = item.email || "";
  el.addressInput.value = item.address || "";
  el.mapsInput.value = item.maps_link || "";
  renderSummary(item);

  const locked = !["draft", "registered"].includes(String(item.status || ""));
  el.submitButton.disabled = locked;
  [...el.form.elements].forEach((field) => {
    if (field !== el.submitButton) {
      field.disabled = locked;
    }
  });
  setStatus(
    locked
      ? "Data sudah masuk tahap verifikasi/pembayaran dan tidak bisa diedit dari form ini."
      : "Periksa data, lalu kirim pendaftaran.",
    locked ? "success" : "idle"
  );
}

async function loadRegistration() {
  if (!token) {
    throw new Error("Token pendaftaran tidak ditemukan.");
  }
  const data = await api(`/public/${encodeURIComponent(token)}`);
  fillForm(data.item || {});
}

async function submitRegistration(event) {
  event.preventDefault();
  el.submitButton.disabled = true;
  setStatus("Mengirim data pendaftaran...");
  try {
    const payload = {
      name: el.nameInput.value.trim(),
      phone: el.phoneInput.value.trim(),
      email: el.emailInput.value.trim() || null,
      address: el.addressInput.value.trim(),
      maps_link: el.mapsInput.value.trim() || null,
    };
    const data = await api(`/public/${encodeURIComponent(token)}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    fillForm(data.item || {});
    setStatus("Pendaftaran terkirim. Verifikasi membutuhkan waktu maksimal 1x24 jam.", "success");
  } catch (error) {
    el.submitButton.disabled = false;
    setStatus(error.message || String(error), "error");
  }
}

el.form.addEventListener("submit", submitRegistration);

loadRegistration().catch((error) => {
  setStatus(error.message || String(error), "error");
});
