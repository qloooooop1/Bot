import telebot
import re
import sqlite3
import time
import json
import random
from datetime import datetime, timedelta
from flask import Flask, request, abort
from telebot import types
from apscheduler.schedulers.background import BackgroundScheduler
from hijri_converter import Hijri, Gregorian

# توكن البوت الخاص بك (الحارس الأمني @AlRASD1_BOT)
BOT_TOKEN = '7812533121:AAFyxg2EeeB4WqFpHecR1gdGUdg9Or7Evlk'
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
scheduler = BackgroundScheduler()

# معرف القروب الوحيد الذي يعمل فيه البوت
ALLOWED_CHAT_ID = -1001224326322

# قاعدة بيانات لتتبع المخالفات والميزات الجديدة
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

# إنشاء جداول قاعدة البيانات
cursor.execute('''CREATE TABLE IF NOT EXISTS violations
                  (user_id INTEGER PRIMARY KEY, count INTEGER)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS user_points
                  (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0,
                   correct_answers INTEGER DEFAULT 0, last_activity TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS custom_azkar
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT,
                   content TEXT, votes INTEGER DEFAULT 0, approved INTEGER DEFAULT 0,
                   submission_date TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS admin_settings
                  (setting_key TEXT PRIMARY KEY, setting_value TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS prayer_times
                  (chat_id INTEGER PRIMARY KEY, location TEXT, latitude REAL, longitude REAL,
                   reminder_enabled INTEGER DEFAULT 1)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS offensive_words
                  (word TEXT PRIMARY KEY)''')

conn.commit()

# بيانات الأذكار الإسلامية
AZKAR_DATA = {
    'الصباح': [
        "أَصْبَحْنَا وَأَصْبَحَ الْمُلْكُ لِلَّهِ وَالْحَمْدُ لِلَّهِ",
        "اللَّهُمَّ بِكَ أَصْبَحْنَا، وَبِكَ أَمْسَيْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ وَإِلَيْكَ النُّشُورُ",
        "رَضِيتُ بِاللَّهِ رَبًّا، وَبِالْإِسْلَامِ دِينًا، وَبِمُحَمَّدٍ صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ نَبِيًّا",
        "اللَّهُمَّ إِنِّي أَصْبَحْتُ أُشْهِدُكَ وَأُشْهِدُ حَمَلَةَ عَرْشِكَ، وَمَلَائِكَتَكَ وَجَمِيعَ خَلْقِكَ، أَنَّكَ أَنْتَ اللَّهُ لَا إِلَهَ إِلَّا أَنْتَ وَحْدَكَ لَا شَرِيكَ لَكَ",
        "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ عَدَدَ خَلْقِهِ، وَرِضَا نَفْسِهِ، وَزِنَةَ عَرْشِ هِ، وَمِدَادَ كَلِمَاتِهِ",
    ],
    'المساء': [
        "أَمْسَيْنَا وَأَمْسَى الْمُلْكُ لِلَّهِ وَالْحَمْدُ لِلَّهِ",
        "اللَّهُمَّ بِكَ أَمْسَيْنَا، وَبِكَ أَصْبَحْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ وَإِلَيْكَ الْمَصِيرُ",
        "اللَّهُمَّ إِنِّي أَمْسَيْتُ أُشْهِدُكَ وَأُشْهِدُ حَمَلَةَ عَرْشِكَ، وَمَلَائِكَتَكَ وَجَمِيعَ خَلْقِكَ، أَنَّكَ أَنْتَ اللَّهُ لَا إِلَهَ إِلَّا أَنْتَ",
        "أَعُوذُ بِكَلِمَاتِ اللَّهِ التَّامَّاتِ مِنْ شَرِّ مَا خَلَقَ",
        "بِسْمِ اللَّهِ الَّذِي لَا يَضُرُّ مَعَ اسْمِهِ شَيْءٌ فِي الْأَرْضِ وَلَا فِي السَّمَاءِ وَهُوَ السَّمِيعُ الْعَلِيمُ",
    ],
    'عامة': [
        "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ",
        "لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ",
        "اللَّهُمَّ صَلِّ وَسَلِّمْ عَلَى نَبِيِّنَا مُحَمَّدٍ",
        "أَسْتَغْفِرُ اللَّهَ وَأَتُوبُ إِلَيْهِ",
        "حَسْبِيَ اللَّهُ لَا إِلَهَ إِلَّا هُوَ عَلَيْهِ تَوَكَّلْتُ وَهُوَ رَبُّ الْعَرْشِ الْعَظِيمِ",
    ],
    'النوم': [
        "بِاسْمِكَ اللَّهُمَّ أَمُوتُ وَأَحْيَا",
        "اللَّهُمَّ إِنِّي أَسْلَمْتُ نَفْسِي إِلَيْكَ، وَوَجَّهْتُ وَجْهِي إِلَيْكَ، وَفَوَّضْتُ أَمْرِي إِلَيْكَ",
        "اللَّهُمَّ قِنِي عَذَابَكَ يَوْمَ تَبْعَثُ عِبَادَكَ",
    ],
    'الطعام': [
        "بِسْمِ اللَّهِ وَعَلَى بَرَكَةِ اللَّهِ",
        "اللَّهُمَّ بَارِكْ لَنَا فِيمَا رَزَقْتَنَا وَقِنَا عَذَابَ النَّارِ",
    ]
}

# الأسئلة الدينية للمسابقات
QUIZ_QUESTIONS = [
    {
        'question': 'كم عدد أركان الإسلام؟',
        'options': ['3', '4', '5', '6'],
        'correct': 2,
        'explanation': 'أركان الإسلام خمسة: الشهادتان، الصلاة، الزكاة، الصوم، الحج'
    },
    {
        'question': 'ما هي أول صلاة فرضها الله على المسلمين؟',
        'options': ['الفجر', 'الظهر', 'العصر', 'المغرب'],
        'correct': 1,
        'explanation': 'صلاة الظهر هي أول صلاة فُرضت'
    },
    {
        'question': 'كم عدد سور القرآن الكريم؟',
        'options': ['110', '114', '120', '100'],
        'correct': 1,
        'explanation': 'عدد سور القرآن الكريم 114 سورة'
    },
    {
        'question': 'ما هو أطول شهر في السنة الهجرية؟',
        'options': ['رمضان', 'شعبان', 'رجب', 'كل الشهور متساوية'],
        'correct': 3,
        'explanation': 'جميع الشهور الهجرية إما 29 أو 30 يوماً'
    },
    {
        'question': 'من هو خاتم الأنبياء والمرسلين؟',
        'options': ['عيسى عليه السلام', 'موسى عليه السلام', 'محمد صلى الله عليه وسلم', 'إبراهيم عليه السلام'],
        'correct': 2,
        'explanation': 'محمد صلى الله عليه وسلم هو خاتم الأنبياء والمرسلين'
    }
]

# النصائح اليومية
DAILY_TIPS = [
    "💡 لا تنسَ قراءة ورد القرآن اليومي",
    "💡 صلاة الضحى سنة مؤكدة، احرص عليها",
    "💡 الاستغفار يفتح أبواب الرزق والفرج",
    "💡 الصلاة على النبي ﷺ تجلب البركة",
    "💡 قراءة سورة الكهف يوم الجمعة سنة مستحبة",
    "💡 أكثر من ذكر الله في كل وقت وحين",
    "💡 صلة الرحم من أعظم القربات إلى الله",
]

# الأحداث الإسلامية الهامة (سيتم تحديثها تلقائياً)
ISLAMIC_EVENTS = {
    'رمضان': {'hijri_month': 9, 'hijri_day': 1, 'message': '🌙 اللهم بلغنا رمضان! بداية شهر رمضان المبارك'},
    'عيد_الفطر': {'hijri_month': 10, 'hijri_day': 1, 'message': '🎉 عيد مبارك! عيد الفطر السعيد'},
    'يوم_عرفة': {'hijri_month': 12, 'hijri_day': 9, 'message': '⛰️ يوم عرفة - أفضل أيام السنة'},
    'عيد_الأضحى': {'hijri_month': 12, 'hijri_day': 10, 'message': '🎉 عيد أضحى مبارك'},
}

# قائمة الكلمات المسيئة الافتراضية (يمكن للمشرف إضافة المزيد)
DEFAULT_OFFENSIVE_WORDS = ['كلمة1', 'كلمة2']  # يمكن إضافة كلمات حقيقية حسب الحاجة

# إضافة الكلمات المسيئة الافتراضية إلى قاعدة البيانات
for word in DEFAULT_OFFENSIVE_WORDS:
    cursor.execute('INSERT OR IGNORE INTO offensive_words (word) VALUES (?)', (word,))
conn.commit()

# متغيرات عالمية للمسابقات
active_quizzes = {}

# دوال مساعدة
def is_admin(chat_id, user_id):
    """التحقق من صلاحيات المشرف"""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

def check_offensive_words(text):
    """فحص النص للكلمات المسيئة"""
    if not text:
        return None
    cursor.execute('SELECT word FROM offensive_words')
    offensive_words = [row[0] for row in cursor.fetchall()]
    text_lower = text.lower()
    for word in offensive_words:
        if word.lower() in text_lower:
            return word
    return None

def update_user_points(user_id, username, points_to_add):
    """تحديث نقاط المستخدم"""
    cursor.execute('''INSERT INTO user_points (user_id, username, points, last_activity)
                      VALUES (?, ?, ?, ?)
                      ON CONFLICT(user_id) DO UPDATE SET
                      points = points + ?,
                      username = ?,
                      last_activity = ?''',
                   (user_id, username, points_to_add, datetime.now().isoformat(),
                    points_to_add, username, datetime.now().isoformat()))
    conn.commit()

def get_prayer_times_aladhan(latitude, longitude):
    """الحصول على مواقيت الصلاة من API"""
    try:
        import requests
        url = f"http://api.aladhan.com/v1/timings/{int(time.time())}?latitude={latitude}&longitude={longitude}&method=4"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            timings = data['data']['timings']
            return {
                'الفجر': timings['Fajr'],
                'الظهر': timings['Dhuhr'],
                'العصر': timings['Asr'],
                'المغرب': timings['Maghrib'],
                'العشاء': timings['Isha']
            }
    except:
        pass
    return None

def check_islamic_events():
    """فحص الأحداث الإسلامية"""
    try:
        today = Gregorian.today().to_hijri()
        for event_name, event_data in ISLAMIC_EVENTS.items():
            if today.month == event_data['hijri_month'] and today.day == event_data['hijri_day']:
                return event_data['message']
    except:
        pass
    return None

# معالجات الأوامر (Command Handlers)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """رسالة الترحيب والمساعدة"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    welcome_text = """
🕌 *مرحباً بكم في بوت الأذكار الإسلامية* 🕌

📿 *الأوامر المتاحة:*

*الأذكار:*
/اذكار_الصباح - أذكار الصباح
/دعاء_المساء - أدعية المساء
/اذكار_عامة - أذكار عامة
/اذكار_النوم - أذكار قبل النوم
/اذكار_الطعام - أذكار الطعام
/قائمة_الاذكار - عرض جميع الأذكار

*المسابقات والتفاعل:*
/سؤال - سؤال ديني تفاعلي
/نقاطي - عرض نقاطك
/ترتيب - عرض أفضل الأعضاء

*المواعيد:*
/مواقيت_الصلاة - عرض مواقيت الصلاة
/التقويم_الهجري - عرض التاريخ الهجري

*الموارد:*
/نصيحة - نصيحة يومية

*للمشرفين فقط:*
/ضبط_الموقع - تعيين موقع للصلاة
/اضافة_كلمة_محظورة - إضافة كلمة للفلترة
/موافقة_ذكر - الموافقة على ذكر مخصص
/تقرير_شهري - تقرير الأعضاء الأكثر تفاعلاً

✨ استخدم الأزرار أدناه للوصول السريع ✨
    """
    
    # أزرار تفاعلية
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📿 أذكار الصباح", callback_data="azkar_الصباح"),
        types.InlineKeyboardButton("🌙 دعاء المساء", callback_data="azkar_المساء"),
        types.InlineKeyboardButton("📖 أذكار عامة", callback_data="azkar_عامة"),
        types.InlineKeyboardButton("❓ سؤال ديني", callback_data="quiz"),
        types.InlineKeyboardButton("🏆 الترتيب", callback_data="leaderboard"),
        types.InlineKeyboardButton("💡 نصيحة اليوم", callback_data="daily_tip")
    )
    
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(commands=['اذكار_الصباح'])
def morning_azkar(message):
    """إرسال أذكار الصباح"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    send_azkar(message.chat.id, 'الصباح')

@bot.message_handler(commands=['دعاء_المساء', 'اذكار_المساء'])
def evening_azkar(message):
    """إرسال دعاء المساء"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    send_azkar(message.chat.id, 'المساء')

@bot.message_handler(commands=['اذكار_عامة'])
def general_azkar(message):
    """إرسال أذكار عامة"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    send_azkar(message.chat.id, 'عامة')

@bot.message_handler(commands=['اذكار_النوم'])
def sleep_azkar(message):
    """إرسال أذكار النوم"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    send_azkar(message.chat.id, 'النوم')

@bot.message_handler(commands=['اذكار_الطعام'])
def food_azkar(message):
    """إرسال أذكار الطعام"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    send_azkar(message.chat.id, 'الطعام')

def send_azkar(chat_id, azkar_type):
    """دالة مساعدة لإرسال الأذكار"""
    if azkar_type in AZKAR_DATA:
        azkar_list = AZKAR_DATA[azkar_type]
        azkar_text = f"📿 *أذكار {azkar_type}* 📿\n\n"
        azkar_text += "\n\n".join([f"{i+1}. {azkar}" for i, azkar in enumerate(azkar_list)])
        bot.send_message(chat_id, azkar_text, parse_mode='Markdown')
        
        # تحديث نقاط المستخدم
        # update_user_points(user_id, username, 1)

@bot.message_handler(commands=['قائمة_الاذكار'])
def azkar_menu(message):
    """عرض قائمة الأذكار"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📿 الصباح", callback_data="azkar_الصباح"),
        types.InlineKeyboardButton("🌙 المساء", callback_data="azkar_المساء"),
        types.InlineKeyboardButton("📖 عامة", callback_data="azkar_عامة"),
        types.InlineKeyboardButton("😴 النوم", callback_data="azkar_النوم"),
        types.InlineKeyboardButton("🍽️ الطعام", callback_data="azkar_الطعام")
    )
    
    bot.send_message(message.chat.id, "📿 *اختر نوع الذكر:*", parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(commands=['سؤال'])
def send_quiz(message):
    """إرسال سؤال ديني"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    question_data = random.choice(QUIZ_QUESTIONS)
    active_quizzes[message.chat.id] = question_data
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for i, option in enumerate(question_data['options']):
        markup.add(types.InlineKeyboardButton(option, callback_data=f"answer_{i}"))
    
    bot.send_message(message.chat.id, f"❓ *{question_data['question']}*", 
                     parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(commands=['نقاطي'])
def my_points(message):
    """عرض نقاط المستخدم"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    user_id = message.from_user.id
    cursor.execute('SELECT points, correct_answers FROM user_points WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result:
        points, correct = result
        text = f"🏆 *نقاطك:* {points}\n✅ *إجابات صحيحة:* {correct}"
    else:
        text = "🏆 ليس لديك نقاط بعد! شارك في المسابقات لكسب النقاط"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['ترتيب'])
def leaderboard(message):
    """عرض لوحة الصدارة"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    cursor.execute('SELECT username, points, correct_answers FROM user_points ORDER BY points DESC LIMIT 10')
    results = cursor.fetchall()
    
    if results:
        text = "🏆 *أفضل 10 أعضاء:*\n\n"
        for i, (username, points, correct) in enumerate(results):
            emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            text += f"{emoji} {username}: {points} نقطة ({correct} إجابة صحيحة)\n"
    else:
        text = "لا توجد بيانات بعد!"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['مواقيت_الصلاة'])
def prayer_times_command(message):
    """عرض مواقيت الصلاة"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    chat_id = message.chat.id
    cursor.execute('SELECT latitude, longitude FROM prayer_times WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    
    if result:
        lat, lon = result
        times = get_prayer_times_aladhan(lat, lon)
        if times:
            text = "🕌 *مواقيت الصلاة اليوم:*\n\n"
            for prayer, time in times.items():
                text += f"• {prayer}: {time}\n"
            bot.send_message(chat_id, text, parse_mode='Markdown')
        else:
            bot.send_message(chat_id, "❌ حدث خطأ في جلب مواقيت الصلاة")
    else:
        bot.send_message(chat_id, "⚠️ لم يتم تعيين الموقع بعد. استخدم /ضبط_الموقع (للمشرفين)")

@bot.message_handler(commands=['التقويم_الهجري'])
def hijri_calendar(message):
    """عرض التاريخ الهجري"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    try:
        today_hijri = Gregorian.today().to_hijri()
        today_gregorian = datetime.now()
        
        text = f"📅 *التاريخ الهجري:*\n{today_hijri.day}/{today_hijri.month}/{today_hijri.year}\n\n"
        text += f"📅 *التاريخ الميلادي:*\n{today_gregorian.strftime('%d/%m/%Y')}\n\n"
        
        # التحقق من الأحداث
        event = check_islamic_events()
        if event:
            text += f"\n🌟 {event}"
        
        bot.send_message(message.chat.id, text, parse_mode='Markdown')
    except:
        bot.send_message(message.chat.id, "❌ حدث خطأ في عرض التقويم")

@bot.message_handler(commands=['نصيحة'])
def daily_tip(message):
    """إرسال نصيحة يومية"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    tip = random.choice(DAILY_TIPS)
    bot.send_message(message.chat.id, tip)

# الأوامر الإدارية (للمشرفين فقط)

@bot.message_handler(commands=['ضبط_الموقع'])
def set_location(message):
    """تعيين موقع المجموعة لمواقيت الصلاة"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "⛔ هذا الأمر للمشرفين فقط")
        return
    
    try:
        # صيغة الأمر: /ضبط_الموقع خط_العرض خط_الطول
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "⚠️ الصيغة الصحيحة: /ضبط_الموقع خط_العرض خط_الطول\nمثال: /ضبط_الموقع 24.7136 46.6753")
            return
        
        lat = float(parts[1])
        lon = float(parts[2])
        
        cursor.execute('''INSERT INTO prayer_times (chat_id, latitude, longitude)
                          VALUES (?, ?, ?)
                          ON CONFLICT(chat_id) DO UPDATE SET
                          latitude = ?, longitude = ?''',
                       (message.chat.id, lat, lon, lat, lon))
        conn.commit()
        
        bot.reply_to(message, "✅ تم تعيين الموقع بنجاح!")
    except ValueError:
        bot.reply_to(message, "❌ خطأ في الإحداثيات. تأكد من إدخال أرقام صحيحة")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {str(e)}")

@bot.message_handler(commands=['اضافة_كلمة_محظورة'])
def add_offensive_word(message):
    """إضافة كلمة للقائمة السوداء"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "⛔ هذا الأمر للمشرفين فقط")
        return
    
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ الصيغة الصحيحة: /اضافة_كلمة_محظورة الكلمة")
            return
        
        word = parts[1].strip()
        cursor.execute('INSERT OR IGNORE INTO offensive_words (word) VALUES (?)', (word,))
        conn.commit()
        
        bot.reply_to(message, f"✅ تم إضافة الكلمة '{word}' إلى قائمة الكلمات المحظورة")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {str(e)}")

@bot.message_handler(commands=['تقرير_شهري'])
def monthly_report(message):
    """تقرير الأعضاء الأكثر تفاعلاً"""
    if message.chat.id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "⛔ هذا الأمر للمشرفين فقط")
        return
    
    try:
        cursor.execute('''SELECT username, points, correct_answers, last_activity
                          FROM user_points
                          ORDER BY points DESC
                          LIMIT 20''')
        results = cursor.fetchall()
        
        if results:
            text = "📊 *تقرير الأعضاء الأكثر تفاعلاً:*\n\n"
            for i, (username, points, correct, last_activity) in enumerate(results):
                text += f"{i+1}. {username}\n"
                text += f"   • النقاط: {points}\n"
                text += f"   • الإجابات الصحيحة: {correct}\n\n"
            
            bot.send_message(message.chat.id, text, parse_mode='Markdown')
        else:
            bot.reply_to(message, "لا توجد بيانات متاحة")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {str(e)}")

# معالج الأزرار التفاعلية (Callback Query Handler)
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """معالجة الأزرار التفاعلية"""
    try:
        if call.data.startswith('azkar_'):
            azkar_type = call.data.replace('azkar_', '')
            send_azkar(call.message.chat.id, azkar_type)
            bot.answer_callback_query(call.id, f"تم إرسال أذكار {azkar_type}")
        
        elif call.data == 'quiz':
            question_data = random.choice(QUIZ_QUESTIONS)
            active_quizzes[call.message.chat.id] = question_data
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            for i, option in enumerate(question_data['options']):
                markup.add(types.InlineKeyboardButton(option, callback_data=f"answer_{i}"))
            
            bot.send_message(call.message.chat.id, f"❓ *{question_data['question']}*", 
                             parse_mode='Markdown', reply_markup=markup)
            bot.answer_callback_query(call.id, "تم إرسال السؤال!")
        
        elif call.data.startswith('answer_'):
            answer_index = int(call.data.replace('answer_', ''))
            chat_id = call.message.chat.id
            
            if chat_id in active_quizzes:
                question_data = active_quizzes[chat_id]
                user_id = call.from_user.id
                username = call.from_user.username or call.from_user.full_name
                
                if answer_index == question_data['correct']:
                    # إجابة صحيحة
                    cursor.execute('''INSERT INTO user_points (user_id, username, points, correct_answers, last_activity)
                                      VALUES (?, ?, 10, 1, ?)
                                      ON CONFLICT(user_id) DO UPDATE SET
                                      points = points + 10,
                                      correct_answers = correct_answers + 1,
                                      username = ?,
                                      last_activity = ?''',
                                   (user_id, username, datetime.now().isoformat(),
                                    username, datetime.now().isoformat()))
                    conn.commit()
                    
                    response = f"✅ *إجابة صحيحة!*\n\n{question_data['explanation']}\n\n🏆 لقد كسبت 10 نقاط!"
                    bot.answer_callback_query(call.id, "✅ إجابة صحيحة!", show_alert=True)
                else:
                    # إجابة خاطئة
                    response = f"❌ *إجابة خاطئة*\n\n{question_data['explanation']}"
                    bot.answer_callback_query(call.id, "❌ إجابة خاطئة", show_alert=True)
                
                bot.edit_message_text(response, chat_id, call.message.message_id, parse_mode='Markdown')
                del active_quizzes[chat_id]
        
        elif call.data == 'leaderboard':
            cursor.execute('SELECT username, points, correct_answers FROM user_points ORDER BY points DESC LIMIT 10')
            results = cursor.fetchall()
            
            if results:
                text = "🏆 *أفضل 10 أعضاء:*\n\n"
                for i, (username, points, correct) in enumerate(results):
                    emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
                    text += f"{emoji} {username}: {points} نقطة ({correct} إجابة)\n"
            else:
                text = "لا توجد بيانات بعد!"
            
            bot.send_message(call.message.chat.id, text, parse_mode='Markdown')
            bot.answer_callback_query(call.id, "تم عرض الترتيب")
        
        elif call.data == 'daily_tip':
            tip = random.choice(DAILY_TIPS)
            bot.send_message(call.message.chat.id, tip)
            bot.answer_callback_query(call.id, "تم إرسال النصيحة")
        
    except Exception as e:
        print(f"خطأ في معالج الأزرار: {e}")
        bot.answer_callback_query(call.id, "حدث خطأ")

# دالة كشف أذكى للأرقام المخفية (الوظيفة الأصلية)
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

# معالج الرسائل الرئيسي (مع الحفاظ على وظيفة فلترة الأرقام الأصلية + إضافة فلترة الكلمات المسيئة)
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
    
    # فحص الكلمات المسيئة (الميزة الجديدة)
    offensive_word = check_offensive_words(text)
    if offensive_word:
        try:
            bot.delete_message(chat_id, message.message_id)
            warning = bot.send_message(chat_id, 
                                       f"⚠️ تم حذف رسالة {display_name} لاحتوائها على محتوى غير مناسب")
            time.sleep(10)
            try:
                bot.delete_message(chat_id, warning.message_id)
            except:
                pass
            return
        except Exception as e:
            print(f"خطأ في فلترة الكلمات المسيئة: {e}")
    
    # تحقق من النص أو الكابشن أو اسم العضو (الوظيفة الأصلية)
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
                try:
                    bot.delete_message(chat_id, notice.message_id)
                except:
                    pass
                
            elif violation_count >= 2:
                # حظر دائم
                bot.ban_chat_member(chat_id, user_id)
                
                # إرسال إشعار يُحذف تلقائياً بعد دقيقتين
                notice = bot.send_message(chat_id, f"🚨 تم حظر العضو {display_name} نهائياً بسبب تكرار إرسال أرقام جوالات.")
                time.sleep(120)
                try:
                    bot.delete_message(chat_id, notice.message_id)
                except:
                    pass
            
            # حفظ عدد المخالفات
            cursor.execute('INSERT OR REPLACE INTO violations (user_id, count) VALUES (?, ?)',
                           (user_id, violation_count))
            conn.commit()
            
        except Exception as e:
            print(f"خطأ: {e}")

# وظائف الجدولة التلقائية (Scheduled Tasks)
def send_morning_azkar():
    """إرسال أذكار الصباح تلقائياً"""
    try:
        cursor.execute('SELECT setting_value FROM admin_settings WHERE setting_key = "auto_morning_azkar"')
        result = cursor.fetchone()
        if result and result[0] == '1':
            send_azkar(ALLOWED_CHAT_ID, 'الصباح')
    except:
        pass

def send_evening_azkar():
    """إرسال دعاء المساء تلقائياً"""
    try:
        cursor.execute('SELECT setting_value FROM admin_settings WHERE setting_key = "auto_evening_azkar"')
        result = cursor.fetchone()
        if result and result[0] == '1':
            send_azkar(ALLOWED_CHAT_ID, 'المساء')
    except:
        pass

def send_daily_tip_scheduled():
    """إرسال نصيحة يومية"""
    try:
        cursor.execute('SELECT setting_value FROM admin_settings WHERE setting_key = "auto_daily_tip"')
        result = cursor.fetchone()
        if result and result[0] == '1':
            tip = random.choice(DAILY_TIPS)
            bot.send_message(ALLOWED_CHAT_ID, tip)
    except:
        pass

def check_islamic_events_scheduled():
    """فحص الأحداث الإسلامية وإرسال تنبيه"""
    event_message = check_islamic_events()
    if event_message:
        try:
            bot.send_message(ALLOWED_CHAT_ID, event_message)
        except:
            pass

# إعداد الجدولة
def setup_scheduler():
    """إعداد المهام المجدولة"""
    try:
        # أذكار الصباح - 7 صباحاً
        scheduler.add_job(send_morning_azkar, 'cron', hour=7, minute=0)
        
        # دعاء المساء - 6 مساءً
        scheduler.add_job(send_evening_azkar, 'cron', hour=18, minute=0)
        
        # نصيحة يومية - 12 ظهراً
        scheduler.add_job(send_daily_tip_scheduled, 'cron', hour=12, minute=0)
        
        # فحص الأحداث الإسلامية - يومياً 8 صباحاً
        scheduler.add_job(check_islamic_events_scheduled, 'cron', hour=8, minute=0)
        
        scheduler.start()
    except:
        pass

# Flask Routes
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
    return "البوت جاهز والـ webhook مُعيَّن! بوت الأذكار الإسلامية يعمل فقط في القروب المحدد.", 200

if __name__ == '__main__':
    setup_scheduler()
    app.run(debug=True)
