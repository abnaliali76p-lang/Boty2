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

# --- إدارة الإعدادات الحية من قاعدة البيانات ---
DEFAULT_SETTINGS = {
    "video_url": "https://qu.ax/YazP4",
    "share_link": "https://t.me/joinchat/hRhhXjTZcCU2NjVh",
    "vip_stars_url": "https://t.me/m/gGbbzgOrZmU8",
    "alt_pay_url": "https://t.me/Gh64yu",
    "vip_price": "1000"
}

def get_setting(key):
    doc = settings_col.find_one({"_id": "bot_config"})
    if doc and key in doc:
        return doc[key]
    return DEFAULT_SETTINGS.get(key)

def update_setting(key, value):
    settings_col.update_one({"_id": "bot_config"}, {"$set": {key: value}}, upsert=True)

# --- متغيرات الحالة للعمليات التفاعلية ---
reply_targets = {}
admin_states = {}   # لتعديل الإعدادات من داخل البوت
bc_sessions = {}    # لإدارة جلسة الإذاعة المتقدمة

# --- النصوص الأساسية باللغة العبرية ---
def get_texts(first_name=""):
    price = get_setting("vip_price")
    stars_url = get_setting("vip_stars_url")
    alt_url = get_setting("alt_pay_url")
    share_link = get_setting("share_link")
    share_text = f"התוכן המלא פתוח / ללא הגבלה🔥👇 {share_link}"

    return {
        "welcome": (
            f"<b>היי {first_name}! 👋🔥\n\n"
            f"פתיחת הקבוצה נעולה (0/2 שיתופים) 🎁\n"
            f"+50,000 סרטונים בלעדיים מחכים לך!</b>\n\n"
            f"<blockquote>🚀 לחצו על \"שתף\" ושתפו את הקישור עם 2 חברים או קבוצות לפתיחה מיידית 👇</blockquote>"
        ),
        "btn_share": "🔗 שיתוף (0/2)",
        "btn_verify": "📥 אימות פתיחה",
        "btn_vip": "👑 פתיחה מהירה - VIP",
        "share_url": f"https://t.me/share/url?url={urllib.parse.quote(share_text)}",
        "share_alert": "⚠️ השיתוף לא הושלם! שתף את הקישור עם 2 חברים כדי לפתוח את הקבוצה 📲",
        "vip_already": "⚠️ כבר קיבלת את הפרטים היום! נסה שוב מחר.",
        "vip_text": (
            f"<blockquote><b>💎 פתיחת VIP ישירה (ללא שיתוף)</b></blockquote>\n"
            f"<blockquote><b>🔥 גישה מלאה + קבוצות פרטיות לכל החיים!</b></blockquote>\n"
            f"<blockquote><b>💰 מחיר כניסה: {price} כוכבים</b></blockquote>\n\n"
            f"👇 בחרו את שיטת התשלום המועדפת עליכם:"
        ),
        "btn_pay_stars": f"⭐ תשלום {price} כוכבים (הודעה ישירה)",
        "btn_pay_alt": "💳 תשלום בדרך אחרת (ללא כוכבים)",
        "stars_url": stars_url,
        "alt_url": alt_url
    }

# --- إرسال رسالة الترحيب ---
def send_welcome_message(user_id, first_name):
    now = datetime.now()

    if user_id != ADMIN_ID:
        user = users_col.find_one({"user_id": user_id})
        is_new = user is None

        if user and user.get("last_welcome"):
            if now - user.get("last_welcome") < timedelta(hours=24):
                return

        update_fields = {
            "last_welcome": now,
            "name": first_name
        }
        if is_new:
            update_fields["joined_at"] = now

        users_col.update_one({"user_id": user_id}, {"$set": update_fields}, upsert=True)

        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📩 رد على المستخدم", callback_data=f"reply_{user_id}"))
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
    markup.add(types.InlineKeyboardButton(t["btn_share"], url=t["share_url"]))
    markup.add(types.InlineKeyboardButton(t["btn_verify"], callback_data="check_share"))
    markup.add(types.InlineKeyboardButton(t["btn_vip"], callback_data="show_vip_info"))

    try:
        bot.send_video(
            user_id,
            get_setting("video_url"),
            caption=t["welcome"],
            parse_mode="HTML",
            protect_content=True,
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error sending welcome video to {user_id}: {e}")

# --- الأوامر الأساسية ---
@bot.message_handler(commands=["start"])
def start_cmd(message):
    send_welcome_message(message.chat.id, message.from_user.first_name)

@bot.chat_join_request_handler()
def join_req(request):
    send_welcome_message(request.from_user.id, request.from_user.first_name)

# --- لوحة تحكم الأدمن الشاملة (/admin) ---
def get_admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 الإحصائيات التفصيلية", callback_data="adm_stats"),
        types.InlineKeyboardButton("📢 إذاعة متقدمة", callback_data="adm_bc_start")
    )
    markup.add(
        types.InlineKeyboardButton("⚙️ تعديل الروابط والأسعار", callback_data="adm_settings"),
        types.InlineKeyboardButton("💾 نسخة احتياطية (Backup)", callback_data="adm_backup")
    )
    markup.add(
        types.InlineKeyboardButton("🔄 تصفير التواريخ", callback_data="confirm_reset_ask")
    )
    return markup

@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.chat.id == ADMIN_ID:
        admin_states.pop(ADMIN_ID, None)
        bc_sessions.pop(ADMIN_ID, None)
        bot.send_message(
            ADMIN_ID,
            "🛠️ **لوحة تحكم الإدارة الشاملة**\nاختر القسم الذي تريد إدارته:",
            reply_markup=get_admin_keyboard(),
            parse_mode="Markdown",
            protect_content=True
        )

# --- قائمة تعديل الإعدادات الحية ---
def get_settings_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🎬 رابط الفيديو الترحيبي", callback_data="set_video_url"),
        types.InlineKeyboardButton("🔗 رابط المشاركة (القناة)", callback_data="set_share_link"),
        types.InlineKeyboardButton("⭐ رابط الدفع بالنجوم", callback_data="set_vip_stars_url"),
        types.InlineKeyboardButton("💳 رابط الدفع البديل", callback_data="set_alt_pay_url"),
        types.InlineKeyboardButton(f"💰 سعر VIP بالنجوم (الحالي: {get_setting('vip_price')})", callback_data="set_vip_price"),
        types.InlineKeyboardButton("🔙 رجوع للوحة الرئيسية", callback_data="adm_home")
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

# --- تنفيذ الإذاعة المتقدمة في الخلفية ---
def run_advanced_broadcast(bc_message_id, session):
    now = datetime.now()
    segment = session["segment"]

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
        if not target_id:
            users_col.delete_one({"_id": u["_id"]})
            deleted_count += 1
            continue

        sent = False
        while not sent:
            try:
                copied = bot.copy_message(
                    chat_id=target_id,
                    from_chat_id=ADMIN_ID,
                    message_id=bc_message_id,
                    reply_markup=reply_markup,
                    protect_content=True
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

                time.sleep(0.06)

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
            for chat_id, msg_id in records:
                try:
                    bot.delete_message(chat_id, msg_id)
                    deleted_msgs += 1
                    time.sleep(0.05)
                except:
                    pass
            try:
                bot.send_message(ADMIN_ID, f"🗑️ اكتمل الحذف التلقائي للإذاعة المؤقتة (تم حذف `{deleted_msgs}` رسالة).", parse_mode="Markdown")
            except:
                pass

        Thread(target=schedule_deletion, args=(sent_records, session["auto_delete"]), daemon=True).start()

# --- معالجة جميع الأزرار التفاعلية ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    t = get_texts()

    # 1. أزرار المستخدمين
    if call.data == "check_share":
        bot.answer_callback_query(call.id, t["share_alert"], show_alert=True)

    elif call.data == "show_vip_info":
        now = datetime.now()
        if user_id != ADMIN_ID:
            user = users_col.find_one({"user_id": user_id})
            users_col.update_one({"user_id": user_id}, {"$set": {"clicked_vip": True, "last_vip_click": now}}, upsert=True)

            if user and user.get("last_vip_request"):
                if now - user.get("last_vip_request") < timedelta(hours=24):
                    bot.answer_callback_query(call.id, t["vip_already"], show_alert=True)
                    return

        try:
            bot.answer_callback_query(call.id)
        except:
            pass

        vip_markup = types.InlineKeyboardMarkup(row_width=1)
        vip_markup.add(
            types.InlineKeyboardButton(t["btn_pay_stars"], url=t["stars_url"]),
            types.InlineKeyboardButton(t["btn_pay_alt"], url=t["alt_url"])
        )

        try:
            bot.send_message(
                chat_id,
                t["vip_text"],
                parse_mode="HTML",
                reply_markup=vip_markup,
                protect_content=True
            )
            if user_id != ADMIN_ID:
                users_col.update_one({"user_id": user_id}, {"$set": {"last_vip_request": now}}, upsert=True)
        except Exception as e:
            print(f"Error sending VIP info to {user_id}: {e}")

    # 2. أزرار الأدمن فقط
    elif user_id == ADMIN_ID:
        if call.data == "adm_home":
            admin_states.pop(ADMIN_ID, None)
            bc_sessions.pop(ADMIN_ID, None)
            bot.edit_message_text(
                "🛠️ **لوحة تحكم الإدارة الشاملة**\nاختر القسم الذي تريد إدارته:",
                chat_id, call.message.message_id,
                reply_markup=get_admin_keyboard(),
                parse_mode="Markdown"
            )

        elif call.data == "adm_stats":
            now = datetime.now()
            total = users_col.count_documents({})
            new_24h = users_col.count_documents({"joined_at": {"$gte": now - timedelta(hours=24)}})
            vip_clicks = users_col.count_documents({"clicked_vip": True})

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home"))

            bot.edit_message_text(
                f"📊 **إحصائيات البوت التفصيلية:**\n\n"
                f"👥 إجمالي المشتركين النشطين: `{total}`\n"
                f"🆕 مشتركو آخر 24 ساعة: `{new_24h}`\n"
                f"👑 مهتمون بالـ VIP (ضغطوا الزر): `{vip_clicks}`",
                chat_id, call.message.message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )

        elif call.data == "adm_backup":
            bot.answer_callback_query(call.id, "⏳ جاري تجهيز النسخة الاحتياطية...")
            all_users = list(users_col.find({}, {"_id": 0}))
            for u in all_users:
                for k, v in u.items():
                    if isinstance(v, datetime):
                        u[k] = v.isoformat()

            json_bytes = json.dumps(all_users, ensure_ascii=False, indent=2).encode("utf-8")
            bio = io.BytesIO(json_bytes)
            bio.name = f"bot_backup_{datetime.now().strftime('%Y_%m_%d')}.json"
            bot.send_document(ADMIN_ID, bio, caption=f"💾 **نسخة احتياطية كاملة**\nعدد السجلات: `{len(all_users)}`", parse_mode="Markdown")

        elif call.data == "adm_settings":
            bot.edit_message_text(
                "⚙️ **إعدادات البوت الحية**\nاختر العنصر الذي تريد تعديله (سيتم حفظه فوراً في قاعدة البيانات):",
                chat_id, call.message.message_id,
                reply_markup=get_settings_keyboard(),
                parse_mode="Markdown"
            )

        elif call.data.startswith("set_"):
            setting_key = call.data.replace("set_", "")
            admin_states[ADMIN_ID] = f"edit_{setting_key}"
            names = {
                "video_url": "رابط الفيديو الجديد (URL)",
                "share_link": "رابط القناة/المجموعة للمشاركة",
                "vip_stars_url": "رابط حسابك للدفع بالنجوم",
                "alt_pay_url": "رابط حسابك للدفع البديل",
                "vip_price": "سعر الباقة بالنجوم (رقم فقط، مثلاً: 1000)"
            }
            bot.answer_callback_query(call.id)
            bot.send_message(ADMIN_ID, f"✍️ أرسل الآن **{names.get(setting_key)}**:", parse_mode="Markdown")

        elif call.data == "adm_bc_start":
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("👥 جميع المشتركين", callback_data="bc_seg_all"),
                types.InlineKeyboardButton("🆕 المشتركون الجدد (آخر 24 ساعة)", callback_data="bc_seg_new_24h"),
                types.InlineKeyboardButton("👑 المهتمون بالـ VIP فقط", callback_data="bc_seg_vip_interested"),
                types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_home")
            )
            bot.edit_message_text(
                "📢 **إعداد الإذاعة المتقدمة (الخطوة 1/2)**\nاختر الفئة المستهدفة:",
                chat_id, call.message.message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )

        elif call.data.startswith("bc_seg_"):
            seg = call.data.replace("bc_seg_", "")
            bc_sessions[ADMIN_ID] = {
                "segment": seg,
                "pin": False,
                "btn_text": None,
                "btn_url": None,
                "auto_delete": 0,
                "step": "config"
            }
            bot.edit_message_text(
                "🎛️ **خيارات الإذاعة المتقدمة (الخطوة 2/2)**\nاضبط الإضافات التي تريدها ثم اضغط على المتابعة:",
                chat_id, call.message.message_id,
                reply_markup=get_bc_config_keyboard(bc_sessions[ADMIN_ID]),
                parse_mode="Markdown"
            )

        elif call.data == "bc_toggle_pin":
            if ADMIN_ID in bc_sessions:
                bc_sessions[ADMIN_ID]["pin"] = not bc_sessions[ADMIN_ID]["pin"]
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_bc_config_keyboard(bc_sessions[ADMIN_ID]))

        elif call.data == "bc_cycle_del":
            if ADMIN_ID in bc_sessions:
                curr = bc_sessions[ADMIN_ID]["auto_delete"]
                nxt = 3600 if curr == 0 else (86400 if curr == 3600 else 0)
                bc_sessions[ADMIN_ID]["auto_delete"] = nxt
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_bc_config_keyboard(bc_sessions[ADMIN_ID]))

        elif call.data == "bc_add_btn":
            if ADMIN_ID in bc_sessions:
                bc_sessions[ADMIN_ID]["step"] = "wait_btn"
                bot.answer_callback_query(call.id)
                bot.send_message(
                    ADMIN_ID,
                    "🔗 أرسل نص الزر والرابط مفصولين بعلامة `|`\n"
                    "**مثال:**\n`🔥 احصل على الخصم الآن | https://t.me/Gh64yu`",
                    parse_mode="Markdown"
                )

        elif call.data == "bc_ready_send":
            if ADMIN_ID in bc_sessions:
                bc_sessions[ADMIN_ID]["step"] = "wait_msg"
                bot.answer_callback_query(call.id)
                bot.send_message(
                    ADMIN_ID,
                    "📨 **أرسل الآن رسالة الإذاعة** (نص، صورة، فيديو، أو توجيه) وسيتم إطلاقها فوراً بالإعدادات التي اخترتها:",
                    parse_mode="Markdown"
                )

        elif call.data.startswith("reply_"):
            target_id = call.data.split("_")[1]
            reply_targets[chat_id] = target_id
            bot.answer_callback_query(call.id, "✅ أرسل الرد الآن")
            bot.send_message(ADMIN_ID, f"✍️ اكتب الرد للمستخدم `{target_id}`:", parse_mode="Markdown", protect_content=True)

        elif call.data == "confirm_reset_ask":
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ نعم، تصفير التواريخ", callback_data="confirm_reset"),
                types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_home")
            )
            bot.edit_message_text("⚠️ هل أنت متأكد من تصفير تواريخ الترحيب وVIP لجميع المستخدمين؟", chat_id, call.message.message_id, reply_markup=markup)

        elif call.data == "confirm_reset":
            users_col.update_many({}, {"$unset": {"last_welcome": "", "last_vip_request": ""}})
            bot.edit_message_text("✅ تم تصفير جميع التواريخ بنجاح.", chat_id, call.message.message_id, reply_markup=get_admin_keyboard())

# --- معالجة رسائل الأدمن (الإعدادات، الإذاعة، والردود) ---
@bot.message_handler(func=lambda message: message.chat.id == ADMIN_ID, content_types=['text', 'photo', 'video', 'animation', 'document', 'voice', 'audio'])
def handle_admin_messages(message):
    if ADMIN_ID in admin_states and message.content_type == 'text':
        state = admin_states.pop(ADMIN_ID)
        key = state.replace("edit_", "")
        update_setting(key, message.text.strip())
        bot.reply_to(message, "✅ تم تحديث الإعداد وحفظه في قاعدة البيانات بنجاح!", reply_markup=get_admin_keyboard())
        return

    if ADMIN_ID in bc_sessions:
        session = bc_sessions[ADMIN_ID]
        if session["step"] == "wait_btn" and message.content_type == 'text':
            if "|" in message.text:
                parts = message.text.split("|", 1)
                session["btn_text"] = parts[0].strip()
                session["btn_url"] = parts[1].strip()
                session["step"] = "config"
                bot.send_message(
                    ADMIN_ID,
                    "✅ تم إضافة الزر بنجاح! يمكنك المتابعة الآن:",
                    reply_markup=get_bc_config_keyboard(session)
                )
            else:
                bot.reply_to(message, "⚠️ صيغة خاطئة! استخدم علامة `|` بين النص والرابط.")
            return

        elif session["step"] == "wait_msg":
            active_session = bc_sessions.pop(ADMIN_ID)
            Thread(target=run_advanced_broadcast, args=(message.message_id, active_session), daemon=True).start()
            return

    if message.reply_to_message and message.content_type == 'text' and (message.text in ["/bc", "/broadcast", "إذاعة", "اذاعة"]):
        quick_session = {"segment": "all", "pin": False, "btn_text": None, "btn_url": None, "auto_delete": 0}
        Thread(target=run_advanced_broadcast, args=(message.reply_to_message.message_id, quick_session), daemon=True).start()
        return

    if ADMIN_ID in reply_targets:
        target_id = reply_targets.pop(ADMIN_ID)
        try:
            bot.copy_message(chat_id=target_id, from_chat_id=ADMIN_ID, message_id=message.message_id, protect_content=True)
            bot.reply_to(message, f"✅ تم إرسال الرد إلى `{target_id}` بنجاح!", parse_mode="Markdown", protect_content=True)
        except Exception as e:
            bot.reply_to(message, f"❌ فشل إرسال الرد: {e}")

# --- توجيه رسائل المستخدمين للأدمن ---
@bot.message_handler(func=lambda message: message.chat.id != ADMIN_ID, content_types=['text', 'photo', 'video', 'animation', 'document', 'voice', 'audio'])
def forward_user_msg(message):
    try:
        bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    except:
        pass

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling(skip_pending=True)
