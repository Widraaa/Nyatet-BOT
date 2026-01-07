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


# === TELEGRAM TOKEN ===
TOKEN = os.getenv("BOT_TOKEN")

# === GOOGLE SHEET ===
SCOPE = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS"))

CREDS = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_json, SCOPE)

client = gspread.authorize(CREDS)
sheet = client.open("nyatet-db").sheet1

# === HANDLER PESAN ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    try:
        keterangan, jumlah = text.rsplit(" ", 1)
        jumlah = int(jumlah)

        tanggal = datetime.now().strftime("%Y-%m-%d")
        tipe = "Pengeluaran"

        sheet.append_row([tanggal, keterangan, jumlah, tipe])

        await update.message.reply_text("✅ Pengeluaran berhasil dicatat")
    except:
        await update.message.reply_text(
            "❌ Format salah\nContoh:\nMakan siang 25000"
        )

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

    await update.message.reply_text(
        f"📆 Laporan {bulan}\n"
        f"📥 Pemasukan: Rp{pemasukan:,}\n"
        f"📤 Pengeluaran: Rp{pengeluaran:,}\n"
        f"💰 Saldo: Rp{saldo:,}"
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



def parse_jumlah(text):
    text = text.lower().replace("ribu","000").replace("k","000")
    angka = re.findall(r'\d+', text)
    return int(angka[-1]) if angka else None

# === MAIN ===

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("bulanini", bulanini))

app.run_polling()

