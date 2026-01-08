import os
import json
import re
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

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

LAST_DELETED_ROW = None

# ===================== HELPER =====================

def clean_number(value):
    if isinstance(value, (int, float)):
        return int(value)

    value = str(value)
    value = value.replace(",", "")
    value = re.sub(r"[^\d]", "", value)

    return int(value) if value else 0


def parse_jumlah(text):
    text = text.lower().replace(" ", "")

    match = re.search(r"(\d+(?:\.\d+)?)(k|ribu)?", text)
    if not match:
        return None

    angka = float(match.group(1))
    satuan = match.group(2)

    if satuan in ["k", "ribu"]:
        angka *= 1000

    return int(angka)


def bulan_sekarang():
    return datetime.now().strftime("%Y-%m")


def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")

# ===================== COMMAND =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Bot Keuangan Aktif*\n\n"
        "Contoh input:\n"
        "• kopi 2k\n"
        "• gaji 5 juta\n\n"
        "Perintah:\n"
        "/bulanini\n"
        "/saldo\n"
        "/hapus_terakhir\n"
        "/undo_hapus",
        parse_mode="Markdown"
    )


async def bulan_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bulan = bulan_sekarang()
    rows = sheet.get_all_values()[1:]

    pemasukan = pengeluaran = 0

    for r in rows:
        if len(r) < 5:
            continue
        if r[4] == bulan:
            jumlah = clean_number(r[2])
            if r[3] == "Pemasukan":
                pemasukan += jumlah
            elif r[3] == "Pengeluaran":
                pengeluaran += jumlah

    await update.message.reply_text(
        f"📅 *Bulan Ini ({bulan})*\n\n"
        f"💰 Pemasukan: Rp{pemasukan:,}\n"
        f"💸 Pengeluaran: Rp{pengeluaran:,}",
        parse_mode="Markdown"
    )


async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = sheet.get_all_values()[1:]

    pemasukan = pengeluaran = 0

    for r in rows:
        if len(r) < 4:
            continue

        jumlah = clean_number(r[2])

        if r[3] == "Pemasukan":
            pemasukan += jumlah
        elif r[3] == "Pengeluaran":
            pengeluaran += jumlah

    saldo_akhir = pemasukan - pengeluaran

    await update.message.reply_text(
        f"💼 *Saldo Saat Ini*\n\n"
        f"💰 Total Pemasukan: Rp{pemasukan:,}\n"
        f"💸 Total Pengeluaran: Rp{pengeluaran:,}\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 Saldo Akhir: Rp{saldo_akhir:,}",
        parse_mode="Markdown"
    )


async def hapus_terakhir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LAST_DELETED_ROW

    try:
        values = sheet.get_all_values()

        if len(values) <= 1:
            await update.message.reply_text("❌ Tidak ada data untuk dihapus")
            return

        LAST_DELETED_ROW = values[-1]
        sheet.delete_rows(len(values))

        jumlah = clean_number(LAST_DELETED_ROW[2])

        await update.message.reply_text(
            f"🗑️ *Data terakhir dihapus*\n\n"
            f"📝 {LAST_DELETED_ROW[1]}\n"
            f"💸 Rp{jumlah:,}\n\n"
            f"↩️ /undo_hapus untuk membatalkan",
            parse_mode="Markdown"
        )

    except Exception as e:
        print("ERROR HAPUS:", e)
        await update.message.reply_text("❌ Gagal menghapus data")


async def undo_hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LAST_DELETED_ROW

    if not LAST_DELETED_ROW:
        await update.message.reply_text("❌ Tidak ada data yang bisa di-undo")
        return

    try:
        sheet.append_row(
            LAST_DELETED_ROW,
            value_input_option="USER_ENTERED"
        )

        jumlah = clean_number(LAST_DELETED_ROW[2])
        LAST_DELETED_ROW = None

        await update.message.reply_text(
            f"↩️ *Undo berhasil*\n\n"
            f"📝 Data dikembalikan\n"
            f"💸 Rp{jumlah:,}",
            parse_mode="Markdown"
        )

    except Exception as e:
        print("ERROR UNDO:", e)
        await update.message.reply_text("❌ Gagal undo")


# ===================== MESSAGE HANDLER =====================

async def catat_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    jumlah = parse_jumlah(text)

    if not jumlah:
        return

    keterangan = re.sub(r"\d.*", "", text).strip().title()
    tipe = "Pemasukan" if "gaji" in text.lower() or "bonus" in text.lower() else "Pengeluaran"

    row = [
        tanggal_hari_ini(),
        keterangan,
        jumlah,
        tipe,
        bulan_sekarang()
    ]

    try:
        sheet.append_row(row, value_input_option="USER_ENTERED")
        await update.message.reply_text(
            f"✅ *Tercatat*\n\n"
            f"📝 {keterangan}\n"
            f"💸 Rp{jumlah:,}\n"
            f"📌 {tipe}",
            parse_mode="Markdown"
        )
    except Exception as e:
        print("ERROR SIMPAN:", e)
        await update.message.reply_text("❌ Gagal menyimpan data")


# ===================== MAIN =====================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bulanini", bulan_ini))
    app.add_handler(CommandHandler("saldo", saldo))
    app.add_handler(CommandHandler("hapus_terakhir", hapus_terakhir))
    app.add_handler(CommandHandler("undo_hapus", undo_hapus))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, catat_text))

    print("🤖 Bot keuangan berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()

