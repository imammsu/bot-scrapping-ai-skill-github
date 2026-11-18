"""
Penilaian relevansi repo terhadap topik "skill untuk AI agentic coding".

Pencarian berbasis kata kunci menghasilkan sebagian repo yang hanya menyebut skill sambil
lalu. Setiap repo diberi skor dari kata kunci pada nama, deskripsi, dan topik. Repo dengan
skor di bawah AMBANG_RELEVAN ditandai relevan = 0 dan dikeluarkan dari analisis (datanya
tetap tersimpan). Ini heuristik sederhana, bukan klasifikasi sempurna.
"""
import re

import config

# (varian kata, bobot). Setiap kelompok dihitung sekali.
KATA_KUNCI = [
    (("skill", "skills"), 2),
    (("skill md",), 3),
    (("agent skills", "agent skill", "agentskills"), 3),
    (("claude code",), 2),
    (("cursor", "codex", "copilot", "windsurf", "gemini cli"), 1),
    (("mcp",), 1),
    (("agentic", "ai agent", "ai agents", "coding agent", "coding agents"), 1),
]
BONUS_NAMA = 2  # nama repo mengandung "skill"
JUMLAH_KELOMPOK_INTI = 3  # tiga kelompok pertama = kata inti "skill"


def normalisasi(teks):
    """Huruf kecil, tanda baca jadi spasi, diapit spasi: 'Claude-Code' -> ' claude code '."""
    return " " + re.sub(r"[^a-z0-9]+", " ", (teks or "").lower()).strip() + " "


def _ada(teks_norm, varian):
    return any(f" {v} " in teks_norm for v in varian)


def skor(nama, deskripsi="", topik=""):
    teks = normalisasi(f"{nama} {deskripsi} {(topik or '').replace(',', ' ')}")
    total = sum(bobot for varian, bobot in KATA_KUNCI if _ada(teks, varian))
    nama_repo = (nama or "").split("/")[-1]
    ada_inti = any(_ada(teks, varian) for varian, _ in KATA_KUNCI[:JUMLAH_KELOMPOK_INTI])
    if _ada(normalisasi(nama_repo), ("skill", "skills", "agentskills")):
        total += BONUS_NAMA
        ada_inti = True
    if not ada_inti:
        # Tanpa kata inti "skill", kata pendukung (mcp, cursor, ...) saja tidak cukup.
        return min(total, config.AMBANG_RELEVAN - 1)
    return total


def relevan(nilai_skor, ambang=None):
    return nilai_skor >= (config.AMBANG_RELEVAN if ambang is None else ambang)
