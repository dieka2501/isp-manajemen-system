# Backend Module

Backend module awal untuk ISP Manajemen System menggunakan FastAPI.

## Menjalankan

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload
```

## Tes Kirim WhatsApp dari CLI

Set token Fonnte di `.env`:

```bash
FONNTE_TOKEN=isi_token_anda
```

Jalankan command berikut dari folder `apps/backend`:

```bash
python -m app.cli.send_whatsapp -n 08123456789 -m "Halo dari CLI"
```

## Sistem Chat Fonnte + SQLite + Google Sheets

Webhook ini menerima chat masuk dari Fonnte, menyimpan percakapan ke SQLite, lalu:

1. Mencari trigger keyword: `diecast`, `hotwheel`, `stock`, `harga`.
2. Menjadikan kata lain di pesan sebagai token pencarian.
3. Mengquery Google Sheet tab `stock` pada kolom nama produk.
4. Mengirim balasan otomatis ke WhatsApp jika produk ditemukan.

Format balasan:

```text
Untuk {Nama Product} {type} mempunyai stock {Stock} buah.
```

Percakapan juga tetap bisa dicatat ke worksheet log inbound bila spreadsheet diisi.

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
GOOGLE_SERVICE_ACCOUNT_FILE=/absolute/path/credentials.json
GOOGLE_SHEETS_SPREADSHEET_ID=spreadsheet_id_anda
GOOGLE_SHEETS_WORKSHEET_NAME=incoming_whatsapp
GOOGLE_SHEETS_STOCK_WORKSHEET_NAME=stock
CHAT_DATABASE_PATH=/absolute/path/chat.sqlite3
```

Alternatifnya, Anda bisa isi `GOOGLE_SERVICE_ACCOUNT_JSON` dengan isi JSON service account.
Jika worksheet log inbound belum ada, backend akan membuat tab tersebut otomatis.

Kolom yang otomatis ditulis:
- `received_at`
- `device`
- `sender`
- `name`
- `message`
- `member`
- `url`
- `filename`
- `extension`
- `location`
- `raw_payload`

Database SQLite akan otomatis dibuat saat app start dan menyimpan:
- `accounts`
- `clients`
- `devices`
- `conversations`
- `messages`

Desain ini mendukung:
- multi account
- multiple client
- satu client memiliki banyak device
- setiap client memiliki token API sendiri

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
GET  /api/v1/chat/conversations
GET  /api/v1/chat/conversations/{conversation_id}/messages
```

Contoh alur setup:

1. Buat account.
2. Buat client di account tersebut dan simpan `api_token` client.
3. Register device Fonnte ke client dengan `device_identifier` dan `outbound_token`.
4. Arahkan webhook Fonnte ke endpoint backend.
5. Saat chat masuk berisi keyword terkait stok hotwheel, sistem akan mencari ke tab `stock` dan membalas otomatis.

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

Setup singkat:

1. Enable Google Sheets API di project Google Cloud.
2. Buat service account key JSON.
3. Share spreadsheet ke email service account dengan akses editor.
4. Jalankan backend dengan `uvicorn app.main:app --reload`.
5. Di dashboard Fonnte, isi webhook URL ke endpoint di atas dan aktifkan auto read.

## Deploy ke Railway

Project ini adalah monorepo, jadi untuk service backend di Railway gunakan konfigurasi berikut:

1. Buat service baru dari repository ini.
2. Set `Root Directory` ke `apps/backend`.
3. Set `Config File` ke `apps/backend/railway.toml`.
4. Pastikan domain publik Railway sudah digenerate.
5. Isi semua environment variable yang dibutuhkan di tab `Variables`.

Catatan:
Railway akan lebih stabil membaca dependency backend ini lewat `requirements.txt`, jadi file tersebut sudah disediakan berdampingan dengan `pyproject.toml`.

Start command dan healthcheck sudah disiapkan di file `railway.toml`:

```toml
[deploy]
startCommand = "python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
```

Environment variable minimum di Railway:

```bash
APP_ENV=production
APP_DEBUG=false
FONNTE_TOKEN=
FONNTE_WEBHOOK_SECRET=
GOOGLE_SHEETS_SPREADSHEET_ID=
GOOGLE_SHEETS_WORKSHEET_NAME=incoming_whatsapp
GOOGLE_SHEETS_STOCK_WORKSHEET_NAME=stock
GOOGLE_SERVICE_ACCOUNT_JSON=
CHAT_DATABASE_PATH=/app/data/chat.sqlite3
```

Setelah deploy berhasil, webhook Fonnte bisa diarahkan ke:

```text
https://domain-railway-anda/api/v1/webhooks/fonnte?secret=isi_rahasia_anda
```
