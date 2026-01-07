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
        tipe = "Pengeluaran"
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


# === MAIN ===

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("bulanini", bulanini))

app.run_polling()



