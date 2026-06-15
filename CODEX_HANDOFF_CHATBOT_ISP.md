# CODEX HANDOFF — Implementasi Chatbot ISP Berbasis Intent, Knowledge Retrieval, Conversation State, dan LLM Response Generation

## 1. Ringkasan Tujuan

Proyek ini adalah chatbot WhatsApp untuk ISP. Sistem sudah memiliki fondasi awal berupa:

- Dataset intent.
- Dataset utterance/training phrase.
- Dataset keyword/normalized keyword dengan weight.
- Knowledge base paket internet, coverage, pembayaran, dan jadwal pemasangan.
- Integrasi WhatsApp gateway.

Masalah utama saat ini: chatbot masih cenderung menjawab dengan pola template/retrieval langsung dari database. Bot belum benar-benar menghasilkan jawaban natural berdasarkan konteks percakapan dan knowledge yang relevan.

Target implementasi berikutnya adalah mengubah alur dari:

```text
User message
→ intent detection
→ template response
→ send WhatsApp message
```

menjadi:

```text
User message
→ get conversation state
→ intent detection
→ entity extraction
→ merge/update conversation state
→ knowledge retrieval
→ prompt builder
→ LLM response generation
→ save conversation state
→ send WhatsApp message
```

Fokus utama bukan melatih LLM dari nol. Fokus utama adalah membangun orchestration layer yang rapi agar LLM bisa menjawab berdasarkan data bisnis yang sudah ada.

---

## 2. Masalah yang Harus Diperbaiki

### 2.1 Bot Masih Template-Based

Saat intent ditemukan, bot mengambil jawaban yang sudah disimpan lalu mengirim ulang kalimat tersebut.

Contoh saat ini:

```text
User:
Paketnya ada apa aja ya?

Bot:
Bisa Kak. Sementara paket yang tersedia:
1. Paket Hemat 20 Mbps...
2. Paket Keluarga 30 Mbps...
```

Masalahnya bukan jawaban salah, tetapi jawaban masih kaku, selalu mirip, dan tidak adaptif.

Expected behavior:

```text
User:
Paketnya ada apa aja ya?

Bot:
Saat ini ada beberapa pilihan paket Kak, mulai dari 20 Mbps sampai 100 Mbps. Paket 20 Mbps mulai Rp150.000/bulan, 30 Mbps Rp200.000/bulan, 50 Mbps Rp300.000/bulan, dan 100 Mbps Rp500.000/bulan.
```

Jawaban boleh bervariasi, tetapi fakta harus tetap berdasarkan DB.

---

### 2.2 Bot Tidak Memahami Follow-Up

Contoh masalah dari testing:

```text
User:
Bisa transfer?

Bot:
Pembayaran bisa kami bantu arahkan sesuai kebijakan client: transfer bank, QRIS, cash, e-wallet, atau virtual account bila tersedia.

User:
Kalau QRIS bisa?

Bot:
Pembayaran bisa kami bantu arahkan sesuai kebijakan client: transfer bank, QRIS, cash, e-wallet, atau virtual account bila tersedia.
```

Bot mengulang jawaban panjang yang sama.

Expected behavior:

```text
User:
Kalau QRIS bisa?

Bot:
Bisa Kak, QRIS juga tersedia untuk pembayaran.
```

Agar ini bisa dilakukan, sistem harus membaca conversation state dan mengetahui bahwa customer sedang membahas payment.

---

### 2.3 Bot Belum Menyimpan State Percakapan dengan Baik

Contoh masalah:

```text
User:
Saya ada di daerah kota Bandung, kira-kira ada paket yang cover daerah saya tidak ya?

Bot:
Siap Kak, saya bantu cek coverage. Untuk awal, sebutkan area/kecamatan dulu juga cukup; alamat lengkap bisa nanti kalau mau dilanjutkan.

User:
Conblong

Bot:
Siap Kak, alamat Conblong saya catat. Ada detail lain yang ingin Kakak tambahkan?
```

Masalah: user sedang menjawab pertanyaan coverage, bukan ingin menambahkan alamat order.

Expected behavior:

```text
User:
Conblong

Bot:
Untuk area Conblong sudah tercover Kak. Paket yang tersedia mulai dari 20 Mbps sampai 100 Mbps.
```

Sistem harus menyimpan:

```json
{
  "current_topic": "coverage_check",
  "last_intent": "ask_coverage",
  "city": "Bandung",
  "district": "Conblong"
}
```

---

## 3. Konsep Teknis yang Harus Diimplementasikan

### 3.1 Conversation State

Conversation state adalah catatan kondisi percakapan per customer/nomor WhatsApp.

Conversation state menjawab pertanyaan:

```text
Customer ini sedang membahas apa?
Data apa yang sudah diberikan customer?
Langkah berikutnya apa?
Apakah message sekarang adalah follow-up dari message sebelumnya?
```

Contoh state:

```json
{
  "phone_number": "628123456789",
  "current_topic": "coverage_check",
  "last_intent": "ask_coverage",
  "last_user_message": "Saya ada di daerah kota Bandung, kira-kira ada paket yang cover daerah saya tidak ya?",
  "last_bot_response": "Boleh sebutkan area/kecamatan dulu Kak.",
  "city": "Bandung",
  "district": null,
  "selected_package": null,
  "payment_method": null,
  "installation_schedule": null,
  "updated_at": "2026-06-13T10:30:00+07:00"
}
```

Recommended storage for early phase:

```sql
CREATE TABLE IF NOT EXISTS conversation_states (
    phone_number TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    updated_at DATETIME NOT NULL
);
```

Reason: JSON is flexible for fast iteration.

Optional normalized version for later:

```sql
CREATE TABLE IF NOT EXISTS conversation_states (
    phone_number TEXT PRIMARY KEY,
    current_topic TEXT,
    last_intent TEXT,
    city TEXT,
    district TEXT,
    selected_package TEXT,
    payment_method TEXT,
    installation_schedule TEXT,
    last_user_message TEXT,
    last_bot_response TEXT,
    updated_at DATETIME NOT NULL
);
```

Minimum required functions:

```ts
getConversationState(phoneNumber): Promise<ConversationState>
saveConversationState(phoneNumber, state): Promise<void>
mergeState(oldState, nlpResult, userMessage, botResponse?): ConversationState
isStateExpired(state): boolean
```

Suggested state TTL:

```text
2 days
```

If state is older than TTL, reset state but keep conversation logs separately if needed.

---

### 3.2 Knowledge Retrieval

Knowledge retrieval adalah proses mengambil data bisnis yang relevan dari database.

Knowledge retrieval tidak membuat kalimat final. Ia hanya mengambil fakta/data mentah.

Contoh:

```text
User:
Paketnya ada apa aja ya?

Detected intent:
ask_package
```

Retrieval:

```sql
SELECT package_name, speed_mbps, monthly_price, installation_fee, benefit
FROM internet_packages
WHERE is_active = true
ORDER BY speed_mbps ASC;
```

Result:

```json
[
  {
    "package_name": "Paket Hemat",
    "speed_mbps": 20,
    "monthly_price": 150000,
    "installation_fee": 150000,
    "benefit": "unlimited, router dipinjamkan"
  },
  {
    "package_name": "Paket Keluarga",
    "speed_mbps": 30,
    "monthly_price": 200000,
    "installation_fee": 150000,
    "benefit": "cocok untuk 3-5 perangkat"
  }
]
```

LLM akan menyusun jawaban berdasarkan data tersebut.

Recommended knowledge tables:

```sql
CREATE TABLE IF NOT EXISTS internet_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_code TEXT UNIQUE NOT NULL,
    package_name TEXT NOT NULL,
    speed_mbps INTEGER NOT NULL,
    monthly_price INTEGER NOT NULL,
    installation_fee INTEGER NOT NULL,
    benefit TEXT,
    is_active BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS coverage_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_name TEXT NOT NULL,
    city TEXT,
    district TEXT,
    coverage_status TEXT NOT NULL, -- covered, partial, not_covered, unknown
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS area_available_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coverage_area_id INTEGER NOT NULL,
    package_code TEXT NOT NULL,
    FOREIGN KEY (coverage_area_id) REFERENCES coverage_areas(id)
);

CREATE TABLE IF NOT EXISTS payment_methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    method_code TEXT UNIQUE NOT NULL,
    method_name TEXT NOT NULL,
    is_available BOOLEAN NOT NULL DEFAULT 1,
    notes TEXT
);
```

Knowledge retrieval should be intent-aware:

```ts
retrieveKnowledge(intent, entities, state): Promise<KnowledgePayload>
```

Example behavior:

```text
intent = ask_package
→ return active packages

intent = ask_price
→ if package/speed known, return specific package price
→ else return all package prices or ask which package

intent = ask_coverage
→ if area/district known, return coverage status
→ else ask for area/kecamatan/kelurahan

intent = ask_payment_method
→ if specific method mentioned, return specific method availability
→ else return all available payment methods

intent = ask_installation_schedule
→ return scheduling rules or available technician schedule if available
```

---

### 3.3 Prompt Builder

Prompt builder adalah komponen yang menyusun input untuk LLM.

Prompt builder menggabungkan:

1. User message.
2. Intent.
3. Entities.
4. Conversation state.
5. Retrieved knowledge.
6. Response rules.
7. Safety/business constraints.

LLM jangan dipanggil hanya dengan user message mentah.

Bad:

```text
Kalau QRIS bisa?
```

Good:

```text
You are a customer service assistant for an ISP.

Customer message:
"Kalau QRIS bisa?"

Conversation state:
- current_topic: payment
- last_intent: ask_payment_method
- previous bot already explained available payment methods

Detected intent:
ask_payment_method

Entities:
- payment_method: QRIS

Knowledge:
- QRIS is available
- Transfer bank is available
- Cash is available
- E-wallet is available if enabled by client

Response rules:
- Reply in Indonesian.
- Use friendly ISP customer service tone.
- Maximum 2 sentences.
- Since customer asks specifically about QRIS, do not repeat all payment methods.
- Do not invent data outside the knowledge section.
- If data is unknown, ask a clarification question.

Generate the final WhatsApp reply.
```

Expected output:

```text
Bisa Kak, pembayaran lewat QRIS tersedia ya.
```

Minimum required function:

```ts
buildPrompt(params: {
  userMessage: string;
  intent: string;
  entities: Record<string, any>;
  state: ConversationState;
  knowledge: KnowledgePayload;
  responseRules?: ResponseRules;
}): string
```

Recommended response rules:

```json
{
  "language": "id",
  "tone": "friendly, helpful, semi-informal",
  "channel": "whatsapp",
  "max_sentences": 4,
  "avoid_repeating_previous_answer": true,
  "do_not_invent_data": true,
  "ask_clarification_if_missing_required_info": true,
  "use_kak": true
}
```

---

## 4. Suggested Main Handler Flow

Implement a main function similar to this:

```ts
async function handleIncomingMessage(phoneNumber: string, userMessage: string) {
  // 1. Load existing state
  const oldState = await getConversationState(phoneNumber);

  // 2. Reset if expired
  const state = isStateExpired(oldState) ? createEmptyState(phoneNumber) : oldState;

  // 3. Detect intent + extract entities
  const nlpResult = await detectIntentAndEntities(userMessage, state);

  // 4. Merge extracted info into state
  const updatedState = mergeState(state, nlpResult, userMessage);

  // 5. Retrieve relevant knowledge from DB
  const knowledge = await retrieveKnowledge(
    nlpResult.intent,
    nlpResult.entities,
    updatedState
  );

  // 6. Build prompt for LLM
  const prompt = buildPrompt({
    userMessage,
    intent: nlpResult.intent,
    entities: nlpResult.entities,
    state: updatedState,
    knowledge,
    responseRules: getDefaultResponseRules()
  });

  // 7. Generate response
  const botResponse = await callLLM(prompt);

  // 8. Save state with last messages
  const finalState = {
    ...updatedState,
    last_intent: nlpResult.intent,
    last_user_message: userMessage,
    last_bot_response: botResponse,
    updated_at: new Date().toISOString()
  };

  await saveConversationState(phoneNumber, finalState);

  // 9. Send response to WhatsApp gateway
  await sendWhatsAppMessage(phoneNumber, botResponse);

  return botResponse;
}
```

---

## 5. Intent and Entity Design

Current intent examples:

```text
ask_installation
ask_package
ask_price
ask_coverage
ask_installation_schedule
ask_payment_method
choose_package
confirm_order
```

Recommended entities:

```json
{
  "location": "string",
  "city": "string",
  "district": "string",
  "package_name": "string",
  "speed_mbps": "number",
  "payment_method": "string",
  "schedule_date": "string",
  "customer_name": "string",
  "phone_number": "string",
  "address": "string"
}
```

Entity extraction rules:

- If message contains area/kecamatan/kelurahan, store as location/district.
- If previous state is `coverage_check` and user sends a short place name, treat it as location/district.
- If message contains `20 Mbps`, `30 Mbps`, `50 Mbps`, `100 Mbps`, treat as speed/package entity.
- If message contains `transfer`, `QRIS`, `cash`, `e-wallet`, treat as payment_method.
- If message contains `besok`, `hari ini`, date, or time, treat as schedule entity.
- If message is short and ambiguous, use conversation state to infer meaning.

Example:

```text
State:
current_topic = coverage_check

User:
Conblong

Entity:
district = Conblong

Intent should be interpreted as:
ask_coverage / provide_location
```

---

## 6. Follow-Up Handling Rules

### 6.1 Payment Follow-Up

Input:

```text
User:
Bisa transfer?

Bot:
Pembayaran bisa transfer bank, QRIS, cash, atau e-wallet.

User:
Kalau QRIS bisa?
```

Expected:

```text
Bisa Kak, QRIS juga tersedia untuk pembayaran.
```

Do not repeat all payment methods.

---

### 6.2 Coverage Follow-Up

Input:

```text
User:
Saya di Kota Bandung, sudah tercover belum?

Bot:
Boleh sebutkan kecamatan/kelurahan dulu Kak.

User:
Conblong
```

Expected:

```text
Untuk area Conblong sudah tercover Kak. Paket yang tersedia mulai dari 20 Mbps sampai 100 Mbps.
```

Do not answer:

```text
Alamat Conblong saya catat.
```

---

### 6.3 Package Follow-Up

Input:

```text
User:
Paketnya ada apa aja?

Bot:
Menampilkan daftar paket.

User:
Yang 30 Mbps berapa?
```

Expected:

```text
Paket 30 Mbps harganya Rp200.000/bulan Kak, dengan biaya instalasi Rp150.000.
```

The system should retrieve package by speed 30 Mbps.

---

### 6.4 Confirmation Flow

Input:

```text
User:
Saya ambil yang 50 Mbps.
```

Expected:

```text
Siap Kak, saya catat pilihan Paket Premium 50 Mbps. Untuk lanjut pemasangan, boleh kirim nama, alamat lengkap, dan jadwal yang diinginkan?
```

State:

```json
{
  "selected_package": "50 Mbps",
  "current_topic": "order_confirmation"
}
```

---

## 7. Fallback Behavior

Current fallback is too generic and may repeat.

Current fallback example:

```text
Maaf Kak, saya belum menangkap kebutuhan detailnya. Boleh jelaskan ingin pasang internet, cek paket, harga, coverage, atau jadwal teknisi?
```

Improved fallback should be context-aware.

If no state:

```text
Maaf Kak, saya belum nangkep maksudnya. Kakak mau tanya paket, harga, coverage area, atau pemasangan?
```

If current topic is payment:

```text
Maksudnya untuk metode pembayaran yang mana ya Kak, transfer, QRIS, atau lainnya?
```

If current topic is coverage:

```text
Boleh sebutkan kecamatan atau kelurahannya dulu Kak, supaya saya cek coverage-nya lebih tepat.
```

If current topic is package:

```text
Maksudnya paket yang berapa Mbps ya Kak?
```

Implement:

```ts
generateFallback(userMessage, state): string
```

Fallback should also go through prompt builder if LLM is available.

---

## 8. Anti-Repetition Rule

Before sending bot response, compare with last_bot_response.

Implement simple similarity check:

```ts
function isTooSimilar(newResponse: string, lastResponse: string): boolean {
  // simple option:
  // normalize lowercase, remove punctuation, compare token overlap/Jaccard similarity
  // if similarity > 0.85, treat as repeated
}
```

If repeated:

- Rebuild prompt with stronger instruction:
  - "Do not repeat the previous answer."
  - "Answer only the specific follow-up."
- Or generate short context-aware answer manually for high-confidence cases.

Example:

```text
last_bot_response:
Pembayaran bisa transfer bank, QRIS, cash, e-wallet...

user:
Kalau QRIS bisa?

new generated response repeats all methods.

Regenerate expected:
Bisa Kak, QRIS tersedia.
```

---

## 9. LLM Usage Boundary

Use LLM for:

- Natural response generation.
- Rephrasing retrieved facts.
- Handling short follow-up messages using state.
- Context-aware fallback.

Do not use LLM as the source of truth for:

- Package prices.
- Coverage availability.
- Payment availability.
- Installation fees.
- Promo status.
- Technician schedule.

All business facts must come from DB/knowledge retrieval.

Prompt must include:

```text
Do not invent facts outside the Knowledge section.
If required data is missing, ask a clarification question.
```

---

## 10. Recommended Module Structure

Suggested folder/module structure:

```text
src/
  chatbot/
    handleIncomingMessage.ts
    nlp/
      detectIntent.ts
      extractEntities.ts
      normalizeKeyword.ts
    state/
      getConversationState.ts
      saveConversationState.ts
      mergeState.ts
      isStateExpired.ts
    knowledge/
      retrieveKnowledge.ts
      packageRepository.ts
      coverageRepository.ts
      paymentRepository.ts
      scheduleRepository.ts
    llm/
      buildPrompt.ts
      callLLM.ts
      responseRules.ts
    response/
      generateFallback.ts
      antiRepetition.ts
    whatsapp/
      sendWhatsAppMessage.ts
```

---

## 11. Minimum Interfaces

```ts
type ConversationState = {
  phone_number: string;
  current_topic?: string | null;
  last_intent?: string | null;
  city?: string | null;
  district?: string | null;
  location?: string | null;
  selected_package?: string | null;
  selected_speed_mbps?: number | null;
  payment_method?: string | null;
  installation_schedule?: string | null;
  last_user_message?: string | null;
  last_bot_response?: string | null;
  updated_at: string;
};

type NLPResult = {
  intent: string;
  confidence: number;
  entities: Record<string, any>;
};

type KnowledgePayload = {
  type: string;
  data: any;
  missing_fields?: string[];
  notes?: string[];
};

type ResponseRules = {
  language: "id";
  tone: string;
  channel: "whatsapp";
  max_sentences: number;
  avoid_repeating_previous_answer: boolean;
  do_not_invent_data: boolean;
  ask_clarification_if_missing_required_info: boolean;
  use_kak: boolean;
};
```

---

## 12. Acceptance Criteria

The implementation is considered successful if these test cases pass.

### Test 1 — Package List

Input:

```text
Paketnya ada apa aja ya?
```

Expected:

- Bot returns active packages from DB.
- Bot mentions speed, price, and installation fee if available.
- Bot does not use hardcoded template as sole source.
- Bot may vary wording naturally.

---

### Test 2 — Coverage Follow-Up

Conversation:

```text
User:
Saya di Kota Bandung, sudah tercover belum?

Bot:
Boleh sebutkan kecamatan atau kelurahannya dulu Kak.

User:
Conblong
```

Expected:

```text
Area Conblong sudah tercover Kak...
```

State must contain:

```json
{
  "current_topic": "coverage_check",
  "city": "Bandung",
  "district": "Conblong"
}
```

---

### Test 3 — Payment Follow-Up

Conversation:

```text
User:
Bisa transfer?

Bot:
Bisa Kak, pembayaran bisa transfer bank, QRIS, cash, atau e-wallet.

User:
Kalau QRIS bisa?
```

Expected:

```text
Bisa Kak, QRIS juga tersedia.
```

Bot must not repeat full payment list.

---

### Test 4 — Package Price Follow-Up

Conversation:

```text
User:
Paketnya apa aja?

Bot:
Shows packages.

User:
Yang 30 Mbps berapa?
```

Expected:

```text
Paket 30 Mbps Rp200.000/bulan...
```

Bot must retrieve the 30 Mbps package from DB.

---

### Test 5 — Confirm Package

Input:

```text
Saya ambil paket 50 Mbps.
```

Expected:

- State updated with selected speed/package.
- Bot asks for next required data: name, full address, schedule.

---

### Test 6 — Unknown Area

Input:

```text
Saya di area Xyzabc, tercover gak?
```

Expected:

- Bot should not invent coverage.
- Bot should say it needs to check or ask for more specific address.
- State should store location candidate.

---

## 13. Priority Implementation Plan

### Phase 1 — State Layer

Implement:

- `conversation_states` table.
- `getConversationState`.
- `saveConversationState`.
- `mergeState`.
- TTL reset.

Goal: bot can remember last topic and extracted entities.

---

### Phase 2 — Knowledge Retrieval

Implement:

- `retrieveKnowledge`.
- Package repository.
- Coverage repository.
- Payment repository.

Goal: bot retrieves facts instead of using final response text.

---

### Phase 3 — Prompt Builder + LLM

Implement:

- `buildPrompt`.
- `callLLM`.
- Response rules.
- Business guardrails.

Goal: generate natural response from data.

---

### Phase 4 — Follow-Up + Anti-Repetition

Implement:

- Context-aware follow-up inference.
- Anti-repetition check.
- Contextual fallback.

Goal: bot no longer repeats generic answers and can answer short follow-up messages.

---

### Phase 5 — Logging and Evaluation

Create conversation logs table:

```sql
CREATE TABLE IF NOT EXISTS conversation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number TEXT NOT NULL,
    user_message TEXT NOT NULL,
    detected_intent TEXT,
    confidence REAL,
    entities_json TEXT,
    state_before_json TEXT,
    state_after_json TEXT,
    knowledge_json TEXT,
    bot_response TEXT,
    created_at DATETIME NOT NULL
);
```

Use logs to evaluate:

- Wrong intent.
- Missing entity.
- Bad retrieval.
- Bad prompt.
- Repeated response.
- Hallucinated facts.

---

## 14. Important Design Principle

Do not store final CS sentences as the primary answer source.

Store:

```text
facts
rules
business data
availability
pricing
coverage
```

Then let the LLM generate the final sentence.

Bad database design:

```json
{
  "intent": "ask_payment_method",
  "response": "Pembayaran bisa transfer bank, QRIS, cash, e-wallet..."
}
```

Better database design:

```json
{
  "payment_methods": [
    { "name": "Transfer Bank", "available": true },
    { "name": "QRIS", "available": true },
    { "name": "Cash", "available": true },
    { "name": "E-wallet", "available": true }
  ]
}
```

The final sentence should be generated dynamically based on:

- user message,
- state,
- retrieved knowledge,
- response rules.

---

## 15. Summary for Codex

Build the next version of the ISP chatbot with these core components:

```text
Conversation State
→ remembers context per phone number.

Knowledge Retrieval
→ retrieves factual business data from DB based on intent, entities, and state.

Prompt Builder
→ creates structured prompt for LLM using user message, state, knowledge, and response rules.

LLM Response Generator
→ generates natural WhatsApp reply without inventing facts.

Anti-Repetition
→ prevents bot from sending the same answer repeatedly.

Contextual Fallback
→ asks clarification based on current topic, not always generic fallback.
```

Main goal:

```text
Move from intent-template chatbot to context-aware, knowledge-grounded, LLM-generated chatbot.
```
