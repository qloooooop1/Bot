#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Islamic Adhkar Bot
بوت الأذكار الإسلامية
"""

import telebot
import sqlite3
import random
import logging
from datetime import datetime, time as dt_time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# إعداد تسجيل الأحداث
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# توكن البوت - احصل عليه من @BotFather
# Bot Token - Get it from @BotFather
# ⚠️ IMPORTANT: Replace with your own bot token!
BOT_TOKEN = '7812533121:AAFyxg2EeeB4WqFpHecR1gdGUdg9Or7Evlk'  # استبدل هذا بتوكن البوت الخاص بك
bot = telebot.TeleBot(BOT_TOKEN)

# المنطقة الزمنية (توقيت الرياض)
TIMEZONE = pytz.timezone('Asia/Riyadh')

# قاعدة البيانات
conn = sqlite3.connect('adhkar_bot.db', check_same_thread=False)
cursor = conn.cursor()

# إنشاء الجداول
def init_database():
    """إنشاء جداول قاعدة البيانات"""
    
    # جدول إعدادات المجموعات
    cursor.execute('''CREATE TABLE IF NOT EXISTS group_settings (
        chat_id INTEGER PRIMARY KEY,
        interval_minutes INTEGER DEFAULT 60,
        morning_adhkar_enabled INTEGER DEFAULT 1,
        evening_adhkar_enabled INTEGER DEFAULT 1,
        friday_kahf_enabled INTEGER DEFAULT 1,
        friday_dua_enabled INTEGER DEFAULT 1,
        bedtime_enabled INTEGER DEFAULT 1,
        random_content_enabled INTEGER DEFAULT 1,
        send_text INTEGER DEFAULT 1,
        send_images INTEGER DEFAULT 1,
        send_audio INTEGER DEFAULT 1,
        send_pdf INTEGER DEFAULT 1
    )''')
    
    # جدول أذكار الصباح
    cursor.execute('''CREATE TABLE IF NOT EXISTS morning_adhkar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        repeat_count INTEGER DEFAULT 1
    )''')
    
    # جدول أذكار المساء
    cursor.execute('''CREATE TABLE IF NOT EXISTS evening_adhkar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        repeat_count INTEGER DEFAULT 1
    )''')
    
    # جدول الأدعية العشوائية
    cursor.execute('''CREATE TABLE IF NOT EXISTS random_dua (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL
    )''')
    
    # جدول الآيات القرآنية
    cursor.execute('''CREATE TABLE IF NOT EXISTS quran_verses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        surah_name TEXT,
        verse_number TEXT
    )''')
    
    # جدول أدعية يوم الجمعة
    cursor.execute('''CREATE TABLE IF NOT EXISTS friday_dua (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL
    )''')
    
    conn.commit()
    
    # إضافة محتوى افتراضي إذا كانت الجداول فارغة
    add_default_content()

def add_default_content():
    """إضافة محتوى افتراضي للأذكار والأدعية"""
    
    # أذكار الصباح
    morning_adhkar_list = [
        ("🌅 أَصْبَحْنَا وَأَصْبَحَ الْمُلْكُ لِلَّهِ، وَالْحَمْدُ لِلَّهِ، لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ", 1),
        ("☀️ اللَّهُمَّ بِكَ أَصْبَحْنَا، وَبِكَ أَمْسَيْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ النُّشُورُ", 1),
        ("🤲 اللَّهُمَّ أَنْتَ رَبِّي لَا إِلَهَ إِلَّا أَنْتَ، خَلَقْتَنِي وَأَنَا عَبْدُكَ، وَأَنَا عَلَى عَهْدِكَ وَوَعْدِكَ مَا اسْتَطَعْتُ", 1),
        ("🕌 أَصْبَحْنَا عَلَى فِطْرَةِ الْإِسْلَامِ، وَعَلَى كَلِمَةِ الْإِخْلَاصِ، وَعَلَى دِينِ نَبِيِّنَا مُحَمَّدٍ ﷺ، وَعَلَى مِلَّةِ أَبِينَا إِبْرَاهِيمَ", 1),
        ("📿 سُبْحَانَ اللَّهِ وَبِحَمْدِهِ عَدَدَ خَلْقِهِ، وَرِضَا نَفْسِهِ، وَزِنَةَ عَرْشِهِ، وَمِدَادَ كَلِمَاتِهِ", 3),
        ("✨ لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ", 100),
        ("🌟 سُبْحَانَ اللَّهِ وَبِحَمْدِهِ", 100),
        ("💫 أَسْتَغْفِرُ اللَّهَ وَأَتُوبُ إِلَيْهِ", 100),
    ]
    
    cursor.execute('SELECT COUNT(*) FROM morning_adhkar')
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO morning_adhkar (content, repeat_count) VALUES (?, ?)', 
                          morning_adhkar_list)
    
    # أذكار المساء
    evening_adhkar_list = [
        ("🌙 أَمْسَيْنَا وَأَمْسَى الْمُلْكُ لِلَّهِ، وَالْحَمْدُ لِلَّهِ، لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ", 1),
        ("🌆 اللَّهُمَّ بِكَ أَمْسَيْنَا، وَبِكَ أَصْبَحْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ الْمَصِيرُ", 1),
        ("🤲 اللَّهُمَّ أَنْتَ رَبِّي لَا إِلَهَ إِلَّا أَنْتَ، خَلَقْتَنِي وَأَنَا عَبْدُكَ، وَأَنَا عَلَى عَهْدِكَ وَوَعْدِكَ مَا اسْتَطَعْتُ", 1),
        ("🕌 أَمْسَيْنَا عَلَى فِطْرَةِ الْإِسْلَامِ، وَعَلَى كَلِمَةِ الْإِخْلَاصِ، وَعَلَى دِينِ نَبِيِّنَا مُحَمَّدٍ ﷺ، وَعَلَى مِلَّةِ أَبِينَا إِبْرَاهِيمَ", 1),
        ("⭐ اللَّهُمَّ إِنِّي أَمْسَيْتُ أُشْهِدُكَ وَأُشْهِدُ حَمَلَةَ عَرْشِكَ، وَمَلَائِكَتَكَ وَجَمِيعَ خَلْقِكَ، أَنَّكَ أَنْتَ اللَّهُ لَا إِلَهَ إِلَّا أَنْتَ", 1),
        ("📿 سُبْحَانَ اللَّهِ وَبِحَمْدِهِ عَدَدَ خَلْقِهِ، وَرِضَا نَفْسِهِ، وَزِنَةَ عَرْشِهِ، وَمِدَادَ كَلِمَاتِهِ", 3),
        ("✨ لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ", 100),
        ("🌟 سُبْحَانَ اللَّهِ وَبِحَمْدِهِ", 100),
    ]
    
    cursor.execute('SELECT COUNT(*) FROM evening_adhkar')
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO evening_adhkar (content, repeat_count) VALUES (?, ?)', 
                          evening_adhkar_list)
    
    # أدعية عشوائية
    random_dua_list = [
        "🤲 اللَّهُمَّ إِنِّي أَسْأَلُكَ الْهُدَى وَالتُّقَى وَالْعَفَافَ وَالْغِنَى",
        "💚 رَبِّ اشْرَحْ لِي صَدْرِي، وَيَسِّرْ لِي أَمْرِي",
        "🌟 اللَّهُمَّ إِنِّي أَعُوذُ بِكَ مِنَ الْهَمِّ وَالْحَزَنِ، وَأَعُوذُ بِكَ مِنَ الْعَجْزِ وَالْكَسَلِ",
        "✨ رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الْآخِرَةِ حَسَنَةً وَقِنَا عَذَابَ النَّارِ",
        "🕌 اللَّهُمَّ أَصْلِحْ لِي دِينِي الَّذِي هُوَ عِصْمَةُ أَمْرِي، وَأَصْلِحْ لِي دُنْيَايَ الَّتِي فِيهَا مَعَاشِي",
        "🌙 اللَّهُمَّ اغْفِرْ لِي ذَنْبِي كُلَّهُ، دِقَّهُ وَجِلَّهُ، وَأَوَّلَهُ وَآخِرَهُ، وَعَلَانِيَتَهُ وَسِرَّهُ",
        "☀️ اللَّهُمَّ إِنِّي أَسْأَلُكَ عِلْمًا نَافِعًا، وَرِزْقًا طَيِّبًا، وَعَمَلًا مُتَقَبَّلًا",
        "🌺 رَبِّ أَوْزِعْنِي أَنْ أَشْكُرَ نِعْمَتَكَ الَّتِي أَنْعَمْتَ عَلَيَّ وَعَلَى وَالِدَيَّ",
    ]
    
    cursor.execute('SELECT COUNT(*) FROM random_dua')
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO random_dua (content) VALUES (?)', 
                          [(dua,) for dua in random_dua_list])
    
    # آيات قرآنية
    quran_verses_list = [
        ("﴿ اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ ۚ لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ ﴾", "البقرة", "255"),
        ("﴿ وَإِلَٰهُكُمْ إِلَٰهٌ وَاحِدٌ ۖ لَا إِلَٰهَ إِلَّا هُوَ الرَّحْمَٰنُ الرَّحِيمُ ﴾", "البقرة", "163"),
        ("﴿ فَاذْكُرُونِي أَذْكُرْكُمْ وَاشْكُرُوا لِي وَلَا تَكْفُرُونِ ﴾", "البقرة", "152"),
        ("﴿ يَا أَيُّهَا الَّذِينَ آمَنُوا اسْتَعِينُوا بِالصَّبْرِ وَالصَّلَاةِ ۚ إِنَّ اللَّهَ مَعَ الصَّابِرِينَ ﴾", "البقرة", "153"),
        ("﴿ وَمَا خَلَقْتُ الْجِنَّ وَالْإِنسَ إِلَّا لِيَعْبُدُونِ ﴾", "الذاريات", "56"),
        ("﴿ فَإِنَّ مَعَ الْعُسْرِ يُسْرًا * إِنَّ مَعَ الْعُسْرِ يُسْرًا ﴾", "الشرح", "5-6"),
    ]
    
    cursor.execute('SELECT COUNT(*) FROM quran_verses')
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO quran_verses (content, surah_name, verse_number) VALUES (?, ?, ?)', 
                          quran_verses_list)
    
    # أدعية يوم الجمعة
    friday_dua_list = [
        "🕌 اللَّهُمَّ صَلِّ وَسَلِّمْ عَلَى نَبِيِّنَا مُحَمَّدٍ ﷺ",
        "✨ اللَّهُمَّ إِنِّي أَسْأَلُكَ مِنْ فَضْلِكَ، فَإِنَّ فَضْلَكَ وَاسِعٌ",
        "🌟 رَبَّنَا لَا تُزِغْ قُلُوبَنَا بَعْدَ إِذْ هَدَيْتَنَا وَهَبْ لَنَا مِن لَّدُنكَ رَحْمَةً",
        "💚 اللَّهُمَّ إِنَّا نَسْأَلُكَ الْجَنَّةَ وَنَعُوذُ بِكَ مِنَ النَّارِ",
        "🤲 اللَّهُمَّ بَارِكْ لَنَا فِي يَوْمِ الْجُمُعَةِ وَاجْعَلْهُ خَيْرَ أَيَّامِنَا",
    ]
    
    cursor.execute('SELECT COUNT(*) FROM friday_dua')
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO friday_dua (content) VALUES (?)', 
                          [(dua,) for dua in friday_dua_list])
    
    conn.commit()

def get_group_settings(chat_id):
    """الحصول على إعدادات المجموعة أو إنشاء إعدادات افتراضية"""
    cursor.execute('SELECT * FROM group_settings WHERE chat_id = ?', (chat_id,))
    settings = cursor.fetchone()
    
    if not settings:
        cursor.execute('''INSERT INTO group_settings (chat_id) VALUES (?)''', (chat_id,))
        conn.commit()
        cursor.execute('SELECT * FROM group_settings WHERE chat_id = ?', (chat_id,))
        settings = cursor.fetchone()
    
    return settings

def is_admin(chat_id, user_id):
    """التحقق من أن المستخدم مشرف في المجموعة"""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except:
        return False

# معالجات الأوامر
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """رسالة الترحيب والمساعدة"""
    welcome_text = """
🕌 *بوت الأذكار الإسلامية* 🕌

السلام عليكم ورحمة الله وبركاته 🌟

أنا بوت مخصص لإرسال الأذكار والأدعية الإسلامية تلقائياً في مجموعتك.

*المميزات:*
📿 أذكار الصباح (5:00 صباحاً)
🌙 أذكار المساء (6:00 مساءً)
📖 سورة الكهف (قبل صلاة الجمعة بساعة)
🕌 أدعية يوم الجمعة
💫 أدعية وآيات متنوعة على مدار اليوم
😴 تذكير قبل النوم بقراءة سورة الملك

*أوامر المشرفين:*
/settings - عرض الإعدادات الحالية
/set_interval <دقائق> - تغيير الفاصل الزمني بين الأذكار
/enable_morning - تفعيل أذكار الصباح
/disable_morning - إلغاء أذكار الصباح
/enable_evening - تفعيل أذكار المساء
/disable_evening - إلغاء أذكار المساء
/enable_friday - تفعيل أذكار الجمعة
/disable_friday - إلغاء أذكار الجمعة
/enable_random - تفعيل المحتوى العشوائي
/disable_random - إلغاء المحتوى العشوائي

بارك الله فيكم 🤲
"""
    try:
        bot.reply_to(message, welcome_text, parse_mode='Markdown')
    except:
        bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['settings'])
def show_settings(message):
    """عرض إعدادات المجموعة"""
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "⚠️ هذا الأمر يعمل فقط في المجموعات")
        return
    
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "⚠️ هذا الأمر متاح للمشرفين فقط")
        return
    
    settings = get_group_settings(message.chat.id)
    
    settings_text = f"""
⚙️ *إعدادات المجموعة الحالية:*

⏱ الفاصل الزمني: {settings[1]} دقيقة

*الميزات المفعلة:*
{'✅' if settings[2] else '❌'} أذكار الصباح (5:00 ص)
{'✅' if settings[3] else '❌'} أذكار المساء (6:00 م)
{'✅' if settings[4] else '❌'} سورة الكهف (الجمعة)
{'✅' if settings[5] else '❌'} أدعية الجمعة
{'✅' if settings[6] else '❌'} تذكير قبل النوم
{'✅' if settings[7] else '❌'} محتوى عشوائي

*أنواع المحتوى:*
{'✅' if settings[8] else '❌'} نصوص
{'✅' if settings[9] else '❌'} صور
{'✅' if settings[10] else '❌'} صوتيات
{'✅' if settings[11] else '❌'} ملفات PDF

استخدم /help لرؤية الأوامر المتاحة 📝
"""
    try:
        bot.reply_to(message, settings_text, parse_mode='Markdown')
    except:
        bot.reply_to(message, settings_text)

@bot.message_handler(commands=['set_interval'])
def set_interval(message):
    """تغيير الفاصل الزمني بين الأذكار"""
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "⚠️ هذا الأمر يعمل فقط في المجموعات")
        return
    
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "⚠️ هذا الأمر متاح للمشرفين فقط")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "❌ الاستخدام: /set_interval <دقائق>\nمثال: /set_interval 30")
            return
        
        interval = int(parts[1])
        if interval < 10 or interval > 1440:
            bot.reply_to(message, "❌ الفاصل الزمني يجب أن يكون بين 10 و 1440 دقيقة")
            return
        
        cursor.execute('UPDATE group_settings SET interval_minutes = ? WHERE chat_id = ?', 
                      (interval, message.chat.id))
        conn.commit()
        
        bot.reply_to(message, f"✅ تم تعيين الفاصل الزمني إلى {interval} دقيقة")
    except ValueError:
        bot.reply_to(message, "❌ الرجاء إدخال رقم صحيح")
    except Exception as e:
        logger.error(f"Error in set_interval: {e}")
        bot.reply_to(message, "❌ حدث خطأ أثناء تحديث الإعدادات")

# أوامر التفعيل/الإلغاء
@bot.message_handler(commands=['enable_morning'])
def enable_morning(message):
    if message.chat.type in ['group', 'supergroup'] and is_admin(message.chat.id, message.from_user.id):
        cursor.execute('UPDATE group_settings SET morning_adhkar_enabled = 1 WHERE chat_id = ?', 
                      (message.chat.id,))
        conn.commit()
        bot.reply_to(message, "✅ تم تفعيل أذكار الصباح")

@bot.message_handler(commands=['disable_morning'])
def disable_morning(message):
    if message.chat.type in ['group', 'supergroup'] and is_admin(message.chat.id, message.from_user.id):
        cursor.execute('UPDATE group_settings SET morning_adhkar_enabled = 0 WHERE chat_id = ?', 
                      (message.chat.id,))
        conn.commit()
        bot.reply_to(message, "❌ تم إلغاء أذكار الصباح")

@bot.message_handler(commands=['enable_evening'])
def enable_evening(message):
    if message.chat.type in ['group', 'supergroup'] and is_admin(message.chat.id, message.from_user.id):
        cursor.execute('UPDATE group_settings SET evening_adhkar_enabled = 1 WHERE chat_id = ?', 
                      (message.chat.id,))
        conn.commit()
        bot.reply_to(message, "✅ تم تفعيل أذكار المساء")

@bot.message_handler(commands=['disable_evening'])
def disable_evening(message):
    if message.chat.type in ['group', 'supergroup'] and is_admin(message.chat.id, message.from_user.id):
        cursor.execute('UPDATE group_settings SET evening_adhkar_enabled = 0 WHERE chat_id = ?', 
                      (message.chat.id,))
        conn.commit()
        bot.reply_to(message, "❌ تم إلغاء أذكار المساء")

@bot.message_handler(commands=['enable_friday'])
def enable_friday(message):
    if message.chat.type in ['group', 'supergroup'] and is_admin(message.chat.id, message.from_user.id):
        cursor.execute('UPDATE group_settings SET friday_kahf_enabled = 1, friday_dua_enabled = 1 WHERE chat_id = ?', 
                      (message.chat.id,))
        conn.commit()
        bot.reply_to(message, "✅ تم تفعيل أذكار يوم الجمعة")

@bot.message_handler(commands=['disable_friday'])
def disable_friday(message):
    if message.chat.type in ['group', 'supergroup'] and is_admin(message.chat.id, message.from_user.id):
        cursor.execute('UPDATE group_settings SET friday_kahf_enabled = 0, friday_dua_enabled = 0 WHERE chat_id = ?', 
                      (message.chat.id,))
        conn.commit()
        bot.reply_to(message, "❌ تم إلغاء أذكار يوم الجمعة")

@bot.message_handler(commands=['enable_random'])
def enable_random(message):
    if message.chat.type in ['group', 'supergroup'] and is_admin(message.chat.id, message.from_user.id):
        cursor.execute('UPDATE group_settings SET random_content_enabled = 1 WHERE chat_id = ?', 
                      (message.chat.id,))
        conn.commit()
        bot.reply_to(message, "✅ تم تفعيل المحتوى العشوائي")

@bot.message_handler(commands=['disable_random'])
def disable_random(message):
    if message.chat.type in ['group', 'supergroup'] and is_admin(message.chat.id, message.from_user.id):
        cursor.execute('UPDATE group_settings SET random_content_enabled = 0 WHERE chat_id = ?', 
                      (message.chat.id,))
        conn.commit()
        bot.reply_to(message, "❌ تم إلغاء المحتوى العشوائي")

# وظائف إرسال الأذكار
def send_morning_adhkar():
    """إرسال أذكار الصباح لجميع المجموعات"""
    cursor.execute('SELECT chat_id FROM group_settings WHERE morning_adhkar_enabled = 1')
    groups = cursor.fetchall()
    
    cursor.execute('SELECT content, repeat_count FROM morning_adhkar')
    adhkar = cursor.fetchall()
    
    header = "🌅 *أذكار الصباح* 🌅\n\nصباح الخير والبركة 🌸\n" + "─" * 30 + "\n\n"
    
    for (chat_id,) in groups:
        try:
            message = header
            for content, repeat_count in adhkar:
                if repeat_count > 1:
                    message += f"{content}\n📌 ({repeat_count} مرات)\n\n"
                else:
                    message += f"{content}\n\n"
            
            message += "─" * 30 + "\n\n🤲 تقبل الله منا ومنكم صالح الأعمال"
            
            try:
                bot.send_message(chat_id, message, parse_mode='Markdown')
            except:
                bot.send_message(chat_id, message)
        except Exception as e:
            logger.error(f"Error sending morning adhkar to {chat_id}: {e}")

def send_evening_adhkar():
    """إرسال أذكار المساء لجميع المجموعات"""
    cursor.execute('SELECT chat_id FROM group_settings WHERE evening_adhkar_enabled = 1')
    groups = cursor.fetchall()
    
    cursor.execute('SELECT content, repeat_count FROM evening_adhkar')
    adhkar = cursor.fetchall()
    
    header = "🌙 *أذكار المساء* 🌙\n\nمساء الخير والإيمان 🌟\n" + "─" * 30 + "\n\n"
    
    for (chat_id,) in groups:
        try:
            message = header
            for content, repeat_count in adhkar:
                if repeat_count > 1:
                    message += f"{content}\n📌 ({repeat_count} مرات)\n\n"
                else:
                    message += f"{content}\n\n"
            
            message += "─" * 30 + "\n\n🤲 اللهم أمسِنا وأمسِ علينا بالخير والبركة"
            
            try:
                bot.send_message(chat_id, message, parse_mode='Markdown')
            except:
                bot.send_message(chat_id, message)
        except Exception as e:
            logger.error(f"Error sending evening adhkar to {chat_id}: {e}")

def send_friday_kahf():
    """إرسال تذكير بسورة الكهف يوم الجمعة"""
    cursor.execute('SELECT chat_id FROM group_settings WHERE friday_kahf_enabled = 1')
    groups = cursor.fetchall()
    
    message = """
📖 *تذكير بسورة الكهف* 📖

🕌 السلام عليكم ورحمة الله وبركاته

🌟 من قرأ سورة الكهف يوم الجمعة أضاء له من النور ما بين الجمعتين

📿 بادروا بقراءة سورة الكهف قبل صلاة الجمعة

✨ ﴿ الْحَمْدُ لِلَّهِ الَّذِي أَنزَلَ عَلَىٰ عَبْدِهِ الْكِتَابَ وَلَمْ يَجْعَل لَّهُ عِوَجًا ﴾

بارك الله فيكم 🤲
"""
    
    for (chat_id,) in groups:
        try:
            try:
                bot.send_message(chat_id, message, parse_mode='Markdown')
            except:
                bot.send_message(chat_id, message)
        except Exception as e:
            logger.error(f"Error sending Friday Kahf to {chat_id}: {e}")

def send_friday_dua():
    """إرسال أدعية يوم الجمعة"""
    cursor.execute('SELECT chat_id FROM group_settings WHERE friday_dua_enabled = 1')
    groups = cursor.fetchall()
    
    cursor.execute('SELECT content FROM friday_dua ORDER BY RANDOM() LIMIT 3')
    duas = cursor.fetchall()
    
    header = "🕌 *أدعية يوم الجمعة* 🕌\n\n" + "─" * 30 + "\n\n"
    
    for (chat_id,) in groups:
        try:
            message = header
            for (dua,) in duas:
                message += f"{dua}\n\n"
            
            message += "─" * 30 + "\n\n💚 جمعة مباركة وأعمال صالحة متقبلة"
            
            try:
                bot.send_message(chat_id, message, parse_mode='Markdown')
            except:
                bot.send_message(chat_id, message)
        except Exception as e:
            logger.error(f"Error sending Friday dua to {chat_id}: {e}")

def send_bedtime_reminder():
    """إرسال تذكير قبل النوم"""
    cursor.execute('SELECT chat_id FROM group_settings WHERE bedtime_enabled = 1')
    groups = cursor.fetchall()
    
    message = """
😴 *تذكير قبل النوم* 🌙

السلام عليكم ورحمة الله 💫

🌟 قبل أن تنام، لا تنسَ:

📿 قراءة سورة الملك (تبارك)
✨ أذكار النوم
🤲 الاستغفار والتوبة

﴿ تَبَارَكَ الَّذِي بِيَدِهِ الْمُلْكُ وَهُوَ عَلَىٰ كُلِّ شَيْءٍ قَدِيرٌ ﴾

تصبحون على خير 🌙💤
"""
    
    for (chat_id,) in groups:
        try:
            try:
                bot.send_message(chat_id, message, parse_mode='Markdown')
            except:
                bot.send_message(chat_id, message)
        except Exception as e:
            logger.error(f"Error sending bedtime reminder to {chat_id}: {e}")

def send_random_content():
    """إرسال محتوى عشوائي (دعاء أو آية قرآنية)"""
    cursor.execute('SELECT chat_id FROM group_settings WHERE random_content_enabled = 1')
    groups = cursor.fetchall()
    
    # اختيار نوع المحتوى عشوائياً
    content_type = random.choice(['dua', 'quran'])
    
    if content_type == 'dua':
        cursor.execute('SELECT content FROM random_dua ORDER BY RANDOM() LIMIT 1')
        result = cursor.fetchone()
        if result:
            header = "💫 *دعاء* 💫\n\n"
            message = header + result[0] + "\n\n🤲 آمين"
    else:
        cursor.execute('SELECT content, surah_name, verse_number FROM quran_verses ORDER BY RANDOM() LIMIT 1')
        result = cursor.fetchone()
        if result:
            content, surah, verse = result
            header = "📖 *من القرآن الكريم* 📖\n\n"
            footer = f"\n\n﴿ سورة {surah} - آية {verse} ﴾"
            message = header + content + footer
    
    for (chat_id,) in groups:
        try:
            try:
                bot.send_message(chat_id, message, parse_mode='Markdown')
            except:
                bot.send_message(chat_id, message)
        except Exception as e:
            logger.error(f"Error sending random content to {chat_id}: {e}")

# إعداد المجدول
def setup_scheduler():
    """إعداد جدولة المهام"""
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    
    # أذكار الصباح - 5:00 صباحاً
    scheduler.add_job(
        send_morning_adhkar,
        CronTrigger(hour=5, minute=0, timezone=TIMEZONE),
        id='morning_adhkar',
        replace_existing=True
    )
    
    # أذكار المساء - 6:00 مساءً
    scheduler.add_job(
        send_evening_adhkar,
        CronTrigger(hour=18, minute=0, timezone=TIMEZONE),
        id='evening_adhkar',
        replace_existing=True
    )
    
    # سورة الكهف - الجمعة الساعة 11:00 صباحاً (قبل الصلاة بساعة تقريباً)
    scheduler.add_job(
        send_friday_kahf,
        CronTrigger(day_of_week='fri', hour=11, minute=0, timezone=TIMEZONE),
        id='friday_kahf',
        replace_existing=True
    )
    
    # أدعية يوم الجمعة - الجمعة الساعة 10:00 صباحاً
    scheduler.add_job(
        send_friday_dua,
        CronTrigger(day_of_week='fri', hour=10, minute=0, timezone=TIMEZONE),
        id='friday_dua',
        replace_existing=True
    )
    
    # تذكير قبل النوم - 10:00 مساءً
    scheduler.add_job(
        send_bedtime_reminder,
        CronTrigger(hour=22, minute=0, timezone=TIMEZONE),
        id='bedtime_reminder',
        replace_existing=True
    )
    
    # محتوى عشوائي - كل ساعة من 6 صباحاً إلى 5 مساءً
    scheduler.add_job(
        send_random_content,
        CronTrigger(hour='6-17', minute=30, timezone=TIMEZONE),
        id='random_content',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started successfully")
    return scheduler

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    logger.info("Starting Islamic Adhkar Bot...")
    
    # تهيئة قاعدة البيانات
    init_database()
    
    # إعداد المجدول
    scheduler = setup_scheduler()
    
    logger.info("Bot is ready! Starting polling...")
    
    # بدء التشغيل بـ long polling
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        scheduler.shutdown()
    except Exception as e:
        logger.error(f"Bot polling error: {e}")
        scheduler.shutdown()

if __name__ == '__main__':
    main()
