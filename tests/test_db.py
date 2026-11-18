import pytest

import config
import db
from tests.helpers import atur_hari, buat_item
import github_client


def repo(i, **kw):
    r = github_client.parse_repo(buat_item(i, **kw))
    r.update(skor_relevan=10, relevan=1)
    return r


def siapkan_jendela():
    db.ganti_jendela([{"dari": "2025-01-01", "sampai": "2025-03-31", "total": 250}])
    return db.jendela_berikutnya()["id"]


def test_simpan_halaman_tanpa_duplikat(basis_data):
    id_j = siapkan_jendela()
    assert db.simpan_halaman([repo(1), repo(2)], id_j, 2, "berjalan", "2026-11-14T07:00:00") == 2
    # halaman yang sama terambil lagi: tidak menambah baris, hanya memperbarui
    assert db.simpan_halaman([repo(1, stars=99), repo(2)], id_j, 2, "berjalan", "2026-11-15T07:00:00") == 0
    assert db.jumlah_repo() == 2
    df = db.baca_repo()
    assert int(df.loc[df["id"] == 1, "stars"].iloc[0]) == 99
    assert df.loc[df["id"] == 1, "pertama_dilihat"].iloc[0] == "2026-11-14T07:00:00"
    assert df.loc[df["id"] == 1, "terakhir_dilihat"].iloc[0] == "2026-11-15T07:00:00"


def test_riwayat_stars_bertambah_per_run(basis_data):
    id_j = siapkan_jendela()
    db.simpan_halaman([repo(1, stars=5)], id_j, 2, "berjalan", "2026-11-14T07:00:00")
    db.simpan_halaman([repo(1, stars=8)], id_j, 2, "berjalan", "2026-11-15T07:00:00")
    r = db.riwayat()
    assert sorted(r["stars"].tolist()) == [5, 8]


def test_progres_jendela_diperbarui_bersama_data(basis_data):
    id_j = siapkan_jendela()
    db.simpan_halaman([repo(1), repo(2)], id_j, 2, "berjalan")
    j = db.jendela_berikutnya()
    assert j["halaman_next"] == 2 and j["diambil"] == 2 and j["status"] == "berjalan"
    db.simpan_halaman([repo(3)], id_j, 3, "selesai")
    assert db.jendela_berikutnya() is None
    assert db.ringkas_jendela()["selesai"] == 1


def test_ringkas_jendela_memakai_batas_1000(basis_data):
    db.ganti_jendela([{"dari": "a", "sampai": "b", "total": 5000},
                      {"dari": "c", "sampai": "d", "total": 40}])
    assert db.ringkas_jendela()["perkiraan"] == 1040


def test_siklus_tugas(basis_data):
    assert db.tugas_aktif() is None
    id_t = db.buat_tugas(123, 4, 500)
    assert db.tugas_aktif()["chat_id"] == 123
    assert db.tambah_hari(id_t) == 1
    db.set_chat_id(id_t, 456)
    assert db.tugas_aktif()["chat_id"] == 456
    db.tutup_tugas(id_t, "selesai")
    assert db.tugas_aktif() is None


def data_run(id_t, dihitung, mode="normal", status="ok"):
    return {"id_tugas": id_t, "hari_ke": 1, "waktu_mulai": config.sekarang_str(),
            "waktu_selesai": config.sekarang_str(), "repo_diambil": 10, "repo_baru": 10,
            "jumlah_request": 1, "sisa_kuota": "-", "status": status, "catatan": "",
            "mode": mode, "dihitung": int(dihitung)}


def test_sudah_jalan_hari_ini(basis_data, monkeypatch):
    atur_hari(monkeypatch, "2026-11-14")
    id_t = db.buat_tugas(1, 4, 500)
    assert not db.sudah_jalan_hari_ini(id_t)
    db.catat_run(data_run(id_t, dihitung=False, status="error"))
    assert not db.sudah_jalan_hari_ini(id_t, hanya_dihitung=True)    # gagal tidak dihitung
    assert db.sudah_jalan_hari_ini(id_t, hanya_dihitung=False)       # tetapi sudah dicoba
    db.catat_run(data_run(id_t, dihitung=True))
    assert db.sudah_jalan_hari_ini(id_t, hanya_dihitung=True)
    atur_hari(monkeypatch, "2026-11-15")
    assert not db.sudah_jalan_hari_ini(id_t, hanya_dihitung=False)   # hari baru


def test_run_mode_uji_tidak_memblokir(basis_data, monkeypatch):
    atur_hari(monkeypatch, "2026-11-14")
    id_t = db.buat_tugas(1, 4, 500)
    db.catat_run(data_run(id_t, dihitung=False, mode="uji"))
    assert not db.sudah_jalan_hari_ini(id_t, hanya_dihitung=False)


def test_cari_dan_teratas_hanya_repo_relevan(basis_data):
    id_j = siapkan_jendela()
    tak_relevan = repo(3, stars=1000)
    tak_relevan["relevan"] = 0
    db.simpan_halaman([repo(1, stars=5), repo(2, stars=50), tak_relevan], id_j, 2, "berjalan")
    assert db.teratas(5)["stars"].tolist() == [50, 5]
    assert len(db.cari("skills-2")) == 1
    assert db.jumlah_repo() == 3 and db.jumlah_repo(hanya_relevan=True) == 2


def test_cari_aman_dari_sql_injection(basis_data):
    id_j = siapkan_jendela()
    db.simpan_halaman([repo(1)], id_j, 2, "berjalan")
    assert db.cari("'; DROP TABLE repo; --").empty
    assert db.jumlah_repo() == 1


def test_status_tugas_tanpa_dan_dengan_tugas(basis_data):
    assert db.status_tugas()["ada_tugas"] is False
    db.buat_tugas(1, 4, 500)
    s = db.status_tugas()
    assert s["ada_tugas"] and s["status"] == "berjalan" and s["total_hari"] == 4


def test_perpanjang_tugas_tidak_mengubah_progress_lain(basis_data):
    id_tugas = db.buat_tugas(1, 4, 500)
    db.tambah_hari(id_tugas)

    diperbarui = db.perpanjang_tugas(id_tugas, 7)

    assert diperbarui["total_hari"] == 7
    assert diperbarui["hari_ke"] == 1
    assert diperbarui["kuota_harian"] == 500
    assert db.perpanjang_tugas(id_tugas, 7) is None
    assert db.perpanjang_tugas(id_tugas, 6) is None


def test_perpanjang_tugas_hanya_untuk_tugas_berjalan(basis_data):
    id_tugas = db.buat_tugas(1, 4, 500)
    db.tutup_tugas(id_tugas)

    assert db.perpanjang_tugas(id_tugas, 7) is None


def test_perpanjang_tugas_menolak_jumlah_tidak_valid(basis_data):
    id_tugas = db.buat_tugas(1, 4, 500)

    for nilai in (0, -1, True, "7"):
        with pytest.raises(ValueError):
            db.perpanjang_tugas(id_tugas, nilai)
