import datetime

import pytest

pytest.importorskip("telegram")

import bot  # noqa: E402
import config  # noqa: E402
import db  # noqa: E402


def test_aplikasi_terbentuk_dengan_job_queue():
    app = bot.buat_aplikasi("123456:TOKEN-UJI")
    assert app.job_queue is not None
    assert sum(len(v) for v in app.handlers.values()) >= 10


def test_daftarkan_job_tidak_ganda_dan_bisa_dihapus():
    app = bot.buat_aplikasi("123456:TOKEN-UJI")
    jq = app.job_queue
    bot.daftarkan_job(jq, 42)
    bot.daftarkan_job(jq, 42)  # dipanggil ulang: tidak boleh menggandakan
    assert len(jq.get_jobs_by_name("harian-42")) == 1
    assert len(jq.get_jobs_by_name("pengaman")) == 1
    bot.hapus_job(jq, 42)
    assert not [j for j in jq.get_jobs_by_name("harian-42") if not j.removed]


def test_jam_jadwal_dan_sudah_lewat(monkeypatch):
    monkeypatch.setattr(config, "JAM_JADWAL", "07:30")
    assert bot.jam_jadwal() == (7, 30)
    wib = config.WIB
    monkeypatch.setattr(config, "sekarang", lambda: datetime.datetime(2026, 11, 14, 7, 29, tzinfo=wib))
    assert not bot.sudah_lewat_jadwal()
    monkeypatch.setattr(config, "sekarang", lambda: datetime.datetime(2026, 11, 14, 7, 30, tzinfo=wib))
    assert bot.sudah_lewat_jadwal()


def test_pulihkan_mendaftarkan_job_untuk_tugas_aktif(basis_data):
    app = bot.buat_aplikasi("123456:TOKEN-UJI")
    bot.pulihkan(app)
    assert not app.job_queue.get_jobs_by_name("harian-77")  # belum ada tugas
    db.buat_tugas(77, 4, 500)
    bot.pulihkan(app)
    assert len(app.job_queue.get_jobs_by_name("harian-77")) == 1


def test_tugas_cli_tanpa_chat_tidak_didaftarkan(basis_data):
    app = bot.buat_aplikasi("123456:TOKEN-UJI")
    db.buat_tugas(0, 4, 500)
    bot.pulihkan(app)
    assert not app.job_queue.get_jobs_by_name("harian-0")
