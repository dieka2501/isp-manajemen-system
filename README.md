# ISP Manajemen System

Repository ini digunakan sebagai fondasi pengembangan sistem manajemen ISP dengan pendekatan modular agar backend, frontend, dan service pendukung dapat dikembangkan secara terpisah.

## Struktur Project

```text
.
├── backend
│   ├── app
│   │   ├── api
│   │   ├── auth
│   │   ├── client_dashboard
│   │   ├── core
│   │   ├── provider_dashboard
│   │   └── services
│   ├── pyproject.toml
│   └── requirements.txt
├── .env.example
├── frontend
│   ├── app.js
│   ├── client-dashboard
│   ├── index.html
│   ├── provider-dashboard
│   └── styles.css
├── packages
│   └── shared
├── railway.toml
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
- webhook Fonnte untuk menyimpan chat masuk ke SQLite
- agent CS/Sales ISP berbasis SQLite untuk intent, entity, slot, dan balasan awal
- siap dikembangkan untuk modul autentikasi, pelanggan, billing, dan notifikasi

### Dashboard

- Provider Dashboard: `http://127.0.0.1:8000/sqlexplore`
- Client Dashboard: `http://127.0.0.1:8000/client-dashboard`
- Approval registrasi Client: `http://127.0.0.1:8000/client-dashboard/registrations`
- Route `/` hanya mengarahkan session ke dashboard yang sesuai atau ke `/login`.

Route, layout, navigation, permission, dan API boundary kedua dashboard terpisah. Detail inventory dan migrasi tersedia di [dashboard-separation-inventory.md](docs/dashboard-separation-inventory.md) dan [dashboard-separation-migration.md](docs/dashboard-separation-migration.md).

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

## Validasi

```bash
cd backend
../env/bin/python -m unittest discover -s tests -v
```

Test dashboard mencakup redirect actor-aware, permission Provider, isolasi
tenant Client, penolakan cross-dashboard, manipulasi `client_id`, dan route
compatibility.
