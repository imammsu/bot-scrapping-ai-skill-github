"""
Inti pengambilan data BERTAHAP.

jalankan_tugas_harian() mengambil jatah satu hari (KUOTA_HARIAN repo, dibulatkan ke kelipatan
PER_PAGE), menyimpan progres di SQLite, lalu berhenti. Besoknya ia melanjutkan dari posisi
terakhir. Setelah JUMLAH_HARI jatah selesai (atau data habis), tugas ditutup.

Dipanggil dari bot (lewat JobQueue) maupun dari CLI (main.py) dengan fungsi yang sama.
"""
import logging
import math
import threading
from dataclasses import dataclass

import config
import db
import jendela
import relevansi
from github_client import GitHubClient, GitHubError, KuotaHabis, parse_repo

log = logging.getLogger(__name__)

_KUNCI = threading.Lock()  # satu run pada satu waktu


@dataclass
class HasilRun:
    status: str = "ok"          # ok / terpotong_kuota / data_habis / error / tidak_ada_data /
                                # sudah_hari_ini / sedang_berjalan
    diambil: int = 0
    baru: int = 0
    request: int = 0
    catatan: str = ""
    sisa_kuota: str = "-"
    hari_ke: int = 0
    total_hari: int = 0
    total_repo: int = 0
    data_habis: bool = False
    tugas_selesai: bool = False
    mode: str = "normal"


def siapkan_jendela(klien=None):
    """Susun jendela pencarian dan simpan ke database. Kembalikan ringkasan jendela."""
    klien = klien or GitHubClient()
    daftar = jendela.susun_jendela(klien)
    db.ganti_jendela(daftar)
    return db.ringkas_jendela()


def _siapkan_repo(item):
    r = parse_repo(item)
    nilai = relevansi.skor(r["full_name"], r["deskripsi"], r["topik"])
    r["skor_relevan"] = nilai
    r["relevan"] = int(relevansi.relevan(nilai))
    return r


def _ambil_data(klien, kuota, waktu):
    """Ambil halaman demi halaman sampai kuota terpenuhi, kuota API menipis, atau data habis."""
    h = HasilRun()
    awal = klien.jumlah_request
    halaman_maks = max(1, math.ceil(kuota / config.PER_PAGE))

    for _ in range(halaman_maks):
        j = db.jendela_berikutnya()
        if j is None:
            break
        if klien.jumlah_request - awal >= config.MAKS_REQUEST_PER_RUN:
            h.status, h.catatan = "terpotong_kuota", "Batas request per run tercapai."
            break
        if not klien.kuota_aman():
            h.status, h.catatan = "terpotong_kuota", "Sisa kuota API di bawah ambang."
            break

        query = jendela.buat_query(j["dari"], j["sampai"])
        try:
            data = klien.cari_repo(query, halaman=j["halaman_next"], per_page=config.PER_PAGE)
        except KuotaHabis as e:
            h.status, h.catatan = "terpotong_kuota", str(e)
            break
        except GitHubError as e:
            h.status, h.catatan = "error", str(e)
            break

        items = data.get("items", [])
        repos = [_siapkan_repo(i) for i in items]
        halaman_terakhir = max(1, math.ceil(
            min(j["total"], config.BATAS_HASIL_SEARCH) / config.PER_PAGE))
        selesai = j["halaman_next"] >= halaman_terakhir or len(items) < config.PER_PAGE
        baru = db.simpan_halaman(repos, j["id"], j["halaman_next"] + 1,
                                 "selesai" if selesai else "berjalan", waktu)
        h.diambil += len(repos)
        h.baru += baru
        log.info("Jendela %s..%s halaman %d: %d repo (%d baru)",
                 j["dari"], j["sampai"], j["halaman_next"], len(repos), baru)

    h.request = klien.jumlah_request - awal
    h.sisa_kuota = klien.ringkas_kuota()
    h.data_habis = db.jendela_berikutnya() is None
    if h.status == "ok" and h.data_habis:
        h.status = "data_habis"
    return h


def jalankan_tugas_harian(mode="normal", otomatis=False, klien=None):
    """Jalankan satu jatah harian untuk tugas yang sedang aktif.

    mode="normal": jatah penuh, dihitung sebagai satu hari.
    mode="uji"   : hanya satu halaman, TIDAK dihitung sebagai hari (untuk demo).
    otomatis=True: dipanggil job terjadwal; tidak mengulang jika hari ini sudah dicoba
                   (walau gagal). Perintah manual hanya diblokir jika jatah hari ini
                   sudah berhasil dihitung.

    Mengembalikan HasilRun, atau None jika tidak ada tugas aktif.
    """
    tugas = db.tugas_aktif()
    if tugas is None:
        return None

    dasar = dict(mode=mode, hari_ke=tugas["hari_ke"], total_hari=tugas["total_hari"])
    if not _KUNCI.acquire(blocking=False):
        return HasilRun(status="sedang_berjalan", **dasar)
    try:
        if mode == "normal" and db.sudah_jalan_hari_ini(tugas["id"], hanya_dihitung=not otomatis):
            return HasilRun(status="sudah_hari_ini", **dasar)

        klien = klien or GitHubClient()
        mulai = config.sekarang_str()
        kuota = config.PER_PAGE if mode == "uji" else tugas["kuota_harian"]

        hasil = None
        if db.ringkas_jendela()["jumlah"] == 0:
            try:
                siapkan_jendela(klien)
            except GitHubError as e:  # termasuk KuotaHabis
                hasil = HasilRun(status="error", catatan=f"Gagal menyusun jendela: {e}")
            else:
                if db.ringkas_jendela()["jumlah"] == 0:
                    hasil = HasilRun(status="tidak_ada_data", data_habis=True,
                                     catatan="Tidak ada repo yang cocok dengan query.")
        if hasil is None:
            hasil = _ambil_data(klien, kuota, mulai)

        hasil.mode = mode
        dihitung = mode == "normal" and (hasil.diambil > 0 or hasil.data_habis)
        hari_ke = tugas["hari_ke"]
        if dihitung:
            hari_ke = db.tambah_hari(tugas["id"])
            if hari_ke >= tugas["total_hari"] or hasil.data_habis:
                db.tutup_tugas(tugas["id"], "selesai")
                hasil.tugas_selesai = True
        hasil.hari_ke, hasil.total_hari = hari_ke, tugas["total_hari"]
        hasil.total_repo = db.jumlah_repo()

        db.catat_run({
            "id_tugas": tugas["id"], "hari_ke": hari_ke,
            "waktu_mulai": mulai, "waktu_selesai": config.sekarang_str(),
            "repo_diambil": hasil.diambil, "repo_baru": hasil.baru,
            "jumlah_request": hasil.request, "sisa_kuota": hasil.sisa_kuota,
            "status": hasil.status, "catatan": hasil.catatan,
            "mode": mode, "dihitung": int(dihitung),
        })
        log.info("Run %s selesai: %s, diambil %d (baru %d), hari %d/%d",
                 mode, hasil.status, hasil.diambil, hasil.baru, hari_ke, tugas["total_hari"])
        return hasil
    finally:
        _KUNCI.release()
