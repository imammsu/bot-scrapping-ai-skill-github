"""
Pengaturan proyek di satu tempat.

Nilai rahasia (token) dibaca dari file .env, bukan ditulis di kode.
"""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()  # baca .env ke os.environ (jika file ada)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
LOG_DIR = ROOT / "logs"
DB_PATH = DATA_DIR / "skill.db"

WIB = ZoneInfo("Asia/Jakarta")


def _int(nama, default):
    try:
        return int(os.getenv(nama, "") or default)
    except ValueError:
        return default


def _float(nama, default):
    try:
        return float(os.getenv(nama, "") or default)
    except ValueError:
        return default


# ---------- GitHub API ----------
GITHUB_API = os.getenv("GITHUB_API", "https://api.github.com")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
USER_AGENT = "PantauSkill/1.0 (tugas scripting language; bot telegram)"
TIMEOUT_DETIK = 20
MAKS_COBA = 3                 # retry jika request gagal
PER_PAGE = 100                # maksimum per request pada search API
BATAS_HASIL_SEARCH = 1000     # search API hanya memberi maks 1000 hasil per query

# ---------- Telegram ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = _int("ADMIN_CHAT_ID", 0)  # 0 = tidak dibatasi

# ---------- Jadwal dan kuota ----------
JAM_JADWAL = os.getenv("JAM_JADWAL", "07:00")      # WIB
JUMLAH_HARI = _int("JUMLAH_HARI", 4)
KUOTA_HARIAN = _int("KUOTA_HARIAN", 500)            # dibulatkan ke kelipatan PER_PAGE
JEDA_DETIK = _float("JEDA_DETIK", 2.0)              # jeda sopan antar-request
AMBANG_SISA_KUOTA = _int("AMBANG_SISA_KUOTA", 100)  # untuk kuota per jam (bukan search)
MAKS_REQUEST_PER_RUN = _int("MAKS_REQUEST_PER_RUN", 50)
MAKS_TUNGGU_DETIK = _int("MAKS_TUNGGU_DETIK", 90)   # lebih lama dari ini: hentikan run

# ---------- Cakupan pencarian ----------
QUERY_DASAR = os.getenv("QUERY_DASAR", "claude-code skills in:name,description fork:false")
STARS_MIN = _int("STARS_MIN", 3)
TANGGAL_MULAI_CARI = os.getenv("TANGGAL_MULAI_CARI", "2025-01-01")
AMBANG_RELEVAN = _int("AMBANG_RELEVAN", 4)


def sekarang():
    return datetime.now(WIB)


def sekarang_str():
    return sekarang().isoformat(timespec="seconds")


def hari_ini():
    return sekarang().date().isoformat()
