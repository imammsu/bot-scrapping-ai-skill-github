"""
Titik masuk CLI: menjalankan bagian-bagian proyek TANPA Telegram (untuk uji dan debugging).

Contoh:
  python main.py cek                 # cek jumlah repo yang cocok + sisa kuota API
  python main.py siapkan             # susun jendela pencarian
  python main.py jalankan            # jalankan jatah harian sekali
  python main.py jalankan --uji      # uji 1 halaman (tidak dihitung sebagai hari)
  python main.py status              # lihat progres
  python main.py analisis            # buat grafik + laporan Excel/PDF dari database

Pengambilan data otomatis 4 hari dijalankan oleh bot: python bot.py
"""
import argparse
import logging
import sys

import analisis
import config
import db
import jendela
import laporan
import pesan
import scraper_harian
from github_client import GitHubClient, GitHubError

log = logging.getLogger("main")


def atur_log():
    config.LOG_DIR.mkdir(exist_ok=True)
    config.DATA_DIR.mkdir(exist_ok=True)
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(config.LOG_DIR / "pipeline.log", encoding="utf-8"),
                  logging.StreamHandler()],
    )


def cmd_cek(_args):
    klien = GitHubClient()
    query = jendela.buat_query(config.TANGGAL_MULAI_CARI, config.hari_ini())
    print("Query :", query)
    total = klien.total_count(query)
    target = config.JUMLAH_HARI * config.KUOTA_HARIAN
    print(f"Repo yang cocok : {total}")
    print(f"Target          : {config.JUMLAH_HARI} hari x {config.KUOTA_HARIAN} = {target}")
    print("Cukup untuk target." if total >= target else
          "KURANG dari target. Turunkan STARS_MIN, majukan TANGGAL_MULAI_CARI, atau ubah QUERY_DASAR.")
    for nama, k in klien.kuota().items():
        print(f"Kuota {nama:<6}: sisa {k.get('remaining')} dari {k.get('limit')}")
    if not config.GITHUB_TOKEN:
        print("PERINGATAN: GITHUB_TOKEN kosong (kuota kecil). Isi di .env.")


def cmd_siapkan(_args):
    ringkas = scraper_harian.siapkan_jendela()
    print(f"{ringkas['jumlah']} jendela, perkiraan {ringkas['perkiraan']} repo.")


def cmd_jalankan(args):
    if db.tugas_aktif() is None:
        db.buat_tugas(0, config.JUMLAH_HARI, config.KUOTA_HARIAN)
        print("Tugas baru dibuat (tanpa chat Telegram).")
    mode = "uji" if args.uji else "normal"
    hasil = scraper_harian.jalankan_tugas_harian(mode=mode)
    print(pesan.format_notifikasi_run(hasil))
    if hasil.status == "sudah_hari_ini":
        print("Gunakan --uji untuk uji coba 1 halaman.")


def cmd_status(_args):
    print(pesan.format_status(db.status_tugas()))


def cmd_analisis(_args):
    df = analisis.bersihkan(db.baca_repo())
    if df.empty:
        print("Belum ada data relevan. Jalankan 'jalankan' atau bot dulu.")
        return
    for kalimat in analisis.temuan(df):
        print("-", kalimat)
    grafik = analisis.buat_grafik(df)
    xlsx = laporan.buat_excel(df, grafik)
    pdf = laporan.buat_pdf(df, grafik)
    print("Hasil:", xlsx, pdf, *grafik.values(), sep="\n  ")


def main():
    p = argparse.ArgumentParser(description="PantauSkill (CLI tanpa Telegram)")
    sub = p.add_subparsers(dest="perintah", required=True)
    sub.add_parser("cek", help="cek jumlah repo dan sisa kuota API").set_defaults(fn=cmd_cek)
    sub.add_parser("siapkan", help="susun jendela pencarian").set_defaults(fn=cmd_siapkan)
    pj = sub.add_parser("jalankan", help="jalankan jatah harian sekali")
    pj.add_argument("--uji", action="store_true", help="hanya 1 halaman, tidak dihitung sebagai hari")
    pj.set_defaults(fn=cmd_jalankan)
    sub.add_parser("status", help="lihat progres").set_defaults(fn=cmd_status)
    sub.add_parser("analisis", help="grafik + laporan").set_defaults(fn=cmd_analisis)
    args = p.parse_args()

    atur_log()
    try:
        args.fn(args)
    except GitHubError as e:
        log.error("GitHub: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
