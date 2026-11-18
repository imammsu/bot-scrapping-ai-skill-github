import pytest

import analisis
import db
import github_client
import laporan
from tests.helpers import buat_item


@pytest.fixture
def df(basis_data):
    db.ganti_jendela([{"dari": "2025-01-01", "sampai": "2026-01-01", "total": 8}])
    j = db.jendela_berikutnya()["id"]
    item = [
        buat_item(1, bahasa="Python", stars=100, dibuat="2025-03-10T00:00:00Z", dorong="2026-10-30T00:00:00Z"),
        buat_item(2, bahasa="Python", stars=30, dibuat="2025-03-20T00:00:00Z", dorong="2026-10-20T00:00:00Z"),
        buat_item(3, bahasa="TypeScript", stars=12, dibuat="2025-05-01T00:00:00Z", dorong="2025-06-01T00:00:00Z",
                  desk="Skills for Cursor and Claude Code"),
        buat_item(4, bahasa=None, stars=5, dibuat="2025-05-15T00:00:00Z", dorong="2025-05-20T00:00:00Z",
                  license=None),
        buat_item(5, bahasa="Python", stars=999, desk="Aplikasi keuangan", topics=[], full_name="x/budget"),
    ]
    repos = []
    for it in item:
        r = github_client.parse_repo(it)
        skor = 10 if it["id"] != 5 else 0
        r.update(skor_relevan=skor, relevan=int(skor >= 4))
        repos.append(r)
    repos.append(dict(repos[0]))  # duplikat sengaja
    db.simpan_halaman(repos, j, 2, "selesai")
    return analisis.bersihkan(db.baca_repo())


def test_bersihkan_membuang_tak_relevan(df):
    assert len(df) == 4 and 5 not in df["id"].tolist()
    assert df["bahasa"].iloc[3] == analisis.TANPA_BAHASA
    assert df["lisensi"].iloc[3] == analisis.TANPA_LISENSI
    assert df["dibuat"].dt.tz is None


def test_bersihkan_df_kosong(basis_data):
    assert analisis.bersihkan(db.baca_repo()).empty


def test_ringkasan(df):
    r = analisis.ringkasan(df)
    assert r["jumlah_repo"] == 4 and r["jumlah_bahasa"] == 2 and r["stars_maks"] == 100
    assert r["persen_berlisensi"] == 75.0


def test_bahasa_dan_bulan_dan_agen(df):
    assert analisis.bahasa_teratas(df).index[0] == "Python"
    assert analisis.per_bulan(df).to_dict() == {"2025-03": 2, "2025-05": 2}
    agen = analisis.agen_disebut(df)
    assert agen["Claude Code"] == 4 and agen["Cursor"] == 1


def test_aktivitas_vs_stars(df):
    akt = analisis.aktivitas_vs_stars(df)
    assert akt["aktif_n"] == 2 and akt["tidak_n"] == 2
    assert akt["aktif_median"] > akt["tidak_median"]


def test_temuan_lima_kalimat(df):
    t = analisis.temuan(df)
    assert len(t) == 5 and "Python" in t[0] and "Claude Code" in t[1]
    assert analisis.temuan(df.iloc[0:0]) == ["Belum ada data relevan untuk dianalisis."]


def test_grafik_dibuat(df, tmp_path):
    g = analisis.buat_grafik(df, tmp_path)
    assert set(g) == {"bahasa", "bulan", "agen"}
    assert all(p.exists() and p.stat().st_size > 1000 for p in g.values())


def test_laporan_excel_dan_pdf(df, tmp_path):
    g = analisis.buat_grafik(df, tmp_path)
    xlsx = laporan.buat_excel(df, g, tmp_path)
    pdf = laporan.buat_pdf(df, g, tmp_path)
    assert xlsx.suffix == ".xlsx" and pdf.suffix == ".pdf"
    assert pdf.read_bytes()[:4] == b"%PDF"
    from openpyxl import load_workbook
    wb = load_workbook(xlsx)
    assert wb.sheetnames == ["Ringkasan", "Data"]
    assert wb["Data"].max_row == 5  # header + 4 repo relevan
    assert wb["Data"]["A1"].value == "full_name"


def test_laporan_excel_seluruh_repo(df, tmp_path):
    xlsx = laporan.buat_excel_repo(db.baca_repo(), tmp_path)

    from openpyxl import load_workbook
    wb = load_workbook(xlsx)
    ws = wb["Repo"]
    assert wb.sheetnames == ["Repo"]
    assert ws.max_row == 6  # header + 5 repo, termasuk yang tidak relevan
    assert ws["A1"].value == "id"
    assert "relevan" in [sel.value for sel in ws[1]]
    assert ws.auto_filter.ref == ws.dimensions
