import os
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8760725679:AAH20fnR_lRNA74N3ke9DZnGA5aMQgz6icI"

DOWNLOAD_FOLDER = "downloads"

# create downloads folder if it doesn't exist
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


async def download_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):

    url = update.message.text

    await update.message.reply_text("⚡ Processing your request...")

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
        'cookiefile': 'cookies.txt',
        'noplaylist': True,
        'quiet': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0'
        },
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    mp3_file = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        mp3_file = filename.rsplit(".", 1)[0] + ".mp3"

        await update.message.reply_text("📤 Uploading MP3...")

        with open(mp3_file, "rb") as audio:
            await update.message.reply_audio(audio)

    except Exception as e:
        print(e)
        await update.message.reply_text("❌ Download failed.")

    finally:
        if mp3_file and os.path.exists(mp3_file):
            os.remove(mp3_file)


app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_audio))

print("🚀 Universal Media → MP3 Bot Running")

app.run_polling()
