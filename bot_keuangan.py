from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import re
import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import tempfile

# ================== CONFIG ==================

TOKEN = os.getenv("BOT_TOKEN")

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
CREDS = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, SCOPE)
client = gspread.authorize(CREDS)

SPREADSHEET_ID = "1AAq3K-qWbRow8Sh0r3PDuqPiIFG4AoIRJ4fJp4v6vgQ"
sheet = client.open_by_key(SPREADSHEET_ID).get_worksheet(0)

# ================== UTIL ==================

def parse_jumlah(text: str) -> int | None:
    text = text.lower().replace(".", "").replace(",", "")

    patterns = [
        (r"(\d+)\s*(k|rb|ribu)", 1_000),
        (r"(\d+)\s*(jt|juta)", 1_000_000),
        (r"(\d+)", 1),
    ]

    for pattern, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1)) * multiplier
    return None


PEMASUKAN_KEYWORDS = [
    "gaji", "bonus", "thr", "fee", "komisi", "refund"
]


def deteksi_tipe(text: str) -> str:
    text = text.lower()
    return "Pemasukan" if any(k in text for k in PEMASUKAN_KEYWORDS) else "Pengeluaran"

# ================== MESSAGE HANDLER ==================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    print("TEXT:", text)

    jumlah = parse_jumlah(text)
    if jumlah is None:
        await update.message.reply_text(
            "❌ Format tidak dikenali\n\n"
            "Contoh:\n"
            "• kopi 5k\n"
            "• makan 25rb\n"
            "• gaji 5jt"
        )
        return

    keterangan = re.sub(
        r"\d+(\s*(k|rb|ribu|jt|juta))?",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    tanggal = datetime.now().strftime("%Y-%m-%d")
    bulan = datetime.now().strftime("%Y-%m")
    tipe = deteksi_tipe(text)

    row = [tanggal, keterangan.capitalize(), jumlah, tipe, bulan]
    sheet.append_row(row, value_input_option="USER_ENTERED")

    await update.message.reply_text(
        f"✅ Dicatat\n"
        f"📝 {keterangan}\n"
        f"💸 Rp{jumlah:,}\n"
        f"📌 {tipe}"
    )

# ================== /hariini ==================

async def hari_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")
    data = sheet.get_all_records()

    pengeluaran = [
        d for d in data
        if d["Tanggal"] == today and d["Tipe"] == "Pengeluaran"
    ]

    if not pengeluaran:
        await update.message.reply_text("✅ Tidak ada pengeluaran hari ini")
        return

    total = sum(int(d["Jumlah"]) for d in pengeluaran)

    pesan = f"📅 Pengeluaran Hari Ini ({today})\n\n"
    for d in pengeluaran:
        pesan += f"• {d['Keterangan']} — Rp{int(d['Jumlah']):,}\n"

    pesan += f"\n💸 Total: Rp{total:,}"
    await update.message.reply_text(pesan)

# ================== /bulanini ==================

async def bulanini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bulan = datetime.now().strftime("%Y-%m")
    data = sheet.get_all_records()

    pemasukan = sum(
        int(d["Jumlah"]) for d in data
        if d["Bulan"] == bulan and d["Tipe"] == "Pemasukan"
    )

    pengeluaran = sum(
        int(d["Jumlah"]) for d in data
        if d["Bulan"] == bulan and d["Tipe"] == "Pengeluaran"
    )

    saldo = pemasukan - pengeluaran

    await update.message.reply_text(
        f"📆 Rekap Bulan Ini ({bulan})\n\n"
        f"💰 Pemasukan: Rp{pemasukan:,}\n"
        f"💸 Pengeluaran: Rp{pengeluaran:,}\n"
        f"📊 Saldo: Rp{saldo:,}"
    )

# ================== /grafik ==================

async def grafik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = sheet.get_all_records()
    if not data:
        await update.message.reply_text("❌ Belum ada data")
        return

    df = pd.DataFrame(data)

    # Pastikan tipe data benar
    df["Jumlah"] = pd.to_numeric(df["Jumlah"], errors="coerce")
    df["Tanggal"] = pd.to_datetime(df["Tanggal"], errors="coerce")

    bulan_ini = datetime.now().strftime("%Y-%m")
    df = df[df["Tanggal"].dt.strftime("%Y-%m") == bulan_ini]

    if df.empty:
        await update.message.reply_text("❌ Tidak ada data bulan ini")
        return

    pemasukan = df[df["Tipe"] == "Pemasukan"]["Jumlah"].sum()
    pengeluaran = df[df["Tipe"] == "Pengeluaran"]["Jumlah"].sum()

    if pemasukan == 0 and pengeluaran == 0:
        await update.message.reply_text("❌ Data kosong")
        return

    # ===== PIE CHART =====
    labels = []
    values = []

    if pemasukan > 0:
        labels.append("Pemasukan")
        values.append(pemasukan)

    if pengeluaran > 0:
        labels.append("Pengeluaran")
        values.append(pengeluaran)

    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        plt.figure(figsize=(6, 6))
        plt.pie(
            values,
            labels=labels,
            autopct="%1.1f%%",
            startangle=90
        )
        plt.title(f"Rekap Keuangan {bulan_ini}")
        plt.tight_layout()
        plt.savefig(f.name)
        plt.close()

        caption = (
            f"📊 *Rekap Keuangan {bulan_ini}*\n\n"
            f"💰 Pemasukan: Rp{int(pemasukan):,}\n"
            f"💸 Pengeluaran: Rp{int(pengeluaran):,}\n"
            f"📊 Selisih: Rp{int(pemasukan - pengeluaran):,}"
        )

        await update.message.reply_photo(
            photo=open(f.name, "rb"),
            caption=caption,
            parse_mode="Markdown"
        )

# ================== GRAFIK BULANAN =============
async def grafik_pengeluaran(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = sheet.get_all_records()
    if not data:
        await update.message.reply_text("❌ Belum ada data")
        return

    df = pd.DataFrame(data)

    # Rapihkan data
    df["Jumlah"] = pd.to_numeric(df["Jumlah"], errors="coerce")
    df["Tanggal"] = pd.to_datetime(df["Tanggal"], errors="coerce")
    df["Keterangan"] = df["Keterangan"].str.capitalize()

    bulan_ini = datetime.now().strftime("%Y-%m")

    df = df[
        (df["Tanggal"].dt.strftime("%Y-%m") == bulan_ini)
        & (df["Tipe"] == "Pengeluaran")
    ]

    if df.empty:
        await update.message.reply_text("❌ Tidak ada pengeluaran bulan ini")
        return

    # Group by kategori
    rekap = df.groupby("Keterangan")["Jumlah"].sum().sort_values(ascending=False)

    # Batasi top 6 kategori
    if len(rekap) > 6:
        top = rekap[:6]
        lainnya = rekap[6:].sum()
        rekap = top
        rekap["Lainnya"] = lainnya

    total = rekap.sum()

    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        plt.figure(figsize=(7, 7))
        plt.pie(
            rekap,
            labels=rekap.index,
            autopct=lambda p: f"{p:.1f}%\nRp{int(p*total/100):,}",
            startangle=90
        )
        plt.title(f"Pengeluaran per Kategori ({bulan_ini})")
        plt.tight_layout()
        plt.savefig(f.name)
        plt.close()

        caption = (
            f"🥧 *Pengeluaran per Kategori ({bulan_ini})*\n\n"
            f"💸 Total: Rp{int(total):,}\n\n"
            f"📌 Top kategori:\n"
        )

        for k, v in rekap.items():
            caption += f"• {k}: Rp{int(v):,}\n"

        await update.message.reply_photo(
            photo=open(f.name, "rb"),
            caption=caption,
            parse_mode="Markdown"
        )
# ================== DELETE BEFORE ============
def clean_number(value: str) -> int:
    return int(float(value.replace(",", "")))


async def hapus_terakhir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        values = sheet.get_all_values()

        if len(values) <= 1:
            await update.message.reply_text("❌ Tidak ada data untuk dihapus")
            return

        last_row_index = len(values)
        last_row = values[-1]

        tanggal, keterangan, jumlah, tipe, bulan = last_row

        jumlah_int = clean_number(jumlah)

        sheet.delete_rows(last_row_index)

        await update.message.reply_text(
            f"🗑️ *Data terakhir dihapus*\n\n"
            f"📅 {tanggal}\n"
            f"📝 {keterangan}\n"
            f"💸 Rp{jumlah_int:,}\n"
            f"📌 {tipe}",
            parse_mode="Markdown"
        )

    except Exception as e:
        print("ERROR HAPUS:", e)
        await update.message.reply_text("❌ Gagal menghapus data")

#=================== SALDO ================
async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rows = sheet.get_all_values()

        if len(rows) <= 1:
            await update.message.reply_text("❌ Belum ada data")
            return

        total_pemasukan = 0
        total_pengeluaran = 0

        # Skip header (row 0)
        for row in rows[1:]:
            try:
                jumlah = clean_number(row[2])  # kolom Jumlah
                tipe = row[3].strip()          # kolom Tipe
            except:
                continue

            if tipe == "Pemasukan":
                total_pemasukan += jumlah
            elif tipe == "Pengeluaran":
                total_pengeluaran += jumlah

        saldo_akhir = total_pemasukan - total_pengeluaran

        await update.message.reply_text(
            f"💼 *Saldo Saat Ini*\n\n"
            f"💰 Total Pemasukan: Rp{total_pemasukan:,}\n"
            f"💸 Total Pengeluaran: Rp{total_pengeluaran:,}\n"
            f"━━━━━━━━━━━━━━\n"
            f"📊 *Saldo Akhir: Rp{saldo_akhir:,}*",
            parse_mode="Markdown"
        )

    except Exception as e:
        print("ERROR SALDO:", e)
        await update.message.reply_text("❌ Gagal menghitung saldo")


# ================== MAIN ==================

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("hariini", hari_ini))
app.add_handler(CommandHandler("bulanini", bulanini))
app.add_handler(CommandHandler("grafik", grafik))
app.add_handler(CommandHandler("grafikpengeluaran", grafik_pengeluaran))
app.add_handler(CommandHandler("hapus_terakhir", hapus_terakhir))
app.add_handler(CommandHandler("saldo", saldo))

app.run_polling()



