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

Setelah server jalan, dashboard client ISP tersedia di:

```text
http://127.0.0.1:8000/client-dashboard
```

Dashboard memakai login Client dan session cookie HttpOnly. Bearer token tetap
diterima sementara untuk compatibility API, tetapi frontend tidak lagi menyimpan
token di `localStorage`.

Approval registrasi, pencatatan pembayaran, dan aktivasi customer berada di
`/client-dashboard/registrations` dengan API `/api/v1/client/registrations/*`.
Tenant selalu berasal dari session Client; `client_id` dari URL atau request body
tidak digunakan sebagai sumber identitas tenant.
Credential development default akan dibuat di tabel `clients`:

```text
Email: admin@isp.local
Password: password
```

Ganti lewat `CLIENT_DASHBOARD_SEED_EMAIL` dan
`CLIENT_DASHBOARD_SEED_PASSWORD` sebelum database pertama kali dibuat.
Provider Dashboard tersedia di `/sqlexplore`. Route lama `/sqlexplorer`
melakukan redirect permanen ke route canonical tersebut.

File SQLite yang bisa dipilih dari dashboard dapat dikonfigurasi lewat
`SQLITE_EXPLORER_SOURCES_JSON`. Contoh:

```bash
SQLITE_EXPLORER_SOURCES_JSON=[{"name":"Chat Database","path":"data/chat.sqlite3"},{"name":"Temp DB","path":"/private/tmp/sample.sqlite3"}]
```

`DASHBOARD_SECRET` wajib dikonfigurasi untuk login Provider. Tanpa secret,
Provider Dashboard tetap terkunci dan endpoint login mengembalikan configuration
error; tidak ada mode Provider auto-authenticated.

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
POST /api/v1/provider/chat/agent/preview
```

Kalau ingin endpoint lebih aman, isi `FONNTE_WEBHOOK_SECRET` lalu pasang webhook URL dengan query string:

```text
https://domain-anda/api/v1/webhooks/fonnte?secret=rahasia-anda
```

Environment variable yang perlu diisi:

```bash
APP_HOST=127.0.0.1:8000
FONNTE_WEBHOOK_SECRET=rahasia-anda
CHAT_DATABASE_PATH=/absolute/path/chat.sqlite3
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
LLM_RESPONSE_ENABLED=true
CONVERSATION_STATE_TTL_HOURS=48
CLIENT_DASHBOARD_JWT_SECRET=
CLIENT_DASHBOARD_TOKEN_HOURS=2
CLIENT_DASHBOARD_COOKIE_NAME=client_dashboard_session
CLIENT_DASHBOARD_SEED_EMAIL=admin@isp.local
CLIENT_DASHBOARD_SEED_PASSWORD=password
BILLING_SAMPLE_XLSX_PATH=contoh-list-billing.xlsx
```

`APP_HOST` dipakai untuk membentuk link publik seperti form pendaftaran dan
pembayaran. Isi host beserta port hanya untuk lokal, misalnya
`127.0.0.1:8000`; di production cukup isi domain production tanpa `APP_PORT`,
misalnya `isp.example.com` atau `https://isp.example.com`.

Database SQLite akan otomatis dibuat saat app start dan menyimpan:
- `accounts`
- `clients`
- `devices`
- `customers`
- `billing_records`
- `conversations`
- `messages`
- `stock_products`
- `internet_packages`
- `coverage_areas`
- `payment_methods`
- `conversation_states`
- `conversation_logs`
- `unprocessed_questions`
- `intents`
- `languages`
- `keywords`
- `entities`
- `entity_keywords`
- `sample_utterances`
- `normalization_rules`
- `intent_mappings`

Data referensi intent/entity, paket internet, coverage area, dan payment method
default otomatis di-seed dari modul internal backend `app.services.intent_seed`,
sehingga production deploy tidak membutuhkan file SQL/JSON di root repo.

Desain ini mendukung:
- multi account
- multiple client
- satu client memiliki banyak device
- setiap client memiliki token API sendiri
- dashboard client login memakai email/token client dan password hash
- data customer dan billing tersimpan di SQLite per client
- tabel data/operasional/katalog discope dengan `client_id` dan `device_id`

Jika ingin membuat dan seed database tanpa menjalankan server, gunakan:

```bash
bash init_sqlite.sh
```

Jika sedang berada langsung di folder `backend/`, command modulnya juga bisa
dijalankan manual:

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
GET  /api/v1/provider/chat/accounts
POST /api/v1/provider/chat/accounts
GET  /api/v1/provider/chat/clients
POST /api/v1/provider/chat/clients
POST /api/v1/provider/chat/devices
GET  /api/v1/provider/chat/stock-products
POST /api/v1/provider/chat/stock-products
GET  /api/v1/provider/chat/internet-packages
POST /api/v1/provider/chat/agent/preview
GET  /api/v1/provider/chat/learning/intents
GET  /api/v1/provider/chat/learning/unprocessed
POST /api/v1/provider/chat/learning/unprocessed/{question_id}/map
POST /api/v1/provider/chat/learning/unprocessed/{question_id}/suggest
GET  /api/v1/provider/chat/conversations
GET  /api/v1/provider/chat/conversations/{conversation_id}/messages
```

Semua endpoint Provider memerlukan session Provider. Login dan simpan cookie
sebelum memakai contoh `curl` di bawah:

```bash
curl -c provider.cookies -X POST http://127.0.0.1:8000/api/v1/provider/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password":"isi-DASHBOARD_SECRET"}'
```

Endpoint dashboard client:

```text
POST /api/v1/client/auth/login
GET  /api/v1/client/auth/me
POST /api/v1/client/auth/logout
GET  /api/v1/client/summary
GET  /api/v1/client/devices
GET  /api/v1/client/customers
GET  /api/v1/client/packages
GET  /api/v1/client/billing
GET  /api/v1/client/learning/intents
GET  /api/v1/client/learning/unprocessed
POST /api/v1/client/learning/unprocessed/{question_id}/map
POST /api/v1/client/agent/preview
```

Semua endpoint dashboard selain login memakai session cookie HttpOnly. Header
`Authorization: Bearer <access_token>` tetap diterima selama masa migrasi.

Session dashboard client berlaku 2 jam secara default melalui
`CLIENT_DASHBOARD_TOKEN_HOURS=2`.

Jika `BILLING_SAMPLE_XLSX_PATH` menunjuk file `.xlsx`, database baru akan
mengimpor contoh billing menjadi `customers`, `internet_packages`, dan
`billing_records` untuk client default.

Untuk production, data billing/customer asli tidak perlu dicommit ke Git. Buka
`/sqlexplore`, login dengan `DASHBOARD_SECRET`, masuk tab **SQLite Explorer**,
lalu gunakan panel **Import Billing XLSX**. Pilih client, device, dan file
`.xlsx`; backend akan meng-upsert data ke SQLite:

- `customers`
- `billing_records`
- `internet_packages`

Upload import bersifat idempotent untuk invoice/customer yang sama, sehingga
file yang sama bisa diupload ulang tanpa menggandakan row.

Endpoint data yang discope device menerima parameter `client_id` atau
`client_token` bersama `device_id` atau `device_identifier`. Untuk
`POST /api/v1/provider/chat/stock-products`, client dan device wajib dikirim agar stok
tidak tercampur antar device.

## Learning Queue untuk Pertanyaan yang Belum Terproses

Saat webhook menerima pesan dan agent menghasilkan intent `unknown` atau confidence
di bawah ambang aman, pesan tersebut tetap dibalas sesuai flow saat ini, tetapi
juga disalin ke tabel `unprocessed_questions`. Dashboard di
`http://127.0.0.1:8000/client-dashboard` menampilkan view **Learn Process** untuk:

1. Melihat pertanyaan customer yang belum dipahami native system.
2. Memilih intent yang benar.
3. Menyimpan mapping sebagai `sample_utterance`, `keyword`, atau keduanya.
4. Mengabaikan pertanyaan yang memang di luar scope.

Mapping yang disimpan langsung masuk SQLite (`sample_utterances` dan/atau
`keywords`) sehingga agent berikutnya bisa memakai data native sebelum perlu
fallback ke API OpenAI.

Jika `OPENAI_API_KEY` tersedia, endpoint operasional
`POST /api/v1/provider/chat/learning/unprocessed/{question_id}/suggest` tetap bisa
dipakai untuk meminta saran mapping. Saran ini tidak auto-save; reviewer tetap
perlu memeriksa intent, mapping type, keyword, normalized keyword, dan weight
sebelum menyimpan mapping. Model default adalah `gpt-4o-mini` dan bisa diganti
lewat `OPENAI_MODEL`.

## Memory Percakapan Native

Agent menyimpan memory aktif per conversation di tabel `conversation_states`.
Tabel `messages` tetap menjadi log webhook/inbound/outbound, sedangkan
`conversation_states` menyimpan state terstruktur seperti `current_intent`,
`current_topic`, `waiting_for`, `collected_slots`, `last_user_message`,
`last_bot_response`, `last_bot_question`, dan `expires_at`.

Dengan state ini, jawaban pendek seperti `Soreang` atau `Keluarga` bisa
dipahami sebagai lanjutan dari pertanyaan bot sebelumnya, bukan selalu
diklasifikasikan sebagai intent baru. Memory diperbarui saat agent menghasilkan
`memory_update` dan kedaluwarsa sesuai `CONVERSATION_STATE_TTL_HOURS`
setelah update terakhir.

Algoritma reply memakai prinsip soft selling: pertanyaan paket, harga, dan awal
pemasangan tidak langsung meminta nama/nomor HP. Agent cukup menanyakan area,
kebutuhan, atau speed dulu, lalu baru mengumpulkan identitas saat customer sudah
jelas ingin diproses.

Sebelum reply dikirim, service mengambil knowledge relevan dari SQLite
(`internet_packages`, `coverage_areas`, dan `payment_methods`), membangun prompt
terbatas, lalu memakai OpenAI sebagai final response generator jika
`LLM_RESPONSE_ENABLED=true` dan `OPENAI_API_KEY` tersedia. Jika OpenAI gagal atau
dimatikan, native reply tetap dipakai. Setiap langkah disimpan ke
`conversation_logs` untuk audit dan evaluasi learning.

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
curl -X POST http://127.0.0.1:8000/api/v1/provider/chat/accounts \
  -b provider.cookies \
  -H "Content-Type: application/json" \
  -d '{"name":"ISP Bandung Fiber","slug":"isp-bandung-fiber"}'
```

Contoh membuat client:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/provider/chat/clients \
  -b provider.cookies \
  -H "Content-Type: application/json" \
  -d '{"account_slug":"isp-bandung-fiber","name":"Sales WhatsApp Utama"}'
```

Contoh register device:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/provider/chat/devices \
  -b provider.cookies \
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
curl -X POST http://127.0.0.1:8000/api/v1/provider/chat/agent/preview \
  -b provider.cookies \
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
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=20
LLM_RESPONSE_ENABLED=true
CONVERSATION_STATE_TTL_HOURS=48
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
