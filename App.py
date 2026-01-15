import os
import telebot
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import random
import sqlite3
from datetime import datetime

# ============= إعدادات ثابتة =============
# وضع التشغيل مضبوط مباشرة على webhook
BOT_MODE = 'webhook'

# رابط Webhook الثابت
WEBHOOK_URL = 'https://bot-8c0e.onrender.com'

# الحصول على التوكن من متغير البيئة أو قيمة افتراضية
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')

# التحقق من وجود التوكن
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required. Please set it before running the bot.")

# المنفذ
PORT = int(os.environ.get('PORT', 5000))

# المنطقة الزمنية
TIMEZONE = pytz.timezone('Asia/Riyadh')

# إنشاء مسار آمن للـ webhook (hash من التوكن بدلاً من التوكن نفسه)
import hashlib
WEBHOOK_PATH = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()

# ============= إنشاء البوت وتطبيق Flask =============
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# إنشاء المجدول
scheduler = BackgroundScheduler(timezone=TIMEZONE)
scheduler.start()

# ============= قاعدة البيانات =============
def init_db():
    """إنشاء قاعدة البيانات وجداولها"""
    conn = sqlite3.connect('bot_settings.db')
    c = conn.cursor()
    
    # جدول إعدادات المجموعات
    c.execute('''CREATE TABLE IF NOT EXISTS chat_settings
                 (chat_id INTEGER PRIMARY KEY,
                  is_enabled INTEGER DEFAULT 1,
                  morning_azkar INTEGER DEFAULT 1,
                  evening_azkar INTEGER DEFAULT 1,
                  friday_sura INTEGER DEFAULT 1,
                  friday_dua INTEGER DEFAULT 1,
                  sleep_message INTEGER DEFAULT 1,
                  random_content INTEGER DEFAULT 1,
                  delete_service_messages INTEGER DEFAULT 1,
                  content_interval INTEGER DEFAULT 180,
                  morning_time TEXT DEFAULT '05:00',
                  evening_time TEXT DEFAULT '18:00',
                  sleep_time TEXT DEFAULT '22:00')''')
    
    conn.commit()
    conn.close()

def get_chat_settings(chat_id):
    """الحصول على إعدادات المجموعة"""
    conn = sqlite3.connect('bot_settings.db')
    c = conn.cursor()
    c.execute('SELECT * FROM chat_settings WHERE chat_id = ?', (chat_id,))
    result = c.fetchone()
    conn.close()
    
    if result is None:
        # إنشاء إعدادات افتراضية
        conn = sqlite3.connect('bot_settings.db')
        c = conn.cursor()
        c.execute('INSERT INTO chat_settings (chat_id) VALUES (?)', (chat_id,))
        conn.commit()
        conn.close()
        return get_chat_settings(chat_id)
    
    return {
        'chat_id': result[0],
        'is_enabled': result[1],
        'morning_azkar': result[2],
        'evening_azkar': result[3],
        'friday_sura': result[4],
        'friday_dua': result[5],
        'sleep_message': result[6],
        'random_content': result[7],
        'delete_service_messages': result[8],
        'content_interval': result[9],
        'morning_time': result[10],
        'evening_time': result[11],
        'sleep_time': result[12]
    }

def update_chat_setting(chat_id, setting, value):
    """تحديث إعداد معين للمجموعة"""
    conn = sqlite3.connect('bot_settings.db')
    c = conn.cursor()
    c.execute(f'UPDATE chat_settings SET {setting} = ? WHERE chat_id = ?', (value, chat_id))
    conn.commit()
    conn.close()

# ============= المحتوى الإسلامي =============
# أذكار الصباح
MORNING_AZKAR = [
    "🌅 *أذكار الصباح*\n\n"
    "﴿ اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ ۚ لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ ۚ لَّهُ مَا فِي السَّمَاوَاتِ وَمَا فِي الْأَرْضِ ۗ مَن ذَا الَّذِي يَشْفَعُ عِندَهُ إِلَّا بِإِذْنِهِ ۚ يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَيْءٍ مِّنْ عِلْمِهِ إِلَّا بِمَا شَاءَ ۚ وَسِعَ كُرْسِيُّهُ السَّمَاوَاتِ وَالْأَرْضَ ۖ وَلَا يَئُودُهُ حِفْظُهُمَا ۚ وَهُوَ الْعَلِيُّ الْعَظِيمُ ﴾\n\n"
    "📿 آية الكرسي - [البقرة: 255]",
    
    "🌅 *أذكار الصباح*\n\n"
    "أَصْبَحْنَا وَأَصْبَحَ الْمُلْكُ لِلَّهِ، وَالْحَمْدُ لِلَّهِ، لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ، رَبِّ أَسْأَلُكَ خَيْرَ مَا فِي هَذَا الْيَوْمِ وَخَيْرَ مَا بَعْدَهُ، وَأَعُوذُ بِكَ مِنْ شَرِّ مَا فِي هَذَا الْيَوْمِ وَشَرِّ مَا بَعْدَهُ، رَبِّ أَعُوذُ بِكَ مِنَ الْكَسَلِ وَسُوءِ الْكِبَرِ، رَبِّ أَعُوذُ بِكَ مِنْ عَذَابٍ فِي النَّارِ وَعَذَابٍ فِي الْقَبْرِ\n\n"
    "✨ (مرة واحدة)",
    
    "🌅 *أذكار الصباح*\n\n"
    "اللَّهُمَّ بِكَ أَصْبَحْنَا، وَبِكَ أَمْسَيْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ النُّشُورُ\n\n"
    "✨ (مرة واحدة)",
    
    "🌅 *أذكار الصباح*\n\n"
    "أَصْبَحْنَا عَلَى فِطْرَةِ الْإِسْلَامِ، وَعَلَى كَلِمَةِ الْإِخْلَاصِ، وَعَلَى دِينِ نَبِيِّنَا مُحَمَّدٍ ﷺ، وَعَلَى مِلَّةِ أَبِينَا إِبْرَاهِيمَ، حَنِيفًا مُسْلِمًا وَمَا كَانَ مِنَ الْمُشْرِكِينَ\n\n"
    "✨ (مرة واحدة)",
    
    "🌅 *أذكار الصباح*\n\n"
    "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ\n\n"
    "✨ (مائة مرة)",
    
    "🌅 *أذكار الصباح*\n\n"
    "لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ\n\n"
    "✨ (عشر مرات أو مرة واحدة عند الاستيقاظ)",
    
    "🌅 *أذكار الصباح*\n\n"
    "اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَافِيَةَ فِي الدُّنْيَا وَالْآخِرَةِ، اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَفْوَ وَالْعَافِيَةَ فِي دِينِي وَدُنْيَايَ وَأَهْلِي وَمَالِي، اللَّهُمَّ اسْتُرْ عَوْرَاتِي، وَآمِنْ رَوْعَاتِي، اللَّهُمَّ احْفَظْنِي مِنْ بَيْنِ يَدَيَّ، وَمِنْ خَلْفِي، وَعَنْ يَمِينِي، وَعَنْ شِمَالِي، وَمِنْ فَوْقِي، وَأَعُوذُ بِعَظَمَتِكَ أَنْ أُغْتَالَ مِنْ تَحْتِي\n\n"
    "✨ (مرة واحدة)",
    
    "🌅 *أذكار الصباح*\n\n"
    "اللَّهُمَّ عَالِمَ الْغَيْبِ وَالشَّهَادَةِ فَاطِرَ السَّمَاوَاتِ وَالْأَرْضِ، رَبَّ كُلِّ شَيْءٍ وَمَلِيكَهُ، أَشْهَدُ أَنْ لَا إِلَهَ إِلَّا أَنْتَ، أَعُوذُ بِكَ مِنْ شَرِّ نَفْسِي، وَمِنْ شَرِّ الشَّيْطَانِ وَشِرْكِهِ، وَأَنْ أَقْتَرِفَ عَلَى نَفْسِي سُوءًا أَوْ أَجُرَّهُ إِلَى مُسْلِمٍ\n\n"
    "✨ (مرة واحدة)",
    
    "🌅 *أذكار الصباح*\n\n"
    "بِسْمِ اللَّهِ الَّذِي لَا يَضُرُّ مَعَ اسْمِهِ شَيْءٌ فِي الْأَرْضِ وَلَا فِي السَّمَاءِ وَهُوَ السَّمِيعُ الْعَلِيمُ\n\n"
    "✨ (ثلاث مرات)",
    
    "🌅 *أذكار الصباح*\n\n"
    "رَضِيتُ بِاللَّهِ رَبًّا، وَبِالْإِسْلَامِ دِينًا، وَبِمُحَمَّدٍ ﷺ نَبِيًّا\n\n"
    "✨ (ثلاث مرات)",
    
    "🌅 *أذكار الصباح*\n\n"
    "يَا حَيُّ يَا قَيُّومُ بِرَحْمَتِكَ أَسْتَغِيثُ، أَصْلِحْ لِي شَأْنِي كُلَّهُ، وَلَا تَكِلْنِي إِلَى نَفْسِي طَرْفَةَ عَيْنٍ\n\n"
    "✨ (مرة واحدة)",
    
    "🌅 *أذكار الصباح*\n\n"
    "﴿ قُلْ هُوَ اللَّهُ أَحَدٌ * اللَّهُ الصَّمَدُ * لَمْ يَلِدْ وَلَمْ يُولَدْ * وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ ﴾\n\n"
    "📿 سورة الإخلاص (ثلاث مرات)",
]

# أذكار المساء
EVENING_AZKAR = [
    "🌙 *أذكار المساء*\n\n"
    "﴿ اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ ۚ لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ ۚ لَّهُ مَا فِي السَّمَاوَاتِ وَمَا فِي الْأَرْضِ ۗ مَن ذَا الَّذِي يَشْفَعُ عِندَهُ إِلَّا بِإِذْنِهِ ۚ يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَيْءٍ مِّنْ عِلْمِهِ إِلَّا بِمَا شَاءَ ۚ وَسِعَ كُرْسِيُّهُ السَّمَاوَاتِ وَالْأَرْضَ ۖ وَلَا يَئُودُهُ حِفْظُهُمَا ۚ وَهُوَ الْعَلِيُّ الْعَظِيمُ ﴾\n\n"
    "📿 آية الكرسي - [البقرة: 255]",
    
    "🌙 *أذكار المساء*\n\n"
    "أَمْسَيْنَا وَأَمْسَى الْمُلْكُ لِلَّهِ، وَالْحَمْدُ لِلَّهِ، لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ، رَبِّ أَسْأَلُكَ خَيْرَ مَا فِي هَذِهِ اللَّيْلَةِ وَخَيْرَ مَا بَعْدَهَا، وَأَعُوذُ بِكَ مِنْ شَرِّ مَا فِي هَذِهِ اللَّيْلَةِ وَشَرِّ مَا بَعْدَهَا، رَبِّ أَعُوذُ بِكَ مِنَ الْكَسَلِ وَسُوءِ الْكِبَرِ، رَبِّ أَعُوذُ بِكَ مِنْ عَذَابٍ فِي النَّارِ وَعَذَابٍ فِي الْقَبْرِ\n\n"
    "✨ (مرة واحدة)",
    
    "🌙 *أذكار المساء*\n\n"
    "اللَّهُمَّ بِكَ أَمْسَيْنَا، وَبِكَ أَصْبَحْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ الْمَصِيرُ\n\n"
    "✨ (مرة واحدة)",
    
    "🌙 *أذكار المساء*\n\n"
    "أَمْسَيْنَا عَلَى فِطْرَةِ الْإِسْلَامِ، وَعَلَى كَلِمَةِ الْإِخْلَاصِ، وَعَلَى دِينِ نَبِيِّنَا مُحَمَّدٍ ﷺ، وَعَلَى مِلَّةِ أَبِينَا إِبْرَاهِيمَ، حَنِيفًا مُسْلِمًا وَمَا كَانَ مِنَ الْمُشْرِكِينَ\n\n"
    "✨ (مرة واحدة)",
    
    "🌙 *أذكار المساء*\n\n"
    "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ\n\n"
    "✨ (مائة مرة)",
    
    "🌙 *أذكار المساء*\n\n"
    "لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ\n\n"
    "✨ (عشر مرات)",
    
    "🌙 *أذكار المساء*\n\n"
    "اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَافِيَةَ فِي الدُّنْيَا وَالْآخِرَةِ، اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَفْوَ وَالْعَافِيَةَ فِي دِينِي وَدُنْيَايَ وَأَهْلِي وَمَالِي، اللَّهُمَّ اسْتُرْ عَوْرَاتِي، وَآمِنْ رَوْعَاتِي، اللَّهُمَّ احْفَظْنِي مِنْ بَيْنِ يَدَيَّ، وَمِنْ خَلْفِي، وَعَنْ يَمِينِي، وَعَنْ شِمَالِي، وَمِنْ فَوْقِي، وَأَعُوذُ بِعَظَمَتِكَ أَنْ أُغْتَالَ مِنْ تَحْتِي\n\n"
    "✨ (مرة واحدة)",
    
    "🌙 *أذكار المساء*\n\n"
    "اللَّهُمَّ عَالِمَ الْغَيْبِ وَالشَّهَادَةِ فَاطِرَ السَّمَاوَاتِ وَالْأَرْضِ، رَبَّ كُلِّ شَيْءٍ وَمَلِيكَهُ، أَشْهَدُ أَنْ لَا إِلَهَ إِلَّا أَنْتَ، أَعُوذُ بِكَ مِنْ شَرِّ نَفْسِي، وَمِنْ شَرِّ الشَّيْطَانِ وَشِرْكِهِ، وَأَنْ أَقْتَرِفَ عَلَى نَفْسِي سُوءًا أَوْ أَجُرَّهُ إِلَى مُسْلِمٍ\n\n"
    "✨ (مرة واحدة)",
    
    "🌙 *أذكار المساء*\n\n"
    "بِسْمِ اللَّهِ الَّذِي لَا يَضُرُّ مَعَ اسْمِهِ شَيْءٌ فِي الْأَرْضِ وَلَا فِي السَّمَاءِ وَهُوَ السَّمِيعُ الْعَلِيمُ\n\n"
    "✨ (ثلاث مرات)",
    
    "🌙 *أذكار المساء*\n\n"
    "رَضِيتُ بِاللَّهِ رَبًّا، وَبِالْإِسْلَامِ دِينًا، وَبِمُحَمَّدٍ ﷺ نَبِيًّا\n\n"
    "✨ (ثلاث مرات)",
    
    "🌙 *أذكار المساء*\n\n"
    "﴿ قُلْ هُوَ اللَّهُ أَحَدٌ * اللَّهُ الصَّمَدُ * لَمْ يَلِدْ وَلَمْ يُولَدْ * وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ ﴾\n\n"
    "📿 سورة الإخلاص (ثلاث مرات)",
]

# أدعية الجمعة
FRIDAY_DUA = [
    "🕌 *دعاء يوم الجمعة*\n\n"
    "اللَّهُمَّ صَلِّ وَسَلِّمْ وَبَارِكْ عَلَى سَيِّدِنَا مُحَمَّدٍ وَعَلَى آلِهِ وَصَحْبِهِ أَجْمَعِينَ\n\n"
    "✨ قال رسول الله ﷺ: «مَن صلَّى عليَّ صلاةً واحدةً صلَّى اللهُ عليه بها عشرًا»",
    
    "🕌 *دعاء يوم الجمعة*\n\n"
    "اللَّهُمَّ إِنِّي أَسْأَلُكَ مِنَ الْخَيْرِ كُلِّهِ عَاجِلِهِ وَآجِلِهِ، مَا عَلِمْتُ مِنْهُ وَمَا لَمْ أَعْلَمْ، وَأَعُوذُ بِكَ مِنَ الشَّرِّ كُلِّهِ عَاجِلِهِ وَآجِلِهِ، مَا عَلِمْتُ مِنْهُ وَمَا لَمْ أَعْلَمْ\n\n"
    "✨ دعاء مأثور",
]

# تذكير بسورة الكهف
KAHF_REMINDER = (
    "📿 *تذكير بسورة الكهف*\n\n"
    "السلام عليكم ورحمة الله وبركاته\n\n"
    "نُذَكِّرُكُم بقراءة سورة الكهف في هذا اليوم المبارك\n\n"
    "قال رسول الله ﷺ: «مَن قرأَ سورةَ الكَهفِ في يومِ الجُمُعةِ، أضاءَ له مِن النُّورِ ما بيْنَ الجُمُعتَينِ»\n\n"
    "🕌 جعلنا الله وإياكم من المواظبين على الطاعات"
)

# رسالة النوم
SLEEP_MESSAGE = (
    "😴 *أذكار النوم*\n\n"
    "﴿ قُلْ هُوَ اللَّهُ أَحَدٌ * اللَّهُ الصَّمَدُ * لَمْ يَلِدْ وَلَمْ يُولَدْ * وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ ﴾\n\n"
    "﴿ قُلْ أَعُوذُ بِرَبِّ الْفَلَقِ * مِن شَرِّ مَا خَلَقَ * وَمِن شَرِّ غَاسِقٍ إِذَا وَقَبَ * وَمِن شَرِّ النَّفَّاثَاتِ فِي الْعُقَدِ * وَمِن شَرِّ حَاسِدٍ إِذَا حَسَدَ ﴾\n\n"
    "﴿ قُلْ أَعُوذُ بِرَبِّ النَّاسِ * مَلِكِ النَّاسِ * إِلَٰهِ النَّاسِ * مِن شَرِّ الْوَسْوَاسِ الْخَنَّاسِ * الَّذِي يُوَسْوِسُ فِي صُدُورِ النَّاسِ * مِنَ الْجِنَّةِ وَالنَّاسِ ﴾\n\n"
    "🌙 تصبحون على خير"
)

# ============= الدوال المساعدة =============
def is_user_admin(chat_id, user_id):
    """التحقق من أن المستخدم مشرف في المجموعة"""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except:
        return False

def send_azkar(chat_id, azkar_type):
    """إرسال الأذكار"""
    try:
        settings = get_chat_settings(chat_id)
        if not settings['is_enabled']:
            return
        
        if azkar_type == 'morning' and settings['morning_azkar']:
            for azkar in MORNING_AZKAR:
                bot.send_message(chat_id, azkar, parse_mode='Markdown')
        
        elif azkar_type == 'evening' and settings['evening_azkar']:
            for azkar in EVENING_AZKAR:
                bot.send_message(chat_id, azkar, parse_mode='Markdown')
        
        elif azkar_type == 'friday_kahf' and settings['friday_sura']:
            bot.send_message(chat_id, KAHF_REMINDER, parse_mode='Markdown')
        
        elif azkar_type == 'friday_dua' and settings['friday_dua']:
            for dua in FRIDAY_DUA:
                bot.send_message(chat_id, dua, parse_mode='Markdown')
        
        elif azkar_type == 'sleep' and settings['sleep_message']:
            bot.send_message(chat_id, SLEEP_MESSAGE, parse_mode='Markdown')
    
    except Exception as e:
        print(f"Error sending azkar: {e}")

def schedule_chat_jobs(chat_id):
    """جدولة المهام للمجموعة"""
    settings = get_chat_settings(chat_id)
    
    # إزالة المهام القديمة
    for job in scheduler.get_jobs():
        if str(chat_id) in job.id:
            job.remove()
    
    # جدولة أذكار الصباح
    if settings['morning_azkar']:
        hour, minute = settings['morning_time'].split(':')
        scheduler.add_job(
            send_azkar,
            CronTrigger(hour=int(hour), minute=int(minute)),
            args=[chat_id, 'morning'],
            id=f'morning_{chat_id}'
        )
    
    # جدولة أذكار المساء
    if settings['evening_azkar']:
        hour, minute = settings['evening_time'].split(':')
        scheduler.add_job(
            send_azkar,
            CronTrigger(hour=int(hour), minute=int(minute)),
            args=[chat_id, 'evening'],
            id=f'evening_{chat_id}'
        )
    
    # جدولة سورة الكهف (الجمعة 9:00)
    if settings['friday_sura']:
        scheduler.add_job(
            send_azkar,
            CronTrigger(day_of_week='fri', hour=9, minute=0),
            args=[chat_id, 'friday_kahf'],
            id=f'kahf_{chat_id}'
        )
    
    # جدولة أدعية الجمعة (الجمعة 10:00)
    if settings['friday_dua']:
        scheduler.add_job(
            send_azkar,
            CronTrigger(day_of_week='fri', hour=10, minute=0),
            args=[chat_id, 'friday_dua'],
            id=f'friday_{chat_id}'
        )
    
    # جدولة رسالة النوم
    if settings['sleep_message']:
        hour, minute = settings['sleep_time'].split(':')
        scheduler.add_job(
            send_azkar,
            CronTrigger(hour=int(hour), minute=int(minute)),
            args=[chat_id, 'sleep'],
            id=f'sleep_{chat_id}'
        )

# ============= معالجات البوت =============

# معالج التغييرات في صلاحيات البوت (التفعيل التلقائي)
@bot.my_chat_member_handler()
def handle_my_chat_member(update):
    """معالجة تغييرات عضوية البوت في المجموعات"""
    try:
        chat = update.chat
        new_status = update.new_chat_member.status
        
        # إذا تم تعيين البوت كمشرف
        if new_status == 'administrator':
            # تفعيل البوت تلقائياً
            update_chat_setting(chat.id, 'is_enabled', 1)
            schedule_chat_jobs(chat.id)
            
            # إرسال رسالة ترحيب
            welcome_msg = (
                "✅ *تم تفعيل البوت تلقائياً!*\n\n"
                "🌟 بارك الله فيكم، سيقوم البوت بإرسال:\n"
                "🌅 أذكار الصباح في الساعة 05:00\n"
                "🌙 أذكار المساء في الساعة 18:00\n"
                "📿 تذكير بسورة الكهف يوم الجمعة 09:00\n"
                "🕌 أدعية الجمعة في الساعة 10:00\n"
                "😴 رسالة قبل النوم في الساعة 22:00\n\n"
                "⚙️ للتحكم في الإعدادات، استخدم /settings\n"
                "📊 لعرض الحالة، استخدم /status"
            )
            bot.send_message(chat.id, welcome_msg, parse_mode='Markdown')
        
        # إذا تمت إزالة صلاحيات المشرف
        elif new_status in ['member', 'left', 'kicked']:
            update_chat_setting(chat.id, 'is_enabled', 0)
            # إيقاف جميع المهام المجدولة
            for job in scheduler.get_jobs():
                if str(chat.id) in job.id:
                    job.remove()
    
    except Exception as e:
        print(f"Error in my_chat_member handler: {e}")

# معالج رسائل الخدمة (للحذف التلقائي)
@bot.message_handler(content_types=[
    'new_chat_members', 
    'left_chat_member',
    'new_chat_title',
    'new_chat_photo',
    'delete_chat_photo',
    'group_chat_created',
    'supergroup_chat_created',
    'channel_chat_created',
    'pinned_message',
    'voice_chat_started',
    'voice_chat_ended',
    'voice_chat_participants_invited'
])
def delete_service_messages(message):
    """حذف رسائل الخدمة التلقائية"""
    try:
        chat_id = message.chat.id
        settings = get_chat_settings(chat_id)
        
        # التحقق من تفعيل ميزة حذف رسائل الخدمة
        if settings['is_enabled'] and settings['delete_service_messages']:
            bot.delete_message(chat_id, message.message_id)
    
    except Exception as e:
        print(f"Error deleting service message: {e}")

# معالج أمر /start
@bot.message_handler(commands=['start'])
def start_command(message):
    """معالج أمر البداية"""
    chat_type = message.chat.type
    
    if chat_type == 'private':
        # في المحادثة الخاصة
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            telebot.types.InlineKeyboardButton("👨‍💻 المطور", url="https://t.me/dev3bod"),
            telebot.types.InlineKeyboardButton("👥 المجموعة الرسمية", url="https://t.me/NourAdhkar")
        )
        
        welcome_text = (
            "🌟 *مرحباً بك في بوت الأذكار الإسلامية* 🌟\n\n"
            "📿 هذا البوت يقوم بإرسال الأذكار والأدعية الإسلامية تلقائياً في المجموعات\n\n"
            "✨ *المميزات:*\n"
            "🌅 أذكار الصباح\n"
            "🌙 أذكار المساء\n"
            "📿 سورة الكهف (الجمعة)\n"
            "🕌 أدعية الجمعة\n"
            "😴 رسالة قبل النوم\n"
            "🗑️ حذف رسائل الخدمة تلقائياً\n\n"
            "📝 *كيفية الاستخدام:*\n"
            "1️⃣ أضف البوت إلى مجموعتك\n"
            "2️⃣ اجعله مشرفاً\n"
            "3️⃣ سيعمل تلقائياً! ✅\n\n"
            "⚙️ استخدم /settings للتحكم في الإعدادات"
        )
        
        bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown', reply_markup=markup)
    
    else:
        # في المجموعة
        if is_user_admin(message.chat.id, message.from_user.id):
            # للمشرفين
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton(
                "⚙️ الإعدادات",
                url=f"https://t.me/{bot.get_me().username}?start=settings"
            ))
            
            bot.send_message(
                message.chat.id,
                "✨ مرحباً! أنا بوت الأذكار الإسلامية\n\n"
                "⚙️ يمكنك التحكم في إعداداتي باستخدام /settings",
                parse_mode='Markdown',
                reply_markup=markup
            )
        else:
            # للأعضاء
            bot.send_message(
                message.chat.id,
                "✨ مرحباً! أنا بوت الأذكار الإسلامية\n\n"
                "📿 أقوم بإرسال الأذكار والأدعية تلقائياً",
                parse_mode='Markdown'
            )

# معالج أمر /settings
@bot.message_handler(commands=['settings'])
def settings_command(message):
    """معالج أمر الإعدادات"""
    if message.chat.type == 'private':
        bot.send_message(
            message.chat.id,
            "⚠️ هذا الأمر يعمل فقط في المجموعات"
        )
        return
    
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.send_message(
            message.chat.id,
            "⚠️ هذا الأمر متاح للمشرفين فقط"
        )
        return
    
    settings = get_chat_settings(message.chat.id)
    
    # إنشاء لوحة الأزرار
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    
    # أزرار تفعيل/تعطيل الميزات
    morning_btn = telebot.types.InlineKeyboardButton(
        f"🌅 {'✓' if settings['morning_azkar'] else '✗'} أذكار الصباح",
        callback_data='toggle_morning'
    )
    evening_btn = telebot.types.InlineKeyboardButton(
        f"🌙 {'✓' if settings['evening_azkar'] else '✗'} أذكار المساء",
        callback_data='toggle_evening'
    )
    kahf_btn = telebot.types.InlineKeyboardButton(
        f"📿 {'✓' if settings['friday_sura'] else '✗'} سورة الكهف",
        callback_data='toggle_kahf'
    )
    friday_btn = telebot.types.InlineKeyboardButton(
        f"🕌 {'✓' if settings['friday_dua'] else '✗'} أدعية الجمعة",
        callback_data='toggle_friday'
    )
    sleep_btn = telebot.types.InlineKeyboardButton(
        f"😴 {'✓' if settings['sleep_message'] else '✗'} رسالة النوم",
        callback_data='toggle_sleep'
    )
    service_btn = telebot.types.InlineKeyboardButton(
        f"🗑️ {'✓' if settings['delete_service_messages'] else '✗'} حذف رسائل الخدمة",
        callback_data='toggle_service'
    )
    
    markup.add(morning_btn, evening_btn)
    markup.add(kahf_btn, friday_btn)
    markup.add(sleep_btn, service_btn)
    
    settings_text = (
        "⚙️ *لوحة التحكم*\n\n"
        f"📊 حالة البوت: {'🟢 مفعّل' if settings['is_enabled'] else '🔴 معطّل'}\n\n"
        "📅 *الأوقات المجدولة:*\n"
        f"🌅 الصباح: {settings['morning_time']}\n"
        f"🌙 المساء: {settings['evening_time']}\n"
        f"😴 النوم: {settings['sleep_time']}\n"
        f"📿 سورة الكهف: الجمعة 09:00\n"
        f"🕌 دعاء الجمعة: الجمعة 10:00\n\n"
        "💡 اضغط على الأزرار للتحكم بالميزات"
    )
    
    bot.send_message(
        message.chat.id,
        settings_text,
        parse_mode='Markdown',
        reply_markup=markup
    )

# معالج أزرار الإعدادات
@bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_'))
def handle_settings_callback(call):
    """معالج أزرار الإعدادات"""
    if not is_user_admin(call.message.chat.id, call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ هذا متاح للمشرفين فقط")
        return
    
    chat_id = call.message.chat.id
    settings = get_chat_settings(chat_id)
    
    # تحديد الإعداد المراد تغييره
    setting_map = {
        'toggle_morning': 'morning_azkar',
        'toggle_evening': 'evening_azkar',
        'toggle_kahf': 'friday_sura',
        'toggle_friday': 'friday_dua',
        'toggle_sleep': 'sleep_message',
        'toggle_service': 'delete_service_messages'
    }
    
    setting_key = setting_map.get(call.data)
    if setting_key:
        # عكس القيمة الحالية
        new_value = 0 if settings[setting_key] else 1
        update_chat_setting(chat_id, setting_key, new_value)
        
        # إعادة جدولة المهام
        schedule_chat_jobs(chat_id)
        
        # تحديث الرسالة
        settings = get_chat_settings(chat_id)
        
        # إنشاء لوحة الأزرار المحدثة
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        
        morning_btn = telebot.types.InlineKeyboardButton(
            f"🌅 {'✓' if settings['morning_azkar'] else '✗'} أذكار الصباح",
            callback_data='toggle_morning'
        )
        evening_btn = telebot.types.InlineKeyboardButton(
            f"🌙 {'✓' if settings['evening_azkar'] else '✗'} أذكار المساء",
            callback_data='toggle_evening'
        )
        kahf_btn = telebot.types.InlineKeyboardButton(
            f"📿 {'✓' if settings['friday_sura'] else '✗'} سورة الكهف",
            callback_data='toggle_kahf'
        )
        friday_btn = telebot.types.InlineKeyboardButton(
            f"🕌 {'✓' if settings['friday_dua'] else '✗'} أدعية الجمعة",
            callback_data='toggle_friday'
        )
        sleep_btn = telebot.types.InlineKeyboardButton(
            f"😴 {'✓' if settings['sleep_message'] else '✗'} رسالة النوم",
            callback_data='toggle_sleep'
        )
        service_btn = telebot.types.InlineKeyboardButton(
            f"🗑️ {'✓' if settings['delete_service_messages'] else '✗'} حذف رسائل الخدمة",
            callback_data='toggle_service'
        )
        
        markup.add(morning_btn, evening_btn)
        markup.add(kahf_btn, friday_btn)
        markup.add(sleep_btn, service_btn)
        
        settings_text = (
            "⚙️ *لوحة التحكم*\n\n"
            f"📊 حالة البوت: {'🟢 مفعّل' if settings['is_enabled'] else '🔴 معطّل'}\n\n"
            "📅 *الأوقات المجدولة:*\n"
            f"🌅 الصباح: {settings['morning_time']}\n"
            f"🌙 المساء: {settings['evening_time']}\n"
            f"😴 النوم: {settings['sleep_time']}\n"
            f"📿 سورة الكهف: الجمعة 09:00\n"
            f"🕌 دعاء الجمعة: الجمعة 10:00\n\n"
            "💡 اضغط على الأزرار للتحكم بالميزات"
        )
        
        bot.edit_message_text(
            settings_text,
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
        
        bot.answer_callback_query(call.id, "✅ تم التحديث")

# معالج أمر /status
@bot.message_handler(commands=['status'])
def status_command(message):
    """معالج أمر عرض الحالة"""
    if message.chat.type == 'private':
        bot.send_message(message.chat.id, "⚠️ هذا الأمر يعمل فقط في المجموعات")
        return
    
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.send_message(message.chat.id, "⚠️ هذا الأمر متاح للمشرفين فقط")
        return
    
    settings = get_chat_settings(message.chat.id)
    
    status_text = (
        "📊 *حالة البوت*\n\n"
        f"البوت: {'🟢 مفعّل' if settings['is_enabled'] else '🔴 معطّل'}\n\n"
        "*الميزات المفعلة:*\n"
        f"🌅 أذكار الصباح: {'✓' if settings['morning_azkar'] else '✗'}\n"
        f"🌙 أذكار المساء: {'✓' if settings['evening_azkar'] else '✗'}\n"
        f"📿 سورة الكهف: {'✓' if settings['friday_sura'] else '✗'}\n"
        f"🕌 أدعية الجمعة: {'✓' if settings['friday_dua'] else '✗'}\n"
        f"😴 رسالة النوم: {'✓' if settings['sleep_message'] else '✗'}\n"
        f"🗑️ حذف رسائل الخدمة: {'✓' if settings['delete_service_messages'] else '✗'}\n\n"
        "*الأوقات:*\n"
        f"🌅 الصباح: {settings['morning_time']}\n"
        f"🌙 المساء: {settings['evening_time']}\n"
        f"😴 النوم: {settings['sleep_time']}\n"
        f"📿 سورة الكهف: الجمعة 09:00\n"
        f"🕌 دعاء الجمعة: الجمعة 10:00"
    )
    
    bot.send_message(message.chat.id, status_text, parse_mode='Markdown')

# معالج أمر /enable
@bot.message_handler(commands=['enable'])
def enable_command(message):
    """تفعيل البوت"""
    if message.chat.type == 'private':
        bot.send_message(message.chat.id, "⚠️ هذا الأمر يعمل فقط في المجموعات")
        return
    
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.send_message(message.chat.id, "⚠️ هذا الأمر متاح للمشرفين فقط")
        return
    
    update_chat_setting(message.chat.id, 'is_enabled', 1)
    schedule_chat_jobs(message.chat.id)
    
    bot.send_message(
        message.chat.id,
        "✅ تم تفعيل البوت بنجاح!\n\n"
        "استخدم /settings للتحكم في الإعدادات"
    )

# معالج أمر /disable
@bot.message_handler(commands=['disable'])
def disable_command(message):
    """تعطيل البوت"""
    if message.chat.type == 'private':
        bot.send_message(message.chat.id, "⚠️ هذا الأمر يعمل فقط في المجموعات")
        return
    
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.send_message(message.chat.id, "⚠️ هذا الأمر متاح للمشرفين فقط")
        return
    
    update_chat_setting(message.chat.id, 'is_enabled', 0)
    
    # إيقاف جميع المهام
    for job in scheduler.get_jobs():
        if str(message.chat.id) in job.id:
            job.remove()
    
    bot.send_message(message.chat.id, "✅ تم تعطيل البوت")

# ============= Flask Routes للـ Webhook =============

@app.route('/')
def index():
    """الصفحة الرئيسية"""
    return "🤖 البوت يعمل بنجاح!"

@app.route('/setwebhook', methods=['GET'])
def set_webhook():
    """ضبط الـ webhook"""
    try:
        webhook_url = f"{WEBHOOK_URL}/{WEBHOOK_PATH}"
        bot.remove_webhook()
        result = bot.set_webhook(url=webhook_url)
        if result:
            return f"✅ تم ضبط Webhook بنجاح!"
        else:
            return "❌ فشل ضبط Webhook"
    except Exception as e:
        return f"❌ خطأ: {str(e)}"

@app.route(f'/{WEBHOOK_PATH}', methods=['POST'])
def webhook():
    """معالج الـ webhook"""
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return '', 500

@app.route('/health', methods=['GET'])
def health():
    """فحص صحة البوت"""
    return {
        'status': 'healthy',
        'mode': BOT_MODE,
        'timestamp': datetime.now().isoformat()
    }

# ============= بدء التشغيل =============

def main():
    """الدالة الرئيسية لبدء البوت"""
    print("🚀 بدء تشغيل بوت الأذكار الإسلامية...")
    print(f"📡 وضع التشغيل: {BOT_MODE}")
    
    # إنشاء قاعدة البيانات
    init_db()
    print("✅ تم إنشاء قاعدة البيانات")
    
    if BOT_MODE == 'webhook':
        print(f"🌐 رابط Webhook: {WEBHOOK_URL}")
        print(f"🔧 إعداد Webhook تلقائياً...")
        
        # إعداد الـ webhook تلقائياً عند التشغيل
        try:
            webhook_url = f"{WEBHOOK_URL}/{WEBHOOK_PATH}"
            bot.remove_webhook()
            bot.set_webhook(url=webhook_url)
            print(f"✅ تم ضبط Webhook بنجاح")
        except Exception as e:
            print(f"⚠️ تحذير: فشل ضبط Webhook تلقائياً: {e}")
            print("💡 يمكنك ضبطه يدوياً عبر زيارة: /setwebhook")
        
        print(f"🚀 تشغيل Flask على المنفذ {PORT}...")
        app.run(host='0.0.0.0', port=PORT)
    
    else:
        # وضع Long Polling (للتطوير فقط)
        print("🔄 تشغيل Long Polling...")
        bot.infinity_polling()

if __name__ == '__main__':
    main()
