# Native LLM Orchestration Design

Dokumen ini menjelaskan arsitektur chatbot ISP agar jawaban WhatsApp terasa lebih natural, tetap soft selling, dan tetap aman karena fakta bisnis bersumber dari SQLite.

## Tujuan

- Native agent tetap menjadi pengambil keputusan utama untuk intent, entity, slot, dan state percakapan.
- SQLite menjadi source of truth untuk paket internet, coverage, metode pembayaran, chat log, learning queue, dan memory percakapan.
- OpenAI dipakai sebagai response generator atau helper learning, bukan sebagai database dan bukan pemilik keputusan bisnis.
- Customer diberi ruang bertanya paket, harga, coverage, dan pembayaran sebelum bot meminta identitas.

## Flow Chat

```text
Webhook message
-> save incoming message
-> get conversation state
-> detect intent and entities
-> merge/update state
-> retrieve knowledge from SQLite catalog
-> build guarded LLM prompt
-> generate final reply, fallback to native reply if needed
-> save conversation state
-> save conversation log
-> send WhatsApp reply
```

Jika `LLM_RESPONSE_ENABLED=false`, `OPENAI_API_KEY` kosong, atau request OpenAI gagal, sistem langsung memakai native reply dari `ISPCSAgent`.

## Conversation State

Tabel `conversation_states` menyimpan memory aktif per `conversation_id`.

Field utama:

- `current_intent`: intent terakhir yang sedang dilayani.
- `current_topic`: topik percakapan, misalnya `package_info`, `coverage_check`, `payment`, atau `order_confirmation`.
- `stage`: status dialog seperti `collecting_slots` atau `ready`.
- `waiting_for`: JSON list slot yang masih ditunggu.
- `collected_slots`: JSON object slot yang sudah terkumpul.
- `last_user_message`: pesan customer terakhir.
- `last_bot_response`: jawaban bot terakhir untuk anti-repetition.
- `last_bot_question`: kompatibilitas untuk flow slot lama.
- `expires_at`: TTL state, default `CONVERSATION_STATE_TTL_HOURS=48`.

Contoh:

```json
{
  "current_intent": "ask_coverage",
  "current_topic": "coverage_check",
  "stage": "collecting_slots",
  "waiting_for": ["address"],
  "collected_slots": {
    "city": "Bandung"
  },
  "last_user_message": "Saya ada di kota Bandung, cover tidak?",
  "last_bot_response": "Boleh sebutkan kecamatan/kelurahannya dulu Kak."
}
```

State membuat follow-up pendek seperti `Conblong`, `Kalau QRIS bisa?`, atau `Yang 30 Mbps berapa?` tetap dibaca sesuai konteks sebelumnya.

## Knowledge Retrieval

`KnowledgeRetriever` mengambil fakta mentah dari katalog SQLite yang sudah dimuat oleh `SQLiteChatStore.get_intent_agent_catalog()`.

Data yang dipakai:

- `internet_packages`: paket, speed, harga bulanan, biaya instalasi, area, benefit.
- `coverage_areas`: area/kecamatan/kota dan status coverage.
- `payment_methods`: metode pembayaran dan ketersediaannya.

Retriever tidak membuat kalimat final. Ia hanya mengembalikan payload fakta untuk prompt dan audit log.

Contoh intent `ask_price` dengan entity `30 Mbps`:

```json
{
  "type": "ask_price",
  "topic": "package_info",
  "data": {
    "packages": [
      {
        "package_name": "Paket Keluarga",
        "speed_mbps": 30,
        "monthly_price": 200000
      }
    ]
  }
}
```

## LLM Response Generator

`LLMResponseGenerator` membangun prompt yang berisi:

- pesan customer,
- conversation state,
- detected intent,
- entities,
- knowledge hasil retrieval,
- native fallback reply,
- aturan jawaban.

Guardrail utama:

- Gunakan hanya fakta dari knowledge.
- Jangan mengarang harga, promo, coverage, payment method, atau jadwal.
- Jika data tidak ada, tanya klarifikasi singkat.
- Jangan mengulang jawaban bot sebelumnya.
- Jawaban maksimal pendek dan cocok untuk WhatsApp.

OpenAI tidak diberi akses SQL langsung. Jika suatu saat memakai MCP/tool, tool harus terbatas seperti `get_packages`, `get_coverage`, atau `get_payment_methods`, bukan `run_sql`.

## Soft Selling

Aturan perilaku native agent:

- `ask_package` menampilkan opsi paket dan menawarkan bantu pilih berdasarkan kebutuhan/area.
- `ask_price` menjawab harga sesuai speed/paket bila ada, bukan meminta nama/nomor HP.
- `ask_coverage` cukup minta area/kecamatan dulu; alamat lengkap bisa nanti.
- `ask_payment_method` menjawab metode spesifik bila customer bertanya follow-up, misalnya QRIS.
- `choose_package` baru masuk ke pengumpulan data pemasangan: nama, nomor HP, alamat, dan jadwal.
- `cancel_order` dijawab santai tanpa memaksa lanjut.

## Conversation Logs

Tabel `conversation_logs` menyimpan audit orchestration per pesan:

- `user_message`
- `detected_intent`
- `confidence`
- `entities_json`
- `state_before_json`
- `state_after_json`
- `knowledge_json`
- `bot_response`

Log ini dipakai untuk debugging, evaluasi kualitas jawaban, dan bahan learning berikutnya. Tabel `messages` tetap menyimpan inbound/outbound mentah dari webhook.

## Katalog Default

Seed default production:

- Paket Hemat: 20 Mbps, Rp 150.000/bulan, instalasi Rp 150.000, area Soreang/Bandung/Cangkuang.
- Paket Keluarga: 30 Mbps, Rp 200.000/bulan, instalasi Rp 150.000, area Soreang/Bandung/Cangkuang.
- Paket Premium: 50 Mbps, Rp 300.000/bulan, instalasi Rp 0 promo, area Soreang/Bandung.
- Paket Office: 100 Mbps, Rp 500.000/bulan, instalasi Rp 0 promo, area Kab Bandung/Kota Bandung/Cimahi/Bandung Barat.

Coverage dan payment method juga di-seed otomatis dari `app.services.intent_seed`.

Untuk database baru atau production container:

```bash
bash init_sqlite.sh
```

Atau dari folder `backend`:

```bash
python -m app.cli.init_sqlite
```

## Environment

```bash
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=20
LLM_RESPONSE_ENABLED=true
CONVERSATION_STATE_TTL_HOURS=48
CHAT_DATABASE_PATH=/app/data/chat.sqlite3
```

Matikan response generation OpenAI dengan `LLM_RESPONSE_ENABLED=false` bila ingin full native reply.

## Redis

Redis belum diperlukan untuk tahap awal. SQLite cukup karena:

- state perlu auditable,
- conversation log perlu bertahan setelah restart,
- traffic awal masih bisa ditangani single SQLite database.

Redis baru dipertimbangkan saat webhook sudah ramai, worker horizontal, atau butuh distributed lock/short-lived cache.
