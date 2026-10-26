import os
import time
import telebot
from pymongo import MongoClient
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta

# --- الإعدادات الأساسية ---
TOKEN = os.environ.get("BOT_TOKEN") 
ADMIN_ID = 8873553496 
BOT_USERNAME = "ASDAKBOT" 
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

# --- نص رسالة الترحيب الطويلة (بالعبرية) مع التنسيق الجذاب ---
def get_welcome_text(first_name):
    return (
        f"<b>שלום {first_name}! 👋</b>\n\n"
        f"<b>ברוכים הבאים לבוט הפופולרי והשימושי ביותר בישראל! 🔥</b>\n\n"
        f"<b>כאן תמצאו את כל הסרטונים הבלעדיים, הייחודיים והלוהטים ביותר ברשת שכולם מדברים עליהם. "
        f"הצטרפו עכשיו וחוו את התוכן האיכותי והמרתק ביותר ללא הגבלה! 🇮🇱✨</b>\n\n"
        f"<blockquote><b>הישארו מעודכנים ותיהנו מהחוויה האקסקלוסיבית ביותר. 💋🔞</b></blockquote>"
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

    # تجهيز الأزرار (زر فتح البوت وزر الرد للإدارة إن وجد)
    markup = telebot.types.InlineKeyboardMarkup()
    
    # زر فتح البوت/الموقع (Web App)
    web_app_info = telebot.types.WebAppInfo(url="https://israelhotvideo.com")
    markup.add(telebot.types.InlineKeyboardButton("🌐 פתח את הבוט", web_app=web_app_info))

    # إرسال رسالة الترحيب مع الزر
    try:
        bot.send_message(
            user_id, 
            get_welcome_text(first_name), 
            parse_mode="HTML", 
            protect_content=True,
            reply_markup=markup
        )
    except Exception as e: 
        print(f"Error: {e}")

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

# --- معالجة الأزرار العكسية وتصفير البيانات ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id

    if call.data.startswith("reply_"):
        target_id = call.data.split("_")[1]
        reply_targets[call.message.chat.id] = target_id
        bot.answer_callback_query(call.id, "✅ أرسل الرد الآن في الشات")
        bot.send_message(ADMIN_ID, f"✍️ اكتب الرد للمستخدم `{target_id}`:", protect_content=True)

    elif call.data == "confirm_reset":
        users_col.update_many({}, {"$unset": {"last_welcome": "", "last_vip_click": ""}})
        bot.edit_message_text("✅ تم تصفير جميع التواريخ بنجاح.", call.message.chat.id, call.message.message_id)

    elif call.data == "cancel_reset":
        bot.edit_message_text("❌ تم إلغاء العملية.", call.message.chat.id, call.message.message_id)

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
