import os
import glob
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from yt_dlp import YoutubeDL

# Bot Token & Webhook URL configuration
TOKEN = os.environ.get("BOT_TOKEN", "9284967785:AAG5zzD1swVFRVD-JowIU3gx3PPF1XND9XY")
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Temporary in-memory store for links
user_links = {}

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
    return "Bot Server is Running Live!", 200

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

    # Store link mapped to chat ID
    user_links[message.chat.id] = url

    # Inline quality options
    markup = InlineKeyboardMarkup()
    btn_best = InlineKeyboardButton("🎬 Best Video", callback_data="best")
    btn_720 = InlineKeyboardButton("🎥 720p Video", callback_data="720")
    btn_mp3 = InlineKeyboardButton("🎵 MP3 Audio", callback_data="mp3")
    
    markup.row(btn_best, btn_720)
    markup.row(btn_mp3)

    bot.reply_to(message, "Choose your download format:", reply_markup=markup)

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

    quality = call.data
    output_template = f"/tmp/{chat_id}_%(id)s.%(ext)s"

    # YouTube anti-bot bypass without cookies (Using iOS client and mobile agent)
    common_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'geo_bypass': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'mweb'],
                'skip': ['hls', 'dash']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }

    if quality == "mp3":
        status_text = "⏳ Downloading and converting to MP3 audio..."
        ydl_opts = {
            **common_opts,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    elif quality == "best":
        status_text = "⏳ Downloading in Best Available Quality..."
        ydl_opts = {
            **common_opts,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
        }
    else:  # 720p
        status_text = "⏳ Downloading in 720p Quality..."
        ydl_opts = {
            **common_opts,
            'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
            'merge_output_format': 'mp4',
        }

    bot.edit_message_text(status_text, chat_id=chat_id, message_id=call.message.message_id)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        files = glob.glob(f"/tmp/{chat_id}_*")
        if not files:
            bot.edit_message_text(
                "❌ Download failed. The video might be private or blocked.",
                chat_id=chat_id,
                message_id=call.message.message_id
            )
            return

        file_path = files[0]
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

        if file_size_mb > 50:
            bot.edit_message_text(
                f"⚠️ File size is {file_size_mb:.2f} MB. Telegram Bot API has a 50 MB upload limit.",
                chat_id=chat_id,
                message_id=call.message.message_id
            )
        else:
            bot.edit_message_text("📤 Uploading media to Telegram...", chat_id=chat_id, message_id=call.message.message_id)
            with open(file_path, 'rb') as media_file:
                if quality == "mp3":
                    bot.send_audio(chat_id, media_file, timeout=240)
                else:
                    bot.send_video(chat_id, media_file, timeout=240)
            bot.delete_message(chat_id=chat_id, message_id=call.message.message_id)

        # Cleanup downloaded file
        if os.path.exists(file_path):
            os.remove(file_path)

    except Exception as e:
        bot.edit_message_text(f"Error: {str(e)[:160]}", chat_id=chat_id, message_id=call.message.message_id)
        for f in glob.glob(f"/tmp/{chat_id}_*"):
            if os.path.exists(f):
                os.remove(f)

# Configure Telegram Webhook if running on Render
if WEBHOOK_URL:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL.rstrip('/')}/{TOKEN}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
