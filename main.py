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
from config import BOT_TOKEN  # ضع التوكن في ملف config.py

# --- Flask ويب سيرفر بسيط ليبقي البوت شغال ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is running..."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# --- بيانات البوت ---
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

# --- بداية البوت ---
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🎰 إنشاء روليت", callback_data="create_roulette")],
        [InlineKeyboardButton("🔗 ربط قناة", callback_data="link_channel")]
    ]
    update.message.reply_text(
        "👋 أهلاً بك في بوت الروليت:\nاختر من الخيارات:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- تعامل مع خيارات الربط والقنوات ---
def handle_link_channel(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.message.reply_text("📢 أرسل معرف القناة (مثلاً: @mychannel أو -100...)")
    user_states[query.from_user.id] = "awaiting_link_channel"

def create_roulette(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_states[query.from_user.id] = "awaiting_channel_forward"
    query.message.edit_text("📢 أرسل رسالة معاد توجيهها (Forward) من القناة التي تريد النشر فيها.")

# --- معالجة الرسائل حسب حالة المستخدم ---
def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""
    state = user_states.get(user_id)

    if state == "awaiting_link_channel":
        try:
            chat = context.bot.get_chat(text)
            member = context.bot.get_chat_member(chat.id, context.bot.id)
            if member.status in ["administrator", "creator"]:
                update.message.reply_text("✅ تم ربط القناة بنجاح.")
            else:
                update.message.reply_text("❌ البوت ليس مشرفاً في القناة.")
        except Exception as e:
            update.message.reply_text(f"❌ خطأ:\n{e}")
        user_states[user_id] = None

    elif state == "awaiting_channel_forward":
        if update.message.forward_from_chat:
            channel = update.message.forward_from_chat
            try:
                member = context.bot.get_chat_member(channel.id, context.bot.id)
                if member.status not in ["administrator", "creator"]:
                    update.message.reply_text("❌ البوت ليس مشرفًا في هذه القناة.")
                    return
            except Exception as e:
                update.message.reply_text(f"❌ خطأ في التحقق من البوت كمشرف: {e}")
                return

            channel_username = '@' + channel.username if channel.username else str(channel.id)
            temp_info[user_id] = {"channel": channel_username}
            user_states[user_id] = "awaiting_winner_count"
            update.message.reply_text(f"✅ تم تحديد قناة النشر: {channel_username}\n\n🔢 كم عدد الفائزين؟")
        else:
            update.message.reply_text("❌ الرجاء إرسال رسالة معاد توجيهها من القناة.")

    elif state == "awaiting_winner_count":
        if not text.isdigit() or int(text) < 1:
            update.message.reply_text("❗️ الرجاء إرسال رقم صحيح للفائزين.")
            return
        temp_info[user_id]["winners_count"] = int(text)
        user_states[user_id] = "awaiting_text"
        update.message.reply_text("📝 أرسل نص السحب:")

    elif state == "awaiting_text":
        temp_info[user_id]["text"] = text
        user_states[user_id] = "awaiting_force_join"
        update.message.reply_text("📌 هل تريد تفعيل الاشتراك الإجباري في قناة؟ (نعم / لا)")

    elif state == "awaiting_force_join":
        if text.lower() == "نعم":
            user_states[user_id] = "awaiting_force_channel"
            update.message.reply_text("📢 أرسل معرف قناة الاشتراك الإجباري (مثلاً: @mychannel)")
        else:
            info = temp_info.pop(user_id)
            info["force_channel"] = None
            post_roulette(update, context, user_id, info)

    elif state == "awaiting_force_channel":
        info = temp_info.pop(user_id)
        info["force_channel"] = text
        post_roulette(update, context, user_id, info)

# --- نشر السحب في القناة ---
def post_roulette(update, context, user_id, info):
    channel = info["channel"]
    winners_count = info["winners_count"]
    message_text = info["text"]
    force_channel = info.get("force_channel")

    data[str(user_id)] = {
        "participants": [],
        "active": True,
        "winners_count": winners_count,
        "channel": channel,
        "text": message_text,
        "force_channel": force_channel,
        "message_id": None
    }
    save_data(data)
    user_states[user_id] = None

    try:
        display_text = message_text
        if force_channel:
            display_text += f"\n\n📌 للاشتراك الإجباري: https://t.me/{force_channel.lstrip('@')}"

        keyboard = [
            [InlineKeyboardButton("🎯 شارك", callback_data=f"join_{user_id}")],
            [InlineKeyboardButton("🚫 إيقاف", callback_data=f"stop_{user_id}"),
             InlineKeyboardButton("🎉 سحب", callback_data=f"draw_{user_id}")]
        ]

        sent_msg = context.bot.send_message(
            chat_id=channel,
            text=f"🎰 سحب جديد:\n\n{display_text}\n\n👥 عدد المشاركين: 0",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        data[str(user_id)]["message_id"] = sent_msg.message_id
        save_data(data)
        context.bot.send_message(chat_id=user_id, text="✅ تم نشر السحب في القناة.")

    except Exception as e:
        context.bot.send_message(chat_id=user_id, text=f"❌ خطأ في نشر السحب:\n{e}")

# --- المشاركة في السحب ---
def join_roulette(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    owner_id = query.data.split("_")[1]
    roulette = data.get(owner_id)

    if not roulette or not roulette["active"]:
        query.answer("❌ السحب غير متاح.", show_alert=True)
        return

    force_channel = roulette.get("force_channel")
    if force_channel:
        try:
            member = context.bot.get_chat_member(force_channel, user_id)
            if member.status in ["left", "kicked"]:
                query.answer("❗️ اشترك في القناة أولاً!", show_alert=True)
                return
        except:
            query.answer("❗️ لا يمكن التحقق من الاشتراك.", show_alert=True)
            return

    if user_id in roulette["participants"]:
        query.answer("❗️ أنت مشارك بالفعل.", show_alert=True)
        return

    roulette["participants"].append(user_id)
    save_data(data)
    query.answer("✅ تم انضمامك للسحب!")

    # تحديث عدد المشاركين في رسالة القناة
    try:
        channel = roulette["channel"]
        message_id = roulette["message_id"]
        participants_count = len(roulette["participants"])
        display_text = roulette["text"]
        if force_channel:
            display_text += f"\n\n📌 للاشتراك الإجباري: https://t.me/{force_channel.lstrip('@')}"

        keyboard = [
            [InlineKeyboardButton("🎯 شارك", callback_data=f"join_{owner_id}")],
            [InlineKeyboardButton("🚫 إيقاف", callback_data=f"stop_{owner_id}"),
             InlineKeyboardButton("🎉 سحب", callback_data=f"draw_{owner_id}")]
        ]

        context.bot.edit_message_text(
            chat_id=channel,
            message_id=message_id,
            text=f"🎰 سحب جديد:\n\n{display_text}\n\n👥 عدد المشاركين: {participants_count}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print("خطأ تحديث رسالة القناة:", e)

# --- إيقاف السحب ---
def stop_roulette(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    owner_id = query.data.split("_")[1]
    sender_id = query.from_user.id
    roulette = data.get(owner_id)

    if not roulette or str(sender_id) != owner_id:
        query.answer("❌ أنت غير مخول لإيقاف السحب.", show_alert=True)
        return

    roulette["active"] = False
    save_data(data)
    query.message.edit_text("🚫 تم إيقاف السحب.")

# --- اختيار الفائزين عشوائياً ---
def draw_winners(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    owner_id = query.data.split("_")[1]
    roulette = data.get(owner_id)

    if not roulette:
        query.answer("❌ السحب غير موجود.")
        return

    participants = roulette.get("participants", [])
    if not participants:
        query.answer("❗️ لا يوجد مشاركين.")
        return

    winners_count = roulette["winners_count"]
    winners = random.sample(participants, min(len(participants), winners_count))
    roulette["active"] = False
    save_data(data)

    msg = "🎉 الفائزون:\n"
    for uid in winners:
        try:
            user = context.bot.get_chat(uid)
            msg += f"🏆 {user.full_name}\n"
            context.bot.send_message(chat_id=uid, text="🎉 مبروك! ربحت بالسحب!")
        except:
            msg += f"🏆 ID: {uid}\n"

    query.message.edit_text(msg)

# --- معالج الكل ---
def button_handler(update: Update, context: CallbackContext):
    data_cb = update.callback_query.data

    if data_cb == "create_roulette":
        create_roulette(update, context)
    elif data_cb == "link_channel":
        handle_link_channel(update, context)
    elif data_cb.startswith("join_"):
        join_roulette(update, context)
    elif data_cb.startswith("stop_"):
        stop_roulette(update, context)
    elif data_cb.startswith("draw_"):
        draw_winners(update, context)

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text | Filters.forwarded, handle_message))

    threading.Thread(target=run_flask).start()

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
