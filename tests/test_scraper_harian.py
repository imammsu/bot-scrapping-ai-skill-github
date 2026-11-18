import config
import db
import scraper_harian as sh
from tests.helpers import FakeKlien, atur_hari

A = ("2025-01-01", "2025-03-31")
B = ("2025-04-01", "2025-06-30")


def siapkan(kuota=200, total_hari=4, totals=None):
    totals = totals or {A: 250, B: 150}
    db.ganti_jendela([{"dari": a, "sampai": b, "total": t} for (a, b), t in totals.items()])
    db.buat_tugas(1, total_hari, kuota)
    return FakeKlien(totals=totals)


def test_tanpa_tugas_mengembalikan_none(basis_data):
    assert sh.jalankan_tugas_harian(klien=FakeKlien()) is None


def test_bertahap_per_hari_tanpa_duplikat_dan_berhenti_saat_data_habis(basis_data, monkeypatch):
    klien = siapkan(kuota=200)

    atur_hari(monkeypatch, "2026-11-14")
    h1 = sh.jalankan_tugas_harian(klien=klien)
    assert (h1.status, h1.diambil, h1.hari_ke) == ("ok", 200, 1)
    assert not h1.tugas_selesai

    atur_hari(monkeypatch, "2026-11-15")
    h2 = sh.jalankan_tugas_harian(klien=klien)
    assert (h2.diambil, h2.hari_ke) == (150, 2)   # sisa jendela A (50) + halaman 1 jendela B (100)

    atur_hari(monkeypatch, "2026-11-16")
    h3 = sh.jalankan_tugas_harian(klien=klien)
    assert h3.diambil == 50 and h3.data_habis and h3.status == "data_habis"
    assert h3.tugas_selesai and db.tugas_aktif() is None

    assert db.jumlah_repo() == 400          # 250 + 150, tidak ada duplikat
    assert db.ringkas_jendela()["selesai"] == 2


def test_tugas_selesai_setelah_jumlah_hari_tercapai(basis_data, monkeypatch):
    klien = siapkan(kuota=100, total_hari=2, totals={A: 900})
    atur_hari(monkeypatch, "2026-11-14")
    assert not sh.jalankan_tugas_harian(klien=klien).tugas_selesai
    atur_hari(monkeypatch, "2026-11-15")
    h = sh.jalankan_tugas_harian(klien=klien)
    assert h.tugas_selesai and h.hari_ke == 2 and not h.data_habis
    assert db.jumlah_repo() == 200


def test_manual_kedua_di_hari_yang_sama_diblokir(basis_data, monkeypatch):
    atur_hari(monkeypatch, "2026-11-14")
    klien = siapkan()
    sh.jalankan_tugas_harian(klien=klien)
    h = sh.jalankan_tugas_harian(klien=klien)
    assert h.status == "sudah_hari_ini" and h.diambil == 0
    assert db.tugas_aktif()["hari_ke"] == 1


def test_mode_uji_satu_halaman_dan_tidak_dihitung(basis_data, monkeypatch):
    atur_hari(monkeypatch, "2026-11-14")
    klien = siapkan(kuota=500)
    h = sh.jalankan_tugas_harian(mode="uji", klien=klien)
    assert h.diambil == config.PER_PAGE and h.mode == "uji"
    assert db.tugas_aktif()["hari_ke"] == 0
    # uji tidak memblokir jatah normal hari itu
    assert sh.jalankan_tugas_harian(klien=klien).status != "sudah_hari_ini"


def test_kuota_habis_di_tengah_run_menyimpan_yang_sudah_didapat(basis_data, monkeypatch):
    atur_hari(monkeypatch, "2026-11-14")
    klien = siapkan(kuota=500, totals={A: 500})
    klien.kuota_habis_pada = 2
    h = sh.jalankan_tugas_harian(klien=klien)
    assert h.status == "terpotong_kuota" and h.diambil == 100
    assert db.jumlah_repo() == 100 and h.hari_ke == 1     # ada data, jadi hari dihitung
    assert db.jendela_berikutnya()["halaman_next"] == 2   # besok lanjut dari halaman 2


def test_error_tanpa_data_tidak_menghabiskan_hari(basis_data, monkeypatch):
    atur_hari(monkeypatch, "2026-11-14")
    klien = siapkan(totals={A: 500})
    klien.error_pada = 1
    h = sh.jalankan_tugas_harian(klien=klien, otomatis=True)
    assert h.status == "error" and h.diambil == 0 and h.hari_ke == 0
    assert db.tugas_aktif()["hari_ke"] == 0
    # job otomatis tidak mengulang pada hari yang sama, tetapi perintah manual boleh mencoba lagi
    assert sh.jalankan_tugas_harian(klien=FakeKlien(totals={A: 500}), otomatis=True).status == "sudah_hari_ini"
    assert sh.jalankan_tugas_harian(klien=FakeKlien(totals={A: 500})).status == "ok"


def test_batas_request_per_run(basis_data, monkeypatch):
    atur_hari(monkeypatch, "2026-11-14")
    monkeypatch.setattr(config, "MAKS_REQUEST_PER_RUN", 1)
    klien = siapkan(kuota=500, totals={A: 500})
    h = sh.jalankan_tugas_harian(klien=klien)
    assert h.status == "terpotong_kuota" and h.diambil == 100 and h.request == 1


def test_jendela_disusun_otomatis_jika_belum_ada(basis_data, monkeypatch):
    atur_hari(monkeypatch, "2026-11-14")
    monkeypatch.setattr(config, "TANGGAL_MULAI_CARI", "2025-01-01")
    db.buat_tugas(1, 4, 100)
    klien = FakeKlien(fungsi_total=lambda a, b: 120)
    h = sh.jalankan_tugas_harian(klien=klien)
    assert h.diambil == 100 and db.ringkas_jendela()["jumlah"] == 1


def test_tidak_ada_data_menutup_tugas(basis_data, monkeypatch):
    atur_hari(monkeypatch, "2026-11-14")
    db.buat_tugas(1, 4, 100)
    h = sh.jalankan_tugas_harian(klien=FakeKlien(fungsi_total=lambda a, b: 0))
    assert h.status == "tidak_ada_data" and h.tugas_selesai


def test_siapkan_jendela(basis_data, monkeypatch):
    monkeypatch.setattr(config, "TANGGAL_MULAI_CARI", "2025-01-01")
    ringkas = sh.siapkan_jendela(FakeKlien(fungsi_total=lambda a, b: 300))
    assert ringkas["jumlah"] == 1 and ringkas["perkiraan"] == 300


def test_repo_diberi_skor_relevansi(basis_data, monkeypatch):
    atur_hari(monkeypatch, "2026-11-14")
    klien = siapkan(kuota=100, totals={A: 100})
    sh.jalankan_tugas_harian(klien=klien)
    df = db.baca_repo()
    assert (df["relevan"] == 1).all() and (df["skor_relevan"] >= config.AMBANG_RELEVAN).all()


def test_dua_run_bersamaan_ditolak(basis_data):
    siapkan()
    assert sh._KUNCI.acquire(blocking=False)
    try:
        assert sh.jalankan_tugas_harian(klien=FakeKlien()).status == "sedang_berjalan"
    finally:
        sh._KUNCI.release()
