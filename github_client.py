"""
Lapisan 1: PENGAMBILAN DATA dari GitHub REST API.

Memakai API resmi (bukan scraping HTML): datanya JSON, batasnya jelas, dan
sisa kuota dapat dibaca dari header respons.

Perilaku penting:
- Request dikirim berurutan dengan jeda (tidak paralel) agar aman dari secondary rate limit.
- Search API punya kuota per menit (10 tanpa token, 30 dengan token). Jika sisa kuota
  habis, klien menunggu sampai reset (selama tidak terlalu lama).
- 403/429 dihormati lewat header Retry-After atau X-RateLimit-Reset, bukan retry cepat.
- Galat jaringan dan 5xx di-retry dengan backoff eksponensial.
"""
import logging
import random
import time

import requests
from requests.exceptions import RequestException

import config

log = logging.getLogger(__name__)


class GitHubError(Exception):
    """Kesalahan umum saat memanggil GitHub API."""


class KuotaHabis(GitHubError):
    """Rate limit tercapai dan waktu tunggu terlalu lama. Run dihentikan, progres aman."""


# ---------- Fungsi murni: ubah JSON GitHub menjadi baris data bersih ----------
def parse_repo(item):
    """Satu item hasil pencarian -> dict dengan nama kolom proyek ini."""
    lisensi = item.get("license") or {}
    nama_lisensi = lisensi.get("spdx_id")
    if nama_lisensi in (None, "NOASSERTION"):
        nama_lisensi = lisensi.get("name")
    return {
        "id": item["id"],
        "full_name": item["full_name"],
        "url": item.get("html_url", ""),
        "deskripsi": (item.get("description") or "").strip(),
        "bahasa": item.get("language"),
        "topik": ",".join(item.get("topics") or []),
        "lisensi": nama_lisensi,
        "stars": item.get("stargazers_count", 0),
        "forks": item.get("forks_count", 0),
        "open_issues": item.get("open_issues_count", 0),
        "dibuat": item.get("created_at"),
        "push_terakhir": item.get("pushed_at"),
        "diarsipkan": int(bool(item.get("archived"))),
    }


# ---------- Klien: urusan jaringan ----------
class GitHubClient:
    def __init__(self, token=None, jeda=None, session=None):
        self.token = config.GITHUB_TOKEN if token is None else token
        self.jeda = config.JEDA_DETIK if jeda is None else jeda
        self.session = session or requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "User-Agent": config.USER_AGENT,
        })
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"
        else:
            log.warning("GITHUB_TOKEN kosong: kuota sangat kecil (60/jam, search 10/menit)")
        self.jumlah_request = 0
        self.resource = None   # "search", "core", ...
        self.sisa = None       # sisa kuota pada resource terakhir
        self.limit = None
        self.reset = None      # epoch detik

    # ----- kuota -----
    def _catat_kuota(self, r):
        h = r.headers
        res = h.get("x-ratelimit-resource")
        if res:
            self.resource = res
        for atribut, kunci in (("sisa", "x-ratelimit-remaining"),
                               ("limit", "x-ratelimit-limit"),
                               ("reset", "x-ratelimit-reset")):
            try:
                if kunci in h:
                    setattr(self, atribut, int(h[kunci]))
            except (TypeError, ValueError):
                pass

    def kuota_aman(self):
        """False jika kuota per jam (bukan search) sudah di bawah ambang."""
        if self.sisa is None or self.resource == "search":
            return True  # kuota search dikelola dengan menunggu reset (lihat _tunggu_search)
        return self.sisa >= config.AMBANG_SISA_KUOTA

    def ringkas_kuota(self):
        if self.sisa is None:
            return "-"
        satuan = {"search": "per menit", "core": "per jam"}.get(self.resource, "")
        batas = f"/{self.limit}" if self.limit else ""
        return f"{self.sisa}{batas} {satuan}".strip()

    def _tunggu_search(self):
        """Jika kuota search per menit hampir habis, tunggu sampai reset."""
        if self.resource == "search" and self.sisa is not None and self.sisa <= 1 and self.reset:
            tunggu = self.reset - time.time() + 1
            if tunggu > 0:
                if tunggu > config.MAKS_TUNGGU_DETIK:
                    raise KuotaHabis(f"Kuota search habis; reset {tunggu:.0f} detik lagi")
                log.info("Kuota search habis; menunggu %.0f detik", tunggu)
                time.sleep(tunggu)
            self.sisa = None

    def _hitung_tunggu(self, r):
        """Berapa detik harus menunggu setelah 403/429."""
        retry_after = r.headers.get("retry-after")
        if retry_after and str(retry_after).isdigit():
            return int(retry_after) + 1
        if r.headers.get("x-ratelimit-remaining") == "0" and self.reset:
            return max(self.reset - time.time(), 0) + 1
        return 60  # secondary rate limit tanpa petunjuk

    # ----- request -----
    def _get(self, path, params=None):
        url = config.GITHUB_API.rstrip("/") + path
        terakhir = None
        kena_kuota = False
        for ke in range(1, config.MAKS_COBA + 1):
            self._tunggu_search()
            time.sleep(self.jeda)
            try:
                r = self.session.get(url, params=params, timeout=config.TIMEOUT_DETIK)
            except RequestException as e:
                terakhir = e
                tunggu = 2 ** ke + random.random()
                log.warning("Gagal %s (percobaan %d): %s; tunggu %.1f s", path, ke, e, tunggu)
                time.sleep(tunggu)
                continue

            self.jumlah_request += 1
            self._catat_kuota(r)

            if r.status_code == 401:
                raise GitHubError("Token GitHub ditolak (401). Periksa GITHUB_TOKEN di .env.")
            if r.status_code in (403, 429):
                kena_kuota = True
                tunggu = self._hitung_tunggu(r)
                if tunggu > config.MAKS_TUNGGU_DETIK:
                    raise KuotaHabis(f"Kena rate limit; harus menunggu {tunggu:.0f} detik")
                terakhir = f"HTTP {r.status_code}"
                log.warning("Rate limit (%s): tunggu %.0f detik", r.status_code, tunggu)
                time.sleep(tunggu)
                continue
            if r.status_code >= 500:
                kena_kuota = False
                terakhir = f"HTTP {r.status_code}"
                tunggu = 2 ** ke + random.random()
                log.warning("Server GitHub %s; tunggu %.1f s", r.status_code, tunggu)
                time.sleep(tunggu)
                continue
            if r.status_code == 422:
                raise GitHubError(f"Query ditolak GitHub (422): {r.text[:200]}")
            if r.status_code != 200:
                raise GitHubError(f"HTTP {r.status_code} dari {path}")
            return r.json()

        if kena_kuota:
            raise KuotaHabis(f"Rate limit terus berlanjut setelah {config.MAKS_COBA} percobaan")
        raise GitHubError(f"Gagal setelah {config.MAKS_COBA} percobaan: {terakhir}")

    # ----- endpoint -----
    def cari_repo(self, q, halaman=1, per_page=None, sort="stars", order="desc"):
        """Satu halaman hasil pencarian repositori. Kembalikan dict JSON GitHub apa adanya."""
        data = self._get("/search/repositories", {
            "q": q, "sort": sort, "order": order,
            "per_page": per_page or config.PER_PAGE, "page": halaman,
        })
        if data.get("incomplete_results"):
            log.warning("GitHub menandai hasil tidak lengkap untuk query: %s", q)
        return data

    def total_count(self, q):
        """Jumlah repo yang cocok dengan query (1 request kecil)."""
        data = self._get("/search/repositories", {"q": q, "per_page": 1})
        return int(data.get("total_count", 0))

    def kuota(self):
        """Status kuota saat ini dari /rate_limit (tidak mengurangi kuota REST)."""
        data = self._get("/rate_limit")
        res = data.get("resources", {})
        return {k: res.get(k, {}) for k in ("core", "search")}
