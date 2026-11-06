import os
import time
import telebot
from pymongo import MongoClient
import urllib.parse
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta

# --- الإعدادات (تُجلب من متغيرات البيئة في Render لأعلى درجات الأمان) ---
TOKEN = os.environ.get("BOT_TOKEN") 
ADMIN_ID = 8873553496 
BOT_USERNAME = "Whedrolvedeosbot" 
MONGO_URI = os.environ.get("MONGO_URI") 
PORT = int(os.environ.get("PORT", 5001))

reply_targets = {}
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

# فحص الاتصال بقاعدة البيانات
try:
    client.admin.command('ping')
    print("✅ تم الاتصال بقاعدة البيانات بنجاح!")
except Exception as e:
    print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")

# رابط الفيديو المرفق
VIDEO_URL = "https://files.catbox.moe/lwbdy1.mp4"

# رابط ونص المشاركة باللغة العبرية
SHARE_TEXT = "התוכן המלא פתוח / ללא הגבלה🔥👇 https://t.me/joinchat/hRhhXjTZcCU2NjVh"
SHARE_URL = f"https://t.me/share/url?url={urllib.parse.quote(SHARE_TEXT)}"

# --- النص الأول بالعبرية للترحيب ---
def get_welcome_text(first_name):
    return (
        f"🔥 <b>גישה אושרה: אוסף VIP פתוח!</b>\n\n"
        f"היי <b>{first_name}</b>, השער האישי שלך לכספת מוכן.\n\n"
        "<blockquote>📍 <b>סטטוס כספת:</b> נעול 🔐 (נדרשות 2 שיתופים)\n"
        "🎬 <b>קבצים זמינים:</b> 67,000+ קבצים בלעדיים</blockquote>\n\n"
        "<i>לחץ על שתף ופתח למטה כדי לקבל את הגישה שלך עכשיו! 🔞</i>"
    )

# --- النص الثالث بالعبرية لرسالة VIP ---
def get_vip_text():
    return (
        "<blockquote>⚡ <b>גישת VIP ללא הגבלה</b> ⚡\n"
        "▫️ <b>4,000+ הורדות ישירות ובלעדיות</b>\n"
        "▫️ <b>2 ערוצים פרטיים (עדכונים יומיים)</b>\n"
        "▫️ <b>גישה לכל החיים ללא הגבלה</b>\n"
        "💰 <b>מחיר: 1000 כוכבי טלגרם ⭐️</b>\n"
        "👇 <i>לחץ על הקישור למטה כדי להתחיל צאט תשלום ולקבל גישה:</i>\n"
        "<b>⭐️ https://t.me/m/gGbbzgOrZmU8</b></blockquote>"
    )

def send_welcome_message(user_id, first_name):
    if user_id != ADMIN_ID:
        now = datetime.now()
        user = users_col.find_one({"user_id": user_id})
        if user and user.get("last_welcome"):
            if now - user.get("last_welcome") < timedelta(hours=24):
                return
        users_col.update_one({"user_id": user_id}, {"$set": {"last_welcome": now, "name": first_name}}, upsert=True)
        
        try:
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("📩 رد على المستخدم", callback_data=f"reply_{user_id}"))
            bot.send_message(ADMIN_ID, f"👤 **مشترك جديد:** {first_name}\nID: `{user_id}`", reply_markup=markup, protect_content=True)
        except: 
            pass

    # الأزرار التفاعلية بالعبرية
    markup = telebot.types.InlineKeyboardMarkup()
    btn_share = telebot.types.InlineKeyboardButton("🔓 שתף ופתח (0/1)", url=SHARE_URL)
    btn_verify = telebot.types.InlineKeyboardButton("🔄 אימות גישה", callback_data="check_share")
    btn_vip = telebot.types.InlineKeyboardButton("💎 מעבר VIP מיידי", callback_data="show_vip_info")
    
    markup.row(btn_share)
    markup.row(btn_verify, btn_vip)

    try:
        # إرسال الفيديو مرفقاً بنص الترحيب والأزرار
        bot.send_video(
            user_id, 
            VIDEO_URL, 
            caption=get_welcome_text(first_name), 
            parse_mode="HTML", 
            protect_content=True, 
            reply_markup=markup
        )
    except Exception as e: 
        print(f"Error sending video welcome message to {user_id}: {e}")

# --- الأوامر الأساسية ---
@bot.message_handler(commands=["start"])
def start(message):
    send_welcome_message(message.chat.id, message.from_user.first_name)

@bot.message_handler(commands=["reset_all"])
def reset_all(message):
    if message.chat.id == ADMIN_ID:
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("✅ نعم، تصفير التواريخ", callback_data="confirm_reset"))
        markup.add(telebot.types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_reset"))
        bot.reply_to(message, "⚠️ **تنبيه:** هل أنت متأكد من تصفير تواريخ الترحيب لجميع المستخدمين؟", reply_markup=markup, protect_content=True)

@bot.message_handler(commands=["stats"])
def stats(message):
    if message.chat.id == ADMIN_ID:
        count = users_col.count_documents({})
        bot.reply_to(message, f"👥 عدد المشتركين النشطين: `{count}`", parse_mode="HTML", protect_content=True)

# --- الإذاعة الشاملة ---
@bot.message_handler(func=lambda message: message.chat.id == ADMIN_ID and message.reply_to_message and (message.text in ["/bc", "/broadcast", "إذاعة", "اذاعة"]))
def broadcast(message):
    users = users_col.find()
    count = 0
    deleted_count = 0
    fail_count = 0
    
    target_message_id = message.reply_to_message.message_id
    bot.send_message(ADMIN_ID, "⏳ جاري بدء الإذاعة...", protect_content=True)

    for u in users:
        target_id = u.get("user_id")
        try:
            bot.copy_message(chat_id=target_id, from_chat_id=ADMIN_ID, message_id=target_message_id, protect_content=True)
            count += 1
            time.sleep(0.05) 
        except Exception as e:
            error_message = str(e).lower()
            if "blocked" in error_message or "deactivated" in error_message or "chat not found" in error_message:
                users_col.delete_one({"user_id": target_id})
                deleted_count += 1
            else:
                fail_count += 1
            continue
            
    bot.send_message(
        ADMIN_ID, 
        f"📊 **تقرير الإذاعة والتحسين:**\n\n"
        f"✅ تم الإرسال بنجاح: `{count}`\n"
        f"🗑️ تم حذف المحظورين/الوهميين: `{deleted_count}`\n"
        f"❌ أخطاء أخرى: `{fail_count}`",
        protect_content=True
    )

# --- معالجة الأزرار التفاعلية ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id

    if call.data == "check_share":
        bot.answer_callback_query(
            call.id, 
            "⚠️ בדיקת מערכת: השיתוף לא הושלם (0/1). אנא שתף בצ אט אחד תחילה!", 
            show_alert=True
        )

    elif call.data == "show_vip_info":
        now = datetime.now()
        
        # استثناء الأدمن من فحص الـ 24 ساعة
        if user_id != ADMIN_ID:
            user = users_col.find_one({"user_id": user_id})
            if user and user.get("last_vip_request"):
                if now - user.get("last_vip_request") < timedelta(hours=24):
                    bot.answer_callback_query(
                        call.id, 
                        "⚠️ כבר קיבלת את פרטי ה-VIP. ניתן לבקש שוב רק לאחר 24 שעות!", 
                        show_alert=True
                    )
                    return

        # إغلاق زاوية التحميل في الزر أولاً
        try:
            bot.answer_callback_query(call.id)
        except:
            pass

        # محاولة إرسال الرسالة إلى المستخدم
        try:
            bot.send_message(
                call.message.chat.id, 
                get_vip_text(), 
                parse_mode="HTML", 
                protect_content=True
            )
            # تحديث وقت الطلب بعد النجاح في الإرسال فقط
            if user_id != ADMIN_ID:
                users_col.update_one({"user_id": user_id}, {"$set": {"last_vip_request": now}}, upsert=True)
        except Exception as e:
            print(f"Error sending VIP info to {user_id}: {e}")

    elif call.data.startswith("reply_"):
        target_id = call.data.split("_")[1]
        reply_targets[call.message.chat.id] = target_id
        bot.answer_callback_query(call.id, "✅ أرسل الرد الآن في الشات")
        bot.send_message(ADMIN_ID, f"✍️ اكتب الرد للمستخدم `{target_id}`:", protect_content=True)

    elif call.data == "confirm_reset":
        users_col.update_many({}, {"$unset": {"last_welcome": "", "last_vip_request": ""}})
        bot.edit_message_text("✅ تم تصفير جميع التواريخ بنجاح.", call.message.chat.id, call.message.message_id)

    elif call.data == "cancel_reset":
        bot.edit_message_text("❌ تم إلغاء العملية.", call.message.chat.id, call.message.message_id)

@bot.chat_join_request_handler()
def join_req(request):
    send_welcome_message(request.from_user.id, request.from_user.first_name)

# --- معالجة رد الأدمن الشامل على المستخدمين ---
@bot.message_handler(func=lambda message: message.chat.id == ADMIN_ID and message.chat.id in reply_targets)
def send_admin_reply(message):
    target_id = reply_targets.pop(message.chat.id)
    try:
        bot.copy_message(chat_id=target_id, from_chat_id=ADMIN_ID, message_id=message.message_id, protect_content=True)
        bot.reply_to(message, f"✅ تم إرسال الرد إلى `{target_id}` بنجاح!")
    except Exception as e:
        bot.reply_to(message, f"❌ فشل إرسال الرد: {e}")

@bot.message_handler(func=lambda message: message.chat.id != ADMIN_ID)
def forward(message):
    try: 
        bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    except: 
        pass

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling(skip_pending=True)
