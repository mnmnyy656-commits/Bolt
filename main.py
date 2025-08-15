# main.py
import json
import random
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler,
    CallbackContext, MessageHandler, Filters
)
from config import BOT_TOKEN

# =========================
# Flask للبقاء أونلاين
# =========================
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is running..."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# =========================
# تخزين البيانات
# =========================
DATA_FILE = "database.json"

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_data(d):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("خطأ حفظ البيانات:", e)

data = load_data()            # هيكل: { owner_id: {...} }
user_states = {}              # حالات الخطوات
temp_info = {}                # معلومات مؤقتة أثناء إنشاء السحب

# =========================
# أدوات مساعدة
# =========================
def is_admin(user_id: int, channel_username: str, context: CallbackContext):
    try:
        chat = context.bot.get_chat(channel_username)
        admins = context.bot.get_chat_administrators(chat.id)
        return any(a.user.id == user_id for a in admins)
    except Exception as e:
        print(f"خطأ في التحقق من المشرفين: {e}")
        return False

def update_channel_message(context: CallbackContext, owner_id: str):
    r = data.get(owner_id)
    if not r:
        return
    channel = r["channel"]
    msg_id = r["message_id"]
    participants_count = len(r.get("participants", []))
    display_text = r.get("text", "")
    force_channel = r.get("force_channel")
    if force_channel:
        display_text += f"\n\n📌 للاشتراك الإجباري: https://t.me/{str(force_channel).lstrip('@')}"
    keyboard = [
        [InlineKeyboardButton("🎯 شارك", callback_data=f"join_{owner_id}")],
        [InlineKeyboardButton("🚫 إيقاف", callback_data=f"stop_{owner_id}"),
         InlineKeyboardButton("🎉 سحب", callback_data=f"draw_{owner_id}")]
    ]
    try:
        context.bot.edit_message_text(
            chat_id=channel,
            message_id=msg_id,
            text=f"[🎰 روليت Batman🦇](https://t.me/Replit_Batman_bot)\n\n{display_text}\n\n👥 عدد المشاركين: {participants_count}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        print("خطأ تحديث رسالة القناة:", e)

def notify_owner_new_participant(context: CallbackContext, owner_id: str, participant_id: int, display_name: str):
    try:
        name_md = f"[{display_name}](tg://user?id={participant_id})"
        keyboard = [
            [InlineKeyboardButton("🎯 تحديد كفائز", callback_data=f"selectwin_{owner_id}_{participant_id}"),
             InlineKeyboardButton("🚫 استبعاد", callback_data=f"exclude_{owner_id}_{participant_id}")]
        ]
        context.bot.send_message(
            chat_id=int(owner_id),
            text=f"👤 {name_md} شارك الآن!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        print("خطأ في إشعار المالك:", e)

# =========================
# أوامر البداية
# =========================
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🎰 إنشاء روليت", callback_data="create_roulette")],
        [InlineKeyboardButton("🔗 ربط قناة", callback_data="link_channel")]
    ]
    update.message.reply_text(
        "👋 أهلاً بك في بوت الروليت:\nاختر من الخيارات:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =========================
# خطوات إنشاء السحب
# =========================
def handle_link_channel(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    q.message.reply_text("📢 أرسل معرف القناة (مثلاً: @mychannel)")
    user_states[q.from_user.id] = "awaiting_link_channel"

def create_roulette(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    user_states[q.from_user.id] = "awaiting_channel_forward"
    q.message.edit_text("📢 أرسل رسالة معاد توجيهها (Forward) من القناة التي تريد النشر فيها.")

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
        context.bot.send_message(
            chat_id=user_id,
            text="📌 هل تريد تفعيل الاشتراك الإجباري؟",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

def force_join_choice(update: Update, context: CallbackContext):
    q = update.callback_query
    user_id = q.from_user.id
    q.answer()
    if q.data == "force_yes":
        user_states[user_id] = "awaiting_force_channel"
        context.bot.send_message(chat_id=user_id, text="📢 أرسل معرف قناة الاشتراك الإجباري (مثلاً: @mychannel)")
    else:
        info = temp_info.pop(user_id)
        info["force_channel"] = None
        context.bot.send_message(chat_id=user_id, text="✅ سيتم نشر السحب بدون اشتراك إجباري.")
        post_roulette(update, context, user_id, info)

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
            info = temp_info.get(user_id, {})
            info["force_channel"] = text
            temp_info[user_id] = info
            post_roulette(update, context, user_id, info)
            user_states[user_id] = None
        except Exception as e:
            update.message.reply_text(f"❌ خطأ:\n{e}")

def post_roulette(update, context, user_id, info):
    channel = info["channel"]
    winners_count = info["winners_count"]
    display_text = info["text"]
    force_channel = info.get("force_channel")

    data[str(user_id)] = {
        "participants": [],
        "manual_selected": [],
        "active": True,
        "winners_count": winners_count,
        "channel": channel,
        "text": display_text,
        "force_channel": force_channel,
        "message_id": None
    }
    save_data(data)
    user_states[user_id] = None

    try:
        text_msg = f"[🎰 روليت Batman🦇](https://t.me/Replit_Batman_bot)\n\n{display_text}\n\n👥 عدد المشاركين: 0"
        if force_channel:
            text_msg += f"\n\n📌 للاشتراك الإجباري: https://t.me/{str(force_channel).lstrip('@')}"
        keyboard = [
            [InlineKeyboardButton("🎯 شارك", callback_data=f"join_{user_id}")],
            [InlineKeyboardButton("🚫 إيقاف", callback_data=f"stop_{user_id}"),
             InlineKeyboardButton("🎉 سحب", callback_data=f"draw_{user_id}")]
        ]
        sent_msg = context.bot.send_message(
            chat_id=channel,
            text=text_msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        data[str(user_id)]["message_id"] = sent_msg.message_id
        save_data(data)
        context.bot.send_message(chat_id=user_id, text="✅ تم نشر السحب في القناة.")
    except Exception as e:
        context.bot.send_message(chat_id=user_id, text=f"❌ خطأ في نشر السحب:\n{e}")

# =========================
# المشاركة والانضمام
# =========================
def join_roulette(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    participant_id = q.from_user.id
    owner_id = q.data.split("_")[1]
    r = data.get(owner_id)

    if not r or not r.get("active", False):
        q.answer("❌ السحب غير متاح.", show_alert=True)
        return

    force_channel = r.get("force_channel")
    if force_channel:
        try:
            member = context.bot.get_chat_member(force_channel, participant_id)
            if member.status in ["left", "kicked"]:
                q.answer("❗️ اشترك في القناة أولاً!", show_alert=True)
                return
        except:
            q.answer("❗️ لا يمكن التحقق من الاشتراك.", show_alert=True)
            return

    if participant_id in r["participants"]:
        q.answer("❗️ أنت مشارك بالفعل.", show_alert=True)
        return

    r["participants"].append(participant_id)
    save_data(data)
    q.answer("✅ تم انضمامك للسحب!")

    notify_owner_new_participant(context, owner_id, participant_id, q.from_user.full_name)
    update_channel_message(context, owner_id)

# =========================
# استبعاد وتحديد يدوي
# =========================
def exclude_participant(update: Update, context: CallbackContext):
    q = update.callback_query
    _, owner_id, target_id = q.data.split("_")
    sender_id = q.from_user.id
    r = data.get(owner_id)

    if not r:
        q.answer("❌ السحب غير موجود.", show_alert=True)
        return

    if str(sender_id) != owner_id and not is_admin(sender_id, r["channel"], context):
        q.answer("❌ غير مخول.", show_alert=True)
        return

    target_id = int(target_id)
    changed = False
    if target_id in r["participants"]:
        r["participants"].remove(target_id)
        changed = True
    if target_id in r.get("manual_selected", []):
        r["manual_selected"].remove(target_id)
        changed = True

    if changed:
        save_data(data)
        q.answer("✅ تم الاستبعاد.")
        update_channel_message(context, owner_id)
    else:
        q.answer("ℹ️ هذا المستخدم غير موجود في السحب.")

def manual_select(update: Update, context: CallbackContext):
    q = update.callback_query
    _, owner_id, target_id = q.data.split("_")
    sender_id = q.from_user.id
    r = data.get(owner_id)

    if not r:
        q.answer("❌ السحب غير موجود.", show_alert=True)
        return

    if str(sender_id) != owner_id and not is_admin(sender_id, r["channel"], context):
        q.answer("❌ غير مخول.", show_alert=True)
        return

    target_id = int(target_id)
    if target_id not in r.get("participants", []):
        q.answer("❌ هذا المستخدم ليس مشاركًا.", show_alert=True)
        return

    if target_id not in r["manual_selected"]:
        r["manual_selected"].append(target_id)
        save_data(data)
        q.answer("✅ تم تحديد الشخص كفائز محتمل.")
    else:
        q.answer("ℹ️ محدد مسبقًا.")

# =========================
# السحب النهائي + الإيقاف
# =========================
def draw_winners(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    owner_id = q.data.split("_")[1]
    sender_id = q.from_user.id
    r = data.get(owner_id)

    if not r:
        q.answer("❌ السحب غير موجود.")
        return

    if str(sender_id) != owner_id and not is_admin(sender_id, r["channel"], context):
        q.answer("❌ أنت لست مخولاً لهذا الإجراء.", show_alert=True)
        return

    winners_count = r["winners_count"]
    participants = r.get("participants", [])
    manual_selected = r.get("manual_selected", [])

    # تحديد مجموعة السحب
    source_pool = manual_selected if manual_selected else participants

    # تحقق من وجود عدد كافي
    if len(source_pool) < winners_count:
        q.answer(f"❗️ عدد المشاركين ({len(source_pool)}) أقل من عدد الفائزين المطلوب ({winners_count}).", show_alert=True)
        return

    winners = random.sample(source_pool, winners_count)

    r["active"] = False
    save_data(data)

    msg = "🎉 الفائزون:\n"
    for i, uid in enumerate(winners, start=1):
        user = context.bot.get_chat(uid)
        msg += f"{i}. 🏆 [{user.full_name}](tg://user?id={uid})\n"
        context.bot.send_message(chat_id=uid, text="🎉 مبروك! ربحت بالسحب!")

    q.message.edit_text(msg, parse_mode="Markdown")

def stop_roulette(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    owner_id = q.data.split("_")[1]
    sender_id = q.from_user.id
    r = data.get(owner_id)

    if not r:
        q.answer("❌ السحب غير موجود.")
        return

    if str(sender_id) != owner_id and not is_admin(sender_id, r["channel"], context):
        q.answer("❌ أنت لست مخولاً لهذا الإجراء.", show_alert=True)
        return

    r["active"] = False
    save_data(data)
    q.message.edit_text("🚫 تم إيقاف السحب.")

# =========================
# الراوتر (الأزرار والرسائل)
# =========================
def button_handler(update: Update, context: CallbackContext):
    data_cb = update.callback_query.data
    if data_cb == "create_roulette":
        create_roulette(update, context)
    elif data_cb == "link_channel":
        handle_link_channel(update, context)
    elif data_cb in ["force_yes", "force_no"]:
        force_join_choice(update, context)
    elif data_cb.startswith("join_"):
        join_roulette(update, context)
    elif data_cb.startswith("stop_"):
        stop_roulette(update, context)
    elif data_cb.startswith("draw_"):
        draw_winners(update, context)
    elif data_cb.startswith("exclude_"):
        exclude_participant(update, context)
    elif data_cb.startswith("selectwin_"):
        manual_select(update, context)

def message_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_states.get(user_id) == "awaiting_force_channel":
        handle_force_channel(update, context)
    else:
        handle_message(update, context)

# =========================
# تشغيل البوت
# =========================
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, message_handler))

    # تشغيل Flask وبوت في نفس الوقت
    threading.Thread(target=run_flask).start()
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
