const DEFAULT_STATE = {
  current_intent: "ask_installation",
  current_topic: "coverage_check",
  stage: "collecting_information",
  waiting_for: ["address"],
  collected_slots: {},
  last_bot_question: "Boleh informasikan alamatnya?",
  last_user_message: null,
  last_bot_response: null,
  next_action: "ask_address_or_show_packages",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function splitLines(value) {
  return String(value || "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

export class ChatTestLabPage {
  constructor({ root, api, onError }) {
    this.root = root;
    this.api = api;
    this.onError = onError;
    this.context = null;
    this.result = null;
    this.mounted = false;
    this.loadingContext = false;
  }

  mount() {
    if (!this.root || this.mounted) return;
    this.root.innerHTML = `
      <div class="test-lab-safety-bar">
        <div>
          <div class="section-label text-emerald-200/80">Dry-Run Test Lab</div>
          <h2 class="mt-2 text-2xl font-semibold text-white">Inspect the decision, not only the answer.</h2>
          <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-300">
            Run the production intent, memory, knowledge, LLM, and registration-invitation stages inside a read-only sandbox.
          </p>
        </div>
        <div class="sandbox-seal"><span></span>SANDBOX — NO PRODUCTION MUTATION</div>
      </div>

      <div class="grid gap-6 xl:grid-cols-[minmax(360px,0.82fr)_minmax(0,1.5fr)]">
        <form id="testLabForm" class="space-y-5">
          <section class="glass-panel p-5">
            <div class="test-lab-panel-heading"><span>01</span><div><h3>Test context</h3><p>Scope the exact tenant catalog.</p></div></div>
            <div class="mt-5 grid gap-4 sm:grid-cols-2">
              <label class="space-y-2"><span class="section-label">Client</span><select id="testClient" class="control-input" required></select></label>
              <label class="space-y-2"><span class="section-label">WhatsApp device</span><select id="testDevice" class="control-input" required></select></label>
            </div>
            <div id="testLlmRuntime" class="mt-4 info-chip text-xs leading-5 text-slate-300">Loading runtime configuration…</div>
          </section>

          <section class="glass-panel p-5">
            <div class="test-lab-panel-heading"><span>02</span><div><h3>Customer message</h3><p>The exact input sent through the pipeline.</p></div></div>
            <label class="mt-5 block space-y-2">
              <span class="section-label">Message</span>
              <textarea id="testMessage" class="editor-input test-message-input" required>Kak, saya mau daftar</textarea>
            </label>
          </section>

          <section class="glass-panel p-5">
            <div class="test-lab-panel-heading"><span>03</span><div><h3>Conversation state</h3><p>Copied into the sandbox; never written back.</p></div></div>
            <div class="mt-4 flex flex-wrap gap-4 text-sm text-slate-200">
              <label class="test-radio"><input type="radio" name="stateSource" value="fresh" checked /> Fresh conversation</label>
              <label class="test-radio"><input type="radio" name="stateSource" value="custom" /> Custom state</label>
            </div>
            <label id="customStateWrap" class="mt-4 hidden space-y-2">
              <span class="section-label">State JSON</span>
              <textarea id="testStateJson" class="editor-input test-json-input" spellcheck="false">${escapeHtml(pretty(DEFAULT_STATE))}</textarea>
            </label>
          </section>

          <section class="glass-panel p-5">
            <div class="test-lab-panel-heading"><span>04</span><div><h3>Business state</h3><p>Simulate registration lifecycle facts.</p></div></div>
            <div class="mt-5 grid gap-4 sm:grid-cols-2">
              <label class="space-y-2">
                <span class="section-label">Registration status</span>
                <select id="testRegistrationStatus" class="control-input">
                  <option value="none">None</option><option value="draft">Draft</option><option value="registered" selected>Registered</option>
                  <option value="approved">Approved</option><option value="paid">Paid</option><option value="active">Active</option><option value="cancelled">Cancelled</option>
                </select>
              </label>
              <label class="space-y-2"><span class="section-label">Incoming message count</span><input id="testMessageCount" class="control-input" type="number" min="0" value="2" /></label>
              <label class="test-check sm:col-span-2"><input id="testInvitationExists" type="checkbox" checked /> Existing registration invitation already exists</label>
            </div>
          </section>

          <section class="glass-panel p-5">
            <div class="test-lab-panel-heading"><span>05</span><div><h3>Learn mapping overlay</h3><p>Candidate data exists only for this execution.</p></div></div>
            <label class="mt-5 block space-y-2">
              <span class="section-label">Mapping mode</span>
              <select id="testMappingMode" class="control-input">
                <option value="published">Published catalog</option>
                <option value="candidate">Published + candidate</option>
                <option value="compare" selected>Compare before vs after</option>
              </select>
            </label>
            <div id="candidateFields" class="mt-4 grid gap-4 sm:grid-cols-2">
              <label class="space-y-2"><span class="section-label">Intent</span><select id="testCandidateIntent" class="control-input"></select></label>
              <label class="space-y-2"><span class="section-label">Mapping type</span><select id="testMappingType" class="control-input"><option value="both">Sample + keyword</option><option value="sample">Sample</option><option value="keyword">Keyword</option><option value="ignore">Ignore</option></select></label>
              <label class="space-y-2 sm:col-span-2"><span class="section-label">Sample utterance</span><input id="testSample" class="control-input" value="Kak, saya mau daftar" /></label>
              <label class="space-y-2"><span class="section-label">Keyword</span><input id="testKeyword" class="control-input" value="mau daftar" /></label>
              <label class="space-y-2"><span class="section-label">Weight</span><input id="testWeight" class="control-input" type="number" min="1" max="10" value="8" /></label>
            </div>
          </section>

          <section class="glass-panel p-5">
            <div class="test-lab-panel-heading"><span>06</span><div><h3>Pipeline configuration</h3><p>Native is always evaluated; optional stages can be isolated.</p></div></div>
            <div class="mt-5 grid gap-3 text-sm text-slate-200">
              <label class="test-check"><input id="testKnowledgeEnabled" type="checkbox" checked /> Knowledge retrieval enabled</label>
              <label class="test-check"><input id="testLlmEnabled" type="checkbox" checked /> LLM response enabled</label>
              <label class="test-check"><input id="testInvitationEnabled" type="checkbox" checked /> Registration invitation simulation enabled</label>
            </div>
          </section>

          <section class="glass-panel p-5">
            <div class="test-lab-panel-heading"><span>07</span><div><h3>Expected result</h3><p>Optional assertions turn investigation into a repeatable check.</p></div></div>
            <div class="mt-5 grid gap-4 sm:grid-cols-2">
              <label class="space-y-2"><span class="section-label">Expected intent</span><select id="testExpectedIntent" class="control-input"><option value="">Not configured</option></select></label>
              <label class="space-y-2"><span class="section-label">Expected action</span><input id="testExpectedAction" class="control-input" placeholder="show_payment_instruction" /></label>
              <label class="space-y-2"><span class="section-label">Forbidden slots</span><input id="testForbiddenSlots" class="control-input" value="address" placeholder="address, area" /></label>
              <label class="space-y-2"><span class="section-label">Minimum confidence</span><input id="testMinimumConfidence" class="control-input" type="number" min="0" max="1" step="0.01" value="0.60" /></label>
              <label class="space-y-2 sm:col-span-2"><span class="section-label">Required response content (one per line)</span><textarea id="testRequiredContent" class="editor-input test-rule-input">pendaftaran</textarea></label>
              <label class="space-y-2 sm:col-span-2"><span class="section-label">Forbidden response content (one per line)</span><textarea id="testForbiddenContent" class="editor-input test-rule-input">informasikan alamat\nkecamatan atau kelurahan</textarea></label>
            </div>
          </section>

          <div class="glass-panel sticky bottom-4 z-10 p-4">
            <div class="flex flex-wrap gap-3">
              <button id="runTestButton" class="action-button action-primary flex-1" type="submit">Run Dry-Run</button>
              <button id="runCompareButton" class="action-button action-secondary" type="button">Compare Before / After</button>
              <button id="runNativeButton" class="action-button action-secondary" type="button">Native Only</button>
              <button id="resetTestButton" class="action-button action-secondary" type="button">Reset</button>
            </div>
            <div id="testRunStatus" class="mt-3 text-xs text-slate-400">Ready. No production data will be changed.</div>
          </div>
        </form>

        <section class="min-w-0 space-y-5">
          <div id="testLabEmpty" class="glass-panel test-lab-empty">
            <div class="test-lab-orbit"><span></span><span></span><span></span></div>
            <div class="section-label">Awaiting execution</div>
            <h3 class="mt-3 text-xl font-semibold text-white">The trace will explain why the bot answered that way.</h3>
            <p class="mt-2 max-w-xl text-sm leading-6 text-slate-400">Intent ranking, slot inference, knowledge, native reply, LLM context, planned state, side effects, and validation appear here.</p>
          </div>
          <div id="testLabResult" class="hidden space-y-5"></div>
        </section>
      </div>
    `;
    this.mounted = true;
    this.bindEvents();
  }

  q(selector) {
    return this.root.querySelector(selector);
  }

  async ensureLoaded() {
    this.mount();
    if (!this.context && !this.loadingContext) await this.loadContext();
  }

  async loadContext(clientId = null, deviceId = null) {
    this.loadingContext = true;
    try {
      const params = new URLSearchParams();
      if (clientId) params.set("client_id", clientId);
      if (deviceId) params.set("device_id", deviceId);
      const suffix = params.size ? `?${params}` : "";
      const data = await this.api(`/dry-run/context${suffix}`);
      this.context = data.item || {};
      this.renderContext(clientId, deviceId);
    } finally {
      this.loadingContext = false;
    }
  }

  renderContext(preferredClientId = null, preferredDeviceId = null) {
    const clients = this.context?.clients || [];
    const clientSelect = this.q("#testClient");
    const selectedClientId = Number(preferredClientId || this.context?.selected?.client_id || clients[0]?.id || 0);
    clientSelect.innerHTML = clients.length
      ? clients.map((item) => `<option value="${item.id}" ${item.id === selectedClientId ? "selected" : ""}>${escapeHtml(item.name)} · ${escapeHtml(item.account_name || item.account_slug || "Provider")}</option>`).join("")
      : '<option value="">No Client available</option>';
    this.renderDevices(preferredDeviceId || this.context?.selected?.device_id);
    this.renderIntents();
    const llm = this.context?.llm || {};
    this.q("#testLlmRuntime").innerHTML = `
      <div class="flex flex-wrap items-center justify-between gap-2">
        <span><strong class="text-white">${escapeHtml(llm.model || "Unknown model")}</strong> · ${escapeHtml(llm.prompt_version || "prompt unknown")}</span>
        <span class="${llm.configured ? "text-emerald-300" : "text-amber-300"}">${llm.configured ? "OpenAI configured" : "Native fallback — API key unavailable"}</span>
      </div>`;
  }

  renderDevices(preferredDeviceId = null) {
    const clientId = Number(this.q("#testClient").value || 0);
    const client = (this.context?.clients || []).find((item) => item.id === clientId);
    const devices = client?.devices || [];
    const selectedDeviceId = Number(preferredDeviceId || devices[0]?.id || 0);
    this.q("#testDevice").innerHTML = devices.length
      ? devices.map((item) => `<option value="${item.id}" ${item.id === selectedDeviceId ? "selected" : ""}>${escapeHtml(item.name || item.identifier)}</option>`).join("")
      : '<option value="">No device available</option>';
  }

  renderIntents() {
    const intents = this.context?.intents || [];
    const options = intents.map((item) => `<option value="${escapeHtml(item.intent_code)}">${escapeHtml(item.intent_code)} — ${escapeHtml(item.intent_name)}</option>`).join("");
    this.q("#testCandidateIntent").innerHTML = options || '<option value="">No intent catalog</option>';
    this.q("#testExpectedIntent").innerHTML = `<option value="">Not configured</option>${options}`;
    const preferred = intents.find((item) => item.intent_code === "ask_installation")?.intent_code;
    if (preferred) {
      this.q("#testCandidateIntent").value = preferred;
      this.q("#testExpectedIntent").value = preferred;
    }
  }

  bindEvents() {
    this.q("#testLabForm").addEventListener("submit", (event) => {
      event.preventDefault();
      this.run().catch(this.onError);
    });
    this.q("#runCompareButton").addEventListener("click", () => {
      this.q("#testMappingMode").value = "compare";
      this.syncVisibility();
      this.run({ mappingMode: "compare" }).catch(this.onError);
    });
    this.q("#runNativeButton").addEventListener("click", () => {
      this.run({ execution: "native_only" }).catch(this.onError);
    });
    this.q("#resetTestButton").addEventListener("click", () => this.reset());
    this.q("#testClient").addEventListener("change", async () => {
      this.renderDevices();
      const clientId = Number(this.q("#testClient").value || 0);
      const deviceId = Number(this.q("#testDevice").value || 0);
      try {
        await this.loadContext(clientId, deviceId);
      } catch (error) {
        this.onError(error);
      }
    });
    this.q("#testDevice").addEventListener("change", async () => {
      try {
        await this.loadContext(Number(this.q("#testClient").value), Number(this.q("#testDevice").value));
      } catch (error) {
        this.onError(error);
      }
    });
    this.root.querySelectorAll('input[name="stateSource"]').forEach((input) => input.addEventListener("change", () => this.syncVisibility()));
    this.q("#testMappingMode").addEventListener("change", () => this.syncVisibility());
    this.root.addEventListener("click", (event) => {
      const copy = event.target.closest("[data-test-copy]");
      if (!copy) return;
      this.copyResult(copy.dataset.testCopy).catch(this.onError);
    });
    this.syncVisibility();
  }

  syncVisibility() {
    const stateSource = this.root.querySelector('input[name="stateSource"]:checked')?.value || "fresh";
    this.q("#customStateWrap").classList.toggle("hidden", stateSource !== "custom");
    this.q("#candidateFields").classList.toggle("hidden", this.q("#testMappingMode").value === "published");
  }

  buildPayload(overrides = {}) {
    const stateSource = this.root.querySelector('input[name="stateSource"]:checked')?.value || "fresh";
    let initialState = {};
    if (stateSource === "custom") {
      try {
        initialState = JSON.parse(this.q("#testStateJson").value);
      } catch (error) {
        throw new Error(`Custom state JSON is invalid: ${error.message}`);
      }
    }
    const mappingMode = overrides.mappingMode || this.q("#testMappingMode").value;
    const mappingType = this.q("#testMappingType").value;
    const minimumConfidence = this.q("#testMinimumConfidence").value.trim();
    return {
      client_id: Number(this.q("#testClient").value),
      device_id: Number(this.q("#testDevice").value),
      message: this.q("#testMessage").value.trim(),
      state_source: stateSource,
      initial_state: initialState,
      business_state: {
        registration_status: this.q("#testRegistrationStatus").value,
        incoming_message_count: Number(this.q("#testMessageCount").value || 0),
        invitation_already_exists: this.q("#testInvitationExists").checked,
      },
      mapping_mode: mappingMode,
      candidate_mapping: mappingMode === "published" ? null : {
        intent_code: this.q("#testCandidateIntent").value,
        mapping_type: mappingType,
        sample_utterance: ["sample", "both"].includes(mappingType) ? this.q("#testSample").value.trim() : null,
        keyword: ["keyword", "both"].includes(mappingType) ? this.q("#testKeyword").value.trim() : null,
        normalized_keyword: null,
        weight: Number(this.q("#testWeight").value || 4),
        notes: "Dry-Run Test Lab candidate — never published",
      },
      pipeline: {
        execution: overrides.execution || "full_pipeline",
        knowledge_retrieval_enabled: this.q("#testKnowledgeEnabled").checked,
        llm_enabled: this.q("#testLlmEnabled").checked,
        registration_invitation_enabled: this.q("#testInvitationEnabled").checked,
      },
      expected: {
        expected_intent: this.q("#testExpectedIntent").value || null,
        minimum_confidence: minimumConfidence ? Number(minimumConfidence) : null,
        forbidden_slots: this.q("#testForbiddenSlots").value.split(",").map((item) => item.trim()).filter(Boolean),
        expected_action: this.q("#testExpectedAction").value.trim() || null,
        required_response_content: splitLines(this.q("#testRequiredContent").value),
        forbidden_response_content: splitLines(this.q("#testForbiddenContent").value),
      },
    };
  }

  async run(overrides = {}) {
    const payload = this.buildPayload(overrides);
    if (!payload.client_id || !payload.device_id) throw new Error("Select a Client and WhatsApp device first.");
    if (!payload.message) throw new Error("Customer message is required.");
    const buttons = this.root.querySelectorAll("#runTestButton, #runCompareButton, #runNativeButton");
    buttons.forEach((button) => { button.disabled = true; });
    this.q("#testRunStatus").textContent = "Running sandbox pipeline… database writes and Fonnte are blocked.";
    try {
      const data = await this.api("/dry-run/execute", { method: "POST", body: JSON.stringify(payload) });
      this.result = data.item;
      this.renderResult();
      this.q("#testRunStatus").textContent = `Completed ${this.result.report.test_id}. Production mutation: NO.`;
    } finally {
      buttons.forEach((button) => { button.disabled = false; });
    }
  }

  renderResult() {
    const report = this.result?.report;
    if (!report) return;
    this.q("#testLabEmpty").classList.add("hidden");
    const target = this.q("#testLabResult");
    target.classList.remove("hidden");
    const variants = Object.entries(report.variants || {});
    const primary = report.variants.after || report.variants.single || variants[0]?.[1];
    const executive = primary?.executive_result || { result: "failed", groups: {} };
    const resultClass = executive.result === "passed" ? "test-result-pass" : "test-result-fail";
    target.innerHTML = `
      <section class="glass-panel overflow-hidden">
        <div class="test-executive ${resultClass}">
          <div>
            <div class="section-label">Executive result</div>
            <h3 class="mt-2 text-3xl font-semibold text-white">${executive.result.toUpperCase()}</h3>
            <p class="mt-2 text-sm text-slate-300">${escapeHtml(report.test_id)} · ${escapeHtml(report.mode)}</p>
          </div>
          <div class="test-score-grid">${Object.entries(executive.groups).map(([name, status]) => `<div><span>${escapeHtml(name.replaceAll("_", " "))}</span><strong class="test-status-${status}">${escapeHtml(status.replaceAll("_", " "))}</strong></div>`).join("")}</div>
        </div>
        <div class="flex flex-wrap gap-3 border-t border-white/10 p-4">
          <button class="action-button action-primary" type="button" data-test-copy="summary">Copy Audit Summary</button>
          <button class="action-button action-secondary" type="button" data-test-copy="json">Copy Sanitized JSON</button>
          <span class="ml-auto self-center text-xs text-emerald-300">Writes blocked · Fonnte blocked</span>
        </div>
      </section>

      ${report.conclusion ? this.renderConclusion(report.conclusion) : ""}

      <div class="grid gap-5 ${variants.length > 1 ? "2xl:grid-cols-2" : ""}">
        ${variants.map(([name, variant]) => this.renderVariant(name, variant)).join("")}
      </div>

      ${report.diff ? this.renderDiff(report.diff) : ""}

      <details class="glass-panel overflow-hidden">
        <summary class="test-details-summary">Full sanitized technical trace</summary>
        <pre class="custom-scroll max-h-[720px] overflow-auto border-t border-white/10 p-5 text-xs leading-6 text-slate-300">${escapeHtml(pretty(this.result.sanitized_report))}</pre>
      </details>
    `;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  renderConclusion(conclusion) {
    return `<section class="glass-panel p-5">
      <div class="section-label">Automated conclusion</div>
      <p class="mt-3 text-base leading-7 text-white">${escapeHtml(conclusion.recognition_summary)}</p>
      <div class="mt-4 grid gap-3 sm:grid-cols-3">
        <div class="info-chip"><div class="section-label">Business fixed</div><div class="mt-2 font-semibold ${conclusion.business_behavior_fixed ? "text-emerald-300" : "text-rose-300"}">${conclusion.business_behavior_fixed ? "YES" : "NO"}</div></div>
        <div class="info-chip"><div class="section-label">Safe to publish</div><div class="mt-2 font-semibold ${conclusion.safe_to_publish_as_complete_fix ? "text-emerald-300" : "text-amber-300"}">${conclusion.safe_to_publish_as_complete_fix ? "YES" : "NOT AS COMPLETE FIX"}</div></div>
        <div class="info-chip"><div class="section-label">Suspected layer</div><div class="mt-2 text-sm text-slate-200">${escapeHtml((conclusion.suspected_layer || []).join(", ") || "None")}</div></div>
      </div>
    </section>`;
  }

  renderVariant(name, variant) {
    const intent = variant.native_analysis?.intent || {};
    const validation = variant.validation || [];
    const prompt = variant.llm_input_summary?.sanitized_prompt;
    return `<article class="glass-panel min-w-0 overflow-hidden">
      <header class="border-b border-white/10 p-5">
        <div class="flex items-start justify-between gap-3">
          <div><div class="section-label">${escapeHtml(name)} run</div><h3 class="mt-2 text-xl font-semibold text-white">${escapeHtml(intent.intent_code || "unknown")}</h3></div>
          <div class="text-right"><div class="text-2xl font-semibold text-cyan-200">${Math.round(Number(intent.confidence || 0) * 100)}%</div><div class="text-xs text-slate-500">confidence</div></div>
        </div>
        <div class="mt-4 flex flex-wrap gap-2">${(intent.matched_keywords || []).map((item) => `<span class="test-token">${escapeHtml(item)}</span>`).join("") || '<span class="test-token">No catalog match</span>'}</div>
      </header>
      <div class="space-y-5 p-5">
        <div class="grid gap-3 sm:grid-cols-2">
          <div class="info-chip"><div class="section-label">Slot inference</div><div class="mt-2 text-sm text-slate-200">${variant.slot_processing?.message_accepted_as_waiting_slot ? "Accepted as waiting slot" : "Not accepted as waiting slot"}</div><p class="mt-2 text-xs leading-5 text-slate-500">${escapeHtml(variant.slot_processing?.inference_reason)}</p></div>
          <div class="info-chip"><div class="section-label">Planned action</div><div class="mt-2 text-sm text-slate-200">${escapeHtml(variant.planned_action || "None")}</div><p class="mt-2 text-xs text-slate-500">Source: ${escapeHtml(variant.slot_processing?.classification_source || "none")}</p></div>
        </div>
        <div><div class="section-label">Native response</div><div class="test-response-box mt-2">${escapeHtml(variant.native_response)}</div></div>
        <div><div class="section-label">LLM final response</div><div class="test-response-box test-response-final mt-2">${escapeHtml(variant.final_response)}</div></div>
        <div>
          <div class="section-label">Validation</div>
          <div class="mt-2 divide-y divide-white/5 rounded-2xl border border-white/10 bg-black/10">${validation.map((check) => `<div class="flex items-start justify-between gap-3 px-4 py-3 text-sm"><span class="text-slate-300">${escapeHtml(check.label)}</span><strong class="test-status-${check.status}">${check.status.toUpperCase()}</strong></div>`).join("")}</div>
        </div>
        ${prompt ? `<details class="rounded-2xl border border-white/10 bg-white/[0.02]"><summary class="test-details-summary">Show sanitized prompt</summary><pre class="custom-scroll max-h-80 overflow-auto border-t border-white/10 p-4 text-xs leading-5 text-slate-300">${escapeHtml(prompt)}</pre></details>` : ""}
        <details class="rounded-2xl border border-white/10 bg-white/[0.02]"><summary class="test-details-summary">Pipeline trace</summary><pre class="custom-scroll max-h-[520px] overflow-auto border-t border-white/10 p-4 text-xs leading-5 text-slate-300">${escapeHtml(pretty({ state_before: variant.state_before, native_analysis: variant.native_analysis, slot_processing: variant.slot_processing, business_state: variant.business_state, knowledge: variant.knowledge, llm_input_summary: { ...variant.llm_input_summary, sanitized_prompt: prompt ? "Available above" : null }, planned_state_after: variant.planned_state_after, planned_side_effects: variant.planned_side_effects }))}</pre></details>
      </div>
    </article>`;
  }

  renderDiff(diff) {
    return `<section class="glass-panel overflow-hidden">
      <div class="border-b border-white/10 p-5"><div class="section-label">Before vs after diff</div><h3 class="mt-2 text-xl font-semibold text-white">What the Learn Mapping actually changed</h3></div>
      <div class="custom-scroll overflow-auto"><table class="test-diff-table"><thead><tr><th>Component</th><th>Before</th><th>After</th><th>Evaluation</th></tr></thead><tbody>${diff.map((row) => `<tr><td>${escapeHtml(row.component)}</td><td>${escapeHtml(typeof row.before === "string" ? row.before : pretty(row.before))}</td><td>${escapeHtml(typeof row.after === "string" ? row.after : pretty(row.after))}</td><td><span class="test-token">${escapeHtml(row.evaluation)}</span></td></tr>`).join("")}</tbody></table></div>
    </section>`;
  }

  async copyResult(kind) {
    if (!this.result) return;
    const value = kind === "summary" ? this.result.audit_summary : pretty(this.result.sanitized_report);
    await this.writeClipboard(value);
    this.q("#testRunStatus").textContent = kind === "summary" ? "Sanitized audit summary copied." : "Sanitized technical JSON copied.";
  }

  async writeClipboard(value) {
    let clipboardError = null;
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(value);
        return;
      } catch (error) {
        clipboardError = error;
      }
    }
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    if (!copied) {
      throw clipboardError || new Error("Browser did not allow copying to the clipboard.");
    }
  }

  reset() {
    this.q("#testLabForm").reset();
    this.q("#testMessage").value = "Kak, saya mau daftar";
    this.q("#testStateJson").value = pretty(DEFAULT_STATE);
    this.q("#testMappingMode").value = "compare";
    this.q("#testRegistrationStatus").value = "registered";
    this.q("#testInvitationExists").checked = true;
    this.result = null;
    this.q("#testLabResult").classList.add("hidden");
    this.q("#testLabResult").innerHTML = "";
    this.q("#testLabEmpty").classList.remove("hidden");
    this.q("#testRunStatus").textContent = "Reset complete. No production data will be changed.";
    this.renderIntents();
    this.syncVisibility();
  }
}
