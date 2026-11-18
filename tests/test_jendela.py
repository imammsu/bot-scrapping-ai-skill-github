from datetime import date

import jendela
from tests.helpers import FakeKlien


def test_buat_query_memuat_semua_bagian():
    q = jendela.buat_query("2025-01-01", "2025-02-01", dasar="skills fork:false", stars_min=5)
    assert q == "skills fork:false stars:>=5 created:2025-01-01..2025-02-01"


def test_belah_tanpa_celah_dan_tumpang_tindih():
    kiri, kanan = jendela.belah("2025-01-01", "2025-01-10")
    assert kiri[0] == "2025-01-01" and kanan[1] == "2025-01-10"
    assert date.fromisoformat(kanan[0]) - date.fromisoformat(kiri[1]) == (date(2025, 1, 2) - date(2025, 1, 1))


def test_belah_satu_hari_mengembalikan_none():
    assert jendela.belah("2025-01-01", "2025-01-01") is None


def test_susun_jendela_semua_di_bawah_batas_dan_menutup_seluruh_rentang():
    # 10 repo per hari: rentang setahun harus dibelah sampai <= 1000 per jendela
    def total(a, b):
        return ((date.fromisoformat(b) - date.fromisoformat(a)).days + 1) * 10

    klien = FakeKlien(fungsi_total=total)
    hasil = jendela.susun_jendela(klien, "2025-01-01", "2025-12-31", batas=1000)

    assert len(hasil) > 1
    assert all(j["total"] <= 1000 for j in hasil)
    assert hasil[0]["dari"] == "2025-01-01" and hasil[-1]["sampai"] == "2025-12-31"
    for sebelum, sesudah in zip(hasil, hasil[1:]):
        assert (date.fromisoformat(sesudah["dari"]) - date.fromisoformat(sebelum["sampai"])).days == 1
    assert sum(j["total"] for j in hasil) == 365 * 10


def test_susun_jendela_membuang_rentang_kosong():
    klien = FakeKlien(fungsi_total=lambda a, b: 0)
    assert jendela.susun_jendela(klien, "2025-01-01", "2025-03-01") == []


def test_satu_hari_melebihi_batas_tetap_dimasukkan():
    klien = FakeKlien(fungsi_total=lambda a, b: 5000)
    hasil = jendela.susun_jendela(klien, "2025-01-01", "2025-01-01", batas=1000)
    assert hasil == [{"dari": "2025-01-01", "sampai": "2025-01-01", "total": 5000}]
