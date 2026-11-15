import os
import io
import json
import time
import urllib.parse
from datetime import datetime, timedelta
from threading import Thread

import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException
from pymongo import MongoClient
from flask import Flask

# --- الإعدادات الأساسية ---
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 8873553496
BOT_USERNAME = "Whedrolvedeosbot"
MONGO_URI = os.environ.get("MONGO_URI")
PORT = int(os.environ.get("PORT", 5001))

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_web():
    app.run(host="0.0.0.0", port=PORT)

bot = telebot.TeleBot(TOKEN)
bot.remove_webhook()

# --- الاتصال بقاعدة البيانات ---
client = MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True)
db = client["bot_database_new"]
users_col = db["users"]
settings_col = db["settings"]

try:
    client.admin.command('ping')
    print("✅ تم الاتصال بقاعدة البيانات بنجاح!")
except Exception as e:
    print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")

# --- الإعدادات الافتراضية الشاملة ---
DEFAULT_SETTINGS = {
    # 1. الوسائط والمحتوى
    "media_type": "video",  # video, photo, animation, text
    "media_file": "https://qu.ax/YazP4",
    "protect_content": True,

    # 2. الروابط والأسعار
    "share_link": "https://t.me/joinchat/hRhhXjTZcCU2NjVh",
    "vip_stars_url": "https://t.me/m/7_KEyMT7OTg8",
    "alt_pay_url": "https://t.me/Gh64yu",
    "vip_price": "1000",

    # 3. النصوص القابلة للتعديل
    "welcome_text": (
        "<b>היי {first_name}! 👋🔥\n\n"
        "פתיחת הקבוצה נעולה (0/2 שיתופים) 🎁\n"
        "+50,000 סרטונים בלעדיים מחכים לך!</b>\n\n"
        "<blockquote>🚀 לחצו על \"שתף\" ושתפו את הקישור עם 2 חברים או קבוצות לפתיחה מיידית 👇</blockquote>"
    ),
    "vip_text": (
        "<blockquote><b>מחיר כניסה: 1000 כוכבי טלגרם 😎</b></blockquote>\n"
        "<blockquote><b>התוכן כולל: 4,000 סרטונים + 2 קבוצות במתנה (ישראלית וערבית) ❤️</b></blockquote>\n"
        "<blockquote><b>שלח הודעה כאן לתשלום ולקבלת הקישורים:⬇️✅</b></blockquote>\n"
        "<b>https://t.me/m/7_KEyMT7OTg8</b>"
    ),
    "btn_share_text": "🔗 שיתוף (0/2)",
    "btn_verify_text": "📥 אימות פתיחה",
    "btn_vip_text": "👑 פתיחה מהירה - VIP",
    "btn_pay_stars_text": "⭐ תשלום כוכבים (הודעה ישירה)",
    "btn_pay_alt_text": "💳 תשלום בדרך אחרת (ללא כוכבים)",

    # 4. إظهار وإخفاء الأزرار
    "show_btn_share": True,
    "show_btn_verify": True,
    "show_btn_vip": True,
    "show_btn_pay_stars": True,
    "show_btn_pay_alt": True,

    # 5. السلوك والتوقيت
    "cooldown_hours": 24,
    "auto_approve": False,
    "maintenance_mode": False,
    "maintenance_text": "⚠️ <b>הבוט נמצא כעת בתחזוקה ושדרוג, נחזור לפעילות בקרוב!</b>",

    # 6. الإشعارات والرد الآلي
    "notify_mode": "all",  # all, new_only, off
    "notify_vip_click": True,
    "auto_reply_enabled": False,
    "auto_reply_text": "✅ ההודעה שלך התקבלה! למענה מהיר ורכישת VIP שלח הודעה כאן: https://t.me/m/7_KEyMT7OTg8",

    # 7. الاشتراك الإجباري
    "fsub_enabled": False,
    "fsub_channel_id": "",
    "fsub_channel_url": "",
    "fsub_text": "⚠️ <b>כדי להמשיך ולהשתמש בבוט, עליך להצטרף תחילה לערוץ הגיבוי שלנו:</b> 👇",
    "fsub_btn_join": "📢 הצטרפות לערוץ",
    "fsub_btn_check": "✅ הצטרפתי - המשך",

    # 8. الأمان والمشرفون والإذاعة
    "banned_users": [],
    "sub_admins": [],
    "bc_sleep": 0.06,
    "bc_footer": ""
}

def get_setting(key):
    doc = settings_col.find_one({"_id": "bot_config"})
    if doc and key in doc:
        return doc[key]
    return DEFAULT_SETTINGS.get(key)

def update_setting(key, value):
    settings_col.update_one({"_id": "bot_config"}, {"$set": {key: value}}, upsert=True)

def extract_html_with_custom_emojis(message):
    text = message.text or ""
    entities = message.entities or []
    if not entities:
        return message.html_text.strip()

    utf16_text = text.encode("utf-16-le")
    chars = [utf16_text[i:i+2].decode("utf-16-le") for i in range(0, len(utf16_text), 2)]

    insertions = {}
    for ent in entities:
        start = ent.offset
        end = ent.offset + ent.length
        open_tag, close_tag = "", ""

        if ent.type == "custom_emoji":
            open_tag = f'<tg-emoji emoji-id="{ent.custom_emoji_id}">'
            close_tag = "</tg-emoji>"
        elif ent.type == "bold":
            open_tag, close_tag = "<b>", "</b>"
        elif ent.type == "italic":
            open_tag, close_tag = "<i>", "</i>"
        elif ent.type == "underline":
            open_tag, close_tag = "<u>", "</u>"
        elif ent.type == "strikethrough":
            open_tag, close_tag = "<s>", "</s>"
        elif ent.type == "code":
            open_tag, close_tag = "<code>", "</code>"
        elif ent.type == "pre":
            open_tag, close_tag = "<pre>", "</pre>"
        elif ent.type == "spoiler":
            open_tag, close_tag = '<span class="tg-spoiler">', "</span>"
        elif ent.type == "blockquote":
            open_tag, close_tag = "<blockquote>", "</blockquote>"
        elif ent.type == "expandable_blockquote":
            open_tag, close_tag = "<blockquote expandable>", "</blockquote>"
        elif ent.type == "text_link":
            open_tag, close_tag = f'<a href="{ent.url}">', "</a>"

        if open_tag:
            insertions.setdefault(start, []).append(open_tag)
            insertions.setdefault(end, []).insert(0, close_tag)

    result = []
    for idx in range(len(chars) + 1):
        if idx in insertions:
            result.extend(insertions[idx])
        if idx < len(chars):
            result.append(chars[idx])

    return "".join(result).strip()

def is_admin_or_sub(user_id):
    return user_id == ADMIN_ID or user_id in (get_setting("sub_admins") or [])

def is_banned(user_id):
    if user_id == ADMIN_ID:
        return False
    return user_id in (get_setting("banned_users") or [])

# --- متغيرات الحالة ---
reply_targets = {}
admin_states = {}
bc_sessions = {}

# --- التحقق من الاشتراك الإجباري ---
def check_force_sub(user_id):
    if is_admin_or_sub(user_id):
        return True
    if not get_setting("fsub_enabled"):
        return True
    channel_id = get_setting("fsub_channel_id")
    channel_url = get_setting("fsub_channel_url")
    if not channel_id or not channel_url:
        return True  # لا يعمل إذا لم يتم إضافة قناة ورابط

    try:
        member = bot.get_chat_member(channel_id, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
        return False
    except Exception as e:
        print(f"Force Sub check error: {e}")
        return True  # لتجنب تعليق البوت إذا أُزيل البوت من القناة

def send_force_sub_message(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(get_setting("fsub_btn_join"), url=get_setting("fsub_channel_url")),
        types.InlineKeyboardButton(get_setting("fsub_btn_check"), callback_data="check_fsub")
    )
    bot.send_message(
        chat_id,
        get_setting("fsub_text"),
        parse_mode="HTML",
        reply_markup=markup,
        protect_content=bool(get_setting("protect_content"))
    )

# --- جلب النصوص الديناميكية ---
def get_texts(first_name=""):
    share_link = get_setting("share_link")
    share_text = f"התוכן המלא פתוח / ללא הגבלה🔥👇 {share_link}"
    raw_welcome = get_setting("welcome_text")
    formatted_welcome = raw_welcome.replace("{first_name}", first_name)

    return {
        "welcome": formatted_welcome,
        "btn_share": get_setting("btn_share_text"),
        "btn_verify": get_setting("btn_verify_text"),
        "btn_vip": get_setting("btn_vip_text"),
        "share_url": f"https://t.me/share/url?url={urllib.parse.quote(share_text)}",
        "share_alert": "⚠️ השיתוף לא הושלם! שתף את הקישור עם 2 חברים כדי לפתוח את הקבוצה 📲",
        "vip_already": "⚠️ כבר קיבלת את הפרטים היום! נסה שוב מאוחר יותר.",
        "vip_text": get_setting("vip_text"),
        "btn_pay_stars": get_setting("btn_pay_stars_text"),
        "btn_pay_alt": get_setting("btn_pay_alt_text"),
        "stars_url": get_setting("vip_stars_url"),
        "alt_url": get_setting("alt_pay_url")
    }

# --- إرسال رسالة الترحيب ---
def send_welcome_message(user_id, first_name):
    if is_banned(user_id):
        return

    if get_setting("maintenance_mode") and not is_admin_or_sub(user_id):
        try:
            bot.send_message(user_id, get_setting("maintenance_text"), parse_mode="HTML")
        except:
            pass
        return

    if not check_force_sub(user_id):
        send_force_sub_message(user_id)
        return

    now = datetime.now()
    cooldown = int(get_setting("cooldown_hours") or 0)

    if not is_admin_or_sub(user_id):
        user = users_col.find_one({"user_id": user_id})
        is_new = user is None

        if cooldown > 0 and user and user.get("last_welcome"):
            if now - user.get("last_welcome") < timedelta(hours=cooldown):
                return

        update_fields = {"last_welcome": now, "name": first_name}
        if is_new:
            update_fields["joined_at"] = now

        users_col.update_one({"user_id": user_id}, {"$set": update_fields}, upsert=True)

        notify_mode = get_setting("notify_mode")
        if notify_mode == "all" or (notify_mode == "new_only" and is_new):
            try:
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    types.InlineKeyboardButton("📩 رد", callback_data=f"reply_{user_id}"),
                    types.InlineKeyboardButton("🚫 حظر", callback_data=f"quickban_{user_id}")
                )
                bot.send_message(
                    ADMIN_ID,
                    f"👤 **مشترك {'جديد' if is_new else 'عائد'}:** {first_name}\n"
                    f"🆔 ID: `{user_id}`",
                    reply_markup=markup,
                    parse_mode="Markdown",
                    protect_content=True
                )
            except:
                pass

    t = get_texts(first_name)
    markup = types.InlineKeyboardMarkup()
    if get_setting("show_btn_share"):
        markup.add(types.InlineKeyboardButton(t["btn_share"], url=t["share_url"]))
    if get_setting("show_btn_verify"):
        markup.add(types.InlineKeyboardButton(t["btn_verify"], callback_data="check_share"))
    if get_setting("show_btn_vip"):
        markup.add(types.InlineKeyboardButton(t["btn_vip"], callback_data="show_vip_info"))

    media_type = get_setting("media_type")
    media_file = get_setting("media_file")
    protect = bool(get_setting("protect_content"))
    kb = markup if markup.keyboard else None

    try:
        if media_type == "video" and media_file:
            bot.send_video(user_id, media_file, caption=t["welcome"], parse_mode="HTML", protect_content=protect, reply_markup=kb)
        elif media_type == "photo" and media_file:
            bot.send_photo(user_id, media_file, caption=t["welcome"], parse_mode="HTML", protect_content=protect, reply_markup=kb)
        elif media_type == "animation" and media_file:
            bot.send_animation(user_id, media_file, caption=t["welcome"], parse_mode="HTML", protect_content=protect, reply_markup=kb)
        else:
            bot.send_message(user_id, t["welcome"], parse_mode="HTML", protect_content=protect, reply_markup=kb)
    except Exception as e:
        print(f"Error sending welcome to {user_id}: {e}")

# --- الأوامر الأساسية وطلبات الانضمام ---
@bot.message_handler(commands=["start"])
def start_cmd(message):
    send_welcome_message(message.chat.id, message.from_user.first_name)

@bot.chat_join_request_handler()
def join_req(request):
    if get_setting("auto_approve"):
        try:
            bot.approve_chat_join_request(request.chat.id, request.from_user.id)
        except Exception as e:
            print(f"Auto approve error: {e}")
    send_welcome_message(request.from_user.id, request.from_user.first_name)

# --- لوحات تحكم الأدمن الشاملة (/admin) ---
def get_admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 الإحصائيات", callback_data="adm_stats"),
        types.InlineKeyboardButton("📢 إذاعة متقدمة", callback_data="adm_bc_start")
    )
    markup.add(
        types.InlineKeyboardButton("🎬 المحتوى والوسائط", callback_data="adm_media"),
        types.InlineKeyboardButton("⚙️ الروابط والأسعار", callback_data="adm_settings")
    )
    markup.add(
        types.InlineKeyboardButton("📝 تعديل النصوص", callback_data="adm_texts"),
        types.InlineKeyboardButton("👁️ إظهار/إخفاء الأزرار", callback_data="adm_buttons_vis")
    )
    markup.add(
        types.InlineKeyboardButton("🔒 الاشتراك الإجباري", callback_data="adm_fsub"),
        types.InlineKeyboardButton("⏱️ التوقيت والسلوك", callback_data="adm_behavior")
    )
    markup.add(
        types.InlineKeyboardButton("🔔 الإشعارات والرد الآلي", callback_data="adm_notify"),
        types.InlineKeyboardButton("🛡️ الأمان والمشرفون", callback_data="adm_security")
    )
    markup.add(
        types.InlineKeyboardButton("💾 البيانات والصيانة", callback_data="adm_data")
    )
    return markup

@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.chat.id == ADMIN_ID:
        admin_states.pop(ADMIN_ID, None)
        bc_sessions.pop(ADMIN_ID, None)
        bot.send_message(
            ADMIN_ID,
            "🛠️ **لوحة التحكم الشاملة للإدارة**\nجميع إعدادات البوت تحت سيطرتك من هنا:",
            reply_markup=get_admin_keyboard(),
            parse_mode="Markdown",
            protect_content=True
        )

# --- القوائم الفرعية للإعدادات ---
def get_media_keyboard():
    m_type = get_setting("media_type")
    prot = "✅ مفعّلة" if get_setting("protect_content") else "❌ معطّلة"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"🔄 نوع الترحيب الحالي: [{m_type.upper()}] (اضغط للتبديل)", callback_data="cycle_media_type"),
        types.InlineKeyboardButton("📤 رفع فيديو/صورة/GIF أو إرسال رابط جديد", callback_data="set_media_file"),
        types.InlineKeyboardButton(f"🛡️ حماية المحتوى من النسخ: {prot}", callback_data="tog_protect_content"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
    )
    return markup

def get_settings_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔗 رابط المشاركة (القناة)", callback_data="set_share_link"),
        types.InlineKeyboardButton("⭐ رابط الدفع بالنجوم", callback_data="set_vip_stars_url"),
        types.InlineKeyboardButton("💳 رابط الدفع البديل", callback_data="set_alt_pay_url"),
        types.InlineKeyboardButton(f"💰 سعر VIP (الحالي: {get_setting('vip_price')})", callback_data="set_vip_price"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
    )
    return markup

def get_texts_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💬 تعديل نص الترحيب", callback_data="set_welcome_text"),
        types.InlineKeyboardButton("💎 تعديل نص رسالة VIP", callback_data="set_vip_text"),
        types.InlineKeyboardButton("🔗 نص زر المشاركة", callback_data="set_btn_share_text"),
        types.InlineKeyboardButton("📥 نص زر التحقق", callback_data="set_btn_verify_text"),
        types.InlineKeyboardButton("👑 نص زر فتح VIP", callback_data="set_btn_vip_text"),
        types.InlineKeyboardButton("⭐ نص زر الدفع بالنجوم", callback_data="set_btn_pay_stars_text"),
        types.InlineKeyboardButton("💳 نص زر الدفع البديل", callback_data="set_btn_pay_alt_text"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
    )
    return markup

def get_buttons_vis_keyboard():
    def ic(k): return "✅ ظاهر" if get_setting(k) else "❌ مخفي"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"زر المشاركة: {ic('show_btn_share')}", callback_data="tog_show_btn_share"),
        types.InlineKeyboardButton(f"زر التحقق: {ic('show_btn_verify')}", callback_data="tog_show_btn_verify"),
        types.InlineKeyboardButton(f"زر فتح VIP: {ic('show_btn_vip')}", callback_data="tog_show_btn_vip"),
        types.InlineKeyboardButton(f"زر الدفع بالنجوم: {ic('show_btn_pay_stars')}", callback_data="tog_show_btn_pay_stars"),
        types.InlineKeyboardButton(f"زر الدفع البديل: {ic('show_btn_pay_alt')}", callback_data="tog_show_btn_pay_alt"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
    )
    return markup

def get_fsub_keyboard():
    enabled = "✅ مفعّل" if get_setting("fsub_enabled") else "❌ معطّل"
    ch_id = get_setting("fsub_channel_id") or "غير محدد"
    ch_url = get_setting("fsub_channel_url") or "غير محدد"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"حالة الاشتراك الإجباري: {enabled}", callback_data="tog_fsub_enabled"),
        types.InlineKeyboardButton(f"🆔 معرّف القناة: {ch_id}", callback_data="set_fsub_channel_id"),
        types.InlineKeyboardButton(f"🔗 رابط القناة: {ch_url[:25]}...", callback_data="set_fsub_channel_url"),
        types.InlineKeyboardButton("📝 تعديل نص رسالة الاشتراك الإجباري", callback_data="set_fsub_text"),
        types.InlineKeyboardButton("🔘 تعديل نص زر الانضمام", callback_data="set_fsub_btn_join"),
        types.InlineKeyboardButton("✅ تعديل نص زر التحقق", callback_data="set_fsub_btn_check"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
    )
    return markup

def get_behavior_keyboard():
    cd = get_setting("cooldown_hours")
    app_st = "✅ مفعّل" if get_setting("auto_approve") else "❌ معطّل"
    mnt_st = "🔴 مفعّل (البوت متوقف للزوار)" if get_setting("maintenance_mode") else "🟢 معطّل (البوت يعمل)"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"⏳ مدة قفل الترحيب/VIP: {cd} ساعة", callback_data="set_cooldown_hours"),
        types.InlineKeyboardButton(f"✅ القبول التلقائي لطلبات الانضمام: {app_st}", callback_data="tog_auto_approve"),
        types.InlineKeyboardButton(f"🚧 وضع الصيانة: {mnt_st}", callback_data="tog_maintenance_mode"),
        types.InlineKeyboardButton("📝 تعديل رسالة الصيانة", callback_data="set_maintenance_text"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
    )
    return markup

def get_notify_keyboard():
    mode_map = {"all": "الكل (جديد + عائد)", "new_only": "المشتركين الجدد فقط", "off": "إيقاف إشعارات الدخول"}
    n_mode = mode_map.get(get_setting("notify_mode"), "all")
    vip_n = "✅ مفعّل" if get_setting("notify_vip_click") else "❌ معطّل"
    ar_st = "✅ مفعّل" if get_setting("auto_reply_enabled") else "❌ معطّل"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"🔔 إشعارات الدخول: {n_mode}", callback_data="cycle_notify_mode"),
        types.InlineKeyboardButton(f"👑 تنبيه عند ضغط زر VIP: {vip_n}", callback_data="tog_notify_vip_click"),
        types.InlineKeyboardButton(f"🤖 الرد الآلي على الرسائل: {ar_st}", callback_data="tog_auto_reply_enabled"),
        types.InlineKeyboardButton("📝 تعديل نص الرد الآلي", callback_data="set_auto_reply_text"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
    )
    return markup

def get_security_keyboard():
    banned_cnt = len(get_setting("banned_users") or [])
    subs_cnt = len(get_setting("sub_admins") or [])
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"🚫 حظر مستخدم (المحظورون: {banned_cnt})", callback_data="sec_ban_user"),
        types.InlineKeyboardButton("✅ فك حظر مستخدم", callback_data="sec_unban_user"),
        types.InlineKeyboardButton(f"👮 إضافة مشرف مساعد (الحاليون: {subs_cnt})", callback_data="sec_add_sub"),
        types.InlineKeyboardButton("🗑️ إزالة مشرف مساعد", callback_data="sec_del_sub"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
    )
    return markup

def get_data_keyboard():
    sp = get_setting("bc_sleep")
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📤 تصدير نسخة احتياطية (Backup JSON)", callback_data="adm_backup"),
        types.InlineKeyboardButton("📥 استعادة نسخة احتياطية (Restore)", callback_data="adm_restore_ask"),
        types.InlineKeyboardButton("🧹 تنظيف صامت للمحظورين من القاعدة", callback_data="adm_clean_db"),
        types.InlineKeyboardButton(f"⚡ سرعة الإذاعة (التأخير: {sp} ثانية)", callback_data="cycle_bc_sleep"),
        types.InlineKeyboardButton("📝 تعديل تذييل الإذاعة الثابت", callback_data="set_bc_footer"),
        types.InlineKeyboardButton("🔄 تصفير تواريخ المستخدمين", callback_data="confirm_reset_ask"),
        types.InlineKeyboardButton("⚠️ إعادة ضبط المصنع للإعدادات", callback_data="factory_reset_ask"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
    )
    return markup

# --- بناء لوحة خيارات الإذاعة المتقدمة ---
def get_bc_config_keyboard(session):
    pin_txt = "✅ تثبيت الرسالة: مفعّل" if session["pin"] else "❌ تثبيت الرسالة: معطّل"
    btn_txt = f"✅ زر مرفق: {session['btn_text']}" if session["btn_text"] else "➕ إضافة زر رابط للرسالة"
    del_map = {0: "بدون حذف تلقائي", 3600: "حذف بعد 1 ساعة", 86400: "حذف بعد 24 ساعة"}
    del_txt = f"⏳ {del_map[session['auto_delete']]}"

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(pin_txt, callback_data="bc_toggle_pin"),
        types.InlineKeyboardButton(btn_txt, callback_data="bc_add_btn"),
        types.InlineKeyboardButton(del_txt, callback_data="bc_cycle_del"),
        types.InlineKeyboardButton("🚀 المتابعة لإرسال رسالة الإذاعة", callback_data="bc_ready_send"),
        types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_home")
    )
    return markup

# --- تنفيذ الإذاعة المتقدمة ---
def run_advanced_broadcast(bc_message_id, session):
    now = datetime.now()
    segment = session["segment"]
    sleep_delay = float(get_setting("bc_sleep") or 0.06)

    if segment == "new_24h":
        query = {"joined_at": {"$gte": now - timedelta(hours=24)}}
        seg_name = "المستخدمين الجدد (آخر 24 ساعة)"
    elif segment == "vip_interested":
        query = {"clicked_vip": True}
        seg_name = "المهتمين بالـ VIP"
    else:
        query = {}
        seg_name = "جميع المشتركين"

    users = list(users_col.find(query, {"user_id": 1}))
    total_users = len(users)
    count = 0
    deleted_count = 0
    fail_count = 0
    error_logs = {}
    sent_records = []

    reply_markup = None
    if session["btn_text"] and session["btn_url"]:
        reply_markup = types.InlineKeyboardMarkup()
        reply_markup.add(types.InlineKeyboardButton(session["btn_text"], url=session["btn_url"]))

    status_msg = bot.send_message(
        ADMIN_ID,
        f"⏳ **بدأت الإذاعة المتقدمة**\n"
        f"🎯 الفئة: `{seg_name}` ({total_users} مشترك)\n"
        f"📌 التثبيت: `{'نعم' if session['pin'] else 'لا'}` | ⏳ الحذف التلقائي: `{session['auto_delete'] // 3600 if session['auto_delete'] else 0} ساعة`",
        parse_mode="Markdown",
        protect_content=True
    )

    for index, u in enumerate(users):
        target_id = u.get("user_id")
        if not target_id or is_banned(target_id):
            continue

        sent = False
        while not sent:
            try:
                copied = bot.copy_message(
                    chat_id=target_id,
                    from_chat_id=ADMIN_ID,
                    message_id=bc_message_id,
                    reply_markup=reply_markup,
                    protect_content=bool(get_setting("protect_content"))
                )
                count += 1
                sent = True

                if session["auto_delete"] > 0:
                    sent_records.append((target_id, copied.message_id))

                if session["pin"]:
                    try:
                        bot.pin_chat_message(target_id, copied.message_id, disable_notification=False)
                    except:
                        pass

                time.sleep(sleep_delay)

            except ApiTelegramException as e:
                if e.error_code == 429:
                    retry_after = int(e.result_json.get("parameters", {}).get("retry_after", 5))
                    time.sleep(retry_after + 1)
                elif e.error_code in [400, 403]:
                    err_desc = e.description.lower()
                    if any(x in err_desc for x in ["blocked", "deactivated", "chat not found", "can't initiate", "kicked"]):
                        users_col.delete_one({"user_id": target_id})
                        deleted_count += 1
                    else:
                        fail_count += 1
                        error_logs[e.description] = error_logs.get(e.description, 0) + 1
                    sent = True
                else:
                    fail_count += 1
                    error_logs[e.description] = error_logs.get(e.description, 0) + 1
                    sent = True
            except Exception as e:
                fail_count += 1
                err_str = str(e)
                error_logs[err_str] = error_logs.get(err_str, 0) + 1
                sent = True

        if (index + 1) % 250 == 0:
            try:
                bot.edit_message_text(
                    f"⏳ جاري الإذاعة... ({index + 1}/{total_users})\n✅ نجح: `{count}` | 🗑️ حُذف: `{deleted_count}` | ❌ فشل: `{fail_count}`",
                    chat_id=ADMIN_ID,
                    message_id=status_msg.message_id,
                    parse_mode="Markdown"
                )
            except:
                pass

    error_details = ""
    if error_logs:
        error_details = "\n\n🔍 **تفاصيل الأخطاء الأخرى:**\n"
        for err_msg, err_num in list(error_logs.items())[:5]:
            error_details += f"- `{err_msg}`: ({err_num})\n"

    bot.send_message(
        ADMIN_ID,
        f"📊 **تقرير الإذاعة المتقدمة:**\n\n"
        f"🎯 الفئة المستهدفة: `{seg_name}`\n"
        f"✅ تم الإرسال بنجاح: `{count}`\n"
        f"🗑️ تم حذف المحظورين/الوهميين: `{deleted_count}`\n"
        f"❌ أخطاء أخرى: `{fail_count}`"
        f"{error_details}",
        parse_mode="Markdown",
        protect_content=True
    )

    if session["auto_delete"] > 0 and sent_records:
        def schedule_deletion(records, delay):
            time.sleep(delay)
            deleted_msgs = 0
            for c_id, m_id in records:
                try:
                    bot.delete_message(c_id, m_id)
                    deleted_msgs += 1
                    time.sleep(0.05)
                except:
                    pass
            try:
                bot.send_message(ADMIN_ID, f"🗑️ اكتمل الحذف التلقائي (تم حذف `{deleted_msgs}` رسالة).", parse_mode="Markdown")
            except:
                pass

        Thread(target=schedule_deletion, args=(sent_records, session["auto_delete"]), daemon=True).start()

# --- التنظيف الصامت لقاعدة البيانات ---
def run_silent_db_clean():
    users = list(users_col.find({}, {"user_id": 1}))
    deleted = 0
    active = 0
    bot.send_message(ADMIN_ID, f"🧹 جاري فحص وتنظيف `{len(users)}` سجل بصمت...", parse_mode="Markdown")
    for u in users:
        uid = u.get("user_id")
        if not uid:
            users_col.delete_one({"_id": u["_id"]})
            deleted += 1
            continue
        try:
            bot.send_chat_action(uid, "typing")
            active += 1
            time.sleep(0.05)
        except ApiTelegramException as e:
            if e.error_code == 429:
                retry_after = int(e.result_json.get("parameters", {}).get("retry_after", 5))
                time.sleep(retry_after + 1)
            elif e.error_code in [400, 403]:
                users_col.delete_one({"user_id": uid})
                deleted += 1
        except:
            pass
    bot.send_message(ADMIN_ID, f"✅ **اكتمل التنظيف الصامت!**\n🟢 نشطون فعلياً: `{active}`\n🗑️ محذوفون/محظورون أُزيلوا: `{deleted}`", parse_mode="Markdown")

# --- معالجة جميع الأزرار التفاعلية ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if is_banned(user_id):
        return

    t = get_texts()

    # 1. التحقق من الاشتراك الإجباري
    if call.data == "check_fsub":
        if check_force_sub(user_id):
            bot.answer_callback_query(call.id, "✅ תודה שהצטרפת!")
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except:
                pass
            send_welcome_message(user_id, call.from_user.first_name)
        else:
            bot.answer_callback_query(call.id, "⚠️ עדיין לא הצטרפת לערוץ! הצטרף ונסה שוב.", show_alert=True)
        return

    # 2. أزرار المستخدمين العادية
    if call.data == "check_share":
        if not check_force_sub(user_id):
            send_force_sub_message(chat_id)
            return
        bot.answer_callback_query(call.id, t["share_alert"], show_alert=True)

    elif call.data == "show_vip_info":
        if not check_force_sub(user_id):
            send_force_sub_message(chat_id)
            return

        now = datetime.now()
        cooldown = int(get_setting("cooldown_hours") or 0)

        if not is_admin_or_sub(user_id):
            user = users_col.find_one({"user_id": user_id})
            users_col.update_one({"user_id": user_id}, {"$set": {"clicked_vip": True, "last_vip_click": now}}, upsert=True)

            if get_setting("notify_vip_click"):
                try:
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("📩 راسله الآن", callback_data=f"reply_{user_id}"))
                    bot.send_message(ADMIN_ID, f"👑 **تنبيه اهتمام VIP!**\nالمستخدم: {call.from_user.first_name} (`{user_id}`) ضغط على زر VIP الآن.", reply_markup=m, parse_mode="Markdown")
                except:
                    pass

            if cooldown > 0 and user and user.get("last_vip_request"):
                if now - user.get("last_vip_request") < timedelta(hours=cooldown):
                    bot.answer_callback_query(call.id, t["vip_already"], show_alert=True)
                    return

        try:
            bot.answer_callback_query(call.id)
        except:
            pass

        vip_markup = types.InlineKeyboardMarkup(row_width=1)
        if get_setting("show_btn_pay_stars"):
            vip_markup.add(types.InlineKeyboardButton(t["btn_pay_stars"], url=t["stars_url"]))
        if get_setting("show_btn_pay_alt"):
            vip_markup.add(types.InlineKeyboardButton(t["btn_pay_alt"], url=t["alt_url"]))

        try:
            bot.send_message(
                chat_id,
                t["vip_text"],
                parse_mode="HTML",
                reply_markup=vip_markup if vip_markup.keyboard else None,
                protect_content=bool(get_setting("protect_content"))
            )
            if not is_admin_or_sub(user_id):
                users_col.update_one({"user_id": user_id}, {"$set": {"last_vip_request": now}}, upsert=True)
        except Exception as e:
            print(f"Error sending VIP info: {e}")

    # 3. أزرار الرد والحظر السريع (للأدمن والمشرفين)
    elif is_admin_or_sub(user_id) and call.data.startswith("reply_"):
        target_id = call.data.split("_")[1]
        reply_targets[user_id] = target_id
        bot.answer_callback_query(call.id, "✅ أرسل الرد الآن")
        bot.send_message(user_id, f"✍️ اكتب الرد للمستخدم `{target_id}`:", parse_mode="Markdown")

    elif user_id == ADMIN_ID and call.data.startswith("quickban_"):
        target_id = int(call.data.split("_")[1])
        banned = get_setting("banned_users") or []
        if target_id not in banned:
            banned.append(target_id)
            update_setting("banned_users", banned)
        bot.answer_callback_query(call.id, f"🚫 تم حظر {target_id}", show_alert=True)

    # 4. لوحة تحكم الأدمن الرئيسي فقط
    elif user_id == ADMIN_ID:
        if call.data == "adm_home":
            admin_states.pop(ADMIN_ID, None)
            bc_sessions.pop(ADMIN_ID, None)
            bot.edit_message_text("🛠️ **لوحة التحكم الشاملة للإدارة**", chat_id, call.message.message_id, reply_markup=get_admin_keyboard(), parse_mode="Markdown")

        elif call.data == "adm_stats":
            now = datetime.now()
            total = users_col.count_documents({})
            new_24h = users_col.count_documents({"joined_at": {"$gte": now - timedelta(hours=24)}})
            vip_clicks = users_col.count_documents({"clicked_vip": True})
            banned_cnt = len(get_setting("banned_users") or [])
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home"))
            bot.edit_message_text(
                f"📊 **إحصائيات البوت التفصيلية:**\n\n"
                f"👥 إجمالي المشتركين: `{total}`\n"
                f"🆕 مشتركو آخر 24 ساعة: `{new_24h}`\n"
                f"👑 مهتمون بالـ VIP: `{vip_clicks}`\n"
                f"🚫 المحظورون: `{banned_cnt}`",
                chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown"
            )

        # القوائم الفرعية
        elif call.data == "adm_media":
            bot.edit_message_text("🎬 **إعدادات المحتوى والوسائط**", chat_id, call.message.message_id, reply_markup=get_media_keyboard(), parse_mode="Markdown")
        elif call.data == "adm_settings":
            bot.edit_message_text("⚙️ **إعدادات الروابط والأسعار**", chat_id, call.message.message_id, reply_markup=get_settings_keyboard(), parse_mode="Markdown")
        elif call.data == "adm_texts":
            bot.edit_message_text("📝 **تعديل النصوص الحية**\n(يدعم وسوم HTML مثل `<b>` و `<blockquote>`)", chat_id, call.message.message_id, reply_markup=get_texts_keyboard(), parse_mode="Markdown")
        elif call.data == "adm_buttons_vis":
            bot.edit_message_text("👁️ **إظهار وإخفاء الأزرار**", chat_id, call.message.message_id, reply_markup=get_buttons_vis_keyboard(), parse_mode="Markdown")
        elif call.data == "adm_fsub":
            bot.edit_message_text(
                "🔒 **إعدادات الاشتراك الإجباري**\n"
                "⚠️ لن يعمل الاشتراك الإجباري إلا إذا قمت بتفعيله **و** إضافة معرّف القناة ورابطها، ويجب أن يكون البوت مشرفاً في القناة.",
                chat_id, call.message.message_id, reply_markup=get_fsub_keyboard(), parse_mode="Markdown"
            )
        elif call.data == "adm_behavior":
            bot.edit_message_text("⏱️ **إعدادات التوقيت والسلوك**", chat_id, call.message.message_id, reply_markup=get_behavior_keyboard(), parse_mode="Markdown")
        elif call.data == "adm_notify":
            bot.edit_message_text("🔔 **إعدادات الإشعارات والرد الآلي**", chat_id, call.message.message_id, reply_markup=get_notify_keyboard(), parse_mode="Markdown")
        elif call.data == "adm_security":
            bot.edit_message_text("🛡️ **إعدادات الأمان والمشرفين**", chat_id, call.message.message_id, reply_markup=get_security_keyboard(), parse_mode="Markdown")
        elif call.data == "adm_data":
            bot.edit_message_text("💾 **إدارة البيانات والصيانة**", chat_id, call.message.message_id, reply_markup=get_data_keyboard(), parse_mode="Markdown")

        # التبديلات السريعة (Toggles)
        elif call.data.startswith("tog_"):
            key = call.data.replace("tog_", "")
            update_setting(key, not bool(get_setting(key)))
            bot.answer_callback_query(call.id, "✅ تم التحديث!")
            if key.startswith("show_btn_"):
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_buttons_vis_keyboard())
            elif key == "protect_content":
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_media_keyboard())
            elif key == "fsub_enabled":
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_fsub_keyboard())
            elif key in ["auto_approve", "maintenance_mode"]:
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_behavior_keyboard())
            elif key in ["notify_vip_click", "auto_reply_enabled"]:
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_notify_keyboard())

        elif call.data == "cycle_media_type":
            order = ["video", "photo", "animation", "text"]
            curr = get_setting("media_type")
            nxt = order[(order.index(curr) + 1) % len(order)] if curr in order else "video"
            update_setting("media_type", nxt)
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_media_keyboard())

        elif call.data == "cycle_notify_mode":
            order = ["all", "new_only", "off"]
            curr = get_setting("notify_mode")
            nxt = order[(order.index(curr) + 1) % len(order)] if curr in order else "all"
            update_setting("notify_mode", nxt)
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_notify_keyboard())

        elif call.data == "cycle_bc_sleep":
            order = [0.06, 0.1, 0.2]
            curr = float(get_setting("bc_sleep") or 0.06)
            nxt = order[(order.index(curr) + 1) % len(order)] if curr in order else 0.06
            update_setting("bc_sleep", nxt)
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_data_keyboard())

        # طلب إدخال قيمة نصية أو رقمية أو وسائط
        elif call.data.startswith("set_"):
            key = call.data.replace("set_", "")
            admin_states[ADMIN_ID] = f"edit_{key}"
            prompts = {
                "media_file": "📤 أرسل الآن **الفيديو / الصورة / الـ GIF** مباشرة من جهازك، أو أرسل **رابطاً مباشراً (URL)**:",
                "share_link": "🔗 أرسل رابط القناة/المجموعة للمشاركة:",
                "vip_stars_url": "⭐ أرسل رابط حسابك للدفع بالنجوم:",
                "alt_pay_url": "💳 أرسل رابط حسابك للدفع البديل:",
                "vip_price": "💰 أرسل سعر الباقة بالنجوم (رقم فقط):",
                "welcome_text": "💬 أرسل نص الترحيب الجديد (استخدم `{first_name}` لاسم المستخدم):",
                "vip_text": "💎 أرسل نص رسالة الـ VIP الجديد:",
                "btn_share_text": "🔗 أرسل النص الجديد لزر المشاركة:",
                "btn_verify_text": "📥 أرسل النص الجديد لزر التحقق:",
                "btn_vip_text": "👑 أرسل النص الجديد لزر فتح VIP:",
                "btn_pay_stars_text": "⭐ أرسل النص الجديد لزر الدفع بالنجوم:",
                "btn_pay_alt_text": "💳 أرسل النص الجديد لزر الدفع البديل:",
                "fsub_channel_id": "🆔 أرسل معرّف القناة (مثل `@MyChannel` أو `-1001234567890`) وارفع البوت مشرفاً فيها:",
                "fsub_channel_url": "🔗 أرسل رابط الانضمام للقناة (مثل `https://t.me/...`):",
                "fsub_text": "📝 أرسل نص رسالة الاشتراك الإجباري:",
                "fsub_btn_join": "🔘 أرسل نص زر الانضمام للقناة:",
                "fsub_btn_check": "✅ أرسل نص زر التحقق من الاشتراك:",
                "cooldown_hours": "⏳ أرسل عدد ساعات القفل (مثلاً `24` أو `0` لإلغاء القفل):",
                "maintenance_text": "🚧 أرسل نص رسالة الصيانة:",
                "auto_reply_text": "🤖 أرسل نص الرد الآلي:",
                "bc_footer": "📝 أرسل تذييل الإذاعة الثابت (أو أرسل `حذف` لإزالته):"
            }
            bot.answer_callback_query(call.id)
            bot.send_message(ADMIN_ID, prompts.get(key, f"أرسل القيمة الجديدة لـ {key}:"), parse_mode="Markdown")

        # الأمان والمشرفون
        elif call.data in ["sec_ban_user", "sec_unban_user", "sec_add_sub", "sec_del_sub"]:
            admin_states[ADMIN_ID] = call.data
            msgs = {
                "sec_ban_user": "🚫 أرسل **ID المستخدم** الذي تريد حظره:",
                "sec_unban_user": "✅ أرسل **ID المستخدم** لفك الحظر عنه:",
                "sec_add_sub": "👮 أرسل **ID المشرف المساعد** لإضافته:",
                "sec_del_sub": "🗑️ أرسل **ID المشرف المساعد** لإزالته:"
            }
            bot.answer_callback_query(call.id)
            bot.send_message(ADMIN_ID, msgs[call.data], parse_mode="Markdown")

        # النسخ الاحتياطي والاستعادة والتنظيف
        elif call.data == "adm_backup":
            bot.answer_callback_query(call.id, "⏳ جاري تجهيز النسخة...")
            all_users = list(users_col.find({}, {"_id": 0}))
            for u in all_users:
                for k, v in u.items():
                    if isinstance(v, datetime):
                        u[k] = v.isoformat()
            json_bytes = json.dumps(all_users, ensure_ascii=False, indent=2).encode("utf-8")
            bio = io.BytesIO(json_bytes)
            bio.name = f"bot_backup_{datetime.now().strftime('%Y_%m_%d')}.json"
            bot.send_document(ADMIN_ID, bio, caption=f"💾 **نسخة احتياطية كاملة** (`{len(all_users)}` سجل)", parse_mode="Markdown")

        elif call.data == "adm_restore_ask":
            admin_states[ADMIN_ID] = "restore_json"
            bot.answer_callback_query(call.id)
            bot.send_message(ADMIN_ID, "📥 أرسل الآن ملف النسخة الاحتياطية (`.json`) لاستعادة المستخدمين:")

        elif call.data == "adm_clean_db":
            bot.answer_callback_query(call.id, "🧹 بدأ التنظيف الصامت...")
            Thread(target=run_silent_db_clean, daemon=True).start()

        elif call.data == "confirm_reset_ask":
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("✅ نعم، صفّر التواريخ", callback_data="confirm_reset"), types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_data"))
            bot.edit_message_text("⚠️ هل أنت متأكد من تصفير تواريخ الترحيب وVIP؟", chat_id, call.message.message_id, reply_markup=m)

        elif call.data == "confirm_reset":
            users_col.update_many({}, {"$unset": {"last_welcome": "", "last_vip_request": ""}})
            bot.edit_message_text("✅ تم تصفير التواريخ بنجاح.", chat_id, call.message.message_id, reply_markup=get_data_keyboard())

        elif call.data == "factory_reset_ask":
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("⚠️ نعم، استعادة الإعدادات الافتراضية", callback_data="factory_reset_do"), types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_data"))
            bot.edit_message_text("⚠️ سيتم إرجاع جميع النصوص والروابط للإعدادات الافتراضية (لن يُحذف المشتركون). هل أنت متأكد؟", chat_id, call.message.message_id, reply_markup=m)

        elif call.data == "factory_reset_do":
            settings_col.delete_one({"_id": "bot_config"})
            bot.edit_message_text("✅ تمت استعادة الإعدادات الافتراضية بنجاح!", chat_id, call.message.message_id, reply_markup=get_admin_keyboard())

        # الإذاعة المتقدمة
        elif call.data == "adm_bc_start":
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("👥 جميع المشتركين", callback_data="bc_seg_all"),
                types.InlineKeyboardButton("🆕 المشتركون الجدد (آخر 24 ساعة)", callback_data="bc_seg_new_24h"),
                types.InlineKeyboardButton("👑 المهتمون بالـ VIP فقط", callback_data="bc_seg_vip_interested"),
                types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
            )
            bot.edit_message_text("📢 **إعداد الإذاعة المتقدمة (1/2)**\nاختر الفئة المستهدفة:", chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data.startswith("bc_seg_"):
            seg = call.data.replace("bc_seg_", "")
            bc_sessions[ADMIN_ID] = {"segment": seg, "pin": False, "btn_text": None, "btn_url": None, "auto_delete": 0, "step": "config"}
            bot.edit_message_text("🎛️ **خيارات الإذاعة المتقدمة (2/2)**", chat_id, call.message.message_id, reply_markup=get_bc_config_keyboard(bc_sessions[ADMIN_ID]), parse_mode="Markdown")

        elif call.data == "bc_toggle_pin" and ADMIN_ID in bc_sessions:
            bc_sessions[ADMIN_ID]["pin"] = not bc_sessions[ADMIN_ID]["pin"]
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_bc_config_keyboard(bc_sessions[ADMIN_ID]))

        elif call.data == "bc_cycle_del" and ADMIN_ID in bc_sessions:
            curr = bc_sessions[ADMIN_ID]["auto_delete"]
            bc_sessions[ADMIN_ID]["auto_delete"] = 3600 if curr == 0 else (86400 if curr == 3600 else 0)
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_bc_config_keyboard(bc_sessions[ADMIN_ID]))

        elif call.data == "bc_add_btn" and ADMIN_ID in bc_sessions:
            bc_sessions[ADMIN_ID]["step"] = "wait_btn"
            bot.answer_callback_query(call.id)
            bot.send_message(ADMIN_ID, "🔗 أرسل نص الزر والرابط مفصولين بعلامة `|`\nمثال: `🔥 عرض خاص | https://t.me/Gh64yu`", parse_mode="Markdown")

        elif call.data == "bc_ready_send" and ADMIN_ID in bc_sessions:
            bc_sessions[ADMIN_ID]["step"] = "wait_msg"
            bot.answer_callback_query(call.id)
            bot.send_message(ADMIN_ID, "📨 **أرسل الآن رسالة الإذاعة** وسيتم إطلاقها فوراً:", parse_mode="Markdown")

# --- معالجة رسائل الأدمن والمشرفين ---
@bot.message_handler(func=lambda message: is_admin_or_sub(message.chat.id), content_types=['text', 'photo', 'video', 'animation', 'document', 'voice', 'audio'])
def handle_admin_messages(message):
    uid = message.chat.id

    # 1. معالجة حالات التعديل للأدمن الرئيسي
    if uid == ADMIN_ID and ADMIN_ID in admin_states:
        state = admin_states.pop(ADMIN_ID)

        # رفع وسائط مباشرة للترحيب
        if state == "edit_media_file":
            if message.content_type == "video":
                update_setting("media_file", message.video.file_id)
                update_setting("media_type", "video")
            elif message.content_type == "photo":
                update_setting("media_file", message.photo[-1].file_id)
                update_setting("media_type", "photo")
            elif message.content_type == "animation":
                update_setting("media_file", message.animation.file_id)
                update_setting("media_type", "animation")
            elif message.content_type == "text":
                update_setting("media_file", message.text.strip())
            bot.reply_to(message, "✅ تم حفظ الوسائط/الرابط الجديد بنجاح!", reply_markup=get_media_keyboard())
            return

        # استعادة نسخة احتياطية JSON
        if state == "restore_json" and message.content_type == "document":
            try:
                file_info = bot.get_file(message.document.file_id)
                downloaded = bot.download_file(file_info.file_path)
                records = json.loads(downloaded.decode("utf-8"))
                restored = 0
                for r in records:
                    if "user_id" in r:
                        for dt_key in ["joined_at", "last_welcome", "last_vip_request", "last_vip_click"]:
                            if isinstance(r.get(dt_key), str):
                                try:
                                    r[dt_key] = datetime.fromisoformat(r[dt_key])
                                except:
                                    pass
                        users_col.update_one({"user_id": r["user_id"]}, {"$set": r}, upsert=True)
                        restored += 1
                bot.reply_to(message, f"✅ تمت استعادة `{restored}` سجل إلى قاعدة البيانات بنجاح!", parse_mode="Markdown", reply_markup=get_admin_keyboard())
            except Exception as e:
                bot.reply_to(message, f"❌ فشل استعادة الملف: {e}")
            return

        # إدارة الحظر والمشرفين
        if state in ["sec_ban_user", "sec_unban_user", "sec_add_sub", "sec_del_sub"] and message.content_type == "text":
            try:
                target_uid = int(message.text.strip())
                if state == "sec_ban_user":
                    lst = get_setting("banned_users") or []
                    if target_uid not in lst: lst.append(target_uid)
                    update_setting("banned_users", lst)
                elif state == "sec_unban_user":
                    lst = [x for x in (get_setting("banned_users") or []) if x != target_uid]
                    update_setting("banned_users", lst)
                elif state == "sec_add_sub":
                    lst = get_setting("sub_admins") or []
                    if target_uid not in lst: lst.append(target_uid)
                    update_setting("sub_admins", lst)
                elif state == "sec_del_sub":
                    lst = [x for x in (get_setting("sub_admins") or []) if x != target_uid]
                    update_setting("sub_admins", lst)
                bot.reply_to(message, "✅ تم تحديث القائمة بنجاح!", reply_markup=get_security_keyboard())
            except:
                bot.reply_to(message, "⚠️ يرجى إرسال رقم ID صحيح.")
            return

        # بقية الإعدادات النصية والرقمية
        if state.startswith("edit_") and message.content_type == "text":
            key = state.replace("edit_", "")
            html_keys = ["welcome_text", "vip_text", "fsub_text", "maintenance_text", "auto_reply_text", "bc_footer"]
            val = extract_html_with_custom_emojis(message) if key in html_keys else message.text.strip()
            if key == "cooldown_hours":
                val = int(val) if val.isdigit() else 24
            elif key == "bc_footer" and val == "حذف":
                val = ""
            update_setting(key, val)
            bot.reply_to(message, "✅ تم الحفظ في قاعدة البيانات بنجاح!", reply_markup=get_admin_keyboard())
            return

    # 2. جلسة الإذاعة المتقدمة
    if uid == ADMIN_ID and ADMIN_ID in bc_sessions:
        session = bc_sessions[ADMIN_ID]
        if session["step"] == "wait_btn" and message.content_type == "text":
            if "|" in message.text:
                parts = message.text.split("|", 1)
                session["btn_text"] = parts[0].strip()
                session["btn_url"] = parts[1].strip()
                session["step"] = "config"
                bot.send_message(ADMIN_ID, "✅ تم إضافة الزر! تابع الآن:", reply_markup=get_bc_config_keyboard(session))
            else:
                bot.reply_to(message, "⚠️ استخدم علامة `|` بين النص والرابط.")
            return
        elif session["step"] == "wait_msg":
            active_session = bc_sessions.pop(ADMIN_ID)
            Thread(target=run_advanced_broadcast, args=(message.message_id, active_session), daemon=True).start()
            return

    # 3. الإذاعة السريعة بالرد
    if uid == ADMIN_ID and message.reply_to_message and message.content_type == "text" and (message.text in ["/bc", "/broadcast", "إذاعة", "اذاعة"]):
        quick_session = {"segment": "all", "pin": False, "btn_text": None, "btn_url": None, "auto_delete": 0}
        Thread(target=run_advanced_broadcast, args=(message.reply_to_message.message_id, quick_session), daemon=True).start()
        return

    # 4. الرد على المستخدمين
    if uid in reply_targets:
        target_id = reply_targets.pop(uid)
        try:
            bot.copy_message(chat_id=target_id, from_chat_id=uid, message_id=message.message_id, protect_content=bool(get_setting("protect_content")))
            bot.reply_to(message, f"✅ تم إرسال الرد إلى `{target_id}` بنجاح!", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ فشل الإرسال: {e}")

# --- توجيه رسائل المستخدمين للأدمن ---
@bot.message_handler(func=lambda message: not is_admin_or_sub(message.chat.id), content_types=['text', 'photo', 'video', 'animation', 'document', 'voice', 'audio'])
def forward_user_msg(message):
    uid = message.chat.id
    if is_banned(uid):
        return

    if get_setting("maintenance_mode"):
        try:
            bot.send_message(uid, get_setting("maintenance_text"), parse_mode="HTML")
        except:
            pass
        return

    if not check_force_sub(uid):
        send_force_sub_message(uid)
        return

    if get_setting("auto_reply_enabled"):
        try:
            bot.reply_to(message, get_setting("auto_reply_text"), parse_mode="HTML", protect_content=bool(get_setting("protect_content")))
        except:
            pass

    try:
        bot.forward_message(ADMIN_ID, uid, message.message_id)
    except:
        pass

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling(skip_pending=True)
