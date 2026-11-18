"""Bantuan untuk tes: data palsu dan pengganti GitHubClient tanpa internet."""
import json
import re

import config
from github_client import GitHubError, KuotaHabis


def buat_item(i, desk="Agent skills for Claude Code", bahasa="Python", stars=10,
              dibuat="2025-06-15T10:00:00Z", dorong="2026-10-01T10:00:00Z", **lain):
    """Satu item JSON seperti hasil search GitHub."""
    item = {
        "id": i, "full_name": f"user{i}/skills-{i}",
        "html_url": f"https://github.com/user{i}/skills-{i}",
        "description": desk, "language": bahasa, "topics": ["claude-code", "skills"],
        "license": {"spdx_id": "MIT", "name": "MIT License"},
        "stargazers_count": stars, "forks_count": 1, "open_issues_count": 0,
        "created_at": dibuat, "pushed_at": dorong, "archived": False,
    }
    item.update(lain)
    return item


def atur_hari(monkeypatch, tanggal):
    """Pura-pura hari ini = tanggal (ISO)."""
    monkeypatch.setattr(config, "sekarang_str", lambda: f"{tanggal}T07:00:00+07:00")
    monkeypatch.setattr(config, "hari_ini", lambda: tanggal)


class FakeKlien:
    """Pengganti GitHubClient: tiap jendela (rentang created:) punya total repo tertentu."""

    def __init__(self, totals=None, fungsi_total=None, kuota_habis_pada=None, error_pada=None):
        self.totals = totals or {}           # {(dari, sampai): total}
        self.fungsi_total = fungsi_total     # fungsi (dari, sampai) -> total
        self.kuota_habis_pada = kuota_habis_pada
        self.error_pada = error_pada
        self.jumlah_request = 0
        self.panggilan_cari = 0
        self._indeks = {}

    @staticmethod
    def _rentang(q):
        m = re.search(r"created:(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})", q)
        return m.group(1), m.group(2)

    def _total(self, a, b):
        if self.fungsi_total:
            return self.fungsi_total(a, b)
        return self.totals.get((a, b), 0)

    def total_count(self, q):
        self.jumlah_request += 1
        return self._total(*self._rentang(q))

    def cari_repo(self, q, halaman=1, per_page=100, **_):
        self.jumlah_request += 1
        self.panggilan_cari += 1
        if self.kuota_habis_pada == self.panggilan_cari:
            raise KuotaHabis("kuota habis (palsu)")
        if self.error_pada == self.panggilan_cari:
            raise GitHubError("galat palsu")
        a, b = self._rentang(q)
        total = self._total(a, b)
        indeks = self._indeks.setdefault((a, b), len(self._indeks))
        awal = (halaman - 1) * per_page
        jumlah = max(0, min(per_page, min(total, 1000) - awal))
        return {"total_count": total,
                "items": [buat_item(indeks * 100000 + awal + k + 1) for k in range(jumlah)]}

    def kuota_aman(self):
        return True

    def ringkas_kuota(self):
        return "25/30 per menit"


class FakeResp:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code = status
        self._data = data if data is not None else {}
        self.headers = headers or {}
        self.text = json.dumps(self._data)

    def json(self):
        return self._data


class FakeSession:
    """Pengganti requests.Session: mengembalikan respons berurutan."""

    def __init__(self, respons):
        self.respons = list(respons)
        self.headers = {}
        self.panggilan = []

    def get(self, url, params=None, timeout=None):
        self.panggilan.append((url, params))
        r = self.respons.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
