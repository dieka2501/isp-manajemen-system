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

Webhook ini menerima chat masuk dari Fonnte, menyimpan percakapan ke SQLite, lalu:

1. Mencari trigger keyword: `diecast`, `hotwheel`, `stock`, `harga`.
2. Menjadikan kata lain di pesan sebagai token pencarian.
3. Mengquery tabel SQLite `stock_products` pada kolom nama produk milik client.
4. Mengirim balasan otomatis ke WhatsApp jika produk ditemukan.
5. Jika pesan tidak mengandung keyword, sistem membalas dengan pesan fallback.

Format balasan:

```text
Untuk {Nama Product} {type} mempunyai stock {Stock} buah.
```

Endpoint:

```text
GET /api/v1/webhooks/fonnte
POST /api/v1/webhooks/fonnte
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
- `intents`
- `languages`
- `keywords`
- `entities`
- `entity_keywords`
- `sample_utterances`
- `normalization_rules`
- `intent_mappings`

Data referensi intent/entity otomatis di-seed dari file SQL/JSON di root repo:
- `intents.sql`
- `languages.sql`
- `entities.sql`
- `keywords.sql`
- `entity_keywords.sql`
- `sample_utterances.sql`
- `normalization_rules.sql`
- `intent_mapping.json`

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
GET  /api/v1/chat/conversations
GET  /api/v1/chat/conversations/{conversation_id}/messages
```

Contoh alur setup:

1. Buat account.
2. Buat client di account tersebut dan simpan `api_token` client.
3. Register device Fonnte ke client dengan `device_identifier` dan `outbound_token`.
4. Tambahkan data produk/stok untuk client tersebut ke SQLite.
5. Arahkan webhook Fonnte ke endpoint backend.
6. Saat chat masuk berisi keyword terkait stok hotwheel, sistem akan mencari ke tabel `stock_products` dan membalas otomatis.

Contoh membuat account:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat/accounts \
  -H "Content-Type: application/json" \
  -d '{"name":"Toko Diecast A","slug":"toko-diecast-a"}'
```

Contoh membuat client:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat/clients \
  -H "Content-Type: application/json" \
  -d '{"account_slug":"toko-diecast-a","name":"Client Utama"}'
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

Contoh menambahkan atau memperbarui stok produk:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat/stock-products \
  -H "Content-Type: application/json" \
  -d '{
    "client_token":"isi_token_dari_endpoint_client",
    "product_name":"Hotwheel Civic EG",
    "product_type":"regular",
    "stock":12
  }'
```

Setup singkat:

1. Jalankan backend dengan `uvicorn app.main:app --reload`.
2. Buat account, client, device, dan data stok lewat endpoint API.
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
