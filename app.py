import os
import glob
import requests
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from yt_dlp import YoutubeDL

TOKEN = os.environ.get("BOT_TOKEN", "9284967785:AAG5zzD1swVFRVD-JowIU3gx3PPF1XND9XY")
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

user_links = {}

# Public Cobalt API instances for reliable bypass
COBALT_INSTANCES = [
    "https://api.cobalt.tools",
    "https://cobalt-api.kwiatekm.tokyo",
    "https://api.wuk.sh"
]

def download_via_cobalt(url, is_audio=False, chat_id=None):
    payload = {
        "url": url,
        "videoQuality": "720",
        "downloadMode": "audio" if is_audio else "auto",
        "youtubeVideoCodec": "h264"
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    for api in COBALT_INSTANCES:
        try:
            resp = requests.post(f"{api}/", json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                stream_url = data.get("url")
                if stream_url:
                    ext = "mp3" if is_audio else "mp4"
                    file_path = f"/tmp/{chat_id}_cobalt.{ext}"
                    with requests.get(stream_url, stream=True, timeout=120) as r:
                        r.raise_for_status()
                        with open(file_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                    return file_path
        except Exception:
            continue
    return None

@app.route(f"/{TOKEN}", methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

@app.route('/')
def home():
    return "Bot Server is Live and Running!", 200

@app.route('/set_webhook')
def setup_webhook():
    if WEBHOOK_URL:
        target_url = f"{WEBHOOK_URL.rstrip('/')}/{TOKEN}"
        bot.remove_webhook()
        success = bot.set_webhook(url=target_url)
        return f"Webhook status: {success} -> {target_url}", 200
    return "RENDER_EXTERNAL_URL is not set", 400

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(
        message, 
        "Welcome! Send me a video link from YouTube, Instagram, Facebook, or TikTok to download."
    )

@bot.message_handler(func=lambda message: True)
def handle_link(message):
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "⚠️ Please send a valid video URL.")
        return

    user_links[message.chat.id] = url

    markup = InlineKeyboardMarkup()
    btn_original = InlineKeyboardButton("🎬 Original Video", callback_data="original")
    btn_mp3 = InlineKeyboardButton("🎵 MP3 Audio", callback_data="mp3")
    markup.row(btn_original, btn_mp3)

    bot.reply_to(message, "Choose format:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def process_download(call):
    chat_id = call.message.chat.id
    url = user_links.get(chat_id)

    if not url:
        bot.edit_message_text(
            "❌ Session expired or link missing. Please send the link again.",
            chat_id=chat_id,
            message_id=call.message.message_id
        )
        return

    choice = call.data
    is_audio = (choice == "mp3")
    file_path = None

    bot.edit_message_text("⏳ Processing download request...", chat_id=chat_id, message_id=call.message.message_id)

    # 1. Try Cobalt API first (YouTube & Social Media bypass)
    try:
        file_path = download_via_cobalt(url, is_audio=is_audio, chat_id=chat_id)
    except Exception:
        file_path = None

    # 2. Fallback to yt-dlp if Cobalt fails (works great for Instagram/Facebook)
    if not file_path or not os.path.exists(file_path):
        output_template = f"/tmp/{chat_id}_%(id)s.%(ext)s"
        common_opts = {
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }
        if is_audio:
            ydl_opts = {
                **common_opts,
                'format': 'ba/b',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
        else:
            ydl_opts = {
                **common_opts,
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
            }

        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            files = glob.glob(f"/tmp/{chat_id}_*")
            if files:
                file_path = files[0]
        except Exception as e:
            bot.edit_message_text(f"Error: {str(e)[:160]}", chat_id=chat_id, message_id=call.message.message_id)
            return

    # Check and upload file
    if not file_path or not os.path.exists(file_path):
        bot.edit_message_text(
            "❌ Download failed. The video might be private or blocked.",
            chat_id=chat_id,
            message_id=call.message.message_id
        )
        return

    try:
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 50:
            bot.edit_message_text(
                f"⚠️ File size is {file_size_mb:.2f} MB. Telegram Bot API limits uploads to 50 MB.",
                chat_id=chat_id,
                message_id=call.message.message_id
            )
        else:
            bot.edit_message_text("📤 Uploading media to Telegram...", chat_id=chat_id, message_id=call.message.message_id)
            with open(file_path, 'rb') as media_file:
                if is_audio:
                    bot.send_audio(chat_id, media_file, timeout=240)
                else:
                    bot.send_video(chat_id, media_file, timeout=240)
            bot.delete_message(chat_id=chat_id, message_id=call.message.message_id)
    finally:
        for f in glob.glob(f"/tmp/{chat_id}_*"):
            if os.path.exists(f):
                os.remove(f)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
