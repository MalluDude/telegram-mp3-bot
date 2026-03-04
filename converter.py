import os
import yt_dlp
import re
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables!")

DOWNLOAD_FOLDER = os.getenv("DOWNLOAD_FOLDER", "downloads")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 50 * 1024 * 1024))
MAX_DURATION = int(os.getenv("MAX_DURATION", 3600))

# Create download folder
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Platform emojis
PLATFORM_EMOJIS = {
    'youtube': '📺',
    'spotify': '🎵',
    'instagram': '📸',
    'pinterest': '📌',
    'facebook': '👤',
    'twitter': '🐦',
    'tiktok': '🎵',
    'reddit': '👽',
    'default': '🔗'
}

def detect_platform(url):
    url = url.lower()

    if "youtu" in url:
        return "youtube"

    if "spotify" in url:
        return "spotify"

    if "instagram" in url:
        return "instagram"

    if "pinterest" in url or "pin.it" in url:
        return "pinterest"

    if "facebook" in url or "fb.watch" in url:
        return "facebook"

    if "twitter" in url or "x.com" in url:
        return "twitter"

    if "tiktok" in url:
        return "tiktok"

    if "reddit" in url:
        return "reddit"

    return "unknown"
    
    platforms = {
        'youtube': ['youtube.com', 'youtu.be', 'm.youtube.com', 'youtube shorts'],
        'spotify': ['spotify.com', 'open.spotify.com', 'spotify:'],
        'instagram': ['instagram.com', 'instagr.am'],
        'pinterest': ['pinterest.com', 'pin.it', 'pinterest.co'],
        'facebook': ['facebook.com', 'fb.watch', 'fb.com', 'fb.me'],
        'twitter': ['twitter.com', 'x.com', 'tweet'],
        'tiktok': ['tiktok.com', 'vm.tiktok.com'],
        'reddit': ['reddit.com', 'redd.it']
    }
    
    for platform, domains in platforms.items():
        for domain in domains:
            if domain in url_lower:
                return platform
    
    return 'unknown'

def format_size(bytes):
    """Format file size"""
    if not bytes:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.1f} GB"

def format_duration(seconds):
    """Format duration"""
    if not seconds:
        return "Unknown"
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = (
        "🎵 *Universal Media to MP3 Converter Bot*\n\n"
        "Send me a link from any supported platform and I'll convert it to MP3!\n\n"
        "*Supported Platforms:*\n"
        "📺 YouTube (videos, shorts)\n"
        "🎵 Spotify (tracks)\n"
        "📸 Instagram (reels, posts, stories)\n"
        "📌 Pinterest (videos)\n"
        "👤 Facebook (videos, reels)\n"
        "🐦 Twitter/X (videos)\n"
        "🎵 TikTok (videos)\n"
        "👽 Reddit (videos)\n\n"
        "⚠️ *Limitations:*\n"
        f"• Max file size: {MAX_FILE_SIZE // (1024*1024)}MB\n"
        f"• Max duration: {MAX_DURATION // 60} minutes\n"
        "• No playlists or albums\n\n"
        "Simply paste any link and I'll handle the rest! 🚀"
    )
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)

async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main conversion function"""
    url = update.message.text.strip()
    user = update.effective_user
    username = user.username or user.first_name
    
    # Basic URL validation
    if not url.startswith(('http://', 'https://', 'spotify:')):
        await update.message.reply_text("❌ Please send a valid URL")
        return
    
    # Detect platform
    platform = detect_platform(url)
    
    if platform == 'unknown':
        await update.message.reply_text("❌ Platform not supported or unrecognized URL.")
        return
    
    emoji = PLATFORM_EMOJIS.get(platform, PLATFORM_EMOJIS['default'])
    processing_msg = await update.message.reply_text(
        f"{emoji} Processing {platform.title()} link...\n"
        f"⏳ This may take a moment..."
    )
    
    try:
        # Handle Spotify
        if platform == 'spotify':
            await processing_msg.edit_text(f"{emoji} 🎵 Searching YouTube for this track...")
            url = f"ytsearch1:{url} audio"
            platform = 'youtube'
        
        # Generate filename
        timestamp = int(time.time())
        safe_filename = f"{username}_{timestamp}"
        
        # yt-dlp options
        ydl_opts = {
    'cookiefile': 'cookies.txt',
    'format': 'bestaudio/best',
    'outtmpl': f'{DOWNLOAD_FOLDER}/{safe_filename}.%(ext)s',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'geo_bypass': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'http_headers': {
        'User-Agent': 'Mozilla/5.0'
    }
}
        
        # Add YouTube-specific options
        if platform == 'youtube':
    ydl_opts.update({
        'extractor_args': {
            'youtube': {
                'player_client': ['android']
            }
        }
    })
        
        mp3_file = None
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await processing_msg.edit_text(f"{emoji} 🔍 Fetching video information...")
                
                info = ydl.extract_info(url, download=False)
                
                # Handle search results
                if 'entries' in info:
                    if not info['entries']:
                        await processing_msg.edit_text(f"{emoji} ❌ No videos found.")
                        return
                    info = info['entries'][0]
                
                # Check duration
                duration = info.get('duration', 0)
                if duration > MAX_DURATION:
                    await processing_msg.edit_text(
                        f"{emoji} ❌ Video too long (> {MAX_DURATION//60} minutes)."
                    )
                    return
                
                title = info.get('title', 'Unknown')
                uploader = info.get('uploader', 'Unknown')
                
                await processing_msg.edit_text(
                    f"{emoji} *Found:* {title[:100]}\n"
                    f"👤 *Uploader:* {uploader}\n"
                    f"⏱️ *Duration:* {format_duration(duration)}\n\n"
                    f"⬇️ Downloading and converting...",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Download
                ydl.download([url])
                filename = ydl.prepare_filename(info)
            
            mp3_file = filename.rsplit(".", 1)[0] + ".mp3"
            
            if not os.path.exists(mp3_file):
                await processing_msg.edit_text(f"{emoji} ❌ Conversion failed")
                return
            
            # Upload
            await processing_msg.edit_text(f"{emoji} 📤 Uploading MP3...")
            
            with open(mp3_file, "rb") as audio:
                await update.message.reply_audio(
                    audio,
                    title=title[:200],
                    performer=uploader[:100],
                    duration=duration
                )
            
            os.remove(mp3_file)
            await processing_msg.delete()
            logger.info(f"User @{username} converted: {title[:50]}")
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            await processing_msg.edit_text(f"{emoji} ❌ Download failed: {str(e)[:100]}")
        finally:
            if mp3_file and os.path.exists(mp3_file):
                os.remove(mp3_file)
                
    except Exception as e:
        logger.error(f"General error: {e}")
        await processing_msg.edit_text("❌ An unexpected error occurred.")

def main():
    """Start the bot"""
    print("🚀 Starting bot...")
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, convert))
    
    print("✅ Bot is running!")
    application.run_polling()

if __name__ == "__main__":
    main()





