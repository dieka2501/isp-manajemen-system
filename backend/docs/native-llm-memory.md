# Native LLM Memory Design

Dokumen ini menjelaskan arah sistem CS/Sales ISP agar terasa lebih natural tanpa langsung bergantung pada OpenAI untuk setiap chat.

## Tujuan

- Native agent tetap menjadi pengambil keputusan utama untuk intent, entity, slot, dan reply.
- SQLite menjadi source of truth untuk chat log, learning queue, dan memory percakapan.
- OpenAI dipakai belakangan sebagai helper untuk rekomendasi learning keyword, humanizer, atau fallback saat confidence rendah.

## Komponen

### Chat log

Tabel `messages` menyimpan riwayat mentah inbound/outbound dari webhook. Tabel ini dipakai untuk audit dan debugging, bukan sebagai memory aktif.

Catatan:

- `message_text` kosong atau null dari payload lama/non-text harus diabaikan saat membangun konteks.
- Query konteks sebaiknya memfilter `message_text IS NOT NULL` dan `TRIM(message_text) != ''`.

### Conversation state

Tabel `conversation_states` menyimpan memory aktif per `conversation_id`.

Field utama:

- `current_intent`: intent yang sedang dilayani.
- `stage`: status dialog, misalnya `collecting_slots` atau `ready`.
- `waiting_for`: JSON list slot yang masih ditunggu.
- `collected_slots`: JSON object slot yang sudah terkumpul.
- `last_bot_question`: pertanyaan terakhir dari bot.
- `next_action`: aksi lanjutan dari `intent_mappings`.
- `expires_at`: batas waktu memory aktif, default diperbarui 24 jam dari update terakhir.

Contoh:

```json
{
  "current_intent": "ask_installation",
  "stage": "collecting_slots",
  "waiting_for": ["customer_name", "phone_number"],
  "collected_slots": {
    "address": "Soreang"
  },
  "last_bot_question": "Siap Kak, alamat Soreang saya catat. Mohon kirim nama pelanggan, nomor HP aktif agar prosesnya bisa dilanjutkan."
}
```

## Flow Native Agent

1. Webhook menyimpan pesan masuk ke `messages`.
2. Backend mengambil `conversation_states` aktif untuk conversation tersebut.
3. Jika `waiting_for` masih ada, agent mencoba mengisi slot dari pesan terbaru lebih dulu.
4. Jika ada slot yang terisi, agent membalas sebagai kelanjutan dialog lama.
5. Jika tidak ada slot cocok, agent menjalankan intent classifier seperti biasa.
6. Agent membangun reply dan `memory_update`.
7. Backend menyimpan `memory_update` kembali ke `conversation_states`.
8. Reply dikirim via Fonnte dan disimpan sebagai outgoing message.

## Prinsip Soft Selling

Native agent harus memberi ruang customer bertanya sebelum masuk pengambilan data
lead. Pertanyaan identitas seperti nama pelanggan dan nomor HP aktif hanya
diminta saat customer sudah jelas ingin diproses, misalnya intent
`confirm_order` atau state memang sedang menunggu data tersebut.

Aturan awal:

- `ask_package` menjawab dengan orientasi kebutuhan/area, bukan langsung meminta identitas.
- `ask_price` mengarahkan ke speed/area agar harga relevan, bukan meminta nama atau nomor HP.
- `ask_installation` cukup meminta area/alamat singkat dulu; nama dan nomor HP ditunda.
- `choose_package` mencatat minat paket lalu cek area/coverage dulu sebelum data pelanggan.
- `cancel_order` atau "gak jadi" dijawab santai dan tidak meminta data tambahan.

Tujuannya agar bot terasa seperti CS yang mengikuti ritme customer, bukan langsung
menutup transaksi.

## Katalog Paket Internet

Informasi paket native disimpan di tabel `internet_packages`, bukan
`stock_products`. Tabel stock tetap untuk barang/stok, sedangkan paket internet
membutuhkan field khusus seperti speed, harga bulanan, biaya instalasi, area,
dan benefit.

Seed default yang dipakai untuk production deploy:

- Paket Hemat: 20 Mbps, Rp 150.000/bulan, instalasi Rp 150.000, area Soreang/Bandung/Cangkuang.
- Paket Keluarga: 30 Mbps, Rp 200.000/bulan, instalasi Rp 150.000, area Soreang/Bandung/Cangkuang.
- Paket Premium: 50 Mbps, Rp 300.000/bulan, instalasi Rp 0 promo, area Soreang/Bandung.
- Paket Office: 100 Mbps, Rp 500.000/bulan, instalasi Rp 0 promo, area Kab Bandung/Kota Bandung/Cimahi/Bandung Barat.

Backend men-seed data ini otomatis saat startup melalui `SQLiteChatStore.initialize()`.
Untuk database production yang sudah ada, restart backend atau jalankan:

```bash
python -m app.cli.init_sqlite
```

Agent memakai katalog ini untuk `ask_package`, `ask_price`,
`ask_installation_fee`, dan `compare_package`. Jika area customer terdeteksi,
agent mencoba memfilter paket berdasarkan area tersebut.

## Contoh Perilaku

Input:

```text
Saya mau pasang internet, bisa?
```

Native response:

```text
Bisa Kak, kami bantu proses pemasangan internet rumah. Mohon kirim alamat lengkap, nama pelanggan, nomor HP aktif.
```

Memory:

```json
{
  "current_intent": "ask_installation",
  "stage": "collecting_slots",
  "waiting_for": ["address", "customer_name", "phone_number"]
}
```

Input berikutnya:

```text
Soreang
```

Native response:

```text
Siap Kak, alamat Soreang saya catat. Mohon kirim nama pelanggan, nomor HP aktif agar prosesnya bisa dilanjutkan.
```

## Peran OpenAI

OpenAI tidak diberi akses raw SQL langsung. Integrasi awal memakai
`OPENAI_API_KEY` dan `OPENAI_MODEL` dengan default `gpt-4o-mini` untuk memberi
saran Learning Queue yang tetap harus direview manusia.

Endpoint awal:

```text
POST /api/v1/chat/learning/unprocessed/{question_id}/suggest
```

Endpoint ini mengirim konteks terbatas:

- teks pertanyaan,
- normalized text,
- detected intent dan confidence,
- candidates/entities dari native agent,
- daftar intent yang tersedia.

Ia mengembalikan:

- `intent_code`,
- `mapping_type`,
- `keyword`,
- `normalized_keyword`,
- `weight`,
- `reason`.

Jika nanti diperluas, berikan tool terbatas dari backend:

- `suggest_learning_mapping(message, candidates)`
- `suggest_normalized_keyword(message, intent_catalog)`
- `polish_reply(draft_reply, conversation_context)`
- `classify_low_confidence_message(message, safe_context)`

Jangan berikan tool bebas seperti `run_sql(query)` karena terlalu berisiko untuk data customer.

## Prinsip Keamanan

- Kirim konteks minimal ke OpenAI.
- Jangan kirim token Fonnte, API token client, atau raw payload penuh.
- Simpan keputusan akhir tetap di backend.
- Rekomendasi OpenAI untuk learning queue sebaiknya reviewable, bukan auto-save.
- Audit data yang dikirim ke tool eksternal.

## Kapan Redis Dipakai

Redis belum diperlukan pada tahap awal. SQLite cukup untuk memory karena:

- Data perlu auditable.
- Traffic awal masih bisa ditangani single SQLite database.
- State perlu bertahan setelah restart.

Redis baru dipertimbangkan untuk cache/lock saat:

- traffic webhook tinggi,
- worker/server paralel,
- perlu TTL otomatis sangat cepat,
- atau deploy sudah scale horizontal.
