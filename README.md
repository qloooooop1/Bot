import telebot
import re
import sqlite3
import time
from flask import Flask, request, abort

# توكن البوت الخاص بك (الحارس الأمني @AlRASD1_BOT)
BOT_TOKEN = '7812533121:AAFyxg2EeeB4WqFpHecR1gdGUdg9Or7Evlk'
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# معرف القروب الوحيد الذي يعمل فيه البوت
ALLOWED_CHAT_ID = -1001224326322

# قاعدة بيانات لتتبع المخالفات
conn = sqlite3.connect('violations.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS violations
                  (user_id INTEGER PRIMARY KEY, count INTEGER)''')
conn.commit()

# دالة كشف أذكى للأرقام المخفية
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
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url='https://YOUR-VERCEL-APP.vercel.app/' + BOT_TOKEN)
    return "البوت جاهز والـ webhook مُعيَّن! يعمل فقط في القروب المحدد.", 200

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    # التحقق من أن الرسالة من القروب المسموح فقط
    if message.chat.id != ALLOWED_CHAT_ID:
        return  # تجاهل كل الرسائل من قروبات أو محادثات أخرى
    
    # التأكد من أنها قروب أو سوبر جروب
    if message.chat.type not in ['group', 'supergroup']:
        return
    
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
                time.sleep(120)
                bot.delete_message(chat_id, notice.message_id)
                
            elif violation_count >= 2:
                # حظر دائم
                bot.ban_chat_member(chat_id, user_id)
                
                # إرسال إشعار يُحذف تلقائياً بعد دقيقتين
                notice = bot.send_message(chat_id, f"🚨 تم حظر العضو {display_name} نهائياً بسبب تكرار إرسال أرقام جوالات.")
                time.sleep(120)
                bot.delete_message(chat_id, notice.message_id)
            
            # حفظ عدد المخالفات
            cursor.execute('INSERT OR REPLACE INTO violations (user_id, count) VALUES (?, ?)',
                           (user_id, violation_count))
            conn.commit()
            
        except Exception as e:
            print(f"خطأ: {e}")

if __name__ == '__main__':
    app.run(debug=True)