import json
import random
import threading
from flask import Flask
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler,
    CallbackContext, MessageHandler, Filters
)
from config import BOT_TOKEN

# --- Flask ويب سيرفر ---
app = Flask(__name__)
@app.route('/')
def home():
    return "🤖 Bot is running..."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# --- تحميل وحفظ البيانات ---
DATA_FILE = "database.json"
def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}
def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("خطأ حفظ البيانات:", e)

data = load_data()
user_states = {}
temp_info = {}

# --- فحص إذا كان المستخدم مشرف في القناة ---
def is_admin(user_id: int, channel_username: str, context: CallbackContext):
    try:
        chat = context.bot.get_chat(channel_username)
        admins = context.bot.get_chat_administrators(chat.id)
        for admin in admins:
            if admin.user.id == user_id:
                return True
        return False
    except Exception as e:
        print(f"خطأ في التحقق من المشرفين: {e}")
        return False

# --- /start
