from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from telegram.ext import CommandHandler
import re
import os
import json
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import matplotlib.pyplot as plt
import tempfile


# === TELEGRAM TOKEN ===
TOKEN = os.getenv("BOT_TOKEN")

# === GOOGLE SHEET ===
SCOPE = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS"))

CREDS = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_json, SCOPE)

client = gspread.authorize(CREDS)
spreadsheet = client.open("nyatet-db")
sheet = spreadsheet.worksheet("Data")

# === HANDLER PESAN ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    try:
        jumlah = parse_jumlah(text)
        if jumlah is None:
            raise ValueError("Jumlah tidak ditemukan")

        # hapus angka dari keterangan
        keterangan = re.sub(r'\d+(\s*(k|rb|ribu|jt|juta))?', '', text, flags=re.IGNORECASE).strip()

        tanggal = datetime.now().strftime("%Y-%m-%d")
        tipe = deteksi_tipe(text)
        bulan = datetime.now().strftime("%Y-%m")

        row = [tanggal, keterangan, jumlah, tipe, bulan]

        sheet.append_row(row, value_input_option="USER_ENTERED")

        await update.message.reply_text(
            f"✅ Dicatat\n📝 {keterangan}\n💸 Rp{jumlah:,}"
        )

    except Exception as e:
        await update.message.reply_text(
            "❌ Format tidak dikenali\n"
            "Contoh:\n"
            "• makan siang 25k\n"
            "• beli kopi 18rb\n"
            "• gaji 5jt"
        )
        print("ERROR:", e)

#=== HARI INI ===
async def hari_ini(update, context):
    data = sheet.get_all_records()
    if not data:
        await update.message.reply_text("❌ Belum ada data")
        return

    today = datetime.now().strftime("%Y-%m-%d")

    pengeluaran_hari_ini = [
        d for d in data
        if d["Tanggal"] == today and d["Tipe"] == "Pengeluaran"
    ]

    if not pengeluaran_hari_ini:
        await update.message.reply_text("✅ Tidak ada pengeluaran hari ini")
        return

    total = sum(int(d["Jumlah"]) for d in pengeluaran_hari_ini)

    pesan = f"📅 *Pengeluaran Hari Ini ({today})*\n\n"
    for d in pengeluaran_hari_ini:
        pesan += f"• {d['Keterangan']} — Rp{int(d['Jumlah']):,}\n"

    pesan += f"\n💸 *Total:* Rp{total:,}"

    await update.message.reply_text(
        pesan,
        parse_mode="Markdown"
    )

#=== BULAN INI ===
async def bulanini(update, context):
    bulan = datetime.now().strftime("%Y-%m")

    data = sheet.get_all_records()
    pemasukan = sum(
        d["Jumlah"] for d in data
        if d["Bulan"] == bulan and d["Tipe"] == "Pemasukan"
    )
    pengeluaran = sum(
        d["Jumlah"] for d in data
        if d["Bulan"] == bulan and d["Tipe"] == "Pengeluaran"
    )

    saldo = pemasukan - pengeluaran

#=== MESSAGE ===
await update.message.reply_text(
    f"✅ Dicatat\n"
    f"📝 {keterangan}\n"
    f"💸 Rp{jumlah:,}\n"
    f"📌 {tipe}"
)


async def hariini(update, context):
    hari = datetime.now().strftime("%Y-%m-%d")

    data = sheet.get_all_records()
    total = sum(
        d["Jumlah"] for d in data
        if d["Tanggal"] == hari and d["Tipe"] == "Pengeluaran"
    )

    await update.message.reply_text(
        f"📅 Pengeluaran hari ini: Rp{total:,}"
    )

# === GRAFIK ===
async def grafik(update, context):
    data = sheet.get_all_records()
    if not data:
        await update.message.reply_text("❌ Belum ada data")
        return

    df = pd.DataFrame(data)

    bulan_ini = datetime.now().strftime("%Y-%m")
    df = df[df["Bulan"] == bulan_ini]

    if df.empty:
        await update.message.reply_text("❌ Tidak ada data bulan ini")
        return

    rekap = df.groupby("Tipe")["Jumlah"].sum()

    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        plt.figure()
        rekap.plot(kind="bar")
        plt.title(f"Pemasukan vs Pengeluaran ({bulan_ini})")
        plt.ylabel("Rupiah")
        plt.tight_layout()
        plt.savefig(f.name)
        plt.close()

        await update.message.reply_photo(
            photo=open(f.name, "rb"),
            caption=f"📊 Grafik Keuangan {bulan_ini}"
        )

# === FUNCTION ===

def parse_jumlah(text: str) -> int | None:
    text = text.lower().replace(".", "").replace(",", "")

    # pola: 25k, 25rb, 25 ribu, 2jt, 2 juta
    patterns = [
        (r'(\d+)\s*(k|rb|ribu)', 1_000),
        (r'(\d+)\s*(jt|juta)', 1_000_000),
        (r'(\d+)', 1)
    ]

    for pattern, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1)) * multiplier

    return None

PEMASUKAN_KEYWORDS = [
    "gaji", "bonus", "thr", "fee", "komisi", "transfer masuk", "refund"
]

def deteksi_tipe(text: str) -> str:
    text = text.lower()
    for k in PEMASUKAN_KEYWORDS:
        if k in text:
            return "Pemasukan"
    return "Pengeluaran"


# === MAIN ===

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("hariini", hari_ini))
app.add_handler(CommandHandler("bulanini", bulanini))
app.add_handler(CommandHandler("grafik", grafik))

app.run_polling()




