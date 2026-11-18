"""
Lapisan 3b: LAPORAN (Excel dengan openpyxl, PDF dengan reportlab).
"""
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import analisis
import config

KOLOM_DATA = ["full_name", "deskripsi", "bahasa", "stars", "forks", "open_issues",
              "lisensi", "dibuat", "push_terakhir", "topik", "url"]
URUT_GRAFIK = ("bahasa", "bulan", "agen")


def _folder(folder):
    folder = Path(folder or config.OUTPUT_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _nama_berkas(folder, ekstensi):
    return folder / f"laporan_{config.hari_ini()}.{ekstensi}"


def _label_ringkasan(r):
    return [
        ("Jumlah repo relevan", r["jumlah_repo"]),
        ("Bahasa terdeteksi", r["jumlah_bahasa"]),
        ("Stars (median)", round(r["stars_median"], 1)),
        ("Stars (rata-rata)", round(r["stars_rata"], 1)),
        ("Stars tertinggi", r["stars_maks"]),
        ("Repo berlisensi (%)", r["persen_berlisensi"]),
    ]


def buat_excel(df, grafik, folder=None):
    folder = _folder(folder)
    wb = Workbook()

    ws = wb.active
    ws.title = "Ringkasan"
    ws["A1"] = "Laporan PantauSkill"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Dibuat: {config.hari_ini()}"
    baris = 4
    for nama, nilai in _label_ringkasan(analisis.ringkasan(df)):
        ws.cell(baris, 1, nama)
        ws.cell(baris, 2, nilai)
        baris += 1
    baris += 1
    ws.cell(baris, 1, "Temuan").font = Font(bold=True)
    for i, kalimat in enumerate(analisis.temuan(df), 1):
        baris += 1
        sel = ws.cell(baris, 1, f"{i}. {kalimat}")
        sel.alignment = Alignment(wrap_text=False)
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 14
    posisi = 3
    for kunci in URUT_GRAFIK:
        if kunci in grafik:
            gambar = XLImage(str(grafik[kunci]))
            gambar.width, gambar.height = 480, 270
            ws.add_image(gambar, f"D{posisi}")
            posisi += 16

    data = wb.create_sheet("Data")
    tampil = df[KOLOM_DATA].copy()
    for k in ("dibuat", "push_terakhir"):
        tampil[k] = tampil[k].dt.strftime("%Y-%m-%d")
    tampil = tampil.astype(object).where(tampil.notna(), "")
    data.append(KOLOM_DATA)
    for sel in data[1]:
        sel.font = Font(bold=True, color="FFFFFF")
        sel.fill = PatternFill("solid", fgColor="2F6DB5")
    for baris_data in tampil.values.tolist():
        data.append(baris_data)
    data.freeze_panes = "A2"
    lebar = {"A": 34, "B": 60, "C": 14, "D": 9, "E": 9, "F": 11, "G": 14,
             "H": 12, "I": 14, "J": 40, "K": 45}
    for huruf, nilai in lebar.items():
        data.column_dimensions[huruf].width = nilai

    path = _nama_berkas(folder, "xlsx")
    wb.save(path)
    return path


def buat_excel_repo(df, folder=None):
    """Buat Excel berisi seluruh baris dan kolom tabel ``repo``.

    Berbeda dari :func:`buat_excel`, fungsi ini tidak membersihkan atau
    memfilter data untuk analisis.  Jadi repo yang tidak relevan dan seluruh
    kolom mentah dari database tetap ikut diekspor.
    """
    folder = _folder(folder)
    path = folder / f"seluruh_data_repo_{config.hari_ini()}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Repo"

    kolom = list(df.columns)
    ws.append(kolom)
    for sel in ws[1]:
        sel.font = Font(bold=True, color="FFFFFF")
        sel.fill = PatternFill("solid", fgColor="2F6DB5")
        sel.alignment = Alignment(horizontal="center")

    for nilai in df.itertuples(index=False, name=None):
        # SQLite mengembalikan nilai skalar. Konversi NaN/NaT menjadi sel
        # kosong agar file Excel tidak menampilkan nilai sentinel pandas.
        ws.append(["" if pd.isna(item) else item for item in nilai])

    ws.freeze_panes = "A2"
    if kolom:
        ws.auto_filter.ref = ws.dimensions
    for kolom_ke, nama in enumerate(kolom, 1):
        isi = [str(nama)]
        isi.extend(str(ws.cell(baris, kolom_ke).value or "")
                   for baris in range(2, min(ws.max_row, 101) + 1))
        lebar = min(max(len(item) for item in isi) + 2, 60)
        ws.column_dimensions[get_column_letter(kolom_ke)].width = max(lebar, 10)

    wb.save(path)
    return path


def buat_pdf(df, grafik, folder=None):
    folder = _folder(folder)
    path = _nama_berkas(folder, "pdf")
    gaya = getSampleStyleSheet()
    isi = [Paragraph("Laporan PantauSkill", gaya["Title"]),
           Paragraph(f"Dibuat: {config.hari_ini()}", gaya["Normal"]),
           Spacer(1, 0.4 * cm)]

    tabel_ringkas = Table([[n, str(v)] for n, v in _label_ringkasan(analisis.ringkasan(df))],
                          colWidths=[7 * cm, 4 * cm])
    tabel_ringkas.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                                       ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    isi += [tabel_ringkas, Spacer(1, 0.5 * cm), Paragraph("Temuan", gaya["Heading2"])]
    for i, kalimat in enumerate(analisis.temuan(df), 1):
        isi.append(Paragraph(f"{i}. {escape(kalimat)}", gaya["Normal"]))

    isi += [Spacer(1, 0.5 * cm), Paragraph("10 repo dengan stars terbanyak", gaya["Heading2"])]
    baris = [["Repo", "Bahasa", "Stars", "Forks"]]
    for r in df.nlargest(10, "stars").itertuples():
        baris.append([r.full_name[:45], r.bahasa, str(r.stars), str(r.forks)])
    tabel = Table(baris, colWidths=[8 * cm, 3.5 * cm, 2 * cm, 2 * cm])
    tabel.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F6DB5")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                               ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    isi.append(tabel)

    for kunci in URUT_GRAFIK:
        if kunci in grafik:
            isi += [Spacer(1, 0.5 * cm), Image(str(grafik[kunci]), width=15 * cm, height=8.4 * cm)]

    SimpleDocTemplate(str(path), pagesize=A4, title="Laporan PantauSkill").build(isi)
    return path
