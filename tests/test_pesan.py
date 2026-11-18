from types import SimpleNamespace

import pandas as pd

import pesan


def hasil(**kw):
    dasar = dict(status="ok", diambil=500, baru=480, request=5, catatan="", sisa_kuota="25/30 per menit",
                 hari_ke=2, total_hari=4, total_repo=1000, tugas_selesai=False, mode="normal")
    dasar.update(kw)
    return SimpleNamespace(**dasar)


def test_notifikasi_run_normal():
    t = pesan.format_notifikasi_run(hasil())
    assert "Hari 2/4 selesai" in t and "500 repo (480 baru)" in t and "1000" in t


def test_notifikasi_mode_uji():
    assert "tidak dihitung" in pesan.format_notifikasi_run(hasil(mode="uji"))


def test_notifikasi_terpotong_dan_selesai():
    t = pesan.format_notifikasi_run(hasil(status="terpotong_kuota", catatan="Kena rate limit",
                                          tugas_selesai=True))
    assert "dilanjutkan" in t and "Kena rate limit" in t and "Tugas selesai" in t


def test_notifikasi_sudah_hari_ini_ringkas():
    t = pesan.format_notifikasi_run(hasil(status="sudah_hari_ini"))
    assert "sudah dijalankan" in t and "Diambil" not in t


def status(**kw):
    dasar = {"ada_tugas": True, "status": "berjalan", "hari_ke": 1, "total_hari": 4,
             "kuota_harian": 500, "jumlah_repo": 500, "jumlah_relevan": 450,
             "jendela": {"jumlah": 12, "selesai": 3, "perkiraan": 9000, "diambil": 500},
             "jadwal": "07:00 WIB",
             "run_terakhir": {"waktu_mulai": "2026-11-14T07:00:01+07:00", "mode": "normal",
                              "status": "ok", "repo_diambil": 500}}
    dasar.update(kw)
    return dasar


def test_status_berjalan():
    t = pesan.format_status(status())
    assert "1/4" in t and "3/12" in t and "07:00 WIB" in t and "2026-11-14 07:00" in t


def test_status_tanpa_tugas():
    assert "/mulai" in pesan.format_status({"ada_tugas": False})


def test_status_selesai_tidak_menampilkan_jadwal():
    assert "Jadwal" not in pesan.format_status(status(status="selesai"))


def test_format_daftar_repo_dan_pemotongan():
    df = pd.DataFrame([{"full_name": "a/b", "deskripsi": "x" * 300, "bahasa": None, "stars": 7}])
    t = pesan.format_daftar_repo(df, "Top:")
    assert "a/b - 7 stars [-]" in t and "..." in t
    assert "Tidak ada" in pesan.format_daftar_repo(df.iloc[0:0], "Top:")


def test_ringkasan_memuat_temuan():
    r = {"jumlah_repo": 10, "jumlah_bahasa": 3, "stars_median": 5.0, "stars_rata": 6.2,
         "stars_maks": 40, "persen_berlisensi": 80.0}
    t = pesan.format_ringkasan(r, ["Temuan satu.", "Temuan dua."])
    assert "1. Temuan satu." in t and "2. Temuan dua." in t
