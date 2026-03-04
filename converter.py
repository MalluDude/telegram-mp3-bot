import os
import yt_dlp
import re
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode
from urllib.parse import urlparse
import time

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "8760725679:AAH20fnR_lRNA74N3ke9DZnGA5aMQgz6icI"
DOWNLOAD_FOLDER = "downloads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB Telegram limit
MAX_DURATION = 3600  # 1 hour max duration
ALLOWED_DOMAINS = [
    'youtube.com', 'youtu.be', 'youtube shorts',
    'spotify.com', 'open.spotify.com',
    'instagram.com', 'instagr.am',
    'pinterest.com', 'pin.it',
    'facebook.com', 'fb.watch', 'fb.com',
    'twitter.com', 'x.com', 'tiktok.com', 'reddit.com'
]

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
        'youtube': ['youtube.com', 'youtu.be', 'm.youtube.com'],
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

def extract_spotify_track_id(url):
    """Extract track ID from Spotify URL"""
    patterns = [
        r'track/([a-zA-Z0-9]+)',
        r'spotify:track:([a-zA-Z0-9]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

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
    if platform == 'instagram':
        opts['extractor_args'] = {'instagram': {'api': 'android'}}
    elif platform == 'facebook':
        opts['extractor_args'] = {'facebook': {'api': 'android'}}
    elif platform == 'tiktok':
        opts['extractor_args'] = {'tiktok': {'api': 'android'}}
    elif platform == 'youtube':
        opts['extractor_args'] = {
            'youtube': {
                'player_client': ['android', 'web']
            }
        }
    elif platform == 'pinterest':
        opts['extract_flat'] = True  # Pinterest needs special handling
    
    # Add cookies if available
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
    
    return opts

def format_size(bytes):
    """Format file size"""
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
        f"• Max file size: 50MB\n"
        f"• Max duration: 60 minutes\n"
        "• No playlists or albums\n\n"
        "Simply paste any link and I'll handle the rest! 🚀"
    )
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = (
        "*How to use:*\n"
        "1. Copy a link from any supported platform\n"
        "2. Paste it here\n"
        "3. Wait for conversion\n"
        "4. Download the MP3\n\n"
        "*Tips:*\n"
        "• For Spotify, I'll search YouTube for the best match\n"
        "• Longer videos take more time to process\n"
        "• Make sure the video is publicly accessible\n"
        "• If conversion fails, try a different link"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

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
        if platform == 'spotify':
            await processing_msg.edit_text(f"{emoji} 🎵 Extracting Spotify track info...")
            
            # Try to extract track ID
            track_id = extract_spotify_track_id(url)
            
            if track_id:
                # Use yt-dlp to extract Spotify metadata
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        info = ydl.extract_info(url, download=False)
                        if info and 'title' in info:
                            search_query = f"{info['title']} {info.get('artist', '')} audio"
                            url = f"ytsearch:{search_query}"
                            platform = 'youtube'  # Switch to YouTube for download
                    except:
                        # Fallback to simple search
                        url = f"ytsearch:{url} audio"
                        platform = 'youtube'
            else:
                url = f"ytsearch:{url} audio"
                platform = 'youtube'
        
        # Generate safe filename
        timestamp = int(time.time())
        safe_filename = f"{username}_{timestamp}_{platform}"
        
        # Configure download options
        ydl_opts = get_ydl_opts(safe_filename, platform)
        
        mp3_file = None
        
        try:
            # Extract info first
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await processing_msg.edit_text(f"{emoji} 🔍 Fetching video information...")
                
                # Try to extract info
                try:
                    info = ydl.extract_info(url, download=False)
                except Exception as e:
                    logger.error(f"Info extraction error: {e}")
                    await processing_msg.edit_text(
                        f"{emoji} ❌ Could not access the video.\n"
                        "It might be private, age-restricted, or unavailable."
                    )
                    return
                
                # Handle playlists
                if 'entries' in info:
                    if len(info['entries']) > 1:
                        await processing_msg.edit_text(
                            f"{emoji} ❌ Playlists are not supported.\n"
                            "Please send a single video/track URL."
                        )
                        return
                    elif len(info['entries']) == 1:
                        info = info['entries'][0]
                
                # Check duration
                duration = info.get('duration', 0)
                if duration > MAX_DURATION:
                    await processing_msg.edit_text(
                        f"{emoji} ❌ Video too long (>60 minutes).\n"
                        f"Duration: {format_duration(duration)}"
                    )
                    return
                
                # Get video details for response
                title = info.get('title', 'Unknown')
                uploader = info.get('uploader', 'Unknown')
                duration_str = format_duration(duration)
                
                # Estimate size
                filesize = info.get('filesize', 0) or info.get('filesize_approx', 0)
                size_str = format_size(filesize) if filesize else "Unknown"
                
                # Send info message
                await processing_msg.edit_text(
                    f"{emoji} *Found:* {title[:100]}{'...' if len(title) > 100 else ''}\n"
                    f"👤 *Uploader:* {uploader}\n"
                    f"⏱️ *Duration:* {duration_str}\n"
                    f"📦 *Est. Size:* {size_str}\n\n"
                    f"⬇️ Starting download..."
                )
                
                # Download and convert
                ydl.download([url])
                filename = ydl.prepare_filename(info)
            
            mp3_file = filename.rsplit(".", 1)[0] + ".mp3"
            
            # Check if file exists
            if not os.path.exists(mp3_file):
                await processing_msg.edit_text(f"{emoji} ❌ Conversion failed - output file not found")
                return
            
            # Check file size
            file_size = os.path.getsize(mp3_file)
            if file_size > MAX_FILE_SIZE:
                os.remove(mp3_file)
                await processing_msg.edit_text(
                    f"{emoji} ❌ Converted file too large (>50MB): {format_size(file_size)}"
                )
                return
            
            # Upload with progress
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
            logger.error(f"Download error for {url}: {e}")
            error_msg = str(e)
            
            if "Private video" in error_msg:
                await processing_msg.edit_text(f"{emoji} 🔒 This video is private")
            elif "age" in error_msg.lower():
                await processing_msg.edit_text(
                    f"{emoji} 🔞 Age-restricted content.\n"
                    "Try adding YouTube cookies to bypass."
                )
            elif "copyright" in error_msg.lower():
                await processing_msg.edit_text(f"{emoji} ⚖️ Video removed due to copyright")
            else:
                await processing_msg.edit_text(
                    f"{emoji} ❌ Download failed.\n"
                    "The video might be unavailable or region-locked."
                )
        except Exception as e:
            logger.error(f"Conversion error for {url}: {e}", exc_info=True)
            await processing_msg.edit_text(
                f"{emoji} ❌ Conversion failed: {str(e)[:100]}"
            )
        finally:
            # Cleanup on error
            if mp3_file and os.path.exists(mp3_file):
                os.remove(mp3_file)
                
    except Exception as e:
        logger.error(f"General error for {url}: {e}", exc_info=True)
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
    if BOT_TOKEN == "8760725679:AAH20fnR_lRNA74N3ke9DZnGA5aMQgz6icI":
        print("⚠️ Please set your BOT_TOKEN in the script")
        return
    
    # Create application
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, convert))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)
    
    print("🚀 Universal Media to MP3 Bot Started!")
    print(f"✅ Supported platforms: YouTube, Spotify, Instagram, Pinterest, Facebook, Twitter, TikTok, Reddit")
    print("📝 Send any supported link to convert to MP3")
    
    # Start bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()


