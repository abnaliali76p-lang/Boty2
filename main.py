import os
import time
import telebot
from pymongo import MongoClient
from flask import Flask
from threading import Thread
from datetime import datetime

# --- الإعدادات الأساسية ---
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 8873553496 
BOT_USERNAME = "ASDAKBOT" 
MONGO_URI = os.environ.get("MONGO_URI") 
PORT = int(os.environ.get("PORT", 5001))

# --- إعدادات القنوات والروابط المطلوبة ---
FORCE_SUB_CHANNEL_LINK = "https://t.me/+Fjt6_udvGoY3ZGRk"
PROOF_CHANNEL_URL = "https://t.me/FPHTE"
PROOF_CHANNEL_ID = "@FPHTE"
VIP_CHANNEL_URL = "https://t.me/+Kd-iHtw-IOUyYzI0"

# عناوين أزرار القائمة (Reply Keyboard)
BTN_VIP_TEXT = "🔞 כניסה לערוץ ה-VIP"
BTN_LINK_TEXT = "🔗 הקישור האישי שלי לנקודות"
BTN_STATS_TEXT = "📊 סטטיסטיקת הנקודות שלי"
BTN_PROOF_TEXT = "✅ ערוץ הוכחות ואמינות"

app = Flask(__name__)

@app.route("/")
def home(): 
    return "Bot is running!"

def run_web(): 
    app.run(host="0.0.0.0", port=PORT)

bot = telebot.TeleBot(TOKEN)
bot.remove_webhook()

client = MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True)
db = client["bot_database_new"]
users_col = db["users"]

reply_targets = {}

# --- دالة التحقق من اشتراك المستخدم في القناة ---
def is_user_subscribed(user_id):
    try:
        member = bot.get_chat_member(PROOF_CHANNEL_ID, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception:
        return True

# --- رسالة طلب الاشتراك الإجباري ---
def send_force_sub_message(chat_id, referrer_id=None):
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    btn_sub = telebot.types.InlineKeyboardButton("📢 לחץ כאן להצטרפות לערוץ", url=FORCE_SUB_CHANNEL_LINK)
    
    cb_data = f"check_sub_{referrer_id}" if referrer_id else "check_sub_none"
    btn_check = telebot.types.InlineKeyboardButton("✅ אימות הצטרפות", callback_data=cb_data)
    
    markup.add(btn_sub, btn_check)

    msg_text = (
        "⚠️ <b>על מנת להשתמש בבוט, עליך להצטרף לערוץ ההוכחות שלנו תחילה!</b>\n\n"
        "1️⃣ לחץ על הכפתור למטה והצטרף לערוץ.\n"
        "2️⃣ לאחר ההצטרפות, לחץ על <b>'אימות הצטרפות'</b> כדי להתחיל."
    )
    bot.send_message(chat_id, msg_text, parse_mode="HTML", reply_markup=markup)

# --- نص الترحيب في المرة الأولى ---
def get_first_welcome_text(first_name, referrer_name=None):
    ref_header = f"👤 הוזמנת על ידי: <b>{referrer_name}</b> והוא קיבל 5 נקודות!\n\n" if referrer_name else ""
    return (
        f"{ref_header}"
        f"<blockquote>"
        f"<b>👋 שלום {first_name}!</b>\n"
        f"<b>ברוכים הבאים לבוט הכי לוהט בישראל! 🔥🔞</b>\n\n"
        f"🎁 קיבלת 5 נקודות בונוס על ההצטרפות!\n\n"
        f"<b>השתמש בכפתורים למטה כדי לנווט בבוט 👇</b>"
        f"</blockquote>"
    )

# --- نص الترحيب عند الضغط على /start مرة أخرى ---
def get_returning_welcome_text(first_name, points):
    return (
        f"<blockquote>"
        f"<b>👋 שלום {first_name}!</b>\n"
        f"<b>ברוכים הבאים לבוט הכי לוהט בישראל! 🔥🔞</b>\n\n"
        f"💎 <b>הנקודות שלך כעת: {points}/50</b>\n\n"
        f"<b>השתמש בכפתורים למטה כדי לנווט בבוט 👇</b>"
        f"</blockquote>"
    )

# --- 1. قائمة الأزرار الشفافة (Inline Keyboard) المرفقة بالرسالة ---
def get_inline_keyboard():
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    btn_vip = telebot.types.InlineKeyboardButton("🔞 כניסה לערוץ ה-VIP", callback_data="check_vip")
    btn_link = telebot.types.InlineKeyboardButton("🔗 הקישור האישי שלי לנקודות", callback_data="get_link")
    btn_stats = telebot.types.InlineKeyboardButton("📊 סטטיסטיקת הנקודות שלי", callback_data="get_stats")
    btn_proof = telebot.types.InlineKeyboardButton("✅ ערוץ הוכחות ואמינות", url=PROOF_CHANNEL_URL)
    
    markup.add(btn_vip, btn_link, btn_stats, btn_proof)
    return markup

# --- معالج أمر START ---
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.chat.id
    first_name = message.from_user.first_name
    
    command_args = message.text.split()
    referrer_id = None
    if len(command_args) > 1 and command_args[1].isdigit():
        referrer_id = int(command_args[1])

    # فحص الاشتراك الإجباري
    if not is_user_subscribed(user_id):
        send_force_sub_message(user_id, referrer_id)
        return

    process_user_registration(user_id, first_name, referrer_id)

# --- تسجيل وتفعيل المستخدم ---
def process_user_registration(user_id, first_name, referrer_id=None):
    user = users_col.find_one({"user_id": user_id})

    if not user:
        initial_points = 5
        referrer_name = None

        if referrer_id and referrer_id != user_id:
            referrer = users_col.find_one({"user_id": referrer_id})
            if referrer:
                referrer_name = referrer.get("name", "חבר")
                new_points = referrer.get("points", 0) + 5
                new_referrals = referrer.get("referrals", 0) + 1
                users_col.update_one(
                    {"user_id": referrer_id},
                    {"$set": {"points": new_points, "referrals": new_referrals}}
                )
                
                try:
                    bot.send_message(
                        referrer_id,
                        f"🎉 <b>משתמש חדש הצטרף דרך הקישור שלך!</b>\n\n"
                        f"👤 מצטרף: <b>{first_name}</b>\n"
                        f"💎 קיבלת: <b>+5 נקודות</b>\n"
                        f"📈 סך הכל נקודות: <b>{new_points}</b>",
                        parse_mode="HTML"
                    )
                except:
                    pass

        users_col.insert_one({
            "user_id": user_id,
            "name": first_name,
            "points": initial_points,
            "referrals": 0,
            "joined_at": datetime.now(),
            "claimed_vip": False,
            "referrer_name": referrer_name
        })

        # إرسال الرسالة مع الأزرار الشفافة فقط وبدون فتح القائمة السفلية تلقائياً
        bot.send_message(
            user_id,
            get_first_welcome_text(first_name, referrer_name),
            parse_mode="HTML",
            reply_markup=get_inline_keyboard()
        )

        try:
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("📩 رد على المستخدم", callback_data=f"reply_{user_id}"))
            bot.send_message(ADMIN_ID, f"👤 **مشترك جديد:** {first_name}\nID: `{user_id}`", reply_markup=markup, parse_mode="Markdown")
        except:
            pass

    else:
        points = user.get("points", 0)
        
        # إرسال الرسالة مع الأزرار الشفافة فقط وبدون فتح القائمة السفلية تلقائياً
        bot.send_message(
            user_id,
            get_returning_welcome_text(first_name, points),
            parse_mode="HTML",
            reply_markup=get_inline_keyboard()
        )

# --- معالجة الأزرار الشفافة (Inline Keyboard) ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    first_name = call.from_user.first_name

    if call.data.startswith("check_sub_"):
        if is_user_subscribed(user_id):
            bot.answer_callback_query(call.id, "✅ הצטרפותך אושרה בהצלחה!")
            ref_str = call.data.replace("check_sub_", "")
            referrer_id = int(ref_str) if ref_str.isdigit() else None
            try:
                bot.delete_message(user_id, call.message.message_id)
            except:
                pass
            process_user_registration(user_id, first_name, referrer_id)
        else:
            bot.answer_callback_query(call.id, "❌ עדיין לא הצטרפת לערוץ! אנא הצטרף ונסה שוב.", show_alert=True)
        return

    user = users_col.find_one({"user_id": user_id})
    points = user.get("points", 0) if user else 0

    if call.data == "check_vip":
        if points < 50:
            alert_text = (
                f"❌ סליחה! יש לך {points} נקודות בלבד.\n\n"
                f"🔒 כדי להיכנס לערוץ ה-VIP, עליך לצבור 50 נקודות.\n"
                f"📲 עבור כל חבר שתזמין תרוויח 5 נקודות!"
            )
            bot.answer_callback_query(call.id, alert_text, show_alert=True)
        else:
            bot.answer_callback_query(call.id)
            bot.send_message(
                user_id,
                f"🎉 <b>כל הכבוד! הגעת ל-50 נקודות!</b>\n\n"
                f"🔗 הנה הקישור הבלעדי שלך לערוץ ה-VIP:\n{VIP_CHANNEL_URL}",
                parse_mode="HTML"
            )

            if user and not user.get("claimed_vip", False):
                users_col.update_one({"user_id": user_id}, {"$set": {"claimed_vip": True}})
                
                now_str = datetime.now().strftime("%Y-%m-%d | %H:%M")
                proof_text = (
                    f"🥳 <b>ברכות! משתמש קיבל גישה מיידית!</b>\n\n"
                    f"🆔 <b>מזהה משתמש:</b> <code>{user_id}</code>\n"
                    f"🌍 <b>מדינה:</b> ישראל 🇮🇱\n"
                    f"📅 <b>תאריך ושעה:</b> <code>{now_str}</code>\n"
                    f"💎 <b>נקודות שנצברו:</b> 50 נקודות ✅"
                )
                
                proof_markup = telebot.types.InlineKeyboardMarkup()
                proof_markup.add(telebot.types.InlineKeyboardButton("🤖 לחץ כאן לכניסה לבוט", url=f"https://t.me/{BOT_USERNAME}?start={user_id}"))

                try:
                    bot.send_message(PROOF_CHANNEL_ID, proof_text, parse_mode="HTML", reply_markup=proof_markup)
                except Exception as e:
                    print(f"Error sending proof: {e}")

    elif call.data == "get_link":
        bot.answer_callback_query(call.id)
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        
        share_msg = (
            f"🚀 <b>הקישור האישי שלך להזמנת חברים:</b>\n\n"
            f"<code>{ref_link}</code>\n\n"
            f"📲 שתף את הקישור בקבוצות או עם חברים.\n"
            f"🎁 על כל הצטרפות תקבל <b>5 נקודות</b>!"
        )
        
        share_text = "בואו לבוט הכי לוהט בישראל 🔥🔞 קבלו נקודות וגישה לערוץ ה-VIP!"
        share_url = f"https://t.me/share/url?url={ref_link}&text={share_text}"
        
        link_markup = telebot.types.InlineKeyboardMarkup()
        link_markup.add(telebot.types.InlineKeyboardButton("📤 שתף את הקישור שלי", url=share_url))

        bot.send_message(user_id, share_msg, parse_mode="HTML", reply_markup=link_markup)

    elif call.data == "get_stats":
        bot.answer_callback_query(call.id)
        referrals = user.get("referrals", 0) if user else 0
        stats_msg = (
            f"📊 <b>סטטיסטיקת החשבון שלך:</b>\n\n"
            f"👤 שם: <b>{first_name}</b>\n"
            f"💎 נקודות ברשותך: <b>{points} / 50</b>\n"
            f"👥 חברים שהזמנת: <b>{referrals}</b>\n\n"
            f"🎯 נותרו לך עוד <b>{max(0, 50 - points)}</b> נקודות לפתיחת ערוץ ה-VIP!"
        )
        bot.send_message(user_id, stats_msg, parse_mode="HTML")

    elif call.data.startswith("reply_"):
        target_user = call.data.split("_")[1]
        reply_targets[call.message.chat.id] = target_user
        bot.answer_callback_query(call.id, "✅ أرسل الرد الآن في الشات")
        bot.send_message(ADMIN_ID, f"✍️ اكتب الرد للمستخدم `{target_user}`:", parse_mode="Markdown")

# --- أوامر الأدمن الإدارية ---

@bot.message_handler(commands=["stats"])
def stats(message):
    if message.chat.id == ADMIN_ID:
        count = users_col.count_documents({})
        bot.reply_to(message, f"👥 عدد المشتركين النشطين: `{count}`", parse_mode="Markdown")

@bot.message_handler(commands=["del"])
def delete_user(message):
    if message.chat.id == ADMIN_ID:
        args = message.text.split()
        if len(args) > 1 and args[1].isdigit():
            target_id = int(args[1])
            res = users_col.delete_one({"user_id": target_id})
            if res.deleted_count > 0:
                bot.reply_to(message, f"✅ تم مسح المستخدم `{target_id}` بنجاح!", parse_mode="Markdown")
            else:
                bot.reply_to(message, "❌ لم يتم العثور على هذا المستخدم.")
        else:
            bot.reply_to(message, "⚠️ يرجى كتابة الآيدي، مثال:\n`/del 123456789`", parse_mode="Markdown")

@bot.message_handler(commands=["reset_all"])
def reset_all_db(message):
    if message.chat.id == ADMIN_ID:
        try:
            users_col.delete_many({})
            bot.send_message(ADMIN_ID, "🚨 **تم مسح جميع المشتركين وإعادة تعيين قاعدة البيانات بالكامل!**", parse_mode="Markdown")
        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ حدث خطأ أثناء المسح: `{e}`", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.chat.id == ADMIN_ID and message.reply_to_message and (message.text in ["/bc", "/broadcast", "إذاعة", "اذاعة"]))
def broadcast(message):
    users = users_col.find()
    count = 0
    deleted_count = 0
    fail_count = 0
    target_message_id = message.reply_to_message.message_id
    
    bot.send_message(ADMIN_ID, "⏳ جاري بدء الإذاعة...")

    for u in users:
        target_id = u.get("user_id")
        try:
            bot.copy_message(chat_id=target_id, from_chat_id=ADMIN_ID, message_id=target_message_id)
            count += 1
            time.sleep(0.05) 
        except Exception as e:
            error_msg = str(e).lower()
            if "blocked" in error_msg or "deactivated" in error_msg or "chat not found" in error_msg:
                users_col.delete_one({"user_id": target_id})
                deleted_count += 1
            else:
                fail_count += 1
            continue
            
    bot.send_message(
        ADMIN_ID, 
        f"📊 **تقرير الإذاعة:**\n\n"
        f"✅ تم الإرسال بنجاح: `{count}`\n"
        f"🗑️ تم حذف المحظورين/الوهميين: `{deleted_count}`\n"
        f"❌ أخطاء أخرى: `{fail_count}`",
        parse_mode="Markdown"
    )

# --- معالجة الرسائل العادية من قبل المستخدمين ---
@bot.message_handler(func=lambda message: message.chat.id != ADMIN_ID)
def handle_text_messages(message):
    user_id = message.chat.id
    first_name = message.from_user.first_name
    text = message.text

    user = users_col.find_one({"user_id": user_id})
    points = user.get("points", 0) if user else 0

    if text == BTN_VIP_TEXT:
        if points < 50:
            msg_text = (
                f"❌ סליחה! יש לך {points} נקודות בלבד.\n\n"
                f"🔒 כדי להיכנס לערוץ ה-VIP, עליך לצבור 50 נקודות.\n"
                f"📲 עבור כל חבר שתזמין תרוויח 5 נקודות!"
            )
            bot.send_message(user_id, msg_text)
        else:
            bot.send_message(
                user_id,
                f"🎉 <b>כל הכבוד! הגעת ל-50 נקודות!</b>\n\n"
                f"🔗 הנה הקישור הבלעדי שלך לערוץ ה-VIP:\n{VIP_CHANNEL_URL}",
                parse_mode="HTML"
            )

            if user and not user.get("claimed_vip", False):
                users_col.update_one({"user_id": user_id}, {"$set": {"claimed_vip": True}})
                
                now_str = datetime.now().strftime("%Y-%m-%d | %H:%M")
                proof_text = (
                    f"🥳 <b>ברכות! משתמש קיבל גישה מיידית!</b>\n\n"
                    f"🆔 <b>מזהה משתמש:</b> <code>{user_id}</code>\n"
                    f"🌍 <b>מדינה:</b> ישראל 🇮🇱\n"
                    f"📅 <b>תאריך ושעה:</b> <code>{now_str}</code>\n"
                    f"💎 <b>נקודות שנצברו:</b> 50 נקודות ✅"
                )
                
                proof_markup = telebot.types.InlineKeyboardMarkup()
                proof_markup.add(telebot.types.InlineKeyboardButton("🤖 לחץ כאן לכניסה לבוט", url=f"https://t.me/{BOT_USERNAME}?start={user_id}"))

                try:
                    bot.send_message(PROOF_CHANNEL_ID, proof_text, parse_mode="HTML", reply_markup=proof_markup)
                except Exception as e:
                    print(f"Error sending proof: {e}")

    elif text == BTN_LINK_TEXT:
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        
        share_msg = (
            f"🚀 <b>הקישור האישי שלך להזמנת חברים:</b>\n\n"
            f"<code>{ref_link}</code>\n\n"
            f"📲 שתף את הקישור בקבוצות או עם חברים.\n"
            f"🎁 על כל הצטרפות תקבל <b>5 נקודות</b>!"
        )
        
        share_text = "בואו לבוט הכי לוהט בישראל 🔥🔞 קבלו נקודות וגישה לערוץ ה-VIP!"
        share_url = f"https://t.me/share/url?url={ref_link}&text={share_text}"
        
        link_markup = telebot.types.InlineKeyboardMarkup()
        link_markup.add(telebot.types.InlineKeyboardButton("📤 שתף את הקישור שלי", url=share_url))

        bot.send_message(user_id, share_msg, parse_mode="HTML", reply_markup=link_markup)

    elif text == BTN_STATS_TEXT:
        referrals = user.get("referrals", 0) if user else 0
        stats_msg = (
            f"📊 <b>סטטיסטיקת החשבון שלך:</b>\n\n"
            f"👤 שם: <b>{first_name}</b>\n"
            f"💎 נקודות ברשותך: <b>{points} / 50</b>\n"
            f"👥 חברים שהזמנת: <b>{referrals}</b>\n\n"
            f"🎯 נותרו לך עוד <b>{max(0, 50 - points)}</b> נקודות לפתיחת ערוץ ה-VIP!"
        )
        bot.send_message(user_id, stats_msg, parse_mode="HTML")

    elif text == BTN_PROOF_TEXT:
        bot.send_message(user_id, f"✅ ערוץ הוכחות ואמינות:\n{PROOF_CHANNEL_URL}")

    else:
        try: 
            bot.forward_message(ADMIN_ID, user_id, message.message_id)
        except: 
            pass

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling(skip_pending=True)
