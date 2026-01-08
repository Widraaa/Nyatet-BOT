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
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")  # WAJIB
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# ================== GOOGLE SHEET ==================
creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, SCOPE)
gc = gspread.authorize(creds)

spreadsheet = gc.open_by_key(SPREADSHEET_ID)
sheet = spreadsheet.sheet1  # sheet pertama

# ================== GLOBAL ==================
last_deleted_row = None

# ================== UTIL ==================
def clean_number(val):
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    return int(float(str(val).replace(",", "")))

def parse_jumlah(text: str):
    text = text.lower().replace(".", "").replace(",", "")
    patterns = [
        (r"(\d+)\s*(k|rb|ribu)", 1_000),
        (r"(\d+)\s*(jt|juta)", 1_000_000),
        (r"(\d+)", 1),
    ]
    for p, m in patterns:
        match = re.search(p, text)
        if match:
            return int(match.group(1)) * m
    return None

PEMASUKAN_KEYWORDS = ["gaji", "bonus", "thr", "fee", "komisi", "refund"]

def deteksi_tipe(text):
    text = text.lower()
    for k in PEMASUKAN_KEYWORDS:
        if k in text:
            return "Pemasukan"
    return "Pengeluaran"

# ================== TEXT HANDLER ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    jumlah = parse_jumlah(text)
    if jumlah is None:
        await update.message.reply_text("❌ Jumlah tidak ditemukan")
        return

    keterangan = re.sub(
        r"\d+(\s*(k|rb|ribu|jt|juta))?",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip().capitalize()

    tanggal = datetime.now().strftime("%Y-%m-%d")
    bulan = datetime.now().strftime("%Y-%m")
    tipe = deteksi_tipe(text)

    row = [tanggal, keterangan, jumlah, tipe, bulan]
    sheet.append_row(row, value_input_option="USER_ENTERED")

    await update.message.reply_text(
        f"✅ *Dicatat*\n"
        f"📝 {keterangan}\n"
        f"💸 Rp{jumlah:,}\n"
        f"📌 {tipe}",
        parse_mode="Markdown",
    )
# ===================== COMMAND =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Bot Keuangan Aktif*\n\n"
        "Contoh input:\n"
        "• kopi 2k\n"
        "• gaji 5 juta\n\n"
        "Perintah:\n"
        "/hariini\n"
        "/bulanini\n"
        "/saldo\n"
        "/grafik\n"
        "/hapus_terakhir\n"
        "/undo_hapus",
        parse_mode="Markdown"
    )

# ================== /hariini ==================
async def hariini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")
    data = sheet.get_all_records()

    items = [
        d for d in data
        if d["Tanggal"] == today and d["Tipe"] == "Pengeluaran"
    ]

    if not items:
        await update.message.reply_text("✅ Tidak ada pengeluaran hari ini")
        return

    total = sum(clean_number(d["Jumlah"]) for d in items)
    msg = f"📅 *Pengeluaran Hari Ini ({today})*\n\n"
    for d in items:
        msg += f"• {d['Keterangan']} — Rp{clean_number(d['Jumlah']):,}\n"
    msg += f"\n💸 *Total:* Rp{total:,}"

    await update.message.reply_text(msg, parse_mode="Markdown")

# ================== /bulanini ==================
async def bulanini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bulan = datetime.now().strftime("%Y-%m")
    data = sheet.get_all_records()

    pemasukan = sum(
        clean_number(d["Jumlah"])
        for d in data
        if d["Bulan"] == bulan and d["Tipe"] == "Pemasukan"
    )

    pengeluaran = sum(
        clean_number(d["Jumlah"])
        for d in data
        if d["Bulan"] == bulan and d["Tipe"] == "Pengeluaran"
    )

    saldo = pemasukan - pengeluaran

    await update.message.reply_text(
        f"📆 *Rekap Bulan Ini ({bulan})*\n\n"
        f"💰 Pemasukan: Rp{pemasukan:,}\n"
        f"💸 Pengeluaran: Rp{pengeluaran:,}\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 *Saldo:* Rp{saldo:,}",
        parse_mode="Markdown",
    )

# ================== /saldo ==================
async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = sheet.get_all_records()

    pemasukan = sum(
        clean_number(d["Jumlah"])
        for d in data if d["Tipe"] == "Pemasukan"
    )
    pengeluaran = sum(
        clean_number(d["Jumlah"])
        for d in data if d["Tipe"] == "Pengeluaran"
    )

    await update.message.reply_text(
        f"💼 *Saldo Saat Ini*\n\n"
        f"💰 Total Pemasukan: Rp{pemasukan:,}\n"
        f"💸 Total Pengeluaran: Rp{pengeluaran:,}\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 *Saldo Akhir:* Rp{pemasukan - pengeluaran:,}",
        parse_mode="Markdown",
    )

# ================== /grafik ==================
async def grafik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = sheet.get_all_records()
    bulan = datetime.now().strftime("%Y-%m")

    pemasukan = sum(
        clean_number(d["Jumlah"])
        for d in data if d["Bulan"] == bulan and d["Tipe"] == "Pemasukan"
    )
    pengeluaran = sum(
        clean_number(d["Jumlah"])
        for d in data if d["Bulan"] == bulan and d["Tipe"] == "Pengeluaran"
    )

    if pemasukan == 0 and pengeluaran == 0:
        await update.message.reply_text("❌ Tidak ada data bulan ini")
        return

    labels = ["Pemasukan", "Pengeluaran"]
    values = [pemasukan, pengeluaran]

    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        plt.figure()
        plt.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
        plt.title(f"Keuangan {bulan}")
        plt.tight_layout()
        plt.savefig(f.name)
        plt.close()

        await update.message.reply_photo(
            photo=open(f.name, "rb"),
            caption=(
                f"📊 *Rekap {bulan}*\n\n"
                f"💰 Pemasukan: Rp{pemasukan:,}\n"
                f"💸 Pengeluaran: Rp{pengeluaran:,}"
            ),
            parse_mode="Markdown",
        )

# ================== /hapus ==================
async def hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_deleted_row
    values = sheet.get_all_values()
    if len(values) <= 1:
        await update.message.reply_text("❌ Tidak ada data")
        return

    last_deleted_row = values[-1]
    sheet.delete_rows(len(values))
    await update.message.reply_text("🗑️ Data terakhir dihapus")

# ================== /undo_hapus ==================
async def undo_hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_deleted_row
    if not last_deleted_row:
        await update.message.reply_text("❌ Tidak ada data untuk dikembalikan")
        return

    sheet.append_row(last_deleted_row, value_input_option="USER_ENTERED")
    last_deleted_row = None
    await update.message.reply_text("♻️ Data berhasil dikembalikan")

# ================== MAIN ==================
app = ApplicationBuilder().token(TOKEN).build()

# COMMANDS DULU
app.add_handler(CommandHandler("hariini", hariini))
app.add_handler(CommandHandler("bulanini", bulanini))
app.add_handler(CommandHandler("saldo", saldo))
app.add_handler(CommandHandler("grafik", grafik))
app.add_handler(CommandHandler("hapus", hapus))
app.add_handler(CommandHandler("undo_hapus", undo_hapus))

# TEXT TERAKHIR
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
