import os
import yt_dlp
import re
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode
import time
from dotenv import load_dotenv  # You'll need to install python-dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
BOT_TOKEN = os.getenv("8760725679:AAH20fnR_lRNA74N3ke9DZnGA5aMQgz6icI")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables!")

DOWNLOAD_FOLDER = os.getenv("DOWNLOAD_FOLDER", "downloads")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 50 * 1024 * 1024))  # 50MB default
MAX_DURATION = int(os.getenv("MAX_DURATION", 3600))  # 1 hour default

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Platform emojis for better UX
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
    """Detect which platform the URL is from"""
    url_lower = url.lower()
    
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

def get_ydl_opts(filename, platform='youtube'):
    """Get platform-specific youtube-dl options"""
    
    # Base options
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOAD_FOLDER}/{filename}.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }
    
    # Platform-specific configurations
    if platform == 'youtube':
        opts.update({
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web', 'ios', 'mweb'],
                    'skip': ['hls', 'dash'],
                }
            },
            'geo_bypass': True,
            'geo_bypass_country': 'US',
        })
    elif platform == 'instagram':
        opts['extractor_args'] = {'instagram': {'api': 'android'}}
    elif platform == 'facebook':
        opts['extractor_args'] = {'facebook': {'api': 'android'}}
    elif platform == 'tiktok':
        opts['extractor_args'] = {'tiktok': {'api': 'android'}}
        opts['extract_flat'] = False
    elif platform == 'pinterest':
        opts['extract_flat'] = True
    
    # Add cookies if available
    cookies_file = os.getenv('COOKIES_FILE', 'cookies.txt')
    if os.path.exists(cookies_file):
        opts['cookiefile'] = cookies_file
        logger.info(f"Using cookies from {cookies_file}")
    
    return opts

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
    
    # Check if platform is supported
    if platform == 'unknown':
        keyboard = [[InlineKeyboardButton("📋 Supported Platforms", callback_data="list_platforms")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "❌ Platform not supported or unrecognized URL.\n"
            "Click below to see supported platforms.",
            reply_markup=reply_markup
        )
        return
    
    # Send initial message with platform emoji
    emoji = PLATFORM_EMOJIS.get(platform, PLATFORM_EMOJIS['default'])
    processing_msg = await update.message.reply_text(
        f"{emoji} Processing {platform.title()} link...\n"
        f"⏳ This may take a moment..."
    )
    
    try:
        # Special handling for Spotify
        original_url = url
        if platform == 'spotify':
            await processing_msg.edit_text(f"{emoji} 🎵 Extracting Spotify track info...")
            
            try:
                # Try with yt-dlp first
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info and 'title' in info:
                        artist = info.get('artist', info.get('uploader', ''))
                        track = info.get('track', info.get('title', ''))
                        search_query = f"{track} {artist} audio"
                        url = f"ytsearch1:{search_query}"
                        platform = 'youtube'
                        await processing_msg.edit_text(f"{emoji} 🎵 Found: {track} by {artist}\n🔍 Searching YouTube...")
                    else:
                        url = f"ytsearch1:{url} audio"
                        platform = 'youtube'
            except Exception as e:
                logger.warning(f"Spotify extraction failed: {e}")
                url = f"ytsearch1:{url} audio"
                platform = 'youtube'
        
        # Generate safe filename
        timestamp = int(time.time())
        safe_filename = f"{username}_{timestamp}_{platform}"
        
        # Get platform-specific options
        ydl_opts = get_ydl_opts(safe_filename, platform)
        
        mp3_file = None
        
        try:
            # Extract info first
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await processing_msg.edit_text(f"{emoji} 🔍 Fetching video information...")
                
                # Try multiple times for YouTube
                max_retries = 3
                info = None
                
                for attempt in range(max_retries):
                    try:
                        info = ydl.extract_info(url, download=False)
                        break
                    except Exception as e:
                        logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)[:100]}")
                        if attempt == max_retries - 1:
                            raise
                        await asyncio.sleep(2)
                
                if not info:
                    await processing_msg.edit_text(f"{emoji} ❌ Could not fetch video information")
                    return
                
                # Handle search results
                if 'entries' in info:
                    if not info['entries']:
                        await processing_msg.edit_text(
                            f"{emoji} ❌ No videos found.\n"
                            "Please try a different link or search term."
                        )
                        return
                    
                    # Get first entry from search
                    info = info['entries'][0]
                    
                    if not info:
                        await processing_msg.edit_text(
                            f"{emoji} ❌ Could not find any matching video."
                        )
                        return
                
                # Check if video is available
                if info.get('availability') == 'private':
                    await processing_msg.edit_text(f"{emoji} 🔒 This video is private")
                    return
                
                # Check duration
                duration = info.get('duration', 0)
                if duration > MAX_DURATION:
                    await processing_msg.edit_text(
                        f"{emoji} ❌ Video too long (> {MAX_DURATION//60} minutes).\n"
                        f"Duration: {format_duration(duration)}"
                    )
                    return
                
                # Get video details
                title = info.get('title', 'Unknown')
                uploader = info.get('uploader', info.get('channel', 'Unknown'))
                duration_str = format_duration(duration)
                
                # Estimate size
                filesize = info.get('filesize', 0) or info.get('filesize_approx', 0)
                size_str = format_size(filesize)
                
                # Send info message
                info_text = (
                    f"{emoji} *Found:* {title[:100]}{'...' if len(title) > 100 else ''}\n"
                    f"👤 *Uploader:* {uploader}\n"
                    f"⏱️ *Duration:* {duration_str}\n"
                )
                if filesize:
                    info_text += f"📦 *Est. Size:* {size_str}\n"
                info_text += f"\n⬇️ Downloading and converting..."
                
                await processing_msg.edit_text(info_text, parse_mode=ParseMode.MARKDOWN)
                
                # Download and convert
                ydl.download([url])
                
                # Get the actual filename
                if 'requested_downloads' in info:
                    filename = info['requested_downloads'][0]['filepath']
                else:
                    filename = ydl.prepare_filename(info)
            
            # Find the MP3 file
            mp3_file = None
            if filename and os.path.exists(filename):
                base = filename.rsplit(".", 1)[0]
                mp3_file = base + ".mp3"
            else:
                # Try to find any recent MP3 file
                import glob
                mp3_files = sorted(glob.glob(f"{DOWNLOAD_FOLDER}/*.mp3"), key=os.path.getctime, reverse=True)
                if mp3_files:
                    mp3_file = mp3_files[0]
            
            if not mp3_file or not os.path.exists(mp3_file):
                await processing_msg.edit_text(f"{emoji} ❌ Conversion failed - output file not found")
                return
            
            # Check file size
            file_size = os.path.getsize(mp3_file)
            if file_size > MAX_FILE_SIZE:
                os.remove(mp3_file)
                await processing_msg.edit_text(
                    f"{emoji} ❌ Converted file too large (> {MAX_FILE_SIZE//(1024*1024)}MB): {format_size(file_size)}"
                )
                return
            
            # Upload
            await processing_msg.edit_text(f"{emoji} 📤 Uploading MP3...")
            
            with open(mp3_file, "rb") as audio:
                await update.message.reply_audio(
                    audio,
                    title=title[:200],
                    performer=uploader[:100],
                    duration=duration if duration else None,
                    caption=f"✅ Converted by @{context.bot.username}"
                )
            
            # Cleanup
            os.remove(mp3_file)
            await processing_msg.delete()
            
            # Log success
            logger.info(f"User @{username} converted: {title[:50]}... ({platform})")
            
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"Download error: {e}")
            error_msg = str(e).lower()
            
            if "private" in error_msg:
                await processing_msg.edit_text(f"{emoji} 🔒 This video is private")
            elif "age" in error_msg or "age-gate" in error_msg:
                await processing_msg.edit_text(
                    f"{emoji} 🔞 Age-restricted content.\n"
                    "The bot needs cookies.txt to access this video."
                )
            elif "copyright" in error_msg:
                await processing_msg.edit_text(f"{emoji} ⚖️ Video removed due to copyright")
            elif "unavailable" in error_msg:
                await processing_msg.edit_text(f"{emoji} ❌ Video unavailable")
            else:
                await processing_msg.edit_text(
                    f"{emoji} ❌ Download failed.\n"
                    f"Error: {str(e)[:100]}"
                )
        except Exception as e:
            logger.error(f"Conversion error: {e}", exc_info=True)
            await processing_msg.edit_text(
                f"{emoji} ❌ Conversion failed: {str(e)[:100]}"
            )
        finally:
            # Cleanup
            if mp3_file and os.path.exists(mp3_file):
                try:
                    os.remove(mp3_file)
                except:
                    pass
                
    except Exception as e:
        logger.error(f"General error: {e}", exc_info=True)
        await processing_msg.edit_text(
            "❌ An unexpected error occurred.\n"
            "Please try again later or with a different link."
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "list_platforms":
        platforms_text = (
            "*Supported Platforms:*\n\n"
            "📺 *YouTube* - Videos, Shorts\n"
            "🎵 *Spotify* - Tracks (converted via YouTube)\n"
            "📸 *Instagram* - Reels, Posts, Stories\n"
            "📌 *Pinterest* - Videos\n"
            "👤 *Facebook* - Videos, Reels\n"
            "🐦 *Twitter/X* - Videos\n"
            "🎵 *TikTok* - Videos\n"
            "👽 *Reddit* - Videos\n\n"
            "Simply paste any link and I'll handle it! 🚀"
        )
        await query.edit_message_text(platforms_text, parse_mode=ParseMode.MARKDOWN)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot"""
    print("🚀 Universal Media to MP3 Bot Starting...")
    print(f"✅ Download folder: {DOWNLOAD_FOLDER}")
    print(f"✅ Max file size: {MAX_FILE_SIZE//(1024*1024)}MB")
    print(f"✅ Max duration: {MAX_DURATION//60} minutes")
    
    # Check for cookies
    if os.path.exists('cookies.txt'):
        print("✅ Cookies file found")
    else:
        print("⚠️ No cookies.txt found - age-restricted content may fail")
    
    # Create application
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, convert))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)
    
    print("🤖 Bot is running! Press Ctrl+C to stop")
    
    # Start bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
