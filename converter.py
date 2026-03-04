import os
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8760725679:AAH20fnR_lRNA74N3ke9DZnGA5aMQgz6icI"

DOWNLOAD_FOLDER = "downloads"


async def download_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):

    url = update.message.text

    await update.message.reply_text("⚡ Processing your request...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
        'cookiefile': 'cookies.txt',
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
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        mp3_file = filename.rsplit(".", 1)[0] + ".mp3"

        await update.message.reply_text("📤 Uploading MP3...")

        with open(mp3_file, "rb") as audio:
            await update.message.reply_audio(audio)

        os.remove(mp3_file)

    except Exception as e:
        await update.message.reply_text("❌ Download failed.")


app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT, download_audio))

print("🚀 Universal Media → MP3 Bot Running")

app.run_polling()
