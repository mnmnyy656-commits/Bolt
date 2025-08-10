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

# --- /start ---
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🎰 إنشاء روليت", callback_data="create_roulette")],
        [InlineKeyboardButton("🔗 ربط قناة", callback_data="link_channel")]
    ]
    update.message.reply_text(
        "👋 أهلاً بك في بوت الروليت:\nاختر من الخيارات:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- التعامل مع خيارات القناة والسحب ---
def handle_link_channel(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.message.reply_text("📢 أرسل معرف القناة (مثلاً: @mychannel)")
    user_states[query.from_user.id] = "awaiting_link_channel"

def create_roulette(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_states[query.from_user.id] = "awaiting_channel_forward"
    query.message.edit_text("📢 أرسل رسالة معاد توجيهها (Forward) من القناة التي تريد النشر فيها.")

# --- التعامل مع الرسائل حسب حالة المستخدم ---
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
        keyboard = [
            [InlineKeyboardButton("✅ نعم", callback_data="force_yes"),
             InlineKeyboardButton("❌ لا", callback_data="force_no")]
        ]
        context.bot.send_message(chat_id=user_id, text="📌 هل تريد تفعيل الاشتراك الإجباري؟", reply_markup=InlineKeyboardMarkup(keyboard))

# --- التعامل مع اختيار نعم أو لا للاشتراك الإجباري ---
def force_join_choice(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()

    if query.data == "force_yes":
        user_states[user_id] = "awaiting_force_channel"
        context.bot.send_message(chat_id=user_id, text="📢 أرسل معرف قناة الاشتراك الإجباري (مثلاً: @mychannel)")
    else:
        info = temp_info.pop(user_id)
        info["force_channel"] = None
        context.bot.send_message(chat_id=user_id, text="✅ سيتم نشر السحب بدون اشتراك إجباري.")
        post_roulette(update, context, user_id, info)

# --- استقبال معرف قناة الاشتراك الإجباري ---
def handle_force_channel(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""
    if user_states.get(user_id) == "awaiting_force_channel":
        try:
            chat = context.bot.get_chat(text)
            member = context.bot.get_chat_member(chat.id, context.bot.id)
            if member.status not in ["administrator", "creator"]:
                update.message.reply_text("❌ البوت ليس مشرفاً في قناة الاشتراك الإجباري.")
                return
            # احفظ القناة في info المؤقتة
            info = temp_info.get(user_id, {})
            info["force_channel"] = text
            temp_info[user_id] = info
            # انشر السحب
            post_roulette(update, context, user_id, info)
            user_states[user_id] = None
        except Exception as e:
            update.message.reply_text(f"❌ خطأ:\n{e}")

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

    try:
        name = f"[{query.from_user.full_name}](tg://user?id={user_id})"
        keyboard = [
            [InlineKeyboardButton("🎯 اختيار كفائز", callback_data=f"manualwin_{owner_id}_{user_id}"),
             InlineKeyboardButton("🚫 استبعاد", callback_data=f"exclude_{owner_id}_{user_id}")]
        ]
        context.bot.send_message(chat_id=int(owner_id), text=f"👤 {name} شارك الآن!", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception as e:
        print("خطأ في عرض المشارك:", e)

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

# --- استبعاد مشارك ---
def exclude_participant(update: Update, context: CallbackContext):
    query = update.callback_query
    _, owner_id, target_id = query.data.split("_")
    # تحقق من الصلاحية: صاحب السحب أو مشرف القناة فقط
    sender_id = query.from_user.id
    roulette = data.get(owner_id)
    if not roulette:
        query.answer("❌ السحب غير موجود.", show_alert=True)
        return
    if str(sender_id) != owner_id and not is_admin(sender_id, roulette["channel"], context):
        query.answer("❌ غير مخول.", show_alert=True)
        return
    if roulette and int(target_id) in roulette["participants"]:
        roulette["participants"].remove(int(target_id))
        save_data(data)
        query.answer("✅ تم الاستبعاد.")

# --- اختيار فائز يدوي ---
def manual_win(update: Update, context: CallbackContext):
    query = update.callback_query
    _, owner_id, winner_id = query.data.split("_")
    sender_id = query.from_user.id
    roulette = data.get(owner_id)
    if not roulette:
        query.answer("❌ السحب غير موجود.", show_alert=True)
        return
    # تحقق من الصلاحية: صاحب السحب أو مشرف القناة فقط
    if str(sender_id) != owner_id and not is_admin(sender_id, roulette["channel"], context):
        query.answer("❌ غير مخول.", show_alert=True)
        return
    try:
        user = context.bot.get_chat(int(winner_id))
        name = f"[{user.full_name}](tg://user?id={user.id})"
        context.bot.send_message(chat_id=owner_id, text=f"🏆 الفائز: {name}", parse_mode="Markdown")
        context.bot.send_message(chat_id=user.id, text="🎉 مبروك! تم اختيارك كفائز!")
    except:
        query.answer("❌ خطأ في إرسال رسالة للفائز.")

# --- السحب العشوائي مع عرض قائمة الفائزين مرقمة ---
def draw_winners(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    owner_id = query.data.split("_")[1]
    sender_id = query.from_user.id
    roulette = data.get(owner_id)

    if not roulette:
        query.answer("❌ السحب غير موجود.")
        return
    # تحقق صلاحيات: فقط صاحب السحب أو مشرفي القناة
    if str(sender_id) != owner_id and not is_admin(sender_id, roulette["channel"], context):
        query.answer("❌ أنت لست مخولاً لهذا الإجراء.", show_alert=True)
        return

    participants = roulette.get("participants", [])
    if not participants:
        query.answer("❗️ لا يوجد مشاركين.")
        return
    winners_count = roulette["winners_count"]
    # اختيار عشوائي للفائزين:
    winners = random.sample(participants, min(len(participants), winners_count))
    roulette["active"] = False
    save_data(data)

    msg = "🎉 الفائزون:\n"
    for i, uid in enumerate(winners, start=1):
        try:
            user = context.bot.get_chat(uid)
            msg += f"{i}. 🏆 [{user.full_name}](tg://user?id={uid})\n"
            context.bot.send_message(chat_id=uid, text="🎉 مبروك! ربحت بالسحب!")
        except:
            msg += f"{i}. 🏆 فائز مجهول\n"

    query.message.edit_text(msg, parse_mode="Markdown")

# --- إيقاف السحب مع التحقق من الصلاحيات ---
def stop_roulette(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    owner_id = query.data.split("_")[1]
    sender_id = query.from_user.id
    roulette = data.get(owner_id)
    if not roulette:
        query.answer("❌ السحب غير موجود.")
        return
    if str(sender_id) != owner_id and not is_admin(sender_id, roulette["channel"], context):
        query.answer("❌ أنت لست مخولاً لهذا الإجراء.", show_alert=True)
        return

    roulette["active"] = False
    save_data(data)
    query.message.edit_text("🚫 تم إيقاف السحب.")

# --- معالج أزرار البوت ---
def button_handler(update: Update, context: CallbackContext):
    data_cb = update.callback_query.data
    if data_cb == "create_roulette":
        create_roulette(update, context)
    elif data_cb == "link_channel":
        handle_link_channel(update, context)
    elif data_cb == "force_yes" or data_cb == "force_no":
        force_join_choice(update, context)
    elif data_cb.startswith("join_"):
        join_roulette(update, context)
    elif data_cb.startswith("stop_"):
        stop_roulette(update, context)
    elif data_cb.startswith("draw_"):
        draw_winners(update, context)
    elif data_cb.startswith("exclude_"):
        exclude_participant(update, context)
    elif data_cb.startswith("manualwin_"):
        manual_win(update, context)

# --- إضافة معالج خاص لاستقبال معرف قناة الاشتراك الإجباري ---
def message_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_states.get(user_id) == "awaiting_force_channel":
        handle_force_channel(update, context)
    else:
        handle_message(update, context)

# --- تشغيل البوت ---
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text | Filters.forwarded, message_handler))
    threading.Thread(target=run_flask).start()
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
