"""
Pemecahan query menjadi "jendela" berdasarkan tanggal pembuatan repo.

Search API GitHub hanya mengembalikan maksimal 1000 hasil per query. Agar semua repo
bisa dijangkau, rentang tanggal `created:` dibelah dua berulang kali sampai setiap
jendela berisi paling banyak 1000 repo. Tiap hari bot mengonsumsi jendela berurutan.
"""
import logging
from datetime import date, timedelta

import config

log = logging.getLogger(__name__)


def buat_query(dari, sampai, dasar=None, stars_min=None):
    dasar = dasar or config.QUERY_DASAR
    stars_min = config.STARS_MIN if stars_min is None else stars_min
    return f"{dasar} stars:>={stars_min} created:{dari}..{sampai}"


def belah(dari, sampai):
    """Belah rentang tanggal (ISO) menjadi dua bagian tanpa celah/tumpang tindih.
    Kembalikan None jika rentang tinggal satu hari."""
    a, b = date.fromisoformat(dari), date.fromisoformat(sampai)
    if a >= b:
        return None
    tengah = a + (b - a) // 2
    return (a.isoformat(), tengah.isoformat()), ((tengah + timedelta(days=1)).isoformat(), b.isoformat())


def susun_jendela(klien, dari=None, sampai=None, batas=None):
    """Kembalikan list dict {dari, sampai, total} berurutan menurut tanggal."""
    dari = dari or config.TANGGAL_MULAI_CARI
    sampai = sampai or config.hari_ini()
    batas = batas or config.BATAS_HASIL_SEARCH
    hasil = []
    tumpukan = [(dari, sampai)]
    while tumpukan:
        a, b = tumpukan.pop()
        total = klien.total_count(buat_query(a, b))
        if total == 0:
            continue
        pecah = belah(a, b) if total > batas else None
        if pecah is None:
            if total > batas:
                log.warning("Jendela %s..%s berisi %d repo (> %d); hanya %d teratas terjangkau",
                            a, b, total, batas, batas)
            hasil.append({"dari": a, "sampai": b, "total": total})
        else:
            kiri, kanan = pecah
            tumpukan.append(kanan)
            tumpukan.append(kiri)  # kiri diproses lebih dulu
    hasil.sort(key=lambda j: j["dari"])
    log.info("Tersusun %d jendela (perkiraan %d repo)", len(hasil),
             sum(min(j["total"], batas) for j in hasil))
    return hasil
