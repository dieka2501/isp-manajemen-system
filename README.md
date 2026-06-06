# ISP Manajemen System

Repository ini digunakan sebagai fondasi pengembangan sistem manajemen ISP dengan pendekatan modular agar backend, frontend, dan service pendukung dapat dikembangkan secara terpisah.

## Struktur Awal Project

```text
.
├── backend
│   ├── app
│   │   ├── api
│   │   ├── core
│   │   └── services
│   ├── pyproject.toml
│   ├── railway.toml
│   └── requirements.txt
├── .env.example
├── frontend
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── packages
│   └── shared
└── README.md
```

## Modul Awal

### `backend`

Contoh backend pertama menggunakan Python dan FastAPI.

Fitur awal:
- struktur API modular
- konfigurasi berbasis environment variable
- endpoint health check
- utilitas CLI untuk tes kirim WhatsApp via Fonnte
- webhook Fonnte untuk menyimpan chat masuk ke Google Sheets
- siap dikembangkan untuk modul autentikasi, pelanggan, billing, dan notifikasi

### `frontend`

Dashboard SQLite explorer yang disajikan oleh backend dari folder `frontend` di root project.

### `packages/shared`

Placeholder untuk shared schema, utilitas, atau kontrak data yang nantinya dipakai lintas modul.

## Menjalankan Backend

```bash
cp .env.example .env
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload
```

Backend akan berjalan di `http://127.0.0.1:8000`.

Untuk tes kirim WhatsApp via CLI:

```bash
cd backend
python -m app.cli.send_whatsapp -n 08123456789 -m "Halo dari CLI"
```

## Endpoint Awal

- `GET /health`
- `GET /api/v1`

## Langkah Berikutnya

- menambahkan modul autentikasi
- menambahkan modul pelanggan
- menambahkan modul billing reminder
- menambahkan integrasi WhatsApp dan AI service
