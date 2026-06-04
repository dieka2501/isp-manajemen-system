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

## Webhook Fonnte ke Google Sheets

Webhook ini menerima chat masuk dari Fonnte lalu menyimpan payload ke Google Sheet.

Endpoint:

```text
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
```

Alternatifnya, Anda bisa isi `GOOGLE_SERVICE_ACCOUNT_JSON` dengan isi JSON service account.
Jika worksheet belum ada, backend akan membuat tab tersebut otomatis.

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

Setup singkat:

1. Enable Google Sheets API di project Google Cloud.
2. Buat service account key JSON.
3. Share spreadsheet ke email service account dengan akses editor.
4. Jalankan backend dengan `uvicorn app.main:app --reload`.
5. Di dashboard Fonnte, isi webhook URL ke endpoint di atas dan aktifkan auto read.

## Deploy ke Railway

Project ini adalah monorepo, jadi untuk service backend di Railway gunakan konfigurasi berikut:

1. Buat service baru dari repository ini.
2. Set `Root Directory` ke `/apps/backend`.
3. Set `Config File` ke `/apps/backend/railway.toml`.
4. Pastikan domain publik Railway sudah digenerate.
5. Isi semua environment variable yang dibutuhkan di tab `Variables`.

Start command dan healthcheck sudah disiapkan di file `railway.toml`:

```toml
[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
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
GOOGLE_SERVICE_ACCOUNT_JSON=
```

Setelah deploy berhasil, webhook Fonnte bisa diarahkan ke:

```text
https://domain-railway-anda/api/v1/webhooks/fonnte?secret=isi_rahasia_anda
```
