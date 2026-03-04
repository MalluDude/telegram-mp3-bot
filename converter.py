import os
import yt_dlp
import re
import logging
import asyncio
import time
import random
from typing import Optional, Tuple
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
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
RATE_LIMIT = int(os.getenv("RATE_LIMIT", 5))

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

# Rate limiting storage
user_requests = {}

def detect_platform(url: str) -> str:
    """Detect the platform from the URL"""
    url = url.lower()
    
    platform_patterns = {
        'youtube': ['youtube.com', 'youtu.be', 'm.youtube.com', 'youtube shorts', 'youtube.com/shorts'],
        'spotify': ['spotify.com', 'open.spotify.com', 'spotify:'],
        'instagram': ['instagram.com', 'instagr.am', 'instagram.com/reel/', 'instagram.com/p/'],
        'pinterest': ['pinterest.com', 'pin.it', 'pinterest.co', 'pinterest.ca'],
        'facebook': ['facebook.com', 'fb.watch', 'fb.com', 'fb.me', 'facebook.com/watch'],
        'twitter': ['twitter.com', 'x.com', 'tweet'],
        'tiktok': ['tiktok.com', 'vm.tiktok.com', 'tiktok.com/@', 'tiktok.com/t/'],
        'reddit': ['reddit.com', 'redd.it', 'reddit.com/r/']
    }
    
    for platform, patterns in platform_patterns.items():
        for pattern in patterns:
            if pattern in url:
                return platform
    
    return "unknown"

def format_size(bytes: int) -> str:
    """Format file size"""
    if not bytes:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.1f} GB"

def format_duration(seconds: int) -> str:
    """Format duration"""
    if not seconds:
        return "Unknown"
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

def get_ydl_opts(platform: str, filename: str) -> Tuple[dict, Optional[str]]:
    """Get platform-specific yt-dlp options without cookies"""
    
    # Common User-Agents for rotation
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1'
    ]
    
    # Base options optimized for no-cookies operation
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOAD_FOLDER}/{filename}.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'concurrent_fragment_downloads': 3,
        'fragment_retries': 15,
        'retries': 15,
        'extractor_retries': 10,
        'file_access_retries': 10,
        'skip_unavailable_fragments': True,
        'http_headers': {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Connection': 'keep-alive',
        },
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    # Platform-specific configurations without cookies
    if platform == 'youtube':
        opts['extractor_args'] = {
            'youtube': {
                'player_client': ['android', 'web', 'ios', 'mweb'],
                'skip': ['hls', 'dash'],
                'player_skip': ['webpage', 'configs'],
            }
        }
        opts['impersonate'] = 'chrome-120'
        opts['extractor_args']['youtube']['player_skip'] = ['webpage']
        
    elif platform == 'instagram':
        opts['extractor_args'] = {
            'instagram': {
                'api': 'android',
                'check_embed': True,
            }
        }
        # Try different User-Agent rotation for Instagram
        opts['http_headers']['User-Agent'] = 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36'
        # Add delay for Instagram
        opts['sleep_interval_requests'] = 5
        opts['sleep_interval'] = 3
        opts['max_sleep_interval'] = 10
        
    elif platform == 'tiktok':
        opts['extractor_args'] = {
            'tiktok': {
                'api': 'android',
                'app_version': '33.2.2',
                'device_id': random.randint(1000000000000000000, 9999999999999999999)
            }
        }
        opts['impersonate'] = 'chrome-120'
        opts['extractor_args']['tiktok']['app_info'] = 'tiktok_android'
        
    elif platform == 'facebook':
        opts['extractor_args'] = {
            'facebook': {
                'api': 'android',
            }
        }
        opts['impersonate'] = 'chrome-120'
        
    elif platform == 'twitter':
        opts['extractor_args'] = {
            'twitter': {
                'api': 'android',
            }
        }
        opts['impersonate'] = 'chrome-120'
        
    elif platform == 'pinterest':
        opts['extract_flat'] = True
        opts['impersonate'] = 'chrome-120'
        
    elif platform == 'reddit':
        opts['extractor_args'] = {
            'reddit': {
                'api': 'android',
            }
        }
    
    return opts, None

def check_rate_limit(user_id: int) -> Tuple[bool, Optional[str]]:
    """Check if user has exceeded rate limit"""
    current_time = time.time()
    
    # Clean old requests
    if user_id in user_requests:
        user_requests[user_id] = [t for t in user_requests[user_id] 
                                  if current_time - t < 60]
    else:
        user_requests[user_id] = []
    
    # Check rate limit
    if len(user_requests[user_id]) >= RATE_LIMIT:
        wait_time = 60 - (current_time - user_requests[user_id][0])
        return False, f"Rate limit exceeded. Please wait {int(wait_time)} seconds."
    
    # Add current request
    user_requests[user_id].append(current_time)
    return True, None

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
        f"• Rate limit: {RATE_LIMIT} requests per minute\n"
        "• No playlists or albums\n\n"
        "Simply paste any link and I'll handle the rest! 🚀"
    )
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics"""
    total_conversions = context.bot_data.get('total_conversions', 0)
    total_users = len(context.bot_data.get('users', set()))
    
    stats_text = (
        "📊 *Bot Statistics*\n\n"
        f"• Total conversions: {total_conversions}\n"
        f"• Total users: {total_users}\n"
        f"• Rate limit: {RATE_LIMIT} requests/minute\n"
        f"• Max file size: {MAX_FILE_SIZE // (1024*1024)}MB\n"
        f"• Max duration: {MAX_DURATION // 60} minutes\n"
        f"• Downloads folder: {DOWNLOAD_FOLDER}\n"
    )
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main conversion function"""
    url = update.message.text.strip()
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    # Track unique users
    if 'users' not in context.bot_data:
        context.bot_data['users'] = set()
    context.bot_data['users'].add(user_id)
    
    # Basic URL validation
    if not url.startswith(('http://', 'https://', 'spotify:')):
        await update.message.reply_text("❌ Please send a valid URL")
        return
    
    # Detect platform
    platform = detect_platform(url)
    
    if platform == 'unknown':
        await update.message.reply_text(
            "❌ Platform not supported or unrecognized URL.\n"
            "Supported platforms: YouTube, Spotify, Instagram, Pinterest, Facebook, Twitter, TikTok, Reddit"
        )
        return
    
    # Rate limiting check
    allowed, rate_message = check_rate_limit(user_id)
    if not allowed:
        await update.message.reply_text(f"⏱️ {rate_message}")
        return
    
    emoji = PLATFORM_EMOJIS.get(platform, PLATFORM_EMOJIS['default'])
    processing_msg = await update.message.reply_text(
        f"{emoji} Processing {platform.title()} link...\n"
        f"⏳ This may take a moment..."
    )
    
    try:
        # Handle Spotify
        original_platform = platform
        if platform == 'spotify':
            await processing_msg.edit_text(f"{emoji} 🎵 Searching YouTube for this track...")
            url = f"ytsearch1:{url} audio"
            platform = 'youtube'
        
        # Platform-specific pre-processing
        if platform == 'instagram':
            await processing_msg.edit_text(f"{emoji} 📸 Instagram requires extra patience...")
            await asyncio.sleep(3)  # Extra delay for Instagram
        
        # Generate filename
        timestamp = int(time.time())
        safe_filename = f"{username}_{timestamp}_{platform}"
        
        # Get platform-specific options
        ydl_opts, error_msg = get_ydl_opts(platform, safe_filename)
        if error_msg:
            await processing_msg.edit_text(f"{emoji} ❌ {error_msg}")
            return
        
        mp3_file = None
        
        try:
            # Multiple URL attempts for stubborn platforms
            urls_to_try = [url]
            
            # Add alternative URLs for Instagram
            if platform == 'instagram' and '/reel/' in url:
                # Try embed version
                embed_url = url.replace('/reel/', '/p/') + '/embed/'
                urls_to_try.append(embed_url)
            
            success = False
            last_error = None
            
            for attempt_url in urls_to_try:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        await processing_msg.edit_text(f"{emoji} 🔍 Fetching video information...")
                        
                        # Extract info with retries
                        max_retries = 3
                        info = None
                        
                        for attempt in range(max_retries):
                            try:
                                info = ydl.extract_info(attempt_url, download=False)
                                break
                            except Exception as e:
                                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {attempt_url}: {str(e)[:100]}")
                                if attempt == max_retries - 1:
                                    raise
                                await asyncio.sleep(3)
                        
                        if info:
                            success = True
                            break
                            
                except Exception as e:
                    last_error = e
                    logger.warning(f"URL attempt failed: {attempt_url}")
                    continue
            
            if not success:
                raise last_error or Exception("All URL attempts failed")
            
            # Handle search results
            if 'entries' in info:
                if not info['entries']:
                    await processing_msg.edit_text(
                        f"{emoji} ❌ No videos found.\n"
                        "Please try a different link or search term."
                    )
                    return
                info = info['entries'][0]
            
            if not info:
                await processing_msg.edit_text(f"{emoji} ❌ Could not find any matching video.")
                return
            
            # Check duration
            duration = info.get('duration', 0)
            if duration > MAX_DURATION:
                await processing_msg.edit_text(
                    f"{emoji} ❌ Content too long (> {MAX_DURATION//60} minutes).\n"
                    f"Duration: {format_duration(duration)}"
                )
                return
            
            # Get content details
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
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
                mp3_files = sorted(glob.glob(f"{DOWNLOAD_FOLDER}/*.mp3"), 
                                  key=os.path.getctime, reverse=True)
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
            
            # Track successful conversion
            if 'total_conversions' not in context.bot_data:
                context.bot_data['total_conversions'] = 0
            context.bot_data['total_conversions'] += 1
            
            logger.info(f"User @{username} converted: {title[:50]}... ({original_platform})")
            
        except yt_dlp.utils.DownloadError as e:
            error_str = str(e).lower()
            logger.error(f"Download error: {e}")
            
            # User-friendly error messages without cookie mentions
            if "private" in error_str:
                msg = f"{emoji} 🔒 This content is private"
            elif "rate limit" in error_str or "too many requests" in error_str:
                msg = f"{emoji} ⏱️ Platform rate limit reached. Please try again later."
            elif "copyright" in error_str:
                msg = f"{emoji} ⚖️ Content removed due to copyright"
            elif "unavailable" in error_str or "not found" in error_str or "404" in error_str:
                msg = f"{emoji} ❌ Content unavailable or deleted"
            elif "age" in error_str or "age-gate" in error_str:
                msg = f"{emoji} 🔞 Age-restricted content - cannot access without verification"
            elif "instagram" in error_str:
                msg = f"{emoji} 📸 Instagram is heavily restricted. Try a different video or platform."
            else:
                msg = f"{emoji} ❌ Download failed: {str(e)[:100]}"
            
            await processing_msg.edit_text(msg)
            
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

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot"""
    print("🚀 Starting Universal Media to MP3 Bot (No-Cookies Mode)...")
    print(f"✅ Bot token: {'✓ Loaded' if BOT_TOKEN else '✗ Missing'}")
    print(f"✅ Download folder: {DOWNLOAD_FOLDER}")
    print(f"✅ Max file size: {MAX_FILE_SIZE // (1024*1024)}MB")
    print(f"✅ Max duration: {MAX_DURATION // 60} minutes")
    print(f"✅ Rate limit: {RATE_LIMIT} requests/minute")
    print("\n📢 Running in NO-COOKIES mode - some platforms may have limited access:")
    print("   • YouTube: Should work for most videos")
    print("   • Spotify: Works via YouTube search")
    print("   • Instagram: May have limited success")
    print("   • TikTok: Should work with impersonation")
    print("   • Others: Limited success without cookies\n")
    
    # Create application
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, convert))
    application.add_error_handler(error_handler)
    
    print("🤖 Bot is running! Press Ctrl+C to stop")
    
    # Start bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
