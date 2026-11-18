"""
Lapisan 2: PENYIMPANAN (SQLite).

Tabel:
- repo          : satu baris per repo (id GitHub sebagai PRIMARY KEY), kondisi terakhir.
- riwayat_stars : satu baris per repo per run, untuk memantau perubahan stars/forks.
- jendela       : pecahan query (rentang created:) beserta posisi halaman berikutnya (PROGRES).
- tugas         : tugas 4 hari (chat_id, hari ke-berapa, status).
- log_run       : catatan setiap run harian.

Menyimpan satu halaman hasil dan memperbarui progres jendela dilakukan dalam SATU transaksi,
sehingga jika program mati di tengah jalan, data dan progres tetap konsisten.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

import config

SKEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS repo (
    id               INTEGER PRIMARY KEY,   -- id repo dari GitHub
    full_name        TEXT NOT NULL,         -- pemilik/nama
    url              TEXT,
    deskripsi        TEXT,
    bahasa           TEXT,
    topik            TEXT,                  -- dipisah koma
    lisensi          TEXT,
    stars            INTEGER,
    forks            INTEGER,
    open_issues      INTEGER,
    dibuat           TEXT,                  -- created_at
    push_terakhir    TEXT,                  -- pushed_at
    diarsipkan       INTEGER,
    skor_relevan     INTEGER,
    relevan          INTEGER,               -- 1 = ya, 0 = tidak
    pertama_dilihat  TEXT,
    terakhir_dilihat TEXT
);
CREATE INDEX IF NOT EXISTS idx_repo_stars ON repo(stars);

CREATE TABLE IF NOT EXISTS riwayat_stars (
    id_repo      INTEGER,
    waktu_scrape TEXT,
    stars        INTEGER,
    forks        INTEGER,
    PRIMARY KEY (id_repo, waktu_scrape)
);

CREATE TABLE IF NOT EXISTS jendela (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dari         TEXT,
    sampai       TEXT,
    total        INTEGER,                   -- total_count saat disusun
    halaman_next INTEGER DEFAULT 1,
    diambil      INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'menunggu'    -- menunggu / berjalan / selesai
);

CREATE TABLE IF NOT EXISTS tugas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id      INTEGER,                   -- 0 = dibuat lewat CLI (belum terhubung ke chat)
    mulai        TEXT,
    total_hari   INTEGER,
    kuota_harian INTEGER,
    hari_ke      INTEGER DEFAULT 0,         -- jatah yang sudah dihitung
    status       TEXT DEFAULT 'berjalan'    -- berjalan / selesai / dibatalkan
);

CREATE TABLE IF NOT EXISTS log_run (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    id_tugas       INTEGER,
    hari_ke        INTEGER,
    waktu_mulai    TEXT,
    waktu_selesai  TEXT,
    repo_diambil   INTEGER,
    repo_baru      INTEGER,
    jumlah_request INTEGER,
    sisa_kuota     TEXT,
    status         TEXT,                    -- ok / terpotong_kuota / error / data_habis / ...
    catatan        TEXT,
    mode           TEXT,                    -- normal / uji
    dihitung       INTEGER                  -- 1 jika run ini dihitung sebagai satu hari
);
"""

_SIAP = set()  # path database yang skemanya sudah dibuat pada sesi ini


@contextmanager
def koneksi(path=None, dict_row=True):
    """Buka database, commit jika sukses (rollback jika error), lalu tutup."""
    p = Path(path or config.DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=30)
    if dict_row:
        con.row_factory = sqlite3.Row
    try:
        if str(p) not in _SIAP:
            con.executescript(SKEMA)
            _SIAP.add(str(p))
        with con:
            yield con
    finally:
        con.close()


def _dict(baris):
    return dict(baris) if baris is not None else None


# ====================== repo ======================
UPSERT_REPO = """
INSERT INTO repo (id, full_name, url, deskripsi, bahasa, topik, lisensi, stars, forks,
                  open_issues, dibuat, push_terakhir, diarsipkan, skor_relevan, relevan,
                  pertama_dilihat, terakhir_dilihat)
VALUES (:id, :full_name, :url, :deskripsi, :bahasa, :topik, :lisensi, :stars, :forks,
        :open_issues, :dibuat, :push_terakhir, :diarsipkan, :skor_relevan, :relevan,
        :waktu, :waktu)
ON CONFLICT(id) DO UPDATE SET
    full_name = excluded.full_name,
    url = excluded.url,
    deskripsi = excluded.deskripsi,
    bahasa = excluded.bahasa,
    topik = excluded.topik,
    lisensi = excluded.lisensi,
    stars = excluded.stars,
    forks = excluded.forks,
    open_issues = excluded.open_issues,
    dibuat = excluded.dibuat,
    push_terakhir = excluded.push_terakhir,
    diarsipkan = excluded.diarsipkan,
    skor_relevan = excluded.skor_relevan,
    relevan = excluded.relevan,
    terakhir_dilihat = excluded.terakhir_dilihat
"""


def simpan_halaman(repos, id_jendela, halaman_next, status, waktu=None, path=None):
    """Simpan satu halaman repo + perbarui progres jendela dalam satu transaksi.
    Kembalikan jumlah repo BARU (yang belum ada di database)."""
    waktu = waktu or config.sekarang_str()
    with koneksi(path) as con:
        sebelum = con.execute("SELECT COUNT(*) FROM repo").fetchone()[0]
        con.executemany(UPSERT_REPO, [{**r, "waktu": waktu} for r in repos])
        con.executemany(
            "INSERT OR IGNORE INTO riwayat_stars (id_repo, waktu_scrape, stars, forks) "
            "VALUES (?, ?, ?, ?)",
            [(r["id"], waktu, r["stars"], r["forks"]) for r in repos],
        )
        con.execute(
            "UPDATE jendela SET halaman_next = ?, diambil = diambil + ?, status = ? WHERE id = ?",
            (halaman_next, len(repos), status, id_jendela),
        )
        sesudah = con.execute("SELECT COUNT(*) FROM repo").fetchone()[0]
    return sesudah - sebelum


def jumlah_repo(path=None, hanya_relevan=False):
    sql = "SELECT COUNT(*) FROM repo" + (" WHERE relevan = 1" if hanya_relevan else "")
    with koneksi(path) as con:
        return con.execute(sql).fetchone()[0]


def baca_repo(path=None):
    """Seluruh tabel repo sebagai DataFrame (dipakai analisis, laporan, bot)."""
    with koneksi(path, dict_row=False) as con:
        return pd.read_sql("SELECT * FROM repo", con)


def cari(kata, batas=5, path=None):
    """Cari repo relevan berdasarkan nama/deskripsi. Parameter ? mencegah SQL injection."""
    pola = f"%{kata}%"
    with koneksi(path, dict_row=False) as con:
        return pd.read_sql(
            "SELECT full_name, deskripsi, bahasa, stars FROM repo "
            "WHERE relevan = 1 AND (full_name LIKE ? OR deskripsi LIKE ?) "
            "ORDER BY stars DESC LIMIT ?",
            con, params=[pola, pola, batas],
        )


def teratas(batas=5, path=None):
    with koneksi(path, dict_row=False) as con:
        return pd.read_sql(
            "SELECT full_name, deskripsi, bahasa, stars FROM repo WHERE relevan = 1 "
            "ORDER BY stars DESC LIMIT ?",
            con, params=[batas],
        )


def riwayat(path=None):
    with koneksi(path, dict_row=False) as con:
        return pd.read_sql(
            "SELECT r.*, b.full_name FROM riwayat_stars r JOIN repo b ON b.id = r.id_repo", con)


# ====================== jendela (progres) ======================
def ganti_jendela(daftar, path=None):
    """Ganti seluruh daftar jendela dengan yang baru (list dict dari, sampai, total)."""
    with koneksi(path) as con:
        con.execute("DELETE FROM jendela")
        con.executemany(
            "INSERT INTO jendela (dari, sampai, total) VALUES (:dari, :sampai, :total)", daftar)


def jendela_berikutnya(path=None):
    with koneksi(path) as con:
        return _dict(con.execute(
            "SELECT * FROM jendela WHERE status IN ('menunggu', 'berjalan') "
            "ORDER BY id LIMIT 1").fetchone())


def _hitung_jendela(con):
    r = con.execute(
        "SELECT COUNT(*) AS n, "
        "COALESCE(SUM(CASE WHEN status = 'selesai' THEN 1 ELSE 0 END), 0) AS selesai, "
        "COALESCE(SUM(MIN(total, ?)), 0) AS perkiraan, "
        "COALESCE(SUM(diambil), 0) AS diambil FROM jendela",
        (config.BATAS_HASIL_SEARCH,)).fetchone()
    return {"jumlah": r["n"], "selesai": r["selesai"],
            "perkiraan": r["perkiraan"], "diambil": r["diambil"]}


def ringkas_jendela(path=None):
    with koneksi(path) as con:
        return _hitung_jendela(con)


# ====================== tugas ======================
def tugas_aktif(path=None):
    with koneksi(path) as con:
        return _dict(con.execute(
            "SELECT * FROM tugas WHERE status = 'berjalan' ORDER BY id DESC LIMIT 1").fetchone())


def buat_tugas(chat_id, total_hari, kuota_harian, path=None):
    with koneksi(path) as con:
        cur = con.execute(
            "INSERT INTO tugas (chat_id, mulai, total_hari, kuota_harian) VALUES (?, ?, ?, ?)",
            (chat_id, config.sekarang_str(), total_hari, kuota_harian))
        return cur.lastrowid


def set_chat_id(id_tugas, chat_id, path=None):
    with koneksi(path) as con:
        con.execute("UPDATE tugas SET chat_id = ? WHERE id = ?", (chat_id, id_tugas))


def perpanjang_tugas(id_tugas, total_hari, path=None):
    """Perpanjang target hari tugas aktif tanpa mengubah progress atau data lain.

    ``total_hari`` adalah target total baru, bukan jumlah hari tambahan.
    Kembalikan tugas yang sudah diperbarui, atau ``None`` jika tugas tidak
    aktif atau target baru tidak lebih besar dari target sebelumnya.
    """
    if not isinstance(total_hari, int) or isinstance(total_hari, bool) or total_hari < 1:
        raise ValueError("total_hari harus berupa bilangan bulat positif")
    with koneksi(path) as con:
        tugas = con.execute("SELECT * FROM tugas WHERE id = ?", (id_tugas,)).fetchone()
        if tugas is None or tugas["status"] != "berjalan" or total_hari <= tugas["total_hari"]:
            return None
        con.execute("UPDATE tugas SET total_hari = ? WHERE id = ?", (total_hari, id_tugas))
        return _dict(con.execute("SELECT * FROM tugas WHERE id = ?", (id_tugas,)).fetchone())


def tambah_hari(id_tugas, path=None):
    """Naikkan hari_ke dan kembalikan nilai barunya."""
    with koneksi(path) as con:
        con.execute("UPDATE tugas SET hari_ke = hari_ke + 1 WHERE id = ?", (id_tugas,))
        return con.execute("SELECT hari_ke FROM tugas WHERE id = ?", (id_tugas,)).fetchone()[0]


def tutup_tugas(id_tugas, status="selesai", path=None):
    with koneksi(path) as con:
        con.execute("UPDATE tugas SET status = ? WHERE id = ?", (status, id_tugas))


# ====================== log run ======================
def catat_run(data, path=None):
    with koneksi(path) as con:
        con.execute(
            "INSERT INTO log_run (id_tugas, hari_ke, waktu_mulai, waktu_selesai, repo_diambil, "
            "repo_baru, jumlah_request, sisa_kuota, status, catatan, mode, dihitung) "
            "VALUES (:id_tugas, :hari_ke, :waktu_mulai, :waktu_selesai, :repo_diambil, "
            ":repo_baru, :jumlah_request, :sisa_kuota, :status, :catatan, :mode, :dihitung)",
            data)


def sudah_jalan_hari_ini(id_tugas, hanya_dihitung=True, path=None):
    """Apakah run mode normal sudah terjadi hari ini (zona WIB)?
    hanya_dihitung=True : hanya run yang dihitung sebagai satu hari (untuk perintah manual).
    hanya_dihitung=False: run apa pun, termasuk yang gagal (untuk job otomatis, agar
                          tidak mengulang-ulang saat error)."""
    sql = ("SELECT COUNT(*) FROM log_run WHERE id_tugas = ? AND mode = 'normal' "
           "AND substr(waktu_mulai, 1, 10) = ?")
    if hanya_dihitung:
        sql += " AND dihitung = 1"
    with koneksi(path) as con:
        return con.execute(sql, (id_tugas, config.hari_ini())).fetchone()[0] > 0


def run_terakhir(id_tugas=None, path=None):
    with koneksi(path) as con:
        if id_tugas is None:
            baris = con.execute("SELECT * FROM log_run ORDER BY id DESC LIMIT 1").fetchone()
        else:
            baris = con.execute(
                "SELECT * FROM log_run WHERE id_tugas = ? ORDER BY id DESC LIMIT 1",
                (id_tugas,)).fetchone()
        return _dict(baris)


def status_tugas(path=None):
    """Ringkasan untuk /status."""
    with koneksi(path) as con:
        t = _dict(con.execute("SELECT * FROM tugas ORDER BY id DESC LIMIT 1").fetchone())
        total = con.execute("SELECT COUNT(*) FROM repo").fetchone()[0]
        relevan = con.execute("SELECT COUNT(*) FROM repo WHERE relevan = 1").fetchone()[0]
        jendela = _hitung_jendela(con)
        run = _dict(con.execute(
            "SELECT * FROM log_run ORDER BY id DESC LIMIT 1").fetchone())
    return {
        "ada_tugas": t is not None,
        "status": t["status"] if t else "belum_ada",
        "hari_ke": t["hari_ke"] if t else 0,
        "total_hari": t["total_hari"] if t else config.JUMLAH_HARI,
        "kuota_harian": t["kuota_harian"] if t else config.KUOTA_HARIAN,
        "jumlah_repo": total,
        "jumlah_relevan": relevan,
        "jendela": jendela,
        "jadwal": f"{config.JAM_JADWAL} WIB",
        "run_terakhir": run,
    }
