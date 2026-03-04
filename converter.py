import os
from telethon import TelegramClient, events
from moviepy import VideoFileClip

api_id = 38728622
api_hash = "e47b605fefe098c8552007d29f0639ed"

client = TelegramClient("session", api_id, api_hash)

@client.on(events.NewMessage)
async def handler(event):
    if event.video:
        await event.reply("Checking video please wait...")

        file_path = await event.download_media()
        audio_path = file_path + ".mp3"

        await event.reply("Your video is Converting to MP3...")

        clip = VideoFileClip(file_path)
        clip.audio.write_audiofile(audio_path)
        clip.close()

        await event.reply(file=audio_path)

        os.remove(file_path)
        os.remove(audio_path)

client.start()
print("Converter running...")
client.run_until_disconnected()
