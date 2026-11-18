# PantauSkill

Bot Telegram yang **otomatis dan bertahap** mengumpulkan data repositori GitHub bertopik
**skill untuk AI agentic coding** (repo berisi `SKILL.md`, skill untuk Claude Code, Cursor, dan
agen sejenis) selama beberapa hari, dengan jatah data tertentu per hari. Data disimpan di
SQLite, dianalisis, lalu dilaporkan ke Telegram (ringkasan, grafik, laporan Excel dan PDF).

Struktur proyek mengikuti contoh `proyek-pekan-12-contoh`
(scraper, database, analisis, laporan, bot). Bedanya: contoh mengambil semua data sekaligus di
tiap jadwal, sedangkan PantauSkill mengambil **sebagian** setiap hari, menyimpan progres, dan
melanjutkan keesokan harinya.

## Fitur

- Pengambilan bertahap: default **500 repo/hari selama 4 hari** (bisa diubah di `.env`).
- Otomatis penuh: `/mulai` dikirim **sekali**, lalu bot jalan sendiri tiap hari dan melapor.
- Progres tersimpan di SQLite: tidak ada data ganda, bisa lanjut setelah bot dimatikan.
- Aman dari rate limit: request berurutan + jeda, membaca sisa kuota dari header GitHub,
  menghormati `Retry-After`, berhenti dengan rapi jika kuota menipis.
- Pengaman jadwal terlewat: jika laptop sempat sleep atau bot mati, jatah hari itu dikejar saat bot hidup.
- Penyaringan relevansi: repo yang tidak benar-benar tentang skill ditandai dan dikeluarkan dari analisis.
- Analisis 5 pertanyaan, 3 grafik, laporan Excel dan PDF.
- Tes otomatis (pytest) yang berjalan tanpa internet.

## Struktur folder

```
pantauskill/
├── bot.py               # bot Telegram + penjadwalan (JobQueue)  <- dijalankan untuk tugas 4 hari
├── main.py              # CLI tanpa Telegram (cek, siapkan, jalankan, status, analisis)
├── config.py            # semua pengaturan (membaca .env)
├── github_client.py     # klien GitHub REST API: request, retry, rate limit
├── jendela.py           # memecah query menjadi jendela tanggal (batas 1000 hasil/query)
├── scraper_harian.py    # inti pengambilan bertahap: kuota harian + progres
├── relevansi.py         # skor relevansi repo terhadap topik "skill"
├── db.py                # SQLite: skema, upsert, progres, log
├── analisis.py          # pembersihan data, 5 pertanyaan analisis, grafik
├── laporan.py           # laporan Excel dan PDF
├── pesan.py             # teks balasan bot (fungsi murni, mudah diuji)
├── tests/               # tes pytest (tanpa internet)
├── data/                # skill.db dibuat di sini
├── logs/                # bot.log dan pipeline.log
├── output/              # grafik dan laporan hasil
├── requirements.txt
└── .env.example
```

## Prasyarat

- Python 3.10 atau lebih baru
- Akun Telegram dan akun GitHub

## Pemasangan

```bash

# 1. buat dan aktifkan virtual environment
python -m venv venv
venv\Scripts\Activate.ps1         # Windows
source venv/bin/activate       # macOS / Linux

# 2. pasang pustaka
pip install -r requirements.txt

# 3. siapkan konfigurasi
copy .env.example .env         # Windows
cp .env.example .env           # macOS / Linux
```

Lalu isi `.env`:

| Variabel | Cara mendapatkan |
| --- | --- |
| `BOT_TOKEN` | Chat dengan **@BotFather** di Telegram, kirim `/newbot`, salin tokennya |
| `GITHUB_TOKEN` | GitHub: Settings, Developer settings, Personal access tokens. Untuk data publik **tidak perlu scope apa pun** |
| `ADMIN_CHAT_ID` | (Opsional) Chat ID Anda; jika diisi, hanya chat ini yang boleh memakai bot. Bisa dicek lewat bot semacam @userinfobot |
| `JAM_JADWAL` | Jam pengambilan harian, WIB. Default `19:00` |
| `JUMLAH_HARI`, `KUOTA_HARIAN` | Default 4 hari dan 500 repo/hari |
| `JEDA_DETIK` | Jeda antar request. Default 2.0 |

Jangan pernah mengunggah file `.env` ke GitHub atau LMS (sudah ada di `.gitignore`).

## Cara menjalankan

**Langkah 0: cek dulu apakah data cukup (disarankan).**

```bash
python main.py cek
```

Menampilkan jumlah repo yang cocok dengan query, membandingkannya dengan target
(hari x kuota), dan menampilkan sisa kuota API. Jika kurang dari target, turunkan `STARS_MIN`
atau majukan `TANGGAL_MULAI_CARI` di `.env`.

**Langkah 1: jalankan bot dan biarkan terminal terbuka.**

```bash
python bot.py
```

**Langkah 2: di Telegram, kirim `/mulai` ke bot Anda (sekali saja).**

Bot akan menyusun jendela pencarian (sekitar 1 sampai 4 menit; tanpa token lebih lama), lalu:

- jika jam jadwal hari itu sudah lewat, jatah hari ke-1 berjalan sekitar 1 menit kemudian;
- jika belum, jatah hari ke-1 berjalan pada jam jadwal;
- hari-hari berikutnya berjalan otomatis setiap `JAM_JADWAL`.

Setelah tiap run, bot mengirim notifikasi. Setelah hari ke-4 (atau jika data habis), bot mengirim
laporan akhir berupa ringkasan, PDF, dan Excel.

**Penting selama 4 hari:**

- Biarkan `python bot.py` tetap berjalan; terminal tidak boleh ditutup.
- Matikan **sleep/hibernate** laptop. Jika sempat tertidur, job pengaman mengejar jatah hari itu
  setelah laptop aktif (maksimal tertunda sekitar 15 menit setelah bangun), tetapi lebih aman tidak tidur.
- Jangan menjalankan dua instance bot dengan token yang sama (Telegram akan menolak salah satunya
  dengan error conflict).
- Jika bot sempat mati, nyalakan lagi dengan `python bot.py`. Tugas dipulihkan otomatis dari database.

## Perintah bot

| Perintah | Fungsi |
| --- | --- |
| `/mulai` | Memulai tugas bertahap (sekali), lalu berjalan otomatis |
| `/status` | Hari ke-berapa, jumlah repo, jendela tersisa, run terakhir |
| `/perpanjang <jumlah_hari>` | Mengubah target total hari tugas aktif tanpa mengubah data/progress |
| `/scrape_sekarang` | Menjalankan jatah hari ini sekarang (berguna untuk demo) |
| `/scrape_sekarang uji` | Uji coba 1 halaman (100 repo), **tidak dihitung** sebagai hari |
| `/berhenti` | Membatalkan tugas dan jadwal (data tetap tersimpan) |
| `/ringkas` | Ringkasan data dan 5 temuan |
| `/cari <kata>` | Mencari repo berdasarkan nama atau deskripsi |
| `/top` | 5 repo dengan stars terbanyak |
| `/grafik` | Mengirim 3 grafik analisis |
| `/excel` | Mengirim seluruh isi tabel `repo` sebagai file Excel |
| `/help` | Daftar perintah |

Tips demo: kirim `/scrape_sekarang uji` untuk menunjukkan scraping bekerja tanpa menunggu jam jadwal
dan tanpa menghabiskan jatah hari.

## CLI tanpa Telegram

Untuk menguji bagian-bagian proyek tanpa bot:

```bash
python main.py cek               # jumlah repo yang cocok + sisa kuota
python main.py siapkan           # susun jendela pencarian
python main.py jalankan          # satu jatah harian
python main.py jalankan --uji    # uji 1 halaman (tidak dihitung sebagai hari)
python main.py status            # progres
python main.py analisis          # temuan + grafik + laporan di folder output/
```

`jalankan` membuat tugas tanpa chat Telegram jika belum ada. Jika kemudian Anda mengirim `/mulai`
ke bot, tugas itu otomatis disambungkan ke chat Anda.

## Cara kerja

**1. Sumber data: GitHub REST API resmi** (`/search/repositories`), bukan scraping HTML.
Query default:

```
claude-code skills in:name,description fork:false stars:>=3 created:<dari>..<sampai>
```

`fork:false` membuang salinan repo, `stars:>=3` membuang repo percobaan pribadi.

**2. Jendela tanggal.** Search API GitHub hanya mengembalikan maksimal 1000 hasil per query.
Saat `/mulai`, rentang `created:` dibelah dua berulang kali sampai setiap jendela berisi paling
banyak 1000 repo. Daftar jendela disimpan di tabel `jendela`.

**3. Jatah harian dan progres.** Tiap hari bot mengambil `KUOTA_HARIAN` repo (dibulatkan ke
kelipatan 100, satu halaman per request) dari jendela berurutan. Setiap halaman disimpan
**dalam satu transaksi** bersama posisi `halaman_next`. Jika program mati di tengah, data dan
progres tetap konsisten, dan hari berikutnya melanjutkan dari halaman yang benar.

**4. Tanpa duplikat.** `id` repo GitHub adalah PRIMARY KEY dengan upsert
(`ON CONFLICT DO UPDATE`). Jika sebuah halaman terambil dua kali, tidak ada baris ganda.

**5. Hari dihitung hanya jika ada data.** Jika run gagal tanpa mengambil data apa pun
(misalnya jaringan putus), hari itu tidak dihitung dan tugas bertambah satu hari. Job otomatis
tidak mengulang pada hari yang sama, tetapi `/scrape_sekarang` boleh dipakai untuk mencoba lagi.

**6. Rate limit.**

| Mekanisme | Keterangan |
| --- | --- |
| Request berurutan + jeda | Menghindari secondary rate limit |
| Kuota search per menit | Search API punya kuota sendiri (10/menit tanpa token, 30/menit dengan token). Jika sisa habis, klien menunggu sampai reset |
| 403 / 429 | Menunggu sesuai `Retry-After` atau waktu reset. Jika harus menunggu lebih dari `MAKS_TUNGGU_DETIK` (90 detik), run dihentikan dan progres disimpan |
| Galat jaringan / 5xx | Retry dengan backoff eksponensial (maks 3 kali) |
| Pengaman per run | Maksimal `MAKS_REQUEST_PER_RUN` (50) request |

Kebutuhan normal hanya sekitar 5 request data per hari (5 halaman x 100 repo), jauh di bawah batas.

**7. Memori.** Data disimpan per halaman ke SQLite, tidak menampung seluruh hasil di RAM.
Ribuan repo hanya beberapa MB.

**8. Relevansi.** Setiap repo diberi skor dari kata kunci pada nama, deskripsi, dan topik
(`skill`, `SKILL.md`, `agent skills`, `claude code`, `cursor`, `mcp`, dll.), dengan syarat
wajib ada kata inti "skill". Skor di bawah `AMBANG_RELEVAN` (default 4) ditandai `relevan = 0`,
tetap tersimpan, tetapi tidak ikut analisis. Ini heuristik sederhana, bukan klasifikasi sempurna.

## Pertanyaan analisis

1. Bahasa pemrograman apa yang paling dominan pada repo skill?
2. Agen mana yang paling sering disebut (Claude Code, Cursor, Copilot, dll.)?
3. Berapa banyak repo skill dibuat per bulan?
4. Apakah repo yang aktif cenderung punya stars lebih banyak?
5. Lisensi apa yang paling umum?

Catatan: perubahan stars dalam 4 hari kecil untuk kebanyakan repo, jadi tabel `riwayat_stars`
dipakai sebagai data pendukung, bukan analisis utama.

## Model data (SQLite, `data/skill.db`)

| Tabel | Isi |
| --- | --- |
| `repo` | Satu baris per repo: nama, deskripsi, bahasa, topik, lisensi, stars, forks, tanggal, skor relevansi |
| `riwayat_stars` | Stars dan forks tiap repo pada setiap run |
| `jendela` | Pecahan query (rentang tanggal) + `halaman_next` (progres) |
| `tugas` | Tugas 4 hari: chat, hari ke-berapa, status |
| `log_run` | Catatan tiap run: jumlah diambil, request, sisa kuota, status |

Untuk memulai dari nol, hentikan bot lalu hapus `data/skill.db*`.

## Pengujian

```bash
python -m pytest
```

74 tes berjalan tanpa internet (respons GitHub dan klien dipalsukan). Cakupannya: klien GitHub
(retry, rate limit, Retry-After), pemecahan jendela, database (upsert, transaksi, progres),
skenario bertahap beberapa hari (tanpa duplikat, kuota habis, data habis, error, mode uji,
penguncian), relevansi, analisis, laporan Excel dan PDF, teks pesan, dan pembentukan bot.

## Konfigurasi lanjutan (`.env`, opsional)

| Variabel | Default | Fungsi |
| --- | --- | --- |
| `QUERY_DASAR` | `claude-code skills in:name,description fork:false` | Query pencarian dasar |
| `STARS_MIN` | `3` | Minimal stars |
| `TANGGAL_MULAI_CARI` | `2025-01-01` | Batas awal tanggal pembuatan repo |
| `AMBANG_RELEVAN` | `4` | Skor minimal agar repo dianggap relevan |
| `MAKS_REQUEST_PER_RUN` | `50` | Pengaman jumlah request per run |
| `MAKS_TUNGGU_DETIK` | `90` | Batas menunggu rate limit sebelum run dihentikan |

## Pemecahan masalah

| Masalah | Penyebab dan solusi |
| --- | --- |
| `BOT_TOKEN belum diisi` | Salin `.env.example` menjadi `.env` lalu isi |
| `Token GitHub ditolak (401)` | `GITHUB_TOKEN` salah atau kedaluwarsa. Buat token baru |
| Error `Conflict: terminated by other getUpdates request` | Ada dua instance bot dengan token sama. Tutup yang lain |
| `/mulai` lama | Normal: menyusun jendela butuh puluhan request. Tanpa token bisa 3-4 menit, dengan token lebih cepat |
| Notifikasi "Terpotong rate limit" | Kuota API menipis. Progres tersimpan, dilanjutkan pada jadwal berikutnya |
| Data kurang dari target | Jalankan `python main.py cek`, lalu turunkan `STARS_MIN` atau majukan `TANGGAL_MULAI_CARI` |
| Error `ZoneInfo` / zona waktu di Windows | Pastikan `pip install -r requirements.txt` (memuat paket `tzdata`) |
| Job tidak jalan saat laptop tidur | Matikan sleep. Setelah bangun, job pengaman mengejar jatah hari itu |

## Batasan

- Bot harus berjalan terus selama tugas (proses `python bot.py` hidup). Tidak ada penyebaran ke server.
- Hasil pencarian GitHub berurutan menurut stars dan bisa bergeser antar hari. Upsert mencegah
  duplikat, tetapi sebagian kecil repo bisa terlewat. Bila satu hari kalender memuat lebih dari
  1000 repo yang cocok, hanya 1000 teratas yang terjangkau.
- Relevansi berbasis kata kunci, jadi sebagian kecil repo bisa salah golongan. Sesuaikan
  `AMBANG_RELEVAN` jika perlu.
- Hanya metadata repo publik yang disimpan; tidak ada email atau data pribadi.
- Bagian Telegram diuji pada tingkat logika dan pembentukan handler, tetapi tidak dengan bot
  sungguhan, karena butuh token Anda. Cobalah `/mulai` dan `/scrape_sekarang uji` sebelum mulai
  menjalankan 4 hari.

## Penggunaan AI

Kerangka dan kode proyek ini dibuat dengan bantuan asisten AI (Claude) berdasarkan contoh proyek
dan PRD yang disusun bersama. Isi bagian ini sesuai ketentuan tugas: sebutkan bagian yang Anda
tulis atau ubah sendiri, serta alat dan tanggal penggunaannya.
