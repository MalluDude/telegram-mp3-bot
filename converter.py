import os
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8760725679:AAH20fnR_lRNA74N3ke9DZnGA5aMQgz6icI"

async def download_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):

    url = update.message.text

    await update.message.reply_text("⚡ Processing your request...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'audio.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        await update.message.reply_text("📤 Uploading MP3...")

        await update.message.reply_audio(audio=open("audio.mp3", "rb"))

    except Exception as e:
        await update.message.reply_text("❌ Download failed.")

    if os.path.exists("audio.mp3"):
        os.remove("audio.mp3")


app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT, download_audio))

print("🚀 Universal Media → MP3 Bot Running")

app.run_polling()
