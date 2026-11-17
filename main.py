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
from pymongo import MongoClient, IndexModel, ASCENDING
from flask import Flask

# --- الإعدادات الأساسية من السيرفر ---
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 8873553496
MONGO_URI = os.environ.get("MONGO_URI")
PORT = int(os.environ.get("PORT", 5001))

app = Flask(__name__)
active_bot_instances = {}  # {username: bot_instance}
PRIMARY_BOT_USERNAME = None

@app.route("/")
def home():
    active_list = ", ".join([f"@{u}" for u in active_bot_instances.keys()])
    return f"✅ Server is Alive! | Active Bots ({len(active_bot_instances)}): {active_list}"

def run_web():
    app.run(host="0.0.0.0", port=PORT)

# --- الاتصال بقاعدة البيانات وبناء الفهارس (Indexes) ---
client = MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True)
db = client["bot_database_new"]

users_col = db["users"]
settings_col = db["settings"]
states_col = db["admin_states"]
clones_col = db["bot_clones"]
analytics_col = db["analytics"]

try:
    client.admin.command("ping")
    users_col.create_indexes([
        IndexModel([("user_id", ASCENDING)], unique=True),
        IndexModel([("joined_at", ASCENDING)]),
        IndexModel([("clicked_vip", ASCENDING)]),
        IndexModel([("source_tag", ASCENDING)]),
        IndexModel([("last_bot", ASCENDING)])
    ])
    print("✅ تم الاتصال بـ MongoDB وتهيئة الفهارس بنجاح!")
except Exception as e:
    print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")

# --- الإعدادات الافتراضية الشاملة ---
DEFAULT_SETTINGS = {
    "media_type": "video",
    "media_file": "https://qu.ax/YazP4",
    "protect_content": True,
    "share_link": "https://t.me/joinchat/hRhhXjTZcCU2NjVh",
    "vip_stars_url": "https://t.me/m/7_KEyMT7OTg8",
    "alt_pay_url": "https://t.me/Gh64yu",
    "vip_price": "1000",
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
    "show_btn_share": True,
    "show_btn_verify": True,
    "show_btn_vip": True,
    "show_btn_pay_stars": True,
    "show_btn_pay_alt": True,
    "custom_buttons": [],
    "cooldown_hours": 24,
    "auto_approve": False,
    "maintenance_mode": False,
    "maintenance_text": "⚠️ <b>הבוט נמצא כעת בתחזוקה ושדרוג, נחזור לפעילות בקרוב!</b>",
    "notify_mode": "all",
    "notify_vip_click": True,
    "auto_reply_enabled": False,
    "auto_reply_text": "✅ ההודעה שלך התקבלה! למענה מהיר ורכישת VIP שלח הודעה כאן: https://t.me/m/7_KEyMT7OTg8",
    "fsub_enabled": False,
    "fsub_channel_id": "",
    "fsub_channel_url": "",
    "fsub_text": "⚠️ <b>כדי להמשיך ולהשתמש בבוט, עליך להצטרף תחילה לערוץ הגיבוי שלנו:</b> 👇",
    "fsub_btn_join": "📢 הצטרפות לערוץ",
    "fsub_btn_check": "✅ הצטרפתי - המשך",
    "banned_users": [],
    "sub_admins": [],
    "bc_sleep": 0.06,
    "bc_footer": "",
    "paused_bots": []  # قائمة أسماء البوتات المتوقفة مؤقتاً
}

# --- المفاتيح المستقلة لكل بوت (نصوص + روابط + وسائط) ---
PER_BOT_KEYS = [
    "welcome_text", "vip_text", "btn_share_text", "btn_verify_text",
    "btn_vip_text", "btn_pay_stars_text", "btn_pay_alt_text",
    "share_link", "vip_stars_url", "alt_pay_url", "vip_price",
    "media_type", "media_file"
]

# --- نظام الكاش السريع المتزامن (MongoDB + RAM) ---
_SETTINGS_CACHE = {}

def reload_settings_cache():
    global _SETTINGS_CACHE
    doc = settings_col.find_one({"_id": "bot_config"})
    if not doc:
        settings_col.insert_one({"_id": "bot_config", **DEFAULT_SETTINGS})
        _SETTINGS_CACHE = DEFAULT_SETTINGS.copy()
    else:
        _SETTINGS_CACHE = {**DEFAULT_SETTINGS, **doc}

reload_settings_cache()

def get_setting(key, bot_uname=None):
    if bot_uname:
        custom_key = f"{key}_{bot_uname}"
        if custom_key in _SETTINGS_CACHE and _SETTINGS_CACHE[custom_key] is not None:
            return _SETTINGS_CACHE[custom_key]
    return _SETTINGS_CACHE.get(key, DEFAULT_SETTINGS.get(key))

def update_setting(key, value, bot_uname=None):
    target_key = f"{key}_{bot_uname}" if bot_uname else key
    _SETTINGS_CACHE[target_key] = value
    settings_col.update_one({"_id": "bot_config"}, {"$set": {target_key: value}}, upsert=True)

def reset_bot_custom_config(bot_uname):
    unset_fields = {f"{k}_{bot_uname}": "" for k in PER_BOT_KEYS}
    for k in unset_fields:
        _SETTINGS_CACHE.pop(k, None)
    settings_col.update_one({"_id": "bot_config"}, {"$unset": unset_fields})

def is_bot_paused(bot_uname):
    return bot_uname in (get_setting("paused_bots") or [])

def toggle_bot_pause(bot_uname):
    paused = list(get_setting("paused_bots") or [])
    if bot_uname in paused:
        paused.remove(bot_uname)
        status = True  # أصبح يعمل
    else:
        paused.append(bot_uname)
        status = False  # أصبح متوقفاً
    update_setting("paused_bots", paused)
    return status

# --- إدارة الحالات السحابية في MongoDB ---
def set_state(user_id, state_name, extra_data=None):
    states_col.update_one(
        {"user_id": user_id},
        {"$set": {"state": state_name, "data": extra_data or {}, "updated_at": datetime.now()}},
        upsert=True
    )

def get_state(user_id):
    return states_col.find_one({"user_id": user_id})

def clear_state(user_id):
    states_col.delete_one({"user_id": user_id})

def log_metric(metric_name, inc=1):
    today = datetime.now().strftime("%Y-%m-%d")
    analytics_col.update_one({"date": today}, {"$inc": {metric_name: inc}}, upsert=True)

# --- غرفة العمليات المركزية: إرسال إشعارات الأدمن عبر البوت الأساسي أو أول بوت متاح ---
def notify_admin_central(text, reply_markup=None, parse_mode="Markdown", fallback_bot=None):
    # الأولوية للبوت الأساسي إذا كان شغالاً، وإلا أول بوت نشط، وإلا البوت الذي حدث فيه الحدث
    hub_bot = None
    if PRIMARY_BOT_USERNAME and PRIMARY_BOT_USERNAME in active_bot_instances:
        hub_bot = active_bot_instances[PRIMARY_BOT_USERNAME]
    elif active_bot_instances:
        hub_bot = next(iter(active_bot_instances.values()))
    else:
        hub_bot = fallback_bot

    if not hub_bot:
        return

    try:
        hub_bot.send_message(
            ADMIN_ID,
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            protect_content=True
        )
    except Exception:
        if fallback_bot and fallback_bot != hub_bot:
            try:
                fallback_bot.send_message(
                    ADMIN_ID,
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    protect_content=True
                )
            except:
                pass

def extract_html_with_custom_emojis(message):
    text = message.text or ""
    entities = message.entities or []
    if not entities:
        return message.html_text.strip()

    utf16_text = text.encode("utf-16-le")
    chars = [utf16_text[i:i+2].decode("utf-16-le") for i in range(0, len(utf16_text), 2)]
    insertions = {}
    for ent in entities:
        start, end = ent.offset, ent.offset + ent.length
        open_tag, close_tag = "", ""
        if ent.type == "custom_emoji":
            open_tag, close_tag = f'<tg-emoji emoji-id="{ent.custom_emoji_id}">', "</tg-emoji>"
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

# --- المحرك الموحد لتسجيل الأوامر لأي بوت (أساسي أو احتياطي) ---
def register_bot_handlers(bot_instance, bot_uname):
    def check_force_sub(user_id):
        if is_admin_or_sub(user_id) or not get_setting("fsub_enabled"):
            return True
        channel_id = get_setting("fsub_channel_id")
        channel_url = get_setting("fsub_channel_url")
        if not channel_id or not channel_url:
            return True
        try:
            member = bot_instance.get_chat_member(channel_id, user_id)
            return member.status in ["member", "administrator", "creator"]
        except:
            return True

    def send_force_sub_message(chat_id):
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(get_setting("fsub_btn_join"), url=get_setting("fsub_channel_url")),
            types.InlineKeyboardButton(get_setting("fsub_btn_check"), callback_data="check_fsub")
        )
        bot_instance.send_message(
            chat_id,
            get_setting("fsub_text"),
            parse_mode="HTML",
            reply_markup=markup,
            protect_content=bool(get_setting("protect_content"))
        )

    def get_texts(first_name="", target_bot=None):
        b_name = target_bot or bot_uname
        share_link = get_setting("share_link", b_name)
        share_text = f"התוכן המלא פתוח / ללא הגבלה🔥👇 {share_link}"
        raw_welcome = get_setting("welcome_text", b_name)
        return {
            "welcome": raw_welcome.replace("{first_name}", first_name),
            "btn_share": get_setting("btn_share_text", b_name),
            "btn_verify": get_setting("btn_verify_text", b_name),
            "btn_vip": get_setting("btn_vip_text", b_name),
            "share_url": f"https://t.me/share/url?url={urllib.parse.quote(share_text)}",
            "share_alert": "⚠️ השיתוף לא הושלם! שתף את הקישור עם 2 חברים כדי לפתוח את הקבוצה 📲",
            "vip_already": "⚠️ כבר קיבלת את הפרטים היום! נסה שוב מאוחר יותר.",
            "vip_text": get_setting("vip_text", b_name),
            "btn_pay_stars": get_setting("btn_pay_stars_text", b_name),
            "btn_pay_alt": get_setting("btn_pay_alt_text", b_name),
            "stars_url": get_setting("vip_stars_url", b_name),
            "alt_url": get_setting("alt_pay_url", b_name)
        }

    def send_welcome_message(user_id, first_name, source_tag=None):
        if is_banned(user_id):
            return

        # فحص الإيقاف المؤقت للبوت أو وضع الصيانة العام
        if (is_bot_paused(bot_uname) or get_setting("maintenance_mode")) and not is_admin_or_sub(user_id):
            try:
                bot_instance.send_message(user_id, get_setting("maintenance_text"), parse_mode="HTML")
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

            update_fields = {"last_welcome": now, "name": first_name, "last_bot": bot_uname}
            if is_new:
                update_fields["joined_at"] = now
                update_fields["source_tag"] = source_tag or "direct"
                log_metric("new_users")
            else:
                log_metric("returning_users")

            users_col.update_one({"user_id": user_id}, {"$set": update_fields}, upsert=True)

            notify_mode = get_setting("notify_mode")
            if notify_mode == "all" or (notify_mode == "new_only" and is_new):
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    types.InlineKeyboardButton("📩 رد", callback_data=f"reply_{user_id}_{bot_uname}"),
                    types.InlineKeyboardButton("🚫 حظر", callback_data=f"quickban_{user_id}")
                )
                src_txt = f"\n🔗 المصدر: `{source_tag}`" if (is_new and source_tag) else ""
                notify_admin_central(
                    f"👤 **مشترك {'جديد' if is_new else 'عائد'}** | عبر: @{bot_uname}\n"
                    f"📛 الاسم: {first_name}\n"
                    f"🆔 ID: `{user_id}`{src_txt}",
                    reply_markup=markup,
                    fallback_bot=bot_instance
                )

        t = get_texts(first_name)
        markup = types.InlineKeyboardMarkup()
        if get_setting("show_btn_share"):
            markup.add(types.InlineKeyboardButton(t["btn_share"], url=t["share_url"]))
        if get_setting("show_btn_verify"):
            markup.add(types.InlineKeyboardButton(t["btn_verify"], callback_data="check_share"))
        if get_setting("show_btn_vip"):
            markup.add(types.InlineKeyboardButton(t["btn_vip"], callback_data="show_vip_info"))

        for cb in (get_setting("custom_buttons") or []):
            if cb.get("target") == "welcome" and cb.get("text") and cb.get("url"):
                markup.add(types.InlineKeyboardButton(cb["text"], url=cb["url"]))

        media_type = get_setting("media_type", bot_uname)
        media_file = get_setting("media_file", bot_uname)
        protect = bool(get_setting("protect_content"))
        kb = markup if markup.keyboard else None

        try:
            if media_type == "video" and media_file:
                bot_instance.send_video(user_id, media_file, caption=t["welcome"], parse_mode="HTML", protect_content=protect, reply_markup=kb)
            elif media_type == "photo" and media_file:
                bot_instance.send_photo(user_id, media_file, caption=t["welcome"], parse_mode="HTML", protect_content=protect, reply_markup=kb)
            elif media_type == "animation" and media_file:
                bot_instance.send_animation(user_id, media_file, caption=t["welcome"], parse_mode="HTML", protect_content=protect, reply_markup=kb)
            else:
                bot_instance.send_message(user_id, t["welcome"], parse_mode="HTML", protect_content=protect, reply_markup=kb)
        except Exception as e:
            print(f"Error sending welcome via @{bot_uname}: {e}")

    @bot_instance.message_handler(commands=["start"])
    def start_cmd(message):
        parts = message.text.split(maxsplit=1)
        source_tag = parts[1].strip() if len(parts) > 1 else None
        send_welcome_message(message.chat.id, message.from_user.first_name, source_tag)

    @bot_instance.chat_join_request_handler()
    def join_req(request):
        if is_bot_paused(bot_uname):
            return
        if get_setting("auto_approve"):
            try:
                bot_instance.approve_chat_join_request(request.chat.id, request.from_user.id)
            except:
                pass
        send_welcome_message(request.from_user.id, request.from_user.first_name, "join_request")

    # --- لوحات تحكم الأدمن ---
    def get_admin_keyboard():
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📊 الإحصائيات والمصادر", callback_data="adm_stats"),
            types.InlineKeyboardButton("📢 إذاعة متقدمة", callback_data="adm_bc_start")
        )
        markup.add(
            types.InlineKeyboardButton("🤖 إدارة البوتات والتحكم", callback_data="adm_bots_hub"),
            types.InlineKeyboardButton("🎬 المحتوى والوسائط", callback_data="adm_media")
        )
        markup.add(
            types.InlineKeyboardButton("⚙️ الروابط والأسعار", callback_data="adm_settings"),
            types.InlineKeyboardButton("📝 تعديل النصوص", callback_data="adm_texts")
        )
        markup.add(
            types.InlineKeyboardButton("👁️ إظهار/إخفاء الأزرار", callback_data="adm_buttons_vis"),
            types.InlineKeyboardButton("🔒 الاشتراك الإجباري", callback_data="adm_fsub")
        )
        markup.add(
            types.InlineKeyboardButton("⏱️ التوقيت والسلوك", callback_data="adm_behavior"),
            types.InlineKeyboardButton("🔔 الإشعارات والرد الآلي", callback_data="adm_notify")
        )
        markup.add(
            types.InlineKeyboardButton("🛡️ الأمان والمشرفون", callback_data="adm_security"),
            types.InlineKeyboardButton("💾 البيانات والصيانة", callback_data="adm_data")
        )
        return markup

    @bot_instance.message_handler(commands=["admin"])
    def admin_panel(message):
        if message.chat.id == ADMIN_ID:
            clear_state(ADMIN_ID)
            st_icon = "🔴 متوقف مؤقتاً" if is_bot_paused(bot_uname) else "🟢 يعمل بنشاط"
            bot_instance.send_message(
                ADMIN_ID,
                f"🛠️ **لوحة التحكم السحابية الشاملة**\n"
                f"🤖 البوت الحالي: @{bot_uname} ({st_icon})\n"
                f"📡 البوتات النشطة بالسيرفر: `{len(active_bot_instances)}`",
                reply_markup=get_admin_keyboard(),
                parse_mode="Markdown",
                protect_content=True
            )

    # --- لوحة التحكم المركزية بجميع البوتات (تشغيل/إيقاف/تخصيص/حذف) ---
    def get_bots_hub_keyboard():
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("➕ إضافة توكن بوت احتياطي جديد", callback_data="clone_add"))

        # 1. البوت الأساسي
        if PRIMARY_BOT_USERNAME:
            p_paused = is_bot_paused(PRIMARY_BOT_USERNAME)
            p_online = PRIMARY_BOT_USERNAME in active_bot_instances
            p_status = "🔴 متوقف" if p_paused else ("🟢 يعمل" if p_online else "⚠️ غير متصل")
            markup.add(types.InlineKeyboardButton(
                f"👑 [الأساسي] @{PRIMARY_BOT_USERNAME} ({p_status}) - تحكم",
                callback_data=f"botmanage_{PRIMARY_BOT_USERNAME}"
            ))

        # 2. البوتات الاحتياطية من القاعدة
        for c in clones_col.find({}):
            uname = c.get("username", "Unknown")
            c_paused = is_bot_paused(uname)
            c_online = uname in active_bot_instances
            c_status = "🔴 متوقف" if c_paused else ("🟢 يعمل" if c_online else "⛔ محظور/مفصول")
            markup.add(types.InlineKeyboardButton(
                f"🤖 [احتياطي] @{uname} ({c_status}) - تحكم",
                callback_data=f"botmanage_{uname}"
            ))

        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home"))
        return markup

    def get_single_bot_manage_keyboard(target_uname):
        paused = is_bot_paused(target_uname)
        tog_btn_text = "▶️ تشغيل البوت الآن" if paused else "⏸️ إيقاف البوت مؤقتاً"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(tog_btn_text, callback_data=f"bottog_{target_uname}"),
            types.InlineKeyboardButton("📝 تعديل نص الترحيب لهذا البوت", callback_data=f"rem_welcome_text_{target_uname}"),
            types.InlineKeyboardButton("💎 تعديل نص VIP لهذا البوت", callback_data=f"rem_vip_text_{target_uname}"),
            types.InlineKeyboardButton("🔗 تعديل رابط المشاركة لهذا البوت", callback_data=f"rem_share_link_{target_uname}"),
            types.InlineKeyboardButton("🎬 تعديل وسائط الترحيب لهذا البوت", callback_data=f"rem_media_file_{target_uname}"),
            types.InlineKeyboardButton("🔄 استعادة الإعدادات العامة لهذا البوت", callback_data=f"remreset_{target_uname}")
        )
        if target_uname != PRIMARY_BOT_USERNAME:
            markup.add(types.InlineKeyboardButton("🗑️ حذف البوت نهائياً من القاعدة", callback_data=f"clone_del_{target_uname}"))
        markup.add(types.InlineKeyboardButton("🔙 رجوع لإدارة البوتات", callback_data="adm_bots_hub"))
        return markup

    def get_media_keyboard():
        m_type = get_setting("media_type", bot_uname)
        prot = "✅ مفعّلة" if get_setting("protect_content") else "❌ معطّلة"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"🔄 نوع الترحيب الحالي: [{m_type.upper()}]", callback_data="cycle_media_type"),
            types.InlineKeyboardButton("📤 رفع وسائط أو إرسال رابط URL", callback_data="set_media_file"),
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
            types.InlineKeyboardButton(f"💰 سعر VIP (الحالي: {get_setting('vip_price', bot_uname)})", callback_data="set_vip_price"),
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
            types.InlineKeyboardButton("🔄 استعادة نصوص البوت الافتراضية", callback_data="reset_bot_texts"),
            types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
        )
        return markup

    def get_buttons_vis_keyboard():
        def ic(k): return "✅ ظاهر" if get_setting(k) else "❌ مخفي"
        custom_cnt = len(get_setting("custom_buttons") or [])
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"زر المشاركة: {ic('show_btn_share')}", callback_data="tog_show_btn_share"),
            types.InlineKeyboardButton(f"زر التحقق: {ic('show_btn_verify')}", callback_data="tog_show_btn_verify"),
            types.InlineKeyboardButton(f"زر فتح VIP: {ic('show_btn_vip')}", callback_data="tog_show_btn_vip"),
            types.InlineKeyboardButton(f"زر الدفع بالنجوم: {ic('show_btn_pay_stars')}", callback_data="tog_show_btn_pay_stars"),
            types.InlineKeyboardButton(f"زر الدفع البديل: {ic('show_btn_pay_alt')}", callback_data="tog_show_btn_pay_alt"),
            types.InlineKeyboardButton("➕ إضافة زر رابط جديد", callback_data="cbtn_add_menu"),
            types.InlineKeyboardButton(f"🗑️ حذف زر مخصص (الحالي: {custom_cnt})", callback_data="cbtn_del_menu"),
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
            types.InlineKeyboardButton("📝 تعديل نص الاشتراك الإجباري", callback_data="set_fsub_text"),
            types.InlineKeyboardButton("🔘 تعديل نص زر الانضمام", callback_data="set_fsub_btn_join"),
            types.InlineKeyboardButton("✅ تعديل نص زر التحقق", callback_data="set_fsub_btn_check"),
            types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
        )
        return markup

    def get_behavior_keyboard():
        cd = get_setting("cooldown_hours")
        app_st = "✅ مفعّل" if get_setting("auto_approve") else "❌ معطّل"
        mnt_st = "🔴 مفعّل" if get_setting("maintenance_mode") else "🟢 معطّل"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"⏳ مدة قفل الترحيب/VIP: {cd} ساعة", callback_data="set_cooldown_hours"),
            types.InlineKeyboardButton(f"✅ القبول التلقائي لطلبات الانضمام: {app_st}", callback_data="tog_auto_approve"),
            types.InlineKeyboardButton(f"🚧 وضع الصيانة العام (كل البوتات): {mnt_st}", callback_data="tog_maintenance_mode"),
            types.InlineKeyboardButton("📝 تعديل رسالة الصيانة/الإيقاف", callback_data="set_maintenance_text"),
            types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
        )
        return markup

    def get_notify_keyboard():
        mode_map = {"all": "الكل", "new_only": "الجدد فقط", "off": "إيقاف"}
        n_mode = mode_map.get(get_setting("notify_mode"), "الكل")
        vip_n = "✅ مفعّل" if get_setting("notify_vip_click") else "❌ معطّل"
        ar_st = "✅ مفعّل" if get_setting("auto_reply_enabled") else "❌ معطّل"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"🔔 إشعارات الدخول: {n_mode}", callback_data="cycle_notify_mode"),
            types.InlineKeyboardButton(f"👑 تنبيه ضغط VIP: {vip_n}", callback_data="tog_notify_vip_click"),
            types.InlineKeyboardButton(f"🤖 الرد الآلي: {ar_st}", callback_data="tog_auto_reply_enabled"),
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
            types.InlineKeyboardButton(f"👮 إضافة مشرف مساعد ({subs_cnt})", callback_data="sec_add_sub"),
            types.InlineKeyboardButton("🗑️ إزالة مشرف مساعد", callback_data="sec_del_sub"),
            types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
        )
        return markup

    def get_data_keyboard():
        sp = get_setting("bc_sleep")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📤 تصدير نسخة احتياطية (JSON)", callback_data="adm_backup"),
            types.InlineKeyboardButton("📥 استعادة نسخة احتياطية", callback_data="adm_restore_ask"),
            types.InlineKeyboardButton("🧹 تنظيف صامت للمحظورين", callback_data="adm_clean_db"),
            types.InlineKeyboardButton(f"⚡ سرعة الإذاعة ({sp} ثانية)", callback_data="cycle_bc_sleep"),
            types.InlineKeyboardButton("📝 تعديل تذييل الإذاعة الثابت", callback_data="set_bc_footer"),
            types.InlineKeyboardButton("🔄 تصفير تواريخ المستخدمين", callback_data="confirm_reset_ask"),
            types.InlineKeyboardButton("⚠️ إعادة ضبط المصنع للإعدادات", callback_data="factory_reset_ask"),
            types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
        )
        return markup

    def get_bc_config_keyboard(session):
        pin_txt = "✅ تثبيت الرسالة: مفعّل" if session.get("pin") else "❌ تثبيت الرسالة: معطّل"
        btn_txt = f"✅ زر مرفق: {session.get('btn_text')}" if session.get("btn_text") else "➕ إضافة زر رابط للرسالة"
        del_val = session.get("auto_delete", 0)
        del_map = {0: "بدون حذف تلقائي", 3600: "حذف بعد 1 ساعة", 86400: "حذف بعد 24 ساعة"}
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(pin_txt, callback_data="bc_toggle_pin"),
            types.InlineKeyboardButton(btn_txt, callback_data="bc_add_btn"),
            types.InlineKeyboardButton(f"⏳ {del_map.get(del_val, 'بدون حذف')}", callback_data="bc_cycle_del"),
            types.InlineKeyboardButton("🚀 المتابعة لإرسال رسالة الإذاعة", callback_data="bc_ready_send"),
            types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_home")
        )
        return markup

    def run_advanced_broadcast(bc_message_id, session):
        now = datetime.now()
        segment = session.get("segment", "all")
        sleep_delay = float(get_setting("bc_sleep") or 0.06)

        if segment == "new_24h":
            query = {"joined_at": {"$gte": now - timedelta(hours=24)}}
            seg_name = "المستخدمين الجدد (24 ساعة)"
        elif segment == "vip_interested":
            query = {"clicked_vip": True}
            seg_name = "المهتمين بالـ VIP"
        else:
            query = {}
            seg_name = "جميع المشتركين"

        users = list(users_col.find(query, {"user_id": 1, "last_bot": 1}))
        total_users = len(users)
        count, deleted_count, fail_count = 0, 0, 0
        sent_records = []

        reply_markup = None
        if session.get("btn_text") and session.get("btn_url"):
            reply_markup = types.InlineKeyboardMarkup()
            reply_markup.add(types.InlineKeyboardButton(session["btn_text"], url=session["btn_url"]))

        status_msg = bot_instance.send_message(
            ADMIN_ID,
            f"⏳ **بدأت الإذاعة عبر @{bot_uname}**\n🎯 الفئة: `{seg_name}` ({total_users} مشترك)",
            parse_mode="Markdown"
        )

        footer = get_setting("bc_footer") or ""

        for index, u in enumerate(users):
            target_id = u.get("user_id")
            if not target_id or is_banned(target_id):
                continue

            sent = False
            while not sent:
                try:
                    copied = bot_instance.copy_message(
                        chat_id=target_id,
                        from_chat_id=ADMIN_ID,
                        message_id=bc_message_id,
                        reply_markup=reply_markup,
                        protect_content=bool(get_setting("protect_content"))
                    )
                    if footer:
                        try:
                            bot_instance.send_message(target_id, footer, parse_mode="HTML", disable_web_page_preview=True)
                        except:
                            pass
                    count += 1
                    sent = True
                    if session.get("auto_delete", 0) > 0:
                        sent_records.append((target_id, copied.message_id))
                    if session.get("pin"):
                        try:
                            bot_instance.pin_chat_message(target_id, copied.message_id)
                        except:
                            pass
                    time.sleep(sleep_delay)
                except ApiTelegramException as e:
                    if e.error_code == 429:
                        retry_after = int(e.result_json.get("parameters", {}).get("retry_after", 5))
                        time.sleep(retry_after + 1)
                    elif e.error_code in [400, 403]:
                        # يحذف السجل فقط إذا كان المستخدم مسجلاً على نفس البوت الذي يرسل الإذاعة
                        if u.get("last_bot") in [None, bot_uname]:
                            users_col.delete_one({"user_id": target_id})
                            deleted_count += 1
                        else:
                            fail_count += 1
                        sent = True
                    else:
                        fail_count += 1
                        sent = True
                except:
                    fail_count += 1
                    sent = True

            if (index + 1) % 250 == 0:
                try:
                    bot_instance.edit_message_text(
                        f"⏳ جاري الإذاعة... ({index + 1}/{total_users})\n✅ نجح: `{count}` | 🗑️ حُذف: `{deleted_count}`",
                        chat_id=ADMIN_ID, message_id=status_msg.message_id, parse_mode="Markdown"
                    )
                except:
                    pass

        bot_instance.send_message(
            ADMIN_ID,
            f"📊 **تقرير الإذاعة (@{bot_uname}):**\n✅ نجح: `{count}`\n🗑️ حُذف: `{deleted_count}`\n❌ فشل/بوت آخر: `{fail_count}`",
            parse_mode="Markdown"
        )

        if session.get("auto_delete", 0) > 0 and sent_records:
            def schedule_deletion(records, delay):
                time.sleep(delay)
                for c_id, m_id in records:
                    try:
                        bot_instance.delete_message(c_id, m_id)
                        time.sleep(0.05)
                    except:
                        pass
            Thread(target=schedule_deletion, args=(sent_records, session["auto_delete"]), daemon=True).start()

    def run_silent_db_clean():
        users = list(users_col.find({"last_bot": {"$in": [None, bot_uname]}}, {"user_id": 1}))
        deleted, active = 0, 0
        bot_instance.send_message(ADMIN_ID, f"🧹 جاري فحص `{len(users)}` سجل تابع لـ @{bot_uname} بصمت...", parse_mode="Markdown")
        for u in users:
            uid = u.get("user_id")
            if not uid:
                users_col.delete_one({"_id": u["_id"]})
                deleted += 1
                continue
            try:
                bot_instance.send_chat_action(uid, "typing")
                active += 1
                time.sleep(0.05)
            except ApiTelegramException as e:
                if e.error_code == 429:
                    time.sleep(int(e.result_json.get("parameters", {}).get("retry_after", 5)) + 1)
                elif e.error_code in [400, 403]:
                    users_col.delete_one({"user_id": uid})
                    deleted += 1
            except:
                pass
        bot_instance.send_message(ADMIN_ID, f"✅ **اكتمل التنظيف (@{bot_uname})!**\n🟢 نشطون: `{active}`\n🗑️ أُزيلوا: `{deleted}`", parse_mode="Markdown")

    # --- معالجة الأزرار التفاعلية ---
    @bot_instance.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        if is_banned(user_id):
            return

        if (is_bot_paused(bot_uname) or get_setting("maintenance_mode")) and not is_admin_or_sub(user_id):
            bot_instance.answer_callback_query(call.id, "⚠️ البوت متوقف مؤقتاً للصيانة.", show_alert=True)
            return

        t = get_texts()

        if call.data == "check_fsub":
            if check_force_sub(user_id):
                bot_instance.answer_callback_query(call.id, "✅ תודה שהצטרפת!")
                try:
                    bot_instance.delete_message(chat_id, call.message.message_id)
                except:
                    pass
                send_welcome_message(user_id, call.from_user.first_name)
            else:
                bot_instance.answer_callback_query(call.id, "⚠️ עדיין לא הצטרפת לערוץ!", show_alert=True)
            return

        if call.data == "check_share":
            if not check_force_sub(user_id):
                send_force_sub_message(chat_id)
                return
            bot_instance.answer_callback_query(call.id, t["share_alert"], show_alert=True)

        elif call.data == "show_vip_info":
            if not check_force_sub(user_id):
                send_force_sub_message(chat_id)
                return

            now = datetime.now()
            cooldown = int(get_setting("cooldown_hours") or 0)

            if not is_admin_or_sub(user_id):
                user = users_col.find_one({"user_id": user_id})
                users_col.update_one({"user_id": user_id}, {"$set": {"clicked_vip": True, "last_vip_click": now, "last_bot": bot_uname}}, upsert=True)
                log_metric("vip_clicks")

                if get_setting("notify_vip_click"):
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("📩 راسله الآن", callback_data=f"reply_{user_id}_{bot_uname}"))
                    notify_admin_central(
                        f"👑 **اهتمام VIP جديد!** | عبر: @{bot_uname}\n"
                        f"👤 المستخدم: {call.from_user.first_name} (`{user_id}`)",
                        reply_markup=m,
                        fallback_bot=bot_instance
                    )

                if cooldown > 0 and user and user.get("last_vip_request"):
                    if now - user.get("last_vip_request") < timedelta(hours=cooldown):
                        bot_instance.answer_callback_query(call.id, t["vip_already"], show_alert=True)
                        return

            try:
                bot_instance.answer_callback_query(call.id)
            except:
                pass

            vip_markup = types.InlineKeyboardMarkup(row_width=1)
            if get_setting("show_btn_pay_stars"):
                vip_markup.add(types.InlineKeyboardButton(t["btn_pay_stars"], url=t["stars_url"]))
            if get_setting("show_btn_pay_alt"):
                vip_markup.add(types.InlineKeyboardButton(t["btn_pay_alt"], url=t["alt_url"]))

            for cb in (get_setting("custom_buttons") or []):
                if cb.get("target") == "vip" and cb.get("text") and cb.get("url"):
                    vip_markup.add(types.InlineKeyboardButton(cb["text"], url=cb["url"]))

            bot_instance.send_message(
                chat_id, t["vip_text"], parse_mode="HTML",
                reply_markup=vip_markup if vip_markup.keyboard else None,
                protect_content=bool(get_setting("protect_content"))
            )
            if not is_admin_or_sub(user_id):
                users_col.update_one({"user_id": user_id}, {"$set": {"last_vip_request": now}}, upsert=True)

        # الرد الذكي العابر للبوتات
        elif is_admin_or_sub(user_id) and call.data.startswith("reply_"):
            parts = call.data.split("_", 2)
            target_id = parts[1]
            via_bot = parts[2] if len(parts) > 2 else bot_uname
            set_state(user_id, "reply_user", {"target_id": target_id, "via_bot": via_bot})
            bot_instance.answer_callback_query(call.id, "✅ أرسل الرد الآن")
            bot_instance.send_message(user_id, f"✍️ اكتب الرد للمستخدم `{target_id}` (سيُرسل عبر @{via_bot}):", parse_mode="Markdown")

        elif user_id == ADMIN_ID and call.data.startswith("quickban_"):
            target_id = int(call.data.split("_")[1])
            banned = get_setting("banned_users") or []
            if target_id not in banned:
                banned.append(target_id)
                update_setting("banned_users", banned)
            bot_instance.answer_callback_query(call.id, f"🚫 تم حظر {target_id}", show_alert=True)

        elif user_id == ADMIN_ID:
            if call.data == "adm_home":
                clear_state(ADMIN_ID)
                st_icon = "🔴 متوقف مؤقتاً" if is_bot_paused(bot_uname) else "🟢 يعمل بنشاط"
                bot_instance.edit_message_text(
                    f"🛠️ **لوحة التحكم السحابية الشاملة**\n🤖 البوت الحالي: @{bot_uname} ({st_icon})",
                    chat_id, call.message.message_id, reply_markup=get_admin_keyboard(), parse_mode="Markdown"
                )

            elif call.data == "adm_stats":
                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                today_doc = analytics_col.find_one({"date": today_str}) or {}
                total = users_col.count_documents({})
                new_24h = users_col.count_documents({"joined_at": {"$gte": now - timedelta(hours=24)}})
                vip_clicks = users_col.count_documents({"clicked_vip": True})

                # توزيع المشتركين على البوتات
                bot_pipe = [{"$group": {"_id": "$last_bot", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
                bot_stats = list(users_col.aggregate(bot_pipe))
                bot_lines = "\n".join([f"  • @{b['_id'] or 'غير محدد'}: `{b['count']}`" for b in bot_stats])

                # أعلى مصادر الزيارات
                src_pipe = [{"$group": {"_id": "$source_tag", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 5}]
                sources = list(users_col.aggregate(src_pipe))
                src_lines = "\n".join([f"  • `{s['_id'] or 'direct'}`: `{s['count']}`" for s in sources])

                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home"))
                bot_instance.edit_message_text(
                    f"📊 **إحصائيات السحابة (MongoDB):**\n\n"
                    f"👥 إجمالي المشتركين: `{total}`\n"
                    f"🆕 مشتركو آخر 24 ساعة: `{new_24h}`\n"
                    f"👑 مهتمون بالـ VIP: `{vip_clicks}`\n"
                    f"📅 نشاط اليوم: `{today_doc.get('new_users', 0)}` جديد | `{today_doc.get('vip_clicks', 0)}` نقرة VIP\n\n"
                    f"🤖 **توزيع المشتركين حسب البوت:**\n{bot_lines}\n\n"
                    f"🔗 **أعلى مصادر الزيارات:**\n{src_lines}",
                    chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown"
                )

            # --- إدارة البوتات عن بُعد (تشغيل / إيقاف / تخصيص) ---
            elif call.data == "adm_bots_hub":
                bot_instance.edit_message_text(
                    "🤖 **مركز التحكم بالبوتات السحابية**\n"
                    "اختر أي بوت لتشغيله، إيقافه مؤقتاً، أو تعديل نصوصه وروابطه عن بُعد:",
                    chat_id, call.message.message_id, reply_markup=get_bots_hub_keyboard(), parse_mode="Markdown"
                )

            elif call.data.startswith("botmanage_"):
                target_uname = call.data.replace("botmanage_", "")
                paused = is_bot_paused(target_uname)
                online = target_uname in active_bot_instances
                st_str = "🔴 متوقف مؤقتاً" if paused else ("🟢 يعمل الآن" if online else "⛔ غير متصل / محظور")
                bot_instance.edit_message_text(
                    f"⚙️ **إعدادات وتحكم البوت: @{target_uname}**\n"
                    f"📡 الحالة الحالية: **{st_str}**",
                    chat_id, call.message.message_id,
                    reply_markup=get_single_bot_manage_keyboard(target_uname),
                    parse_mode="Markdown"
                )

            elif call.data.startswith("bottog_"):
                target_uname = call.data.replace("bottog_", "")
                now_running = toggle_bot_pause(target_uname)
                msg_alert = f"▶️ تم تشغيل @{target_uname} بنجاح!" if now_running else f"⏸️ تم إيقاف @{target_uname} مؤقتاً!"
                bot_instance.answer_callback_query(call.id, msg_alert, show_alert=True)
                st_str = "🟢 يعمل الآن" if now_running else "🔴 متوقف مؤقتاً"
                bot_instance.edit_message_text(
                    f"⚙️ **إعدادات وتحكم البوت: @{target_uname}**\n"
                    f"📡 الحالة الحالية: **{st_str}**",
                    chat_id, call.message.message_id,
                    reply_markup=get_single_bot_manage_keyboard(target_uname),
                    parse_mode="Markdown"
                )

            elif call.data.startswith("rem_"):
                # الصيغة: rem_<key>_<target_uname>
                rest = call.data[4:]
                for k in PER_BOT_KEYS:
                    if rest.startswith(k + "_"):
                        target_uname = rest[len(k) + 1:]
                        set_state(ADMIN_ID, "remote_edit", {"key": k, "target_bot": target_uname})
                        bot_instance.answer_callback_query(call.id)
                        bot_instance.send_message(
                            ADMIN_ID,
                            f"✍️ أرسل القيمة الجديدة لـ `{k}` الخاصة بالبوت **@{target_uname}**:",
                            parse_mode="Markdown"
                        )
                        break

            elif call.data.startswith("remreset_"):
                target_uname = call.data.replace("remreset_", "")
                reset_bot_custom_config(target_uname)
                bot_instance.answer_callback_query(call.id, f"✅ تمت استعادة إعدادات @{target_uname} العامة!", show_alert=True)

            elif call.data == "clone_add":
                set_state(ADMIN_ID, "add_clone_token")
                bot_instance.answer_callback_query(call.id)
                bot_instance.send_message(ADMIN_ID, "🤖 أرسل الآن **توكن البوت الجديد (Bot Token)** من @BotFather لتشغيله فوراً:")

            elif call.data.startswith("clone_del_"):
                uname = call.data.replace("clone_del_", "")
                clones_col.delete_one({"username": uname})
                reset_bot_custom_config(uname)
                bot_instance.answer_callback_query(call.id, f"🗑️ تم حذف @{uname} نهائياً.", show_alert=True)
                bot_instance.edit_message_text(
                    "🤖 **مركز التحكم بالبوتات السحابية**",
                    chat_id, call.message.message_id, reply_markup=get_bots_hub_keyboard(), parse_mode="Markdown"
                )

            elif call.data == "adm_media":
                bot_instance.edit_message_text(f"🎬 **إعدادات المحتوى والوسائط لـ (@{bot_uname})**\n⚠️ استخدم رابط URL مباشر للميديا لضمان عملها على كل البوتات.", chat_id, call.message.message_id, reply_markup=get_media_keyboard(), parse_mode="Markdown")
            elif call.data == "adm_settings":
                bot_instance.edit_message_text(f"⚙️ **إعدادات الروابط والأسعار لـ (@{bot_uname})**", chat_id, call.message.message_id, reply_markup=get_settings_keyboard(), parse_mode="Markdown")
            elif call.data == "adm_texts":
                bot_instance.edit_message_text(f"📝 **تعديل النصوص المستقلة لـ (@{bot_uname})**", chat_id, call.message.message_id, reply_markup=get_texts_keyboard(), parse_mode="Markdown")
            elif call.data == "reset_bot_texts":
                reset_bot_custom_config(bot_uname)
                bot_instance.answer_callback_query(call.id, f"✅ تمت استعادة نصوص @{bot_uname}!", show_alert=True)
            elif call.data == "adm_buttons_vis":
                bot_instance.edit_message_text("👁️ **إدارة الأزرار**", chat_id, call.message.message_id, reply_markup=get_buttons_vis_keyboard(), parse_mode="Markdown")
            elif call.data == "adm_fsub":
                bot_instance.edit_message_text("🔒 **إعدادات الاشتراك الإجباري**", chat_id, call.message.message_id, reply_markup=get_fsub_keyboard(), parse_mode="Markdown")
            elif call.data == "adm_behavior":
                bot_instance.edit_message_text("⏱️ **إعدادات التوقيت والسلوك**", chat_id, call.message.message_id, reply_markup=get_behavior_keyboard(), parse_mode="Markdown")
            elif call.data == "adm_notify":
                bot_instance.edit_message_text("🔔 **إعدادات الإشعارات والرد الآلي**", chat_id, call.message.message_id, reply_markup=get_notify_keyboard(), parse_mode="Markdown")
            elif call.data == "adm_security":
                bot_instance.edit_message_text("🛡️ **إعدادات الأمان والمشرفين**", chat_id, call.message.message_id, reply_markup=get_security_keyboard(), parse_mode="Markdown")
            elif call.data == "adm_data":
                bot_instance.edit_message_text("💾 **إدارة البيانات والصيانة**", chat_id, call.message.message_id, reply_markup=get_data_keyboard(), parse_mode="Markdown")

            # الأزرار المخصصة
            elif call.data == "cbtn_add_menu":
                m = types.InlineKeyboardMarkup(row_width=1)
                m.add(
                    types.InlineKeyboardButton("👋 إضافة زر في الترحيب", callback_data="cbtn_target_welcome"),
                    types.InlineKeyboardButton("👑 إضافة زر في VIP", callback_data="cbtn_target_vip"),
                    types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_buttons_vis")
                )
                bot_instance.edit_message_text("➕ اختر مكان الزر:", chat_id, call.message.message_id, reply_markup=m)

            elif call.data in ["cbtn_target_welcome", "cbtn_target_vip"]:
                target = "welcome" if call.data == "cbtn_target_welcome" else "vip"
                set_state(ADMIN_ID, f"cbtn_add_{target}")
                bot_instance.answer_callback_query(call.id)
                bot_instance.send_message(ADMIN_ID, "🔗 أرسل **نص الزر | الرابط**\nمثال: `🎬 عينة | https://t.me/YourChannel`", parse_mode="Markdown")

            elif call.data == "cbtn_del_menu":
                cbtns = get_setting("custom_buttons") or []
                if not cbtns:
                    bot_instance.answer_callback_query(call.id, "⚠️ لا توجد أزرار مخصصة.", show_alert=True)
                    return
                m = types.InlineKeyboardMarkup(row_width=1)
                for idx, cb in enumerate(cbtns):
                    m.add(types.InlineKeyboardButton(f"🗑️ {cb.get('text')}", callback_data=f"cbtn_del_{idx}"))
                m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_buttons_vis"))
                bot_instance.edit_message_text("🗑️ اضغط لحذف الزر:", chat_id, call.message.message_id, reply_markup=m)

            elif call.data.startswith("cbtn_del_"):
                idx = int(call.data.split("_")[-1])
                cbtns = get_setting("custom_buttons") or []
                if 0 <= idx < len(cbtns):
                    cbtns.pop(idx)
                    update_setting("custom_buttons", cbtns)
                bot_instance.edit_message_text("👁️ **إدارة الأزرار**", chat_id, call.message.message_id, reply_markup=get_buttons_vis_keyboard(), parse_mode="Markdown")

            # التبديلات السريعة
            elif call.data.startswith("tog_"):
                key = call.data.replace("tog_", "")
                update_setting(key, not bool(get_setting(key)))
                bot_instance.answer_callback_query(call.id, "✅ تم التحديث!")
                if key.startswith("show_btn_"):
                    bot_instance.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_buttons_vis_keyboard())
                elif key == "protect_content":
                    bot_instance.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_media_keyboard())
                elif key == "fsub_enabled":
                    bot_instance.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_fsub_keyboard())
                elif key in ["auto_approve", "maintenance_mode"]:
                    bot_instance.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_behavior_keyboard())
                elif key in ["notify_vip_click", "auto_reply_enabled"]:
                    bot_instance.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_notify_keyboard())

            elif call.data == "cycle_media_type":
                order = ["video", "photo", "animation", "text"]
                curr = get_setting("media_type", bot_uname)
                nxt = order[(order.index(curr) + 1) % len(order)] if curr in order else "video"
                update_setting("media_type", nxt, bot_uname)
                bot_instance.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_media_keyboard())

            elif call.data == "cycle_notify_mode":
                order = ["all", "new_only", "off"]
                curr = get_setting("notify_mode")
                nxt = order[(order.index(curr) + 1) % len(order)] if curr in order else "all"
                update_setting("notify_mode", nxt)
                bot_instance.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_notify_keyboard())

            elif call.data == "cycle_bc_sleep":
                order = [0.06, 0.1, 0.2]
                curr = float(get_setting("bc_sleep") or 0.06)
                nxt = order[(order.index(curr) + 1) % len(order)] if curr in order else 0.06
                update_setting("bc_sleep", nxt)
                bot_instance.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_data_keyboard())

            elif call.data.startswith("set_"):
                key = call.data.replace("set_", "")
                set_state(ADMIN_ID, f"edit_{key}")
                bot_instance.answer_callback_query(call.id)
                scope_note = f" (للبوت @{bot_uname} فقط)" if key in PER_BOT_KEYS else " (عام لجميع البوتات)"
                bot_instance.send_message(ADMIN_ID, f"✍️ أرسل القيمة الجديدة لـ `{key}`{scope_note}:", parse_mode="Markdown")

            elif call.data in ["sec_ban_user", "sec_unban_user", "sec_add_sub", "sec_del_sub"]:
                set_state(ADMIN_ID, call.data)
                bot_instance.answer_callback_query(call.id)
                bot_instance.send_message(ADMIN_ID, "🆔 أرسل رقم الـ ID الآن:")

            elif call.data == "adm_backup":
                bot_instance.answer_callback_query(call.id, "⏳ جاري التجهيز...")
                all_users = list(users_col.find({}, {"_id": 0}))
                for u in all_users:
                    for k, v in u.items():
                        if isinstance(v, datetime):
                            u[k] = v.isoformat()
                bio = io.BytesIO(json.dumps(all_users, ensure_ascii=False, indent=2).encode("utf-8"))
                bio.name = f"backup_{datetime.now().strftime('%Y_%m_%d')}.json"
                bot_instance.send_document(ADMIN_ID, bio, caption=f"💾 نسخة احتياطية (`{len(all_users)}` سجل)", parse_mode="Markdown")

            elif call.data == "adm_restore_ask":
                set_state(ADMIN_ID, "restore_json")
                bot_instance.answer_callback_query(call.id)
                bot_instance.send_message(ADMIN_ID, "📥 أرسل ملف `.json` الآن:")

            elif call.data == "adm_clean_db":
                bot_instance.answer_callback_query(call.id, "🧹 بدأ التنظيف...")
                Thread(target=run_silent_db_clean, daemon=True).start()

            elif call.data == "confirm_reset_ask":
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("✅ نعم، صفّر", callback_data="confirm_reset"), types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_data"))
                bot_instance.edit_message_text("⚠️ تأكيد تصفير تواريخ المستخدمين؟", chat_id, call.message.message_id, reply_markup=m)

            elif call.data == "confirm_reset":
                users_col.update_many({}, {"$unset": {"last_welcome": "", "last_vip_request": ""}})
                bot_instance.edit_message_text("✅ تم التصفير.", chat_id, call.message.message_id, reply_markup=get_data_keyboard())

            elif call.data == "factory_reset_ask":
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("⚠️ نعم، استعادة", callback_data="factory_reset_do"), types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_data"))
                bot_instance.edit_message_text("⚠️ استعادة الإعدادات الافتراضية؟", chat_id, call.message.message_id, reply_markup=m)

            elif call.data == "factory_reset_do":
                settings_col.delete_one({"_id": "bot_config"})
                reload_settings_cache()
                bot_instance.edit_message_text("✅ تمت الاستعادة!", chat_id, call.message.message_id, reply_markup=get_admin_keyboard())

            # الإذاعة المتقدمة المحفوظة في MongoDB
            elif call.data == "adm_bc_start":
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(
                    types.InlineKeyboardButton("👥 جميع المشتركين", callback_data="bc_seg_all"),
                    types.InlineKeyboardButton("🆕 المشتركون الجدد (24 ساعة)", callback_data="bc_seg_new_24h"),
                    types.InlineKeyboardButton("👑 المهتمون بالـ VIP فقط", callback_data="bc_seg_vip_interested"),
                    types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
                )
                bot_instance.edit_message_text("📢 **اختر الفئة المستهدفة:**", chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

            elif call.data.startswith("bc_seg_"):
                seg = call.data.replace("bc_seg_", "")
                sess = {"segment": seg, "pin": False, "btn_text": None, "btn_url": None, "auto_delete": 0}
                set_state(ADMIN_ID, "bc_config", sess)
                bot_instance.edit_message_text("🎛️ **خيارات الإذاعة المتقدمة:**", chat_id, call.message.message_id, reply_markup=get_bc_config_keyboard(sess), parse_mode="Markdown")

            elif call.data in ["bc_toggle_pin", "bc_cycle_del", "bc_add_btn", "bc_ready_send"]:
                st = get_state(ADMIN_ID)
                if not st or not st.get("data"):
                    return
                sess = st["data"]
                if call.data == "bc_toggle_pin":
                    sess["pin"] = not sess.get("pin", False)
                    set_state(ADMIN_ID, "bc_config", sess)
                    bot_instance.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_bc_config_keyboard(sess))
                elif call.data == "bc_cycle_del":
                    curr = sess.get("auto_delete", 0)
                    sess["auto_delete"] = 3600 if curr == 0 else (86400 if curr == 3600 else 0)
                    set_state(ADMIN_ID, "bc_config", sess)
                    bot_instance.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_bc_config_keyboard(sess))
                elif call.data == "bc_add_btn":
                    set_state(ADMIN_ID, "bc_wait_btn", sess)
                    bot_instance.answer_callback_query(call.id)
                    bot_instance.send_message(ADMIN_ID, "🔗 أرسل `نص الزر | الرابط`:", parse_mode="Markdown")
                elif call.data == "bc_ready_send":
                    set_state(ADMIN_ID, "bc_wait_msg", sess)
                    bot_instance.answer_callback_query(call.id)
                    bot_instance.send_message(ADMIN_ID, "📨 **أرسل الآن رسالة الإذاعة:**", parse_mode="Markdown")

    # --- معالجة رسائل الأدمن ---
    @bot_instance.message_handler(func=lambda message: is_admin_or_sub(message.chat.id), content_types=["text", "photo", "video", "animation", "document", "voice", "audio"])
    def handle_admin_messages(message):
        uid = message.chat.id
        st_doc = get_state(uid)

        if uid == ADMIN_ID and st_doc:
            state = st_doc.get("state")
            data = st_doc.get("data", {})

            # التعديل عن بُعد لأي بوت من لوحة التحكم
            if state == "remote_edit":
                clear_state(ADMIN_ID)
                key = data.get("key")
                target_bot = data.get("target_bot")
                if key == "media_file":
                    if message.content_type == "video":
                        update_setting("media_file", message.video.file_id, target_bot)
                        update_setting("media_type", "video", target_bot)
                    elif message.content_type == "photo":
                        update_setting("media_file", message.photo[-1].file_id, target_bot)
                        update_setting("media_type", "photo", target_bot)
                    elif message.content_type == "animation":
                        update_setting("media_file", message.animation.file_id, target_bot)
                        update_setting("media_type", "animation", target_bot)
                    elif message.content_type == "text":
                        update_setting("media_file", message.text.strip(), target_bot)
                elif message.content_type == "text":
                    html_keys = ["welcome_text", "vip_text"]
                    val = extract_html_with_custom_emojis(message) if key in html_keys else message.text.strip()
                    update_setting(key, val, target_bot)

                bot_instance.reply_to(
                    message,
                    f"✅ تم تحديث `{key}` للبوت **@{target_bot}** بنجاح!",
                    parse_mode="Markdown",
                    reply_markup=get_single_bot_manage_keyboard(target_bot)
                )
                return

            # إضافة بوت احتياطي جديد وتشغيله فوراً في حلقة مستقلة
            if state == "add_clone_token" and message.content_type == "text":
                new_token = message.text.strip()
                clear_state(ADMIN_ID)
                try:
                    test_bot = telebot.TeleBot(new_token)
                    info = test_bot.get_me()
                    clones_col.update_one(
                        {"username": info.username},
                        {"$set": {"token": new_token, "username": info.username, "added_at": datetime.now()}},
                        upsert=True
                    )
                    Thread(target=launch_bot_polling, args=(new_token, False), daemon=True).start()
                    bot_instance.reply_to(message, f"🚀 تم حفظ وتشغيل البوت الاحتياطي **@{info.username}** بنجاح في خيط مستقل!", parse_mode="Markdown", reply_markup=get_bots_hub_keyboard())
                except Exception as e:
                    bot_instance.reply_to(message, f"❌ التوكن غير صالح أو حدث خطأ: `{e}`", parse_mode="Markdown")
                return

            if state in ["cbtn_add_welcome", "cbtn_add_vip"] and message.content_type == "text":
                if "|" not in message.text:
                    bot_instance.reply_to(message, "⚠️ استخدم `|` بين النص والرابط.")
                    return
                btn_text, btn_url = [x.strip() for x in message.text.split("|", 1)]
                clear_state(ADMIN_ID)
                target = "welcome" if state == "cbtn_add_welcome" else "vip"
                cbtns = get_setting("custom_buttons") or []
                cbtns.append({"target": target, "text": btn_text, "url": btn_url})
                update_setting("custom_buttons", cbtns)
                bot_instance.reply_to(message, f"✅ تمت إضافة **{btn_text}**!", parse_mode="Markdown", reply_markup=get_buttons_vis_keyboard())
                return

            if state == "edit_media_file":
                clear_state(ADMIN_ID)
                if message.content_type == "video":
                    update_setting("media_file", message.video.file_id, bot_uname)
                    update_setting("media_type", "video", bot_uname)
                elif message.content_type == "photo":
                    update_setting("media_file", message.photo[-1].file_id, bot_uname)
                    update_setting("media_type", "photo", bot_uname)
                elif message.content_type == "animation":
                    update_setting("media_file", message.animation.file_id, bot_uname)
                    update_setting("media_type", "animation", bot_uname)
                elif message.content_type == "text":
                    update_setting("media_file", message.text.strip(), bot_uname)
                bot_instance.reply_to(message, f"✅ تم حفظ الوسائط للبوت (@{bot_uname})!", reply_markup=get_media_keyboard())
                return

            if state == "restore_json" and message.content_type == "document":
                clear_state(ADMIN_ID)
                try:
                    file_info = bot_instance.get_file(message.document.file_id)
                    records = json.loads(bot_instance.download_file(file_info.file_path).decode("utf-8"))
                    restored = 0
                    for r in records:
                        if "user_id" in r:
                            for dt_key in ["joined_at", "last_welcome", "last_vip_request", "last_vip_click"]:
                                if isinstance(r.get(dt_key), str):
                                    try: r[dt_key] = datetime.fromisoformat(r[dt_key])
                                    except: pass
                            users_col.update_one({"user_id": r["user_id"]}, {"$set": r}, upsert=True)
                            restored += 1
                    bot_instance.reply_to(message, f"✅ تمت استعادة `{restored}` سجل!", parse_mode="Markdown", reply_markup=get_admin_keyboard())
                except Exception as e:
                    bot_instance.reply_to(message, f"❌ خطأ: {e}")
                return

            if state in ["sec_ban_user", "sec_unban_user", "sec_add_sub", "sec_del_sub"] and message.content_type == "text":
                clear_state(ADMIN_ID)
                try:
                    target_uid = int(message.text.strip())
                    if state == "sec_ban_user":
                        lst = get_setting("banned_users") or []
                        if target_uid not in lst: lst.append(target_uid)
                        update_setting("banned_users", lst)
                    elif state == "sec_unban_user":
                        update_setting("banned_users", [x for x in (get_setting("banned_users") or []) if x != target_uid])
                    elif state == "sec_add_sub":
                        lst = get_setting("sub_admins") or []
                        if target_uid not in lst: lst.append(target_uid)
                        update_setting("sub_admins", lst)
                    elif state == "sec_del_sub":
                        update_setting("sub_admins", [x for x in (get_setting("sub_admins") or []) if x != target_uid])
                    bot_instance.reply_to(message, "✅ تم التحديث!", reply_markup=get_security_keyboard())
                except:
                    bot_instance.reply_to(message, "⚠️ أرسل ID صحيح.")
                return

            if state.startswith("edit_") and message.content_type == "text":
                clear_state(ADMIN_ID)
                key = state.replace("edit_", "")
                html_keys = ["welcome_text", "vip_text", "fsub_text", "maintenance_text", "auto_reply_text", "bc_footer"]
                val = extract_html_with_custom_emojis(message) if key in html_keys else message.text.strip()
                if key == "cooldown_hours":
                    val = int(val) if val.isdigit() else 24
                elif key == "bc_footer" and val == "حذف":
                    val = ""

                target_bot = bot_uname if key in PER_BOT_KEYS else None
                update_setting(key, val, target_bot)

                saved_msg = f"✅ تم الحفظ في MongoDB للبوت (@{bot_uname}) فقط!" if target_bot else "✅ تم الحفظ في MongoDB لجميع البوتات!"
                bot_instance.reply_to(message, saved_msg, reply_markup=get_admin_keyboard())
                return

            if state == "bc_wait_btn" and message.content_type == "text":
                if "|" in message.text:
                    parts = message.text.split("|", 1)
                    data["btn_text"], data["btn_url"] = parts[0].strip(), parts[1].strip()
                    set_state(ADMIN_ID, "bc_config", data)
                    bot_instance.send_message(ADMIN_ID, "✅ تم إضافة الزر!", reply_markup=get_bc_config_keyboard(data))
                return

            if state == "bc_wait_msg":
                clear_state(ADMIN_ID)
                Thread(target=run_advanced_broadcast, args=(message.message_id, data), daemon=True).start()
                return

            # الرد الذكي العابر للبوتات
            if state == "reply_user":
                clear_state(uid)
                target_id = data.get("target_id")
                via_bot_uname = data.get("via_bot", bot_uname)
                sender_instance = active_bot_instances.get(via_bot_uname) or bot_instance

                try:
                    if sender_instance == bot_instance:
                        sender_instance.copy_message(
                            chat_id=target_id, from_chat_id=uid, message_id=message.message_id,
                            protect_content=bool(get_setting("protect_content"))
                        )
                    else:
                        # تمرير الرسالة للبوت الآخر ليرسلها هو للعميل
                        if message.content_type == "text":
                            sender_instance.send_message(target_id, message.html_text, parse_mode="HTML", protect_content=bool(get_setting("protect_content")))
                        else:
                            fwd = sender_instance.forward_message(uid, uid, message.message_id)
                            sender_instance.copy_message(target_id, uid, fwd.message_id, protect_content=bool(get_setting("protect_content")))
                            try: sender_instance.delete_message(uid, fwd.message_id)
                            except: pass

                    bot_instance.reply_to(message, f"✅ تم إرسال الرد إلى `{target_id}` عبر @{via_bot_uname}!", parse_mode="Markdown")
                except Exception as e:
                    bot_instance.reply_to(message, f"❌ فشل الإرسال: {e}")
                return

        if uid == ADMIN_ID and message.reply_to_message and message.content_type == "text" and (message.text in ["/bc", "/broadcast", "إذاعة", "اذاعة"]):
            quick_session = {"segment": "all", "pin": False, "btn_text": None, "btn_url": None, "auto_delete": 0}
            Thread(target=run_advanced_broadcast, args=(message.reply_to_message.message_id, quick_session), daemon=True).start()

    # --- توجيه رسائل الدعم من المستخدمين إلى غرفة العمليات المركزية ---
    @bot_instance.message_handler(func=lambda message: not is_admin_or_sub(message.chat.id), content_types=["text", "photo", "video", "animation", "document", "voice", "audio"])
    def forward_user_msg(message):
        uid = message.chat.id
        if is_banned(uid):
            return
        if is_bot_paused(bot_uname) or get_setting("maintenance_mode"):
            try: bot_instance.send_message(uid, get_setting("maintenance_text"), parse_mode="HTML")
            except: pass
            return
        if not check_force_sub(uid):
            send_force_sub_message(uid)
            return
        if get_setting("auto_reply_enabled"):
            try: bot_instance.reply_to(message, get_setting("auto_reply_text"), parse_mode="HTML", protect_content=bool(get_setting("protect_content")))
            except: pass

        # إرسال تنبيه مع زر رد مباشر في البوت الأساسي
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📩 رد", callback_data=f"reply_{uid}_{bot_uname}"),
            types.InlineKeyboardButton("🚫 حظر", callback_data=f"quickban_{uid}")
        )
        msg_preview = message.text if message.content_type == "text" else f"[{message.content_type.upper()}]"
        notify_admin_central(
            f"💬 **رسالة دعم جديدة** | عبر: @{bot_uname}\n"
            f"👤 من: {message.from_user.first_name} (`{uid}`)\n"
            f"📝 المحتوى: {msg_preview}",
            reply_markup=markup,
            fallback_bot=bot_instance
        )
        # إذا كان هناك وسائط مرفقة، نوجّهها أيضاً في نفس البوت
        if message.content_type != "text":
            try:
                bot_instance.forward_message(ADMIN_ID, uid, message.message_id)
            except:
                pass

# --- حلقة التشغيل المستقلة والمحمية لكل بوت مع تنبيه الطوارئ ---
def launch_bot_polling(token_str, is_primary=False):
    global PRIMARY_BOT_USERNAME
    bot_uname = None
    while True:
        try:
            bot_instance = telebot.TeleBot(token_str, threaded=True, num_threads=6)
            bot_instance.remove_webhook()
            info = bot_instance.get_me()
            bot_uname = info.username
            if is_primary:
                PRIMARY_BOT_USERNAME = bot_uname
            active_bot_instances[bot_uname] = bot_instance
            print(f"🚀 بدأ تشغيل البوت بنجاح: @{bot_uname}")
            register_bot_handlers(bot_instance, bot_uname)
            bot_instance.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except ApiTelegramException as e:
            if bot_uname and bot_uname in active_bot_instances:
                active_bot_instances.pop(bot_uname, None)
            if e.error_code == 401:
                alert_name = f"@{bot_uname}" if bot_uname else f"{token_str[:10]}..."
                print(f"⛔ تم إيقاف البوت لأن التوكن محظور أو ملغى: {alert_name}")
                notify_admin_central(f"🚨 **تنبيه طوارئ عاجل!**\nتم حظر أو إيقاف البوت **{alert_name}** من تيليجرام للتو!\nيرجى الدخول إلى `🤖 إدارة البوتات` لاستبداله.")
                break
            print(f"⚠️ خطأ تيليجرام في البوت ({bot_uname or token_str[:10]}): {e} - إعادة المحاولة بعد 5 ثوانٍ...")
            time.sleep(5)
        except Exception as e:
            if bot_uname and bot_uname in active_bot_instances:
                active_bot_instances.pop(bot_uname, None)
            print(f"⚠️ خطأ اتصال في البوت ({bot_uname or token_str[:10]}): {e} - إعادة المحاولة بعد 5 ثوانٍ...")
            time.sleep(5)

if __name__ == "__main__":
    # 1. تشغيل خادم الويب والمراقبة
    Thread(target=run_web, daemon=True).start()

    # 2. تشغيل البوت الأساسي في خيط مستقل ومحصّن
    if TOKEN:
        Thread(target=launch_bot_polling, args=(TOKEN, True), daemon=True).start()

    # 3. تشغيل جميع البوتات الاحتياطية من MongoDB في خيوط مستقلة
    for clone in clones_col.find({}):
        c_token = clone.get("token")
        if c_token and c_token != TOKEN:
            Thread(target=launch_bot_polling, args=(c_token, False), daemon=True).start()

    # 4. إبقاء السيرفر حياً باستمرار لحماية البوتات الاحتياطية عند تعطل الأساسي
    while True:
        time.sleep(60)
