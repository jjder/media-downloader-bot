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

# Temporary store for links mapped by chat ID
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

    user_links[message.chat.id] = url

    # Quality selection buttons
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

    # Base options with cookiefile support and headers
    common_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'geo_bypass': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }

    # Attach cookies if available in the directory
    if os.path.exists("cookies.txt"):
        common_opts['cookiefile'] = 'cookies.txt'

    # Format selection with reliable fallbacks to avoid "format not available" error
    if quality == "mp3":
        status_text = "⏳ Downloading and converting to MP3 audio..."
        ydl_opts = {
            **common_opts,
            'format': 'ba/b',
            'postprocessors': [{
