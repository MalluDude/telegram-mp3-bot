import os
import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8760725679:AAH20fnR_lRNA74N3ke9DZnGA5aMQgz6icI"

async def convert_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video or update.message.document

    if not video:
        await update.message.reply_text("❌ Please send a valid video file.")
        return

    await update.message.reply_text("📥 Downloading video...")

    file = await context.bot.get_file(video.file_id)

    video_path = f"{video.file_id}.mp4"
    audio_path = f"{video.file_id}.mp3"

    await file.download_to_drive(video_path)

    await update.message.reply_text("🎵 Converting to MP3...")

    try:
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-vn", "-ab", "192k", audio_path],
            check=True
        )

        await update.message.reply_text("📤 Uploading MP3...")

        with open(audio_path, "rb") as audio:
            await update.message.reply_audio(audio)

    except Exception as e:
        await update.message.reply_text("❌ Conversion failed.")

    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

        if os.path.exists(audio_path):
            os.remove(audio_path)

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, convert_video))

print("🤖 MP3 Converter Bot Running...")

app.run_polling()
