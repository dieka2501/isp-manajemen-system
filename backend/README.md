# Backend Module

Backend module awal untuk ISP Manajemen System menggunakan FastAPI.

## Menjalankan

```bash
cd ..
cp .env.example .env
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

Setelah server jalan, dashboard SQLite explorer tersedia di:

```text
http://127.0.0.1:8000/sqlexplorer
```

Untuk sekarang, buka URL itu langsung tanpa lewat redirect dari `/` atau
`/dashboard`.

File SQLite yang bisa dipilih dari dashboard dapat dikonfigurasi lewat
`SQLITE_EXPLORER_SOURCES_JSON`. Contoh:

```bash
SQLITE_EXPLORER_SOURCES_JSON=[{"name":"Chat Database","path":"data/chat.sqlite3"},{"name":"Temp DB","path":"/private/tmp/sample.sqlite3"}]
```

Kalau `DASHBOARD_SECRET` diisi, dashboard akan meminta login sebelum data
SQLite bisa dibuka.

## Tes Kirim WhatsApp dari CLI

Set token Fonnte di `.env`:

```bash
FONNTE_TOKEN=isi_token_anda
```

Jalankan command berikut dari folder `backend`:

```bash
python -m app.cli.send_whatsapp -n 08123456789 -m "Halo dari CLI"
```

## Sistem Chat Fonnte + SQLite

Webhook ini menerima chat masuk dari Fonnte, menyimpan percakapan ke SQLite, lalu menjalankan agent CS/Sales ISP berbasis data intent/entity di SQLite.

1. Menormalisasi pesan customer memakai `normalization_rules`.
2. Mendeteksi bahasa dan intent dari tabel `keywords`.
3. Mengekstrak entity seperti speed, metode pembayaran, jadwal, alamat, nomor HP, dan harga.
4. Membaca slot dan `next_action` dari `intent_mappings`.
5. Menyusun balasan CS/Sales seperti cek coverage, info paket, harga, jadwal teknisi, pembayaran, atau order pemasangan.
6. Mengirim balasan otomatis ke WhatsApp bila token Fonnte tersedia.

Contoh balasan:

```text
Bisa Kak, kami bantu proses pemasangan internet rumah. Mohon kirim alamat lengkap, nama pelanggan, nomor HP aktif.
```

Endpoint:

```text
GET /api/v1/webhooks/fonnte
POST /api/v1/webhooks/fonnte
POST /api/v1/chat/agent/preview
```

Kalau ingin endpoint lebih aman, isi `FONNTE_WEBHOOK_SECRET` lalu pasang webhook URL dengan query string:

```text
https://domain-anda/api/v1/webhooks/fonnte?secret=rahasia-anda
```

Environment variable yang perlu diisi:

```bash
FONNTE_WEBHOOK_SECRET=rahasia-anda
CHAT_DATABASE_PATH=/absolute/path/chat.sqlite3
```

Database SQLite akan otomatis dibuat saat app start dan menyimpan:
- `accounts`
- `clients`
- `devices`
- `conversations`
- `messages`
- `stock_products`
- `internet_packages`
- `unprocessed_questions`
- `intents`
- `languages`
- `keywords`
- `entities`
- `entity_keywords`
- `sample_utterances`
- `normalization_rules`
- `intent_mappings`

Data referensi intent/entity dan paket internet default otomatis di-seed dari modul internal backend
`app.services.intent_seed`, sehingga production deploy tidak membutuhkan file
SQL/JSON di root repo.

Desain ini mendukung:
- multi account
- multiple client
- satu client memiliki banyak device
- setiap client memiliki token API sendiri

Jika ingin membuat dan seed database tanpa menjalankan server, gunakan:

```bash
python -m app.cli.init_sqlite
```

## Endpoint Operasional Chat

Endpoint webhook:

```text
GET /api/v1/webhooks/fonnte
POST /api/v1/webhooks/fonnte
```

Endpoint pengelolaan data chat:

```text
GET  /api/v1/chat/accounts
POST /api/v1/chat/accounts
GET  /api/v1/chat/clients
POST /api/v1/chat/clients
POST /api/v1/chat/devices
GET  /api/v1/chat/stock-products
POST /api/v1/chat/stock-products
GET  /api/v1/chat/internet-packages
POST /api/v1/chat/agent/preview
GET  /api/v1/chat/learning/intents
GET  /api/v1/chat/learning/unprocessed
POST /api/v1/chat/learning/unprocessed/{question_id}/map
POST /api/v1/chat/learning/unprocessed/{question_id}/suggest
GET  /api/v1/chat/conversations
GET  /api/v1/chat/conversations/{conversation_id}/messages
```

## Learning Queue untuk Pertanyaan yang Belum Terproses

Saat webhook menerima pesan dan agent menghasilkan intent `unknown` atau confidence
di bawah ambang aman, pesan tersebut tetap dibalas sesuai flow saat ini, tetapi
juga disalin ke tabel `unprocessed_questions`. Dashboard di
`http://127.0.0.1:8000/sqlexplorer` menampilkan tab **Learning Queue** untuk:

1. Melihat pertanyaan customer yang belum dipahami native system.
2. Memilih intent yang benar.
3. Menyimpan mapping sebagai `sample_utterance`, `keyword`, atau keduanya.
4. Mengabaikan pertanyaan yang memang di luar scope.

Mapping yang disimpan langsung masuk SQLite (`sample_utterances` dan/atau
`keywords`) sehingga agent berikutnya bisa memakai data native sebelum perlu
fallback ke API OpenAI.

Jika `OPENAI_API_KEY` tersedia, dashboard juga bisa meminta saran mapping lewat
tombol **Suggest with OpenAI**. Saran ini tidak auto-save; reviewer tetap perlu
memeriksa intent, mapping type, keyword, normalized keyword, dan weight sebelum
klik **Save mapping**. Model default adalah `gpt-4o-mini` dan bisa diganti lewat
`OPENAI_MODEL`.

## Memory Percakapan Native

Agent menyimpan memory aktif per conversation di tabel `conversation_states`.
Tabel `messages` tetap menjadi log webhook/inbound/outbound, sedangkan
`conversation_states` menyimpan state terstruktur seperti `current_intent`,
`waiting_for`, `collected_slots`, `last_bot_question`, dan `expires_at`.

Dengan state ini, jawaban pendek seperti `Soreang` atau `Keluarga` bisa
dipahami sebagai lanjutan dari pertanyaan bot sebelumnya, bukan selalu
diklasifikasikan sebagai intent baru. Memory diperbarui saat agent menghasilkan
`memory_update` dan kedaluwarsa 24 jam setelah update terakhir.

Algoritma reply memakai prinsip soft selling: pertanyaan paket, harga, dan awal
pemasangan tidak langsung meminta nama/nomor HP. Agent cukup menanyakan area,
kebutuhan, atau speed dulu, lalu baru mengumpulkan identitas saat customer sudah
jelas ingin diproses.

Rancangan lengkap native LLM, memory, dan posisi OpenAI sebagai helper learning
ditulis di [`docs/native-llm-memory.md`](docs/native-llm-memory.md).

Contoh alur setup:

1. Buat account.
2. Buat client di account tersebut dan simpan `api_token` client.
3. Register device Fonnte ke client dengan `device_identifier` dan `outbound_token`.
4. Pastikan database sudah ter-seed otomatis saat backend start.
5. Arahkan webhook Fonnte ke endpoint backend.
6. Saat chat masuk, agent akan membaca intent dari SQLite dan membalas sebagai CS/Sales ISP.

Contoh membuat account:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat/accounts \
  -H "Content-Type: application/json" \
  -d '{"name":"ISP Bandung Fiber","slug":"isp-bandung-fiber"}'
```

Contoh membuat client:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat/clients \
  -H "Content-Type: application/json" \
  -d '{"account_slug":"isp-bandung-fiber","name":"Sales WhatsApp Utama"}'
```

Contoh register device:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat/devices \
  -H "Content-Type: application/json" \
  -d '{
    "client_token":"isi_token_dari_endpoint_client",
    "device_identifier":"6281234567890",
    "device_name":"Device Gudang",
    "outbound_token":"token_fonnte_device"
  }'
```

Contoh test agent tanpa kirim WhatsApp:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat/agent/preview \
  -H "Content-Type: application/json" \
  -d '{"message":"Halo kak, saya mau pasang internet rumah 30 Mbps di Cibiru"}'
```

Setup singkat:

1. Jalankan backend dengan `uvicorn app.main:app --reload`.
2. Buat account, client, dan device lewat endpoint API.
3. Di dashboard Fonnte, isi webhook URL ke endpoint di atas dan aktifkan auto read.

## Deploy ke Railway

Project ini adalah monorepo, jadi untuk service backend di Railway gunakan konfigurasi berikut:

1. Buat service baru dari repository ini.
2. Set `Root Directory` ke root repository, atau kosongkan jika Railway otomatis memakai root.
3. Set `Config File` ke `railway.toml`.
4. Pastikan domain publik Railway sudah digenerate.
5. Isi semua environment variable yang dibutuhkan di tab `Variables`.

Catatan:
Railway membaca `requirements.txt` dari root project saat membuat layer dependency. File root itu sengaja berisi daftar dependency langsung karena pada tahap install awal Railpack belum selalu menyalin folder `backend/`.

Start command dan healthcheck sudah disiapkan di file `railway.toml`:

```toml
[deploy]
startCommand = "bash start.sh"
healthcheckPath = "/health"
```

Environment variable minimum di Railway:

```bash
APP_ENV=production
APP_DEBUG=false
FONNTE_TOKEN=
FONNTE_WEBHOOK_SECRET=
CHAT_DATABASE_PATH=/app/data/chat.sqlite3
DASHBOARD_SECRET=
SQLITE_EXPLORER_SOURCES_JSON=[{"name":"Chat Database","path":"/app/data/chat.sqlite3"}]
```

Gunakan `/app/data/chat.sqlite3` jika Railway volume dimount ke `/app/data`.
Jangan gunakan `/backend/data/chat.sqlite3`, karena itu menunjuk ke folder absolut
di root container yang tidak dibuat oleh aplikasi. Jika tidak memakai volume,
path sementara yang sesuai layout container adalah `/app/backend/data/chat.sqlite3`.

Setelah deploy berhasil, webhook Fonnte bisa diarahkan ke:

```text
https://domain-railway-anda/api/v1/webhooks/fonnte?secret=isi_rahasia_anda
```
