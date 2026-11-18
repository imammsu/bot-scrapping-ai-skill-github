"""
Lapisan 3: ANALISIS (pandas + matplotlib).

Pertanyaan yang dijawab:
1. Bahasa pemrograman apa yang paling dominan pada repo skill?
2. Agen/platform mana yang paling sering disebut (Claude Code, Cursor, Copilot, ...)?
3. Berapa banyak repo skill dibuat per bulan?
4. Apakah repo yang aktif cenderung punya stars lebih banyak?
5. Lisensi apa yang paling umum?

Hanya repo dengan relevan = 1 yang dianalisis.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # tanpa jendela, aman dipanggil dari thread/bot
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402
from relevansi import normalisasi  # noqa: E402

TANPA_BAHASA = "Tidak diketahui"
TANPA_LISENSI = "Tanpa lisensi"

AGEN = {
    "Claude Code": ["claude code"],
    "Cursor": ["cursor"],
    "GitHub Copilot": ["copilot"],
    "Codex": ["codex"],
    "Gemini CLI": ["gemini cli", "gemini"],
    "Windsurf": ["windsurf"],
    "Cline": ["cline"],
}


# ---------- Pembersihan ----------
def bersihkan(df):
    """Buang duplikat dan repo tidak relevan, rapikan tipe data."""
    if df.empty:
        return df.copy()
    df = df.drop_duplicates(subset="id").copy()
    df = df[df["relevan"] == 1].copy()
    df["bahasa"] = df["bahasa"].fillna(TANPA_BAHASA)
    df["lisensi"] = df["lisensi"].fillna(TANPA_LISENSI)
    df["deskripsi"] = df["deskripsi"].fillna("")
    df["topik"] = df["topik"].fillna("")
    for k in ("stars", "forks", "open_issues"):
        df[k] = pd.to_numeric(df[k], errors="coerce").fillna(0).astype(int)
    for k in ("dibuat", "push_terakhir"):
        df[k] = pd.to_datetime(df[k], utc=True, errors="coerce").dt.tz_convert(None)
    df["bulan_dibuat"] = df["dibuat"].dt.strftime("%Y-%m")
    return df.reset_index(drop=True)


# ---------- Perhitungan ----------
def ringkasan(df):
    if df.empty:
        return {"jumlah_repo": 0, "jumlah_bahasa": 0, "stars_median": 0.0,
                "stars_rata": 0.0, "stars_maks": 0, "persen_berlisensi": 0.0}
    bahasa_dikenal = df.loc[df["bahasa"] != TANPA_BAHASA, "bahasa"].nunique()
    berlisensi = (df["lisensi"] != TANPA_LISENSI).mean() * 100
    return {
        "jumlah_repo": int(len(df)),
        "jumlah_bahasa": int(bahasa_dikenal),
        "stars_median": float(df["stars"].median()),
        "stars_rata": float(df["stars"].mean()),
        "stars_maks": int(df["stars"].max()),
        "persen_berlisensi": round(float(berlisensi), 1),
    }


def bahasa_teratas(df, n=10):
    return df.loc[df["bahasa"] != TANPA_BAHASA, "bahasa"].value_counts().head(n)


def per_bulan(df):
    return df["bulan_dibuat"].dropna().value_counts().sort_index()


def agen_disebut(df):
    """Jumlah repo yang menyebut tiap agen pada nama, deskripsi, atau topik."""
    teks = (df["full_name"] + " " + df["deskripsi"] + " " + df["topik"].str.replace(",", " "))
    teks = teks.map(normalisasi)
    hasil = {}
    for nama, varian in AGEN.items():
        n = int(teks.map(lambda t: any(f" {v} " in t for v in varian)).sum())
        if n:
            hasil[nama] = n
    return pd.Series(hasil, dtype="int64").sort_values(ascending=False)


def lisensi_teratas(df, n=5):
    return df["lisensi"].value_counts().head(n)


def aktivitas_vs_stars(df, hari=90):
    """Bandingkan median stars repo aktif vs tidak aktif.
    Aktif = push terakhir dalam `hari` hari sebelum push terbaru pada data."""
    ada = df["push_terakhir"].notna()
    if not ada.any():
        return None
    batas = df.loc[ada, "push_terakhir"].max() - pd.Timedelta(days=hari)
    aktif = df["push_terakhir"] >= batas
    return {
        "aktif_n": int(aktif.sum()),
        "aktif_median": float(df.loc[aktif, "stars"].median()) if aktif.any() else None,
        "tidak_n": int((~aktif).sum()),
        "tidak_median": float(df.loc[~aktif, "stars"].median()) if (~aktif).any() else None,
    }


def temuan(df):
    """Kalimat temuan otomatis (muncul di bot, laporan, dan log)."""
    if df.empty:
        return ["Belum ada data relevan untuk dianalisis."]
    hasil = []

    bahasa = bahasa_teratas(df, 1)
    tanpa = int((df["bahasa"] == TANPA_BAHASA).sum())
    if len(bahasa):
        hasil.append(f"Dari repo yang bahasanya terdeteksi, {bahasa.index[0]} paling dominan "
                     f"({int(bahasa.iloc[0])} repo); {tanpa} repo tidak punya bahasa terdeteksi.")
    else:
        hasil.append(f"Tidak ada bahasa yang terdeteksi pada {tanpa} repo.")

    agen = agen_disebut(df)
    if len(agen):
        hasil.append(f"Agen yang paling sering disebut adalah {agen.index[0]} "
                     f"({int(agen.iloc[0])} repo).")
    else:
        hasil.append("Belum ada nama agen yang terdeteksi pada deskripsi atau topik.")

    bulan = per_bulan(df)
    if len(bulan):
        hasil.append(f"Repo paling banyak dibuat pada {bulan.idxmax()} ({int(bulan.max())} repo).")

    akt = aktivitas_vs_stars(df)
    if akt and akt["aktif_median"] is not None and akt["tidak_median"] is not None:
        hasil.append(f"Median stars repo aktif (push dalam 90 hari terakhir data) adalah "
                     f"{akt['aktif_median']:.0f}, dibanding {akt['tidak_median']:.0f} "
                     f"pada repo yang tidak aktif.")
    elif akt and akt["aktif_median"] is not None:
        hasil.append(f"Semua repo tergolong aktif; median stars {akt['aktif_median']:.0f}.")

    lis = lisensi_teratas(df, 1)
    tanpa_lis = int((df["lisensi"] == TANPA_LISENSI).sum())
    hasil.append(f"Lisensi terbanyak adalah {lis.index[0]} ({int(lis.iloc[0])} repo); "
                 f"{tanpa_lis} repo tidak punya lisensi.")
    return hasil


# ---------- Grafik ----------
def _bar(seri, judul, sumbu_x, berkas, horizontal=True):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if len(seri) == 0:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center")
        ax.set_axis_off()
    elif horizontal:
        seri = seri.sort_values()
        ax.barh(seri.index.astype(str), seri.values, color="#2f6db5")
        ax.set_xlabel(sumbu_x)
    else:
        ax.bar(seri.index.astype(str), seri.values, color="#2f6db5")
        ax.set_ylabel(sumbu_x)
        ax.tick_params(axis="x", rotation=60)
    ax.set_title(judul)
    fig.tight_layout()
    fig.savefig(berkas, dpi=150)
    plt.close(fig)


def buat_grafik(df, folder=None):
    """Buat 3 grafik PNG. Kembalikan dict kunci -> Path."""
    folder = Path(folder or config.OUTPUT_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    jalur = {
        "bahasa": folder / "grafik_bahasa.png",
        "bulan": folder / "grafik_bulan.png",
        "agen": folder / "grafik_agen.png",
    }
    if df.empty:
        kosong = pd.Series(dtype="int64")
        _bar(kosong, "Bahasa pemrograman teratas", "Jumlah repo", jalur["bahasa"])
        _bar(kosong, "Repo skill dibuat per bulan", "Jumlah repo", jalur["bulan"], horizontal=False)
        _bar(kosong, "Agen yang disebut", "Jumlah repo", jalur["agen"])
        return jalur
    _bar(bahasa_teratas(df, 10), "Bahasa pemrograman teratas", "Jumlah repo", jalur["bahasa"])
    _bar(per_bulan(df), "Repo skill dibuat per bulan", "Jumlah repo", jalur["bulan"],
         horizontal=False)
    _bar(agen_disebut(df), "Agen yang paling sering disebut", "Jumlah repo", jalur["agen"])
    return jalur
