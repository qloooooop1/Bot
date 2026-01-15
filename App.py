import telebot
import re
import sqlite3
import time
import json
import os
import threading
from datetime import datetime, timedelta
from flask import Flask, request, abort
from telebot import types

# توكن البوت الخاص بك
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# معرف القروب الوحيد الذي يعمل فيه البوت
ALLOWED_CHAT_ID_STR = os.environ.get('ALLOWED_CHAT_ID')
if not ALLOWED_CHAT_ID_STR:
    raise ValueError("ALLOWED_CHAT_ID environment variable is required")

try:
    ALLOWED_CHAT_ID = int(ALLOWED_CHAT_ID_STR)
except ValueError:
    raise ValueError("ALLOWED_CHAT_ID must be a valid integer")

# قاعدة بيانات لتتبع المخالفات والإعدادات
conn = sqlite3.connect('bot_data.db', check_same_thread=False)
cursor = conn.cursor()
db_lock = threading.Lock()  # Lock for thread-safe database operations

# إنشاء جداول قاعدة البيانات
cursor.execute('''CREATE TABLE IF NOT EXISTS violations
                  (user_id INTEGER PRIMARY KEY, count INTEGER)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS settings
                  (chat_id INTEGER PRIMARY KEY,
                   azkar_enabled INTEGER DEFAULT 1,
                   delete_service_messages INTEGER DEFAULT 0,
                   interval_hours INTEGER DEFAULT 2,
                   phone_detection_enabled INTEGER DEFAULT 1)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS admins
                  (chat_id INTEGER, user_id INTEGER,
                   PRIMARY KEY (chat_id, user_id))''')

cursor.execute('''CREATE TABLE IF NOT EXISTS azkar_schedule
                  (chat_id INTEGER PRIMARY KEY,
                   last_posted TEXT,
                   current_type TEXT)''')

conn.commit()

# تحميل بيانات الأذكار
def load_azkar_data():
    try:
        with open('azkar_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"خطأ في تحميل بيانات الأذكار: {e}")
        return {"morning": [], "evening": []}

azkar_data = load_azkar_data()

# دالة الحصول على إعدادات المجموعة
def get_settings(chat_id):
    with db_lock:
        cursor.execute('SELECT * FROM settings WHERE chat_id = ?', (chat_id,))
        result = cursor.fetchone()
        if not result:
            cursor.execute('''INSERT INTO settings 
                             (chat_id, azkar_enabled, delete_service_messages, interval_hours, phone_detection_enabled)
                             VALUES (?, 1, 0, 2, 1)''', (chat_id,))
            conn.commit()
            return {'azkar_enabled': 1, 'delete_service_messages': 0, 'interval_hours': 2, 'phone_detection_enabled': 1}
        return {
            'azkar_enabled': result[1],
            'delete_service_messages': result[2],
            'interval_hours': result[3],
            'phone_detection_enabled': result[4]
        }

# دالة تحديث إعداد معين
def update_setting(chat_id, setting_name, value):
    # Whitelist of allowed column names to prevent SQL injection
    allowed_settings = ['azkar_enabled', 'delete_service_messages', 'interval_hours', 'phone_detection_enabled']
    if setting_name not in allowed_settings:
        raise ValueError(f"Invalid setting name: {setting_name}")
    
    # Use parameterized query with validated column name
    with db_lock:
        query = f'UPDATE settings SET {setting_name} = ? WHERE chat_id = ?'
        cursor.execute(query, (value, chat_id))
        conn.commit()

# دالة التحقق من صلاحيات الإدارة
def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

# دالة تحديد نوع الأذكار حسب الوقت
def get_azkar_type():
    """تحديد ما إذا كان وقت أذكار الصباح أو المساء"""
    current_hour = datetime.now().hour
    # أذكار الصباح: من الفجر (5 صباحاً) حتى العصر (3 مساءً)
    # أذكار المساء: من المغرب (5 مساءً) حتى منتصف الليل (12 صباحاً)
    if 5 <= current_hour < 15:
        return 'morning'
    elif 17 <= current_hour < 24:
        return 'evening'
    else:
        return 'evening'  # الأوقات الأخرى تعتبر مساءً

# دالة نشر الأذكار
def post_azkar(chat_id):
    """نشر ذكر واحد عشوائي من الأذكار المناسبة للوقت"""
    settings = get_settings(chat_id)
    if not settings['azkar_enabled']:
        return
    
    azkar_type = get_azkar_type()
    azkar_list = azkar_data.get(azkar_type, [])
    
    if not azkar_list:
        return
    
    import random
    zikr = random.choice(azkar_list)
    
    # تنسيق الرسالة
    message_text = f"🌟 {'أذكار الصباح' if azkar_type == 'morning' else 'أذكار المساء'} 🌟\n\n"
    message_text += f"📿 {zikr['text']}\n\n"
    
    if zikr['count'] > 1:
        message_text += f"🔢 العدد: {zikr['count']}\n"
    
    try:
        bot.send_message(chat_id, message_text)
        # تحديث آخر وقت نشر
        with db_lock:
            cursor.execute('''INSERT OR REPLACE INTO azkar_schedule 
                             (chat_id, last_posted, current_type) 
                             VALUES (?, ?, ?)''', 
                          (chat_id, datetime.now().isoformat(), azkar_type))
            conn.commit()
    except Exception as e:
        print(f"خطأ في نشر الأذكار: {e}")

# دالة جدولة الأذكار
def schedule_azkar():
    """جدولة نشر الأذكار بشكل دوري"""
    while True:
        try:
            # جلب جميع المجموعات التي فعّلت الأذكار
            with db_lock:
                cursor.execute('SELECT chat_id, interval_hours FROM settings WHERE azkar_enabled = 1')
                chats = cursor.fetchall()
            
            for chat_id, interval_hours in chats:
                # التحقق من آخر وقت نشر
                with db_lock:
                    cursor.execute('SELECT last_posted FROM azkar_schedule WHERE chat_id = ?', (chat_id,))
                    result = cursor.fetchone()
                
                should_post = False
                if not result:
                    should_post = True
                else:
                    last_posted = datetime.fromisoformat(result[0])
                    time_diff = datetime.now() - last_posted
                    if time_diff >= timedelta(hours=interval_hours):
                        should_post = True
                
                if should_post:
                    post_azkar(chat_id)
        
        except Exception as e:
            print(f"خطأ في جدولة الأذكار: {e}")
        
        # انتظار 30 دقيقة قبل الفحص التالي
        time.sleep(1800)

# بدء خيط جدولة الأذكار
azkar_thread = threading.Thread(target=schedule_azkar, daemon=True)
azkar_thread.start()


def extract_hidden_phone(text):
    if not text:
        return False
    
    # استبدال شائع للحروف والرموز العربية والإنجليزية اللي يستخدمونها للتخفي
    replacements = {
        'o': '0', 'O': '0', 'i': '1', 'I': '1', 'l': '1', 'L': '1',
        's': '5', 'S': '5', 'a': '4', 'A': '4', 'e': '3', 'E': '3',
        't': '7', 'T': '7', 'g': '9', 'G': '9', 'b': '8', 'B': '8',
        'z': '2', 'Z': '2', 'ق': '0', 'ه': '0', '٥': '5', '٤': '4',
        '٣': '3', '٧': '7', '٨': '8', '٩': '9', '٠': '0', '١': '1', '٢': '2'
    }
    
    cleaned = text.lower()
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    
    # إزالة جميع الرموز غير الأرقام
    digits_only = re.sub(r'\D', '', cleaned)
    
    # كشف أي تسلسل من 9 أرقام فأكثر
    if re.search(r'\d{9,}', digits_only):
        return True
    
    # كشف إضافي للأرقام المفصولة بمسافات أو رموز
    spaced = re.sub(r'[\s\-\.\*\_\+\(\)\[\]]', '', cleaned)
    if re.search(r'\d{9,}', spaced):
        return True
    
    return False

# معالج أمر /admin - لوحة التحكم
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "⛔ هذا الأمر متاح للمشرفين فقط.")
        return
    
    settings = get_settings(message.chat.id)
    
    # إنشاء لوحة التحكم
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # أزرار تفعيل/إلغاء الميزات
    azkar_status = "✅ مفعّل" if settings['azkar_enabled'] else "❌ معطّل"
    service_status = "✅ مفعّل" if settings['delete_service_messages'] else "❌ معطّل"
    phone_status = "✅ مفعّل" if settings['phone_detection_enabled'] else "❌ معطّل"
    
    markup.add(
        types.InlineKeyboardButton(f"الأذكار: {azkar_status}", callback_data="toggle_azkar"),
        types.InlineKeyboardButton(f"حذف رسائل الخدمة: {service_status}", callback_data="toggle_service")
    )
    markup.add(
        types.InlineKeyboardButton(f"كشف الأرقام: {phone_status}", callback_data="toggle_phone"),
        types.InlineKeyboardButton("⏰ ضبط الفاصل الزمني", callback_data="set_interval")
    )
    markup.add(
        types.InlineKeyboardButton("📤 نشر ذكر الآن", callback_data="post_now"),
        types.InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")
    )
    markup.add(types.InlineKeyboardButton("🔄 تحديث", callback_data="refresh_admin"))
    
    bot.send_message(
        message.chat.id,
        f"⚙️ **لوحة التحكم - إدارة البوت**\n\n"
        f"🔹 نشر الأذكار: {azkar_status}\n"
        f"🔹 حذف رسائل الخدمة: {service_status}\n"
        f"🔹 كشف الأرقام: {phone_status}\n"
        f"🔹 الفاصل الزمني: كل {settings['interval_hours']} ساعة\n\n"
        f"اضغط على الأزرار أدناه لتعديل الإعدادات:",
        reply_markup=markup,
        parse_mode='Markdown'
    )

# معالج استدعاءات الأزرار
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.message.chat.id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(call.message.chat.id, call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ هذه الميزة متاحة للمشرفين فقط.")
        return
    
    chat_id = call.message.chat.id
    settings = get_settings(chat_id)
    
    if call.data == "toggle_azkar":
        new_value = 0 if settings['azkar_enabled'] else 1
        update_setting(chat_id, 'azkar_enabled', new_value)
        bot.answer_callback_query(call.id, f"✅ تم {'تفعيل' if new_value else 'تعطيل'} نشر الأذكار")
        # تحديث اللوحة
        refresh_admin_panel(call.message)
    
    elif call.data == "toggle_service":
        new_value = 0 if settings['delete_service_messages'] else 1
        update_setting(chat_id, 'delete_service_messages', new_value)
        bot.answer_callback_query(call.id, f"✅ تم {'تفعيل' if new_value else 'تعطيل'} حذف رسائل الخدمة")
        refresh_admin_panel(call.message)
    
    elif call.data == "toggle_phone":
        new_value = 0 if settings['phone_detection_enabled'] else 1
        update_setting(chat_id, 'phone_detection_enabled', new_value)
        bot.answer_callback_query(call.id, f"✅ تم {'تفعيل' if new_value else 'تعطيل'} كشف الأرقام")
        refresh_admin_panel(call.message)
    
    elif call.data == "set_interval":
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("1 ساعة", callback_data="interval_1"),
            types.InlineKeyboardButton("2 ساعة", callback_data="interval_2"),
            types.InlineKeyboardButton("3 ساعات", callback_data="interval_3")
        )
        markup.add(
            types.InlineKeyboardButton("4 ساعات", callback_data="interval_4"),
            types.InlineKeyboardButton("6 ساعات", callback_data="interval_6"),
            types.InlineKeyboardButton("12 ساعة", callback_data="interval_12")
        )
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="refresh_admin"))
        
        bot.edit_message_text(
            "⏰ اختر الفاصل الزمني لنشر الأذكار:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
    
    elif call.data.startswith("interval_"):
        hours = int(call.data.split("_")[1])
        update_setting(chat_id, 'interval_hours', hours)
        bot.answer_callback_query(call.id, f"✅ تم ضبط الفاصل الزمني على {hours} ساعة")
        refresh_admin_panel(call.message)
    
    elif call.data == "post_now":
        post_azkar(chat_id)
        bot.answer_callback_query(call.id, "✅ تم نشر الذكر")
    
    elif call.data == "show_stats":
        with db_lock:
            cursor.execute('SELECT COUNT(*) FROM violations')
            violation_count = cursor.fetchone()[0]
            cursor.execute('SELECT last_posted FROM azkar_schedule WHERE chat_id = ?', (chat_id,))
            result = cursor.fetchone()
            last_posted = result[0] if result else "لم يتم النشر بعد"
        
        stats_text = f"📊 **إحصائيات البوت**\n\n"
        stats_text += f"🚨 عدد المخالفات المسجلة: {violation_count}\n"
        stats_text += f"📅 آخر نشر للأذكار: {last_posted}\n"
        stats_text += f"⏰ الفاصل الزمني الحالي: {settings['interval_hours']} ساعة"
        
        bot.answer_callback_query(call.id, "📊 عرض الإحصائيات")
        bot.send_message(chat_id, stats_text, parse_mode='Markdown')
    
    elif call.data == "refresh_admin":
        refresh_admin_panel(call.message)
        bot.answer_callback_query(call.id, "🔄 تم تحديث اللوحة")

def refresh_admin_panel(message):
    """تحديث لوحة التحكم"""
    settings = get_settings(message.chat.id)
    
    azkar_status = "✅ مفعّل" if settings['azkar_enabled'] else "❌ معطّل"
    service_status = "✅ مفعّل" if settings['delete_service_messages'] else "❌ معطّل"
    phone_status = "✅ مفعّل" if settings['phone_detection_enabled'] else "❌ معطّل"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"الأذكار: {azkar_status}", callback_data="toggle_azkar"),
        types.InlineKeyboardButton(f"حذف رسائل الخدمة: {service_status}", callback_data="toggle_service")
    )
    markup.add(
        types.InlineKeyboardButton(f"كشف الأرقام: {phone_status}", callback_data="toggle_phone"),
        types.InlineKeyboardButton("⏰ ضبط الفاصل الزمني", callback_data="set_interval")
    )
    markup.add(
        types.InlineKeyboardButton("📤 نشر ذكر الآن", callback_data="post_now"),
        types.InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")
    )
    markup.add(types.InlineKeyboardButton("🔄 تحديث", callback_data="refresh_admin"))
    
    bot.edit_message_text(
        f"⚙️ **لوحة التحكم - إدارة البوت**\n\n"
        f"🔹 نشر الأذكار: {azkar_status}\n"
        f"🔹 حذف رسائل الخدمة: {service_status}\n"
        f"🔹 كشف الأرقام: {phone_status}\n"
        f"🔹 الفاصل الزمني: كل {settings['interval_hours']} ساعة\n\n"
        f"اضغط على الأزرار أدناه لتعديل الإعدادات:",
        chat_id=message.chat.id,
        message_id=message.message_id,
        reply_markup=markup,
        parse_mode='Markdown'
    )

# معالج رسائل الخدمة
@bot.message_handler(content_types=['new_chat_members', 'left_chat_member', 'new_chat_title',
                                     'new_chat_photo', 'delete_chat_photo', 'group_chat_created',
                                     'pinned_message', 'voice_chat_started', 'voice_chat_ended'])
def delete_service_messages(message):
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    settings = get_settings(message.chat.id)
    if settings['delete_service_messages']:
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception as e:
            print(f"خطأ في حذف رسالة الخدمة: {e}")

@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        abort(403)

@app.route('/')
def index():
    webhook_url = os.environ.get('WEBHOOK_URL', 'https://YOUR-RENDER-APP.onrender.com')
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=webhook_url + '/' + BOT_TOKEN)
    return "البوت جاهز والـ webhook مُعيَّن! 🚀", 200

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    # التحقق من أن الرسالة من القروب المسموح فقط
    if message.chat.id != ALLOWED_CHAT_ID:
        return  # تجاهل كل الرسائل من قروبات أو محادثات أخرى
    
    # التأكد من أنها قروب أو سوبر جروب
    if message.chat.type not in ['group', 'supergroup']:
        return
    
    settings = get_settings(message.chat.id)
    
    # التحقق من كشف الأرقام إذا كان مفعلاً
    if settings['phone_detection_enabled']:
        chat_id = message.chat.id
        user_id = message.from_user.id
        text = message.text or message.caption or ''
        full_name = message.from_user.full_name or 'مجهول'
        username = message.from_user.username or ''
        display_name = f"@{username}" if username else full_name
        
        # تحقق من النص أو الكابشن أو اسم العضو
        if extract_hidden_phone(text) or extract_hidden_phone(full_name):
            try:
                # حذف الرسالة المخالفة فوراً
                bot.delete_message(chat_id, message.message_id)
                
                # جلب عدد المخالفات
                with db_lock:
                    cursor.execute('SELECT count FROM violations WHERE user_id = ?', (user_id,))
                    result = cursor.fetchone()
                    violation_count = result[0] + 1 if result else 1
                
                if violation_count == 1:
                    # كتم ليوم واحد (كتم كامل)
                    bot.restrict_chat_member(chat_id, user_id, until_date=int(time.time() + 86400),
                                             can_send_messages=False,
                                             can_send_media_messages=False,
                                             can_send_polls=False,
                                             can_send_other_messages=False,
                                             can_add_web_page_previews=False)
                    
                    # إرسال إشعار يُحذف تلقائياً بعد دقيقتين
                    notice = bot.send_message(chat_id, f"🚨 تم كتم العضو {display_name} لمدة يوم واحد بسبب إرسال رقم جوال ممنوع.")
                    
                    # حذف الإشعار بعد دقيقتين مع معالجة الأخطاء
                    def delete_notice():
                        try:
                            bot.delete_message(chat_id, notice.message_id)
                        except Exception as e:
                            print(f"خطأ في حذف الإشعار: {e}")
                    
                    threading.Timer(120, delete_notice).start()
                    
                elif violation_count >= 2:
                    # حظر دائم
                    bot.ban_chat_member(chat_id, user_id)
                    
                    # إرسال إشعار يُحذف تلقائياً بعد دقيقتين
                    notice = bot.send_message(chat_id, f"🚨 تم حظر العضو {display_name} نهائياً بسبب تكرار إرسال أرقام جوالات.")
                    
                    # حذف الإشعار بعد دقيقتين مع معالجة الأخطاء
                    def delete_ban_notice():
                        try:
                            bot.delete_message(chat_id, notice.message_id)
                        except Exception as e:
                            print(f"خطأ في حذف الإشعار: {e}")
                    
                    threading.Timer(120, delete_ban_notice).start()
                
                # حفظ عدد المخالفات
                with db_lock:
                    cursor.execute('INSERT OR REPLACE INTO violations (user_id, count) VALUES (?, ?)',
                                   (user_id, violation_count))
                    conn.commit()
                
            except Exception as e:
                print(f"خطأ: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

