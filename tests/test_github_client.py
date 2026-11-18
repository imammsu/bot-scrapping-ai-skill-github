import time

import pytest
from requests.exceptions import RequestException

import config
from github_client import GitHubClient, GitHubError, KuotaHabis, parse_repo
from tests.helpers import FakeResp, FakeSession, buat_item


@pytest.fixture
def tidur(monkeypatch):
    """Cegah tidur sungguhan; catat lama tidur yang diminta."""
    catatan = []
    monkeypatch.setattr(time, "sleep", lambda s: catatan.append(s))
    return catatan


def klien_dengan(respons, token="abc"):
    sesi = FakeSession(respons)
    return GitHubClient(token=token, jeda=0, session=sesi), sesi


def header_search(sisa=29, reset_dalam=30):
    return {"x-ratelimit-resource": "search", "x-ratelimit-remaining": str(sisa),
            "x-ratelimit-limit": "30", "x-ratelimit-reset": str(int(time.time()) + reset_dalam)}


def test_parse_repo_memetakan_kolom():
    r = parse_repo(buat_item(7, stars=42))
    assert r["id"] == 7 and r["stars"] == 42 and r["lisensi"] == "MIT"
    assert r["topik"] == "claude-code,skills" and r["diarsipkan"] == 0


def test_parse_repo_tahan_data_kosong():
    r = parse_repo({"id": 1, "full_name": "a/b", "description": None, "language": None,
                    "license": None, "topics": None})
    assert r["deskripsi"] == "" and r["bahasa"] is None and r["lisensi"] is None and r["topik"] == ""


def test_parse_repo_lisensi_noassertion_memakai_nama():
    r = parse_repo(buat_item(1, license={"spdx_id": "NOASSERTION", "name": "Other"}))
    assert r["lisensi"] == "Other"


def test_header_autentikasi_dan_user_agent(tidur):
    klien, sesi = klien_dengan([], token="rahasia")
    assert sesi.headers["Authorization"] == "Bearer rahasia"
    assert "User-Agent" in sesi.headers


def test_cari_repo_sukses_dan_catat_kuota(tidur):
    klien, sesi = klien_dengan([FakeResp(200, {"total_count": 1, "items": []}, header_search(29))])
    data = klien.cari_repo("skills", halaman=2, per_page=100)
    assert data["total_count"] == 1
    assert sesi.panggilan[0][1]["page"] == 2 and sesi.panggilan[0][1]["per_page"] == 100
    assert klien.sisa == 29 and klien.resource == "search"
    assert klien.kuota_aman() is True
    assert "29/30" in klien.ringkas_kuota()


def test_403_dengan_retry_after_menunggu_lalu_berhasil(tidur):
    klien, _ = klien_dengan([FakeResp(403, headers={"retry-after": "3"}),
                             FakeResp(200, {"total_count": 5}, header_search())])
    assert klien.total_count("x") == 5
    assert 4 in tidur  # Retry-After 3 + 1


def test_403_waktu_tunggu_terlalu_lama_menghentikan_run(tidur):
    klien, _ = klien_dengan([FakeResp(403, headers={"retry-after": "500"})])
    with pytest.raises(KuotaHabis):
        klien.total_count("x")


def test_403_terus_menerus_berakhir_kuota_habis(tidur):
    klien, _ = klien_dengan([FakeResp(429, headers={"retry-after": "1"})] * config.MAKS_COBA)
    with pytest.raises(KuotaHabis):
        klien.total_count("x")


def test_5xx_di_retry(tidur):
    klien, sesi = klien_dengan([FakeResp(502), FakeResp(200, {"total_count": 9}, header_search())])
    assert klien.total_count("x") == 9
    assert len(sesi.panggilan) == 2


def test_galat_jaringan_di_retry(tidur):
    klien, _ = klien_dengan([RequestException("putus"),
                             FakeResp(200, {"total_count": 3}, header_search())])
    assert klien.total_count("x") == 3


def test_semua_percobaan_gagal(tidur):
    klien, _ = klien_dengan([RequestException("putus")] * config.MAKS_COBA)
    with pytest.raises(GitHubError):
        klien.total_count("x")


def test_token_ditolak(tidur):
    klien, _ = klien_dengan([FakeResp(401)])
    with pytest.raises(GitHubError, match="GITHUB_TOKEN"):
        klien.total_count("x")


def test_query_invalid_422(tidur):
    klien, _ = klien_dengan([FakeResp(422, {"message": "Validation Failed"})])
    with pytest.raises(GitHubError, match="422"):
        klien.total_count("x")


def test_menunggu_reset_saat_kuota_search_habis(tidur):
    klien, _ = klien_dengan([])
    klien.resource, klien.sisa, klien.reset = "search", 0, int(time.time()) + 5
    klien._tunggu_search()
    assert tidur and tidur[0] > 0


def test_reset_search_terlalu_jauh_menghentikan_run(tidur):
    klien, _ = klien_dengan([])
    klien.resource, klien.sisa, klien.reset = "search", 0, int(time.time()) + 10_000
    with pytest.raises(KuotaHabis):
        klien._tunggu_search()


def test_kuota_per_jam_di_bawah_ambang_tidak_aman(tidur):
    klien, _ = klien_dengan([])
    klien.resource, klien.sisa = "core", config.AMBANG_SISA_KUOTA - 1
    assert klien.kuota_aman() is False
    klien.sisa = config.AMBANG_SISA_KUOTA + 1
    assert klien.kuota_aman() is True
