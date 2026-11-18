"""
Teks balasan bot. Fungsi murni (tanpa Telegram) agar mudah diuji dengan pytest.
"""
BANTUAN = (
    "Perintah yang tersedia:\n"
    "/mulai - mulai tugas pengambilan data bertahap (cukup sekali, lalu otomatis)\n"
    "/status - progres tugas\n"
    "/perpanjang <jumlah_hari> - ubah target total hari tugas aktif\n"
    "/scrape_sekarang - jalankan jatah hari ini sekarang (demo)\n"
    "/scrape_sekarang uji - uji coba 1 halaman, tidak dihitung sebagai hari\n"
    "/berhenti - batalkan tugas dan jadwal\n"
    "/ringkas - ringkasan data dan temuan\n"
    "/cari <kata> - cari repo berdasarkan nama atau deskripsi\n"
    "/top - 5 repo dengan stars terbanyak\n"
    "/grafik - kirim grafik analisis\n"
    "/excel - kirim seluruh data repo sebagai file Excel\n"
    "/help - bantuan ini"
)

LABEL_STATUS = {
    "ok": "Selesai normal",
    "terpotong_kuota": "Terpotong rate limit; dilanjutkan pada jadwal berikutnya",
    "data_habis": "Semua data yang cocok dengan query sudah diambil",
    "error": "Terjadi kesalahan",
    "tidak_ada_data": "Tidak ada repo yang cocok dengan query",
    "sudah_hari_ini": "Jatah hari ini sudah dijalankan",
    "sedang_berjalan": "Pengambilan data sedang berjalan",
}


def potong(teks, panjang):
    teks = (teks or "").replace("\n", " ").strip()
    return teks if len(teks) <= panjang else teks[: panjang - 3].rstrip() + "..."


def format_notifikasi_run(h):
    """Notifikasi setelah satu run. h: HasilRun (atau objek dengan atribut yang sama)."""
    if h.mode == "uji":
        judul = "Uji coba selesai (tidak dihitung sebagai hari)"
    elif h.status in ("sudah_hari_ini", "sedang_berjalan"):
        judul = LABEL_STATUS[h.status]
    else:
        judul = f"Hari {h.hari_ke}/{h.total_hari} selesai"
    baris = [judul]
    if h.status not in ("sudah_hari_ini", "sedang_berjalan"):
        baris += [
            f"Diambil       : {h.diambil} repo ({h.baru} baru)",
            f"Total di DB   : {h.total_repo}",
            f"Request API   : {h.request}",
            f"Sisa kuota    : {h.sisa_kuota}",
            f"Status        : {LABEL_STATUS.get(h.status, h.status)}",
        ]
    if h.catatan:
        baris.append(f"Catatan       : {potong(h.catatan, 200)}")
    if h.tugas_selesai:
        baris.append("\nTugas selesai. Laporan akhir menyusul.")
    return "\n".join(baris)


def format_status(s):
    if not s["ada_tugas"]:
        return "Belum ada tugas. Kirim /mulai untuk memulai pengambilan data bertahap."
    j = s["jendela"]
    label = {"berjalan": "berjalan", "selesai": "selesai", "dibatalkan": "dibatalkan"}.get(
        s["status"], s["status"])
    baris = [
        "Status PantauSkill",
        f"Tugas          : {label}",
        f"Hari           : {s['hari_ke']}/{s['total_hari']}",
        f"Kuota harian   : {s['kuota_harian']} repo",
        f"Repo terkumpul : {s['jumlah_repo']} ({s['jumlah_relevan']} relevan)",
        f"Jendela        : {j['selesai']}/{j['jumlah']} selesai "
        f"(perkiraan {j['perkiraan']} repo, terambil {j['diambil']})",
    ]
    if s["status"] == "berjalan":
        baris.append(f"Jadwal         : setiap hari pukul {s['jadwal']}")
    run = s.get("run_terakhir")
    if run:
        baris.append(f"Run terakhir   : {run['waktu_mulai'][:16].replace('T', ' ')} "
                     f"({run['mode']}, {run['status']}, {run['repo_diambil']} repo)")
    return "\n".join(baris)


def format_ringkasan(r, temuan, judul="Ringkasan data PantauSkill"):
    baris = [
        judul,
        f"Repo relevan      : {r['jumlah_repo']}",
        f"Bahasa terdeteksi : {r['jumlah_bahasa']}",
        f"Stars (median)    : {r['stars_median']:.0f}",
        f"Stars (rata-rata) : {r['stars_rata']:.0f}",
        f"Stars tertinggi   : {r['stars_maks']}",
        f"Berlisensi        : {r['persen_berlisensi']}%",
        "",
        "Temuan:",
    ]
    baris += [f"{i}. {t}" for i, t in enumerate(temuan, 1)]
    return "\n".join(baris)


def format_daftar_repo(df, judul):
    """df berisi kolom full_name, deskripsi, bahasa, stars."""
    if df.empty:
        return "Tidak ada repo yang cocok."
    baris = [judul]
    for i, b in enumerate(df.itertuples(), 1):
        bahasa = b.bahasa if isinstance(b.bahasa, str) and b.bahasa else "-"
        baris.append(f"{i}. {b.full_name} - {b.stars} stars [{bahasa}]")
        if b.deskripsi:
            baris.append(f"   {potong(b.deskripsi, 90)}")
    return "\n".join(baris)
