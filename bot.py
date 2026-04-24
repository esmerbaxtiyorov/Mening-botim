"""
🎵 Telegram Music Bot
YouTube'dan ashula nomi yoki ijrochi ismi bo'yicha qidirib,
foydalanuvchiga MP3 yoki Video klip ko'rinishida yuboradi.
"""

import asyncio
import logging
import os
import uuid
from typing import Any, Dict, Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from yt_dlp import YoutubeDL

# ============================================================
# Sozlamalar
# ============================================================
# SENING TOKENING SHU YERGA QO'YILDI:
BOT_TOKEN = "8654220408:AAFOQe0sx1lPQ4YcrP4T7tuSs0e26TfzDQs"

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE_MB = 49
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SEARCH_CACHE: Dict[str, Dict[str, Any]] = {}


# ============================================================
# Yordamchi funksiyalar
# ============================================================
def safe_remove(path: Optional[str]) -> None:
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info("🗑 Fayl o'chirildi: %s", path)
    except Exception as e:
        logger.warning("Faylni o'chirishda xatolik: %s", e)


def format_views(n: Optional[int]) -> str:
    if not n: return "—"
    if n >= 1_000_000_000: return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return str(n)


def format_duration(sec: Optional[int]) -> str:
    if not sec: return "—"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    if h: return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def parse_upload_year(info: Dict[str, Any]) -> str:
    date = info.get("upload_date") or ""
    return date[:4] if (len(date) >= 4 and date[:4].isdigit()) else "—"


def search_youtube(query: str) -> Optional[Dict[str, Any]]:
    ydl_opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "noplaylist": True, "default_search": "ytsearch1", "extract_flat": False,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            data = ydl.extract_info(query, download=False)
            if not data: return None
            if "entries" in data:
                entries = [e for e in data["entries"] if e]
                return entries[0] if entries else None
            return data
    except Exception as e:
        logger.error("Qidiruv xatosi: %s", e)
        return None


def download_audio(video_id: str) -> Optional[str]:
    out_template = os.path.join(DOWNLOAD_DIR, f"{video_id}-{uuid.uuid4().hex}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filename)
            mp3_path = base + ".mp3"
            return mp3_path if os.path.exists(mp3_path) else None
    except Exception as e:
        logger.error("Audio yuklash xatosi: %s", e)
        return None


def download_video(video_id: str) -> Optional[str]:
    out_template = os.path.join(DOWNLOAD_DIR, f"{video_id}-{uuid.uuid4().hex}.%(ext)s")
    ydl_opts = {
        "format": f"best[ext=mp4][filesize<{MAX_FILE_SIZE}]/best[filesize<{MAX_FILE_SIZE}]/best",
        "outtmpl": out_template,
        "quiet": True, "no_warnings": True, "noplaylist": True, "merge_output_format": "mp4",
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            filename = ydl.prepare_filename(info)
            return filename if os.path.exists(filename) else None
    except Exception as e:
        logger.error("Video yuklash xatosi: %s", e)
        return None


def build_info_text(meta: Dict[str, Any]) -> str:
    return (
        f"🎶 <b>Topildi!</b>\n\n🎤 <b>Ijrochi:</b> {meta['uploader']}\n"
        f"🎵 <b>Qo'shiq:</b> {meta['title']}\n👁 <b>Ko'rishlar:</b> {format_views(meta['view_count'])}\n"
        f"⏱ <b>Davomiyligi:</b> {format_duration(meta['duration'])}\n\n"
        f"⬇️ Tanlang:"
    )


def build_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Video", callback_data=f"video|{token}"), 
         InlineKeyboardButton("🎧 MP3", callback_data=f"audio|{token}")],
        [InlineKeyboardButton("🔁 Qayta qidirish", callback_data="search_again"),
         InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")]
    ])


# ============================================================
# Handlerlar
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🎉 Assalomu alaykum! Ashula nomini yoki ijrochi ismini yozing.",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup([["🎵 Qo'shiq qidirish"]], resize_keyboard=True)
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if text == "🎵 Qo'shiq qidirish":
        return await update.message.reply_text("✍️ Ashula nomini yozing:")

    msg = await update.message.reply_text("🔎 <b>Qidirilmoqda...</b>", parse_mode=ParseMode.HTML)
    info = await asyncio.to_thread(search_youtube, text)

    if not info:
        return await msg.edit_text("😔 Hech narsa topilmadi.")

    meta = {"video_id": info['id'], "title": info['title'], "uploader": info['uploader'], 
            "view_count": info.get('view_count'), "duration": info.get('duration')}
    
    token = uuid.uuid4().hex[:12]
    SEARCH_CACHE[token] = meta
    await msg.delete()
    await update.message.reply_text(build_info_text(meta), parse_mode=ParseMode.HTML, reply_markup=build_keyboard(token))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if "|" not in query.data: return
    
    action, token = query.data.split("|")
    meta = SEARCH_CACHE.get(token)
    if not meta: return await query.edit_message_text("⚠️ Muddati o'tgan.")

    status = await context.bot.send_message(query.message.chat_id, "⏬ Yuklanmoqda...")
    path = None
    try:
        if action == "audio":
            path = await asyncio.to_thread(download_audio, meta['video_id'])
            with open(path, "rb") as f:
                await context.bot.send_audio(query.message.chat_id, audio=f, title=meta['title'])
        else:
            path = await asyncio.to_thread(download_video, meta['video_id'])
            with open(path, "rb") as f:
                await context.bot.send_video(query.message.chat_id, video=f, caption=meta['title'])
        await status.delete()
    except Exception as e:
        await status.edit_text(f"❌ Xatolik: {e}")
    finally:
        safe_remove(path)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Xatolik: %s", context.error)

# ============================================================
# ASOSIY QISM (RENDER UCHUN TO'G'RILANDI)
# ============================================================
async def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("🤖 Bot ishga tushdi!")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        # Serverda bot to'xtab qolmasligi uchun
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        pass
