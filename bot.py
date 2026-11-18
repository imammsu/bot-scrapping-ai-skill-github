"""
Lapisan 4: BOT TELEGRAM - menjalankan pengambilan data otomatis dan melapor.

Satu proses (python bot.py) menangani semuanya:
- /mulai dikirim SEKALI; setelah itu bot mengambil jatah harian sendiri lewat JobQueue
  (run_daily pada JAM_JADWAL, zona WIB) dan mengirim notifikasi setelah tiap run.
- Scraping memakai requests (blocking), jadi dijalankan lewat asyncio.to_thread agar bot
  tetap responsif.
- Progres tersimpan di SQLite. Jika bot mati lalu dinyalakan lagi, job didaftarkan ulang.
- Job pengaman tiap 15 menit: jika jam jadwal sudah lewat dan hari ini belum dicoba
  (misalnya laptop sempat sleep), bot mengejarnya.

Jalankan: python bot.py   (hentikan dengan Ctrl+C)
"""
import asyncio
import datetime
import functools
import logging

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import analisis
import config
import db
import laporan
import pesan
import scraper_harian

WIB = config.WIB
INTERVAL_PENGAMAN = 15 * 60  # detik
log = logging.getLogger("pantauskill")


def atur_log():
    config.LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=logging.INFO,
        handlers=[logging.FileHandler(config.LOG_DIR / "bot.log", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def muat():
    """Baca data terbaru setiap kali dipakai."""
    return analisis.bersihkan(db.baca_repo())


def admin_saja(fungsi):
    """Batasi perintah hanya untuk ADMIN_CHAT_ID (jika diisi)."""
    @functools.wraps(fungsi)
    async def pembungkus(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if config.ADMIN_CHAT_ID and update.effective_chat.id != config.ADMIN_CHAT_ID:
            await update.message.reply_text("Maaf, bot ini hanya melayani admin.")
            return
        await fungsi(update, context)
    return pembungkus


def jam_jadwal():
    jam, menit = map(int, config.JAM_JADWAL.split(":"))
    return jam, menit


def sudah_lewat_jadwal():
    sekarang = config.sekarang()
    return (sekarang.hour, sekarang.minute) >= jam_jadwal()


# ---------- Penjadwalan ----------
def hapus_job(job_queue, chat_id):
    for job in job_queue.get_jobs_by_name(f"harian-{chat_id}"):
        job.schedule_removal()
    for job in job_queue.get_jobs_by_name("pengaman"):
        job.schedule_removal()


def daftarkan_job(job_queue, chat_id):
    """Daftarkan job harian + job pengaman. Aman dipanggil berulang (tidak membuat ganda)."""
    hapus_job(job_queue, chat_id)
    jam, menit = jam_jadwal()
    job_queue.run_daily(job_harian, time=datetime.time(jam, menit, tzinfo=WIB),
                        chat_id=chat_id, name=f"harian-{chat_id}")
    job_queue.run_repeating(job_pengaman, interval=INTERVAL_PENGAMAN, first=60, name="pengaman")


async def proses_run(context, chat_id, mode="normal", otomatis=False):
    """Jalankan satu jatah (di thread terpisah), kirim notifikasi, tutup job jika selesai."""
    try:
        hasil = await asyncio.to_thread(scraper_harian.jalankan_tugas_harian, mode, otomatis)
    except Exception as e:  # jangan biarkan bot ikut mati
        log.exception("Run gagal")
        await context.bot.send_message(chat_id, f"Run gagal: {pesan.potong(str(e), 300)}")
        return None
    if hasil is None:
        hapus_job(context.job_queue, chat_id)
        return None
    if otomatis and hasil.status in ("sudah_hari_ini", "sedang_berjalan"):
        return hasil  # job terjadwal: diam saja
    await context.bot.send_message(chat_id, pesan.format_notifikasi_run(hasil))
    if hasil.tugas_selesai:
        hapus_job(context.job_queue, chat_id)
        await kirim_laporan_akhir(context.bot, chat_id)
    return hasil


async def job_harian(context: ContextTypes.DEFAULT_TYPE):
    await proses_run(context, context.job.chat_id, "normal", otomatis=True)


async def job_pengaman(context: ContextTypes.DEFAULT_TYPE):
    """Kejar jatah hari ini jika jadwal terlewat (bot mati / laptop sleep)."""
    tugas = db.tugas_aktif()
    if not tugas or not tugas["chat_id"]:
        return
    if not sudah_lewat_jadwal():
        return
    if db.sudah_jalan_hari_ini(tugas["id"], hanya_dihitung=False):
        return
    log.info("Jatah hari ini belum dicoba; menjalankan (pengaman)")
    await proses_run(context, tugas["chat_id"], "normal", otomatis=True)


async def kirim_laporan_akhir(bot, chat_id):
    df = muat()
    if df.empty:
        await bot.send_message(chat_id, "Tugas selesai, tetapi belum ada data relevan.")
        return
    teks = pesan.format_ringkasan(analisis.ringkasan(df), analisis.temuan(df),
                                  judul="Laporan akhir PantauSkill")
    await bot.send_message(chat_id, teks)
    try:
        grafik = await asyncio.to_thread(analisis.buat_grafik, df)
        xlsx = await asyncio.to_thread(laporan.buat_excel, df, grafik)
        pdf = await asyncio.to_thread(laporan.buat_pdf, df, grafik)
        for berkas in (pdf, xlsx):
            with open(berkas, "rb") as f:
                await bot.send_document(chat_id, f, filename=berkas.name)
    except Exception:
        log.exception("Gagal membuat laporan file")
        await bot.send_message(chat_id, "Laporan file gagal dibuat. Coba: python main.py analisis")


# ---------- Perintah ----------
@admin_saja
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nama = update.effective_user.first_name
    await update.message.reply_text(
        f"Halo, {nama}! Aku PantauSkill, bot pengumpul data repo skill AI agentic coding.\n\n"
        + pesan.BANTUAN)


@admin_saja
async def bantuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(pesan.BANTUAN)


@admin_saja
async def mulai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tugas = db.tugas_aktif()
    if tugas:
        if tugas["chat_id"] in (0, None):  # tugas yang dibuat lewat CLI: sambungkan ke chat ini
            db.set_chat_id(tugas["id"], chat_id)
        daftarkan_job(context.job_queue, chat_id)
        await update.message.reply_text(
            "Tugas sudah berjalan, jadwal dipastikan aktif. Kirim /status untuk melihat progres.")
        return

    await update.message.reply_text(
        "Menyusun jendela pencarian di GitHub. Ini bisa memakan 1-2 menit...")
    try:
        ringkas = await asyncio.to_thread(scraper_harian.siapkan_jendela)
    except Exception as e:
        log.exception("Gagal menyusun jendela")
        await update.message.reply_text(f"Gagal menyusun jendela: {pesan.potong(str(e), 300)}")
        return
    if ringkas["jumlah"] == 0:
        await update.message.reply_text(
            "Tidak ada repo yang cocok dengan query. Longgarkan STARS_MIN atau QUERY_DASAR di .env.")
        return

    db.buat_tugas(chat_id, config.JUMLAH_HARI, config.KUOTA_HARIAN)
    daftarkan_job(context.job_queue, chat_id)
    kapan = ("dalam sekitar 1 menit (jam jadwal hari ini sudah lewat)"
             if sudah_lewat_jadwal() else f"hari ini pukul {config.JAM_JADWAL} WIB")
    await update.message.reply_text(
        f"Siap! Ditemukan sekitar {ringkas['perkiraan']} repo dalam {ringkas['jumlah']} jendela.\n"
        f"Bot akan mengambil {config.KUOTA_HARIAN} repo per hari selama {config.JUMLAH_HARI} hari, "
        f"otomatis setiap pukul {config.JAM_JADWAL} WIB.\n"
        f"Jatah hari ke-1 berjalan {kapan}. Kamu tidak perlu mengirim perintah lagi.")


@admin_saja
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(pesan.format_status(db.status_tugas()))


@admin_saja
async def perpanjang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perpanjang target total hari tugas aktif, tanpa mengubah progress."""
    if len(context.args) != 1:
        await update.message.reply_text("Format: /perpanjang <jumlah_hari>\nContoh: /perpanjang 7")
        return

    try:
        total_hari = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Jumlah hari harus berupa angka bulat. Contoh: /perpanjang 7")
        return
    if total_hari < 1:
        await update.message.reply_text("Jumlah hari harus lebih besar dari 0.")
        return

    tugas = db.tugas_aktif()
    if not tugas:
        await update.message.reply_text("Tidak ada tugas yang berjalan.")
        return
    if total_hari <= tugas["total_hari"]:
        await update.message.reply_text(
            f"Target baru harus lebih besar dari {tugas['total_hari']} hari."
        )
        return

    diperbarui = db.perpanjang_tugas(tugas["id"], total_hari)
    if diperbarui is None:
        await update.message.reply_text("Tugas gagal diperpanjang. Coba lagi.")
        return
    await update.message.reply_text(
        f"Tugas diperpanjang dari {tugas['total_hari']} menjadi "
        f"{diperbarui['total_hari']} hari.\n"
        f"Progress saat ini: hari ke-{diperbarui['hari_ke']}/{diperbarui['total_hari']}."
    )


@admin_saja
async def scrape_sekarang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tugas = db.tugas_aktif()
    if not tugas:
        await update.message.reply_text("Belum ada tugas. Kirim /mulai dulu.")
        return
    mode = "uji" if context.args and context.args[0].lower() == "uji" else "normal"
    await update.message.reply_text(
        "Menjalankan " + ("uji coba 1 halaman..." if mode == "uji" else "jatah hari ini..."))
    hasil = await proses_run(context, update.effective_chat.id, mode, otomatis=False)
    if hasil is not None and hasil.status == "sudah_hari_ini":
        await update.message.reply_text(
            "Jatah hari ini sudah dijalankan. Untuk demo, pakai /scrape_sekarang uji "
            "(1 halaman, tidak dihitung sebagai hari).")


@admin_saja
async def berhenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tugas = db.tugas_aktif()
    hapus_job(context.job_queue, update.effective_chat.id)
    if tugas:
        db.tutup_tugas(tugas["id"], "dibatalkan")
        await update.message.reply_text("Tugas dibatalkan. Data yang sudah terkumpul tetap tersimpan.")
    else:
        await update.message.reply_text("Tidak ada tugas yang berjalan.")


@admin_saja
async def ringkas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = muat()
    if df.empty:
        await update.message.reply_text("Data belum ada. Kirim /mulai dulu.")
        return
    await update.message.reply_text(
        pesan.format_ringkasan(analisis.ringkasan(df), analisis.temuan(df)))


@admin_saja
async def cari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Contoh: /cari testing")
        return
    kata = " ".join(context.args)
    await update.message.reply_text(
        pesan.format_daftar_repo(db.cari(kata, batas=5), f'Hasil pencarian "{kata}":'))


@admin_saja
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        pesan.format_daftar_repo(db.teratas(5), "5 repo dengan stars terbanyak:"))


@admin_saja
async def grafik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = muat()
    if df.empty:
        await update.message.reply_text("Data belum ada. Kirim /mulai dulu.")
        return
    path = await asyncio.to_thread(analisis.buat_grafik, df)
    for kunci, keterangan in [("bahasa", "Bahasa teratas"), ("bulan", "Repo dibuat per bulan"),
                              ("agen", "Agen yang disebut")]:
        with open(path[kunci], "rb") as f:
            await update.message.reply_photo(f, caption=keterangan)


@admin_saja
async def excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kirim seluruh isi tabel repo sebagai file Excel."""
    await update.message.reply_text("Menyiapkan Excel seluruh data repo...")
    try:
        df = await asyncio.to_thread(db.baca_repo)
        path = await asyncio.to_thread(laporan.buat_excel_repo, df)
        with open(path, "rb") as berkas:
            await update.message.reply_document(
                berkas,
                filename=path.name,
                caption=f"Seluruh data repo ({len(df)} baris).",
            )
    except Exception as e:
        log.exception("Gagal membuat Excel seluruh data repo")
        await update.message.reply_text(
            f"Excel gagal dibuat: {pesan.potong(str(e), 300)}"
        )


async def tak_dikenal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Perintah tidak dikenal. Ketik /help.")


async def saat_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Error saat memproses update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Maaf, terjadi kesalahan. Coba lagi.")


# ---------- Siklus hidup ----------
async def setelah_mulai(app: Application):
    await app.bot.set_my_commands([
        BotCommand("mulai", "Mulai tugas pengambilan data bertahap"),
        BotCommand("status", "Progres tugas"),
        BotCommand("perpanjang", "Perpanjang target hari tugas"),
        BotCommand("scrape_sekarang", "Jalankan jatah hari ini (demo)"),
        BotCommand("ringkas", "Ringkasan data"),
        BotCommand("cari", "Cari repo"),
        BotCommand("top", "Repo stars terbanyak"),
        BotCommand("grafik", "Grafik analisis"),
        BotCommand("excel", "Kirim seluruh data repo sebagai Excel"),
        BotCommand("berhenti", "Batalkan tugas"),
        BotCommand("help", "Bantuan"),
    ])
    pulihkan(app)


def pulihkan(app: Application):
    """Setelah restart: daftarkan ulang job untuk tugas yang masih berjalan."""
    tugas = db.tugas_aktif()
    if tugas and tugas["chat_id"]:
        daftarkan_job(app.job_queue, tugas["chat_id"])
        log.info("Tugas #%s dipulihkan (hari %s/%s)", tugas["id"], tugas["hari_ke"],
                 tugas["total_hari"])


def buat_aplikasi(token):
    app = Application.builder().token(token).post_init(setelah_mulai).build()
    for nama, fungsi in [("start", start), ("help", bantuan), ("mulai", mulai),
                         ("status", status), ("perpanjang", perpanjang),
                         ("scrape_sekarang", scrape_sekarang),
                         ("berhenti", berhenti), ("ringkas", ringkas), ("cari", cari),
                         ("top", top), ("grafik", grafik), ("excel", excel)]:
        app.add_handler(CommandHandler(nama, fungsi))
    app.add_handler(MessageHandler(filters.COMMAND, tak_dikenal))  # paling akhir
    app.add_error_handler(saat_error)
    return app


def main():
    atur_log()
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN belum diisi. Salin .env.example menjadi .env lalu isi tokennya.")
    if not config.GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN kosong: kuota GitHub sangat kecil. Isi di .env.")
    app = buat_aplikasi(config.BOT_TOKEN)
    log.info("Bot berjalan. Tekan Ctrl+C untuk berhenti.")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
