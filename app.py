import os
import glob
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from yt_dlp import YoutubeDL

TOKEN = os.environ.get("BOT_TOKEN", "9284967785:AAG5zzD1swVFRVD-JowIU3gx3PPF1XND9XY")
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

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
    output_template = f"/tmp/{chat_id}_%(id)s.%(ext)s"

    common_opts = {
        '
