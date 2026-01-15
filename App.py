import telebot
import sqlite3
import time
import random
import os
from datetime import datetime, timedelta
from flask import Flask, request, abort
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# توكن البوت الخاص بك
BOT_TOKEN = os.environ.get('BOT_TOKEN', '7812533121:AAFyxg2EeeB4WqFpHecR1gdGUdg9Or7Evlk')
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# المنطقة الزمنية (توقيت مكة المكرمة)
TIMEZONE = pytz.timezone('Asia/Riyadh')

# قاعدة بيانات لتخزين إعدادات المجموعات
conn = sqlite3.connect('azkar_bot.db', check_same_thread=False)
cursor = conn.cursor()

# إنشاء جداول قاعدة البيانات
cursor.execute('''CREATE TABLE IF NOT EXISTS chat_settings
                  (chat_id INTEGER PRIMARY KEY,
                   is_admin INTEGER DEFAULT 0,
                   morning_azkar INTEGER DEFAULT 1,
                   evening_azkar INTEGER DEFAULT 1,
                   friday_sura INTEGER DEFAULT 1,
                   friday_dua INTEGER DEFAULT 1,
                   sleep_image INTEGER DEFAULT 1,
                   random_content INTEGER DEFAULT 1,
                   content_interval INTEGER DEFAULT 180,
                   morning_time TEXT DEFAULT '05:00',
                   evening_time TEXT DEFAULT '18:00',
                   sleep_time TEXT DEFAULT '22:00',
                   content_types TEXT DEFAULT 'text,image,audio,pdf')''')

cursor.execute('''CREATE TABLE IF NOT EXISTS admin_users
                  (chat_id INTEGER, user_id INTEGER,
                   PRIMARY KEY (chat_id, user_id))''')

conn.commit()

# محتوى الأذكار والأدعية
MORNING_AZKAR = [
    """🌅 أذكار الصباح 🌅

﴿ اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ ۚ لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ ۚ لَّهُ مَا فِي السَّمَاوَاتِ وَمَا فِي الْأَرْضِ ۗ مَن ذَا الَّذِي يَشْفَعُ عِندَهُ إِلَّا بِإِذْنِهِ ۚ يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَيْءٍ مِّنْ عِلْمِهِ إِلَّا بِمَا شَاءَ ۚ وَسِعَ كُرْسِيُّهُ السَّمَاوَاتِ وَالْأَرْضَ ۖ وَلَا يَئُودُهُ حِفْظُهُمَا ۚ وَهُوَ الْعَلِيُّ الْعَظِيمُ ﴾

📿 آية الكرسي (مرة واحدة)""",
    
    """☀️ أذكار الصباح ☀️

أَصْبَحْنَا وَأَصْبَحَ الْمُلْكُ لِلَّهِ، وَالْحَمْدُ لِلَّهِ، لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ.

رَبِّ أَسْأَلُكَ خَيْرَ مَا فِي هَذَا الْيَوْمِ وَخَيْرَ مَا بَعْدَهُ، وَأَعُوذُ بِكَ مِنْ شَرِّ مَا فِي هَذَا الْيَوْمِ وَشَرِّ مَا بَعْدَهُ.

🌟 (مرة واحدة)""",
    
    """🌄 أذكار الصباح 🌄

اللَّهُمَّ بِكَ أَصْبَحْنَا، وَبِكَ أَمْسَيْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ النُّشُورُ.

سُبْحَانَ اللَّهِ وَبِحَمْدِهِ عَدَدَ خَلْقِهِ وَرِضَا نَفْسِهِ وَزِنَةَ عَرْشِهِ وَمِدَادَ كَلِمَاتِهِ.

💫 (ثلاث مرات)"""
]

EVENING_AZKAR = [
    """🌙 أذكار المساء 🌙

﴿ اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ ۚ لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ ۚ لَّهُ مَا فِي السَّمَاوَاتِ وَمَا فِي الْأَرْضِ ۗ مَن ذَا الَّذِي يَشْفَعُ عِندَهُ إِلَّا بِإِذْنِهِ ۚ يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَيْءٍ مِّنْ عِلْمِهِ إِلَّا بِمَا شَاءَ ۚ وَسِعَ كُرْسِيُّهُ السَّمَاوَاتِ وَالْأَرْضَ ۖ وَلَا يَئُودُهُ حِفْظُهُمَا ۚ وَهُوَ الْعَلِيُّ الْعَظِيمُ ﴾

📿 آية الكرسي (مرة واحدة)""",
    
    """🌆 أذكار المساء 🌆

أَمْسَيْنَا وَأَمْسَى الْمُلْكُ لِلَّهِ، وَالْحَمْدُ لِلَّهِ، لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ.

رَبِّ أَسْأَلُكَ خَيْرَ مَا فِي هَذِهِ اللَّيْلَةِ وَخَيْرَ مَا بَعْدَهَا، وَأَعُوذُ بِكَ مِنْ شَرِّ مَا فِي هَذِهِ اللَّيْلَةِ وَشَرِّ مَا بَعْدَهَا.

🌟 (مرة واحدة)""",
    
    """🌃 أذكار المساء 🌃

اللَّهُمَّ بِكَ أَمْسَيْنَا، وَبِكَ أَصْبَحْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ الْمَصِيرُ.

أَعُوذُ بِكَلِمَاتِ اللَّهِ التَّامَّاتِ مِنْ شَرِّ مَا خَلَقَ.

🛡️ (ثلاث مرات)"""
]

RANDOM_DUAS = [
    "🤲 رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الْآخِرَةِ حَسَنَةً وَقِنَا عَذَابَ النَّارِ 🤲",
    "💚 اللَّهُمَّ إِنِّي أَسْأَلُكَ الْهُدَى وَالتُّقَى، وَالْعَفَافَ وَالْغِنَى 💚",
    "✨ رَبِّ اشْرَحْ لِي صَدْرِي، وَيَسِّرْ لِي أَمْرِي، وَاحْلُلْ عُقْدَةً مِّن لِّسَانِي، يَفْقَهُوا قَوْلِي ✨",
    "🌟 اللَّهُمَّ إِنِّي أَعُوذُ بِكَ مِنَ الْهَمِّ وَالْحَزَنِ، وَأَعُوذُ بِكَ مِنَ الْعَجْزِ وَالْكَسَلِ 🌟",
    "🕊️ رَبَّنَا لَا تُؤَاخِذْنَا إِن نَّسِينَا أَوْ أَخْطَأْنَا، رَبَّنَا وَلَا تَحْمِلْ عَلَيْنَا إِصْرًا كَمَا حَمَلْتَهُ عَلَى الَّذِينَ مِن قَبْلِنَا 🕊️",
    "💎 اللَّهُمَّ إِنِّي أَسْأَلُكَ عِلْمًا نَافِعًا، وَرِزْقًا طَيِّبًا، وَعَمَلًا مُتَقَبَّلًا 💎",
    "🌺 اللَّهُمَّ أَصْلِحْ لِي دِينِي الَّذِي هُوَ عِصْمَةُ أَمْرِي، وَأَصْلِحْ لِي دُنْيَايَ الَّتِي فِيهَا مَعَاشِي 🌺",
    "☘️ رَبِّ أَوْزِعْنِي أَنْ أَشْكُرَ نِعْمَتَكَ الَّتِي أَنْعَمْتَ عَلَيَّ وَعَلَىٰ وَالِدَيَّ وَأَنْ أَعْمَلَ صَالِحًا تَرْضَاهُ ☘️"
]

QURAN_VERSES = [
    "📖 ﴿ فَاذْكُرُونِي أَذْكُرْكُمْ وَاشْكُرُوا لِي وَلَا تَكْفُرُونِ ﴾\n[البقرة: 152]",
    "📖 ﴿ وَقَالَ رَبُّكُمُ ادْعُونِي أَسْتَجِبْ لَكُمْ ﴾\n[غافر: 60]",
    "📖 ﴿ إِنَّ مَعَ الْعُسْرِ يُسْرًا ﴾\n[الشرح: 6]",
    "📖 ﴿ وَمَن يَتَّقِ اللَّهَ يَجْعَل لَّهُ مَخْرَجًا * وَيَرْزُقْهُ مِنْ حَيْثُ لَا يَحْتَسِبُ ﴾\n[الطلاق: 2-3]",
    "📖 ﴿ فَإِنَّ مَعَ الْعُسْرِ يُسْرًا * إِنَّ مَعَ الْعُسْرِ يُسْرًا ﴾\n[الشرح: 5-6]",
    "📖 ﴿ وَلَذِكْرُ اللَّهِ أَكْبَرُ ﴾\n[العنكبوت: 45]",
    "📖 ﴿ يَا أَيُّهَا الَّذِينَ آمَنُوا اذْكُرُوا اللَّهَ ذِكْرًا كَثِيرًا ﴾\n[الأحزاب: 41]",
    "📖 ﴿ أَلَا بِذِكْرِ اللَّهِ تَطْمَئِنُّ الْقُلُوبُ ﴾\n[الرعد: 28]"
]

HADITH_TEXTS = [
    "🌸 قال رسول الله ﷺ:\n«مَن قال: سُبحانَ اللهِ وبِحَمْدِه، في يومٍ مِائةَ مَرَّةٍ، حُطَّتْ خَطاياه وإنْ كانَتْ مِثْلَ زَبَدِ البَحْرِ»\n[متفق عليه]",
    "🌸 قال رسول الله ﷺ:\n«كلمتان خفيفتان على اللسان، ثقيلتان في الميزان، حبيبتان إلى الرحمن: سبحان الله وبحمده، سبحان الله العظيم»\n[متفق عليه]",
    "🌸 قال رسول الله ﷺ:\n«مَن قال: لا إلهَ إلَّا اللهُ وحدَه لا شريكَ له، له المُلكُ وله الحمدُ، وهو على كلِّ شيءٍ قديرٌ، في يومٍ مائةَ مرَّةٍ، كانت له عَدلَ عشرِ رِقابٍ»\n[متفق عليه]",
    "🌸 قال رسول الله ﷺ:\n«الطُّهُورُ شَطْرُ الإيمانِ، والحَمْدُ لِلَّهِ تَمْلأُ المِيزانَ، وسُبْحانَ اللهِ والحَمْدُ لِلَّهِ تَملآنِ - أوْ تَمْلأُ - ما بيْنَ السَّمَواتِ والأرْضِ»\n[صحيح مسلم]",
    "🌸 قال رسول الله ﷺ:\n«أحب الكلام إلى الله أربع: سبحان الله، والحمد لله، ولا إله إلا الله، والله أكبر»\n[صحيح مسلم]"
]

FRIDAY_DUAS = [
    """🕌 أدعية يوم الجمعة 🕌

اللَّهُمَّ صَلِّ وَسَلِّمْ وَبَارِكْ عَلَى سَيِّدِنَا مُحَمَّدٍ وَعَلَى آلِهِ وَصَحْبِهِ أَجْمَعِينَ

عَدَدَ خَلْقِكَ وَرِضَا نَفْسِكَ وَزِنَةَ عَرْشِكَ وَمِدَادَ كَلِمَاتِكَ

🌟 أكثروا من الصلاة على النبي في هذا اليوم المبارك 🌟""",
    
    """🤲 دعاء يوم الجمعة 🤲

رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الْآخِرَةِ حَسَنَةً وَقِنَا عَذَابَ النَّارِ

اللَّهُمَّ اجْعَلْ خَيْرَ أَعْمَالِنَا خَوَاتِمَهَا، وَخَيْرَ أَيَّامِنَا يَوْمَ لِقَائِكَ

💚 يوم الجمعة يوم عيد للمسلمين 💚"""
]

SLEEP_MESSAGE = """🌙 قبل النوم 🌙

﴿ بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ * قُلْ هُوَ اللَّهُ أَحَدٌ * اللَّهُ الصَّمَدُ * لَمْ يَلِدْ وَلَمْ يُولَدْ * وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ ﴾

﴿ بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ * قُلْ أَعُوذُ بِرَبِّ الْفَلَقِ * مِن شَرِّ مَا خَلَقَ * وَمِن شَرِّ غَاسِقٍ إِذَا وَقَبَ * وَمِن شَرِّ النَّفَّاثَاتِ فِي الْعُقَدِ * وَمِن شَرِّ حَاسِدٍ إِذَا حَسَدَ ﴾

﴿ بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ * قُلْ أَعُوذُ بِرَبِّ النَّاسِ * مَلِكِ النَّاسِ * إِلَٰهِ النَّاسِ * مِن شَرِّ الْوَسْوَاسِ الْخَنَّاسِ * الَّذِي يُوَسْوِسُ فِي صُدُورِ النَّاسِ * مِنَ الْجِنَّةِ وَالنَّاسِ ﴾

اللَّهُمَّ بِاسْمِكَ أَمُوتُ وَأَحْيَا

😴 تصبحون على خير 😴"""

KAHF_MESSAGE = """📿 سورة الكهف 📿

🕌 يوم الجمعة المبارك 🕌

﴿ إِنَّ الَّذِينَ آمَنُوا وَعَمِلُوا الصَّالِحَاتِ إِنَّا لَا نُضِيعُ أَجْرَ مَنْ أَحْسَنَ عَمَلًا ﴾

قال رسول الله ﷺ:
«مَن قرأَ سورةَ الكَهفِ يومَ الجُمُعةِ أضاءَ له من النُّورِ ما بينَ الجُمُعتَينِ»

💡 اقرأوا سورة الكهف اليوم تنالوا الأجر والنور 💡

🔗 يمكنكم قراءتها من المصحف أو الاستماع إليها"""

# دوال مساعدة
def get_chat_settings(chat_id):
    """الحصول على إعدادات المجموعة"""
    cursor.execute('SELECT * FROM chat_settings WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    if result:
        return {
            'chat_id': result[0],
            'is_admin': result[1],
            'morning_azkar': result[2],
            'evening_azkar': result[3],
            'friday_sura': result[4],
            'friday_dua': result[5],
            'sleep_image': result[6],
            'random_content': result[7],
            'content_interval': result[8],
            'morning_time': result[9],
            'evening_time': result[10],
            'sleep_time': result[11],
            'content_types': result[12]
        }
    else:
        # إنشاء إعدادات افتراضية
        cursor.execute('''INSERT INTO chat_settings (chat_id) VALUES (?)''', (chat_id,))
        conn.commit()
        return get_chat_settings(chat_id)

def is_user_admin(chat_id, user_id):
    """التحقق من أن المستخدم مشرف في المجموعة"""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except:
        return False

def send_azkar(chat_id, azkar_type):
    """إرسال الأذكار حسب النوع"""
    try:
        settings = get_chat_settings(chat_id)
        
        if azkar_type == 'morning' and settings['morning_azkar']:
            for azkar in MORNING_AZKAR:
                bot.send_message(chat_id, azkar, parse_mode='Markdown')
                time.sleep(2)
                
        elif azkar_type == 'evening' and settings['evening_azkar']:
            for azkar in EVENING_AZKAR:
                bot.send_message(chat_id, azkar, parse_mode='Markdown')
                time.sleep(2)
                
        elif azkar_type == 'sleep' and settings['sleep_image']:
            bot.send_message(chat_id, SLEEP_MESSAGE, parse_mode='Markdown')
            
        elif azkar_type == 'friday_kahf' and settings['friday_sura']:
            bot.send_message(chat_id, KAHF_MESSAGE, parse_mode='Markdown')
            
        elif azkar_type == 'friday_dua' and settings['friday_dua']:
            dua = random.choice(FRIDAY_DUAS)
            bot.send_message(chat_id, dua, parse_mode='Markdown')
            
    except Exception as e:
        print(f"خطأ في إرسال الأذكار: {e}")

def send_random_content(chat_id):
    """إرسال محتوى عشوائي (دعاء، آية، حديث)"""
    try:
        settings = get_chat_settings(chat_id)
        if not settings['random_content']:
            return
            
        content_type = random.choice(['dua', 'quran', 'hadith'])
        
        if content_type == 'dua':
            message = random.choice(RANDOM_DUAS)
        elif content_type == 'quran':
            message = random.choice(QURAN_VERSES)
        else:
            message = random.choice(HADITH_TEXTS)
            
        bot.send_message(chat_id, message, parse_mode='Markdown')
    except Exception as e:
        print(f"خطأ في إرسال المحتوى العشوائي: {e}")

def get_all_active_chats():
    """الحصول على جميع المجموعات النشطة"""
    cursor.execute('SELECT chat_id FROM chat_settings WHERE is_admin = 1')
    return [row[0] for row in cursor.fetchall()]

# إعداد المجدول (Scheduler)
scheduler = BackgroundScheduler(timezone=TIMEZONE)

def schedule_azkar_jobs():
    """جدولة جميع المهام"""
    # مسح المهام القديمة
    scheduler.remove_all_jobs()
    
    chats = get_all_active_chats()
    
    for chat_id in chats:
        settings = get_chat_settings(chat_id)
        
        # أذكار الصباح
        if settings['morning_azkar']:
            hour, minute = settings['morning_time'].split(':')
            scheduler.add_job(
                lambda: send_azkar(chat_id, 'morning'),
                CronTrigger(hour=int(hour), minute=int(minute)),
                id=f'morning_{chat_id}'
            )
        
        # أذكار المساء
        if settings['evening_azkar']:
            hour, minute = settings['evening_time'].split(':')
            scheduler.add_job(
                lambda: send_azkar(chat_id, 'evening'),
                CronTrigger(hour=int(hour), minute=int(minute)),
                id=f'evening_{chat_id}'
            )
        
        # رسالة قبل النوم
        if settings['sleep_image']:
            hour, minute = settings['sleep_time'].split(':')
            scheduler.add_job(
                lambda: send_azkar(chat_id, 'sleep'),
                CronTrigger(hour=int(hour), minute=int(minute)),
                id=f'sleep_{chat_id}'
            )
        
        # سورة الكهف (الخميس قبل صلاة الجمعة بساعة - 11 صباحاً)
        if settings['friday_sura']:
            scheduler.add_job(
                lambda: send_azkar(chat_id, 'friday_kahf'),
                CronTrigger(day_of_week='thu', hour=11, minute=0),
                id=f'kahf_{chat_id}'
            )
        
        # أدعية الجمعة (الساعة 10 صباحاً يوم الجمعة)
        if settings['friday_dua']:
            scheduler.add_job(
                lambda: send_azkar(chat_id, 'friday_dua'),
                CronTrigger(day_of_week='fri', hour=10, minute=0),
                id=f'friday_dua_{chat_id}'
            )
        
        # محتوى عشوائي
        if settings['random_content'] and settings['content_interval'] > 0:
            scheduler.add_job(
                lambda: send_random_content(chat_id),
                'interval',
                minutes=settings['content_interval'],
                id=f'random_{chat_id}'
            )

# معالجات الأوامر
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """رسالة الترحيب"""
    welcome_text = """🌟 مرحباً بك في بوت الأذكار الإسلامية 🌟

هذا البوت يرسل الأذكار والأدعية تلقائياً في أوقات محددة:

📿 الميزات:
• أذكار الصباح (5:00 ص)
• أذكار المساء (6:00 م)
• سورة الكهف (قبل الجمعة)
• أدعية الجمعة
• رسالة قبل النوم (10:00 م)
• أدعية وآيات عشوائية

⚙️ أوامر المشرفين:
/settings - لوحة التحكم
/enable - تفعيل البوت في هذه المجموعة
/disable - تعطيل البوت
/status - حالة البوت

💡 لبدء استخدام البوت:
1. أضف البوت كمشرف في المجموعة
2. استخدم الأمر /enable
3. تمتع بالأذكار التلقائية!

🤲 نسأل الله أن ينفع بهذا البوت"""
    
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['enable'])
def enable_bot(message):
    """تفعيل البوت في المجموعة"""
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "❌ هذا الأمر يعمل فقط في المجموعات")
        return
    
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ هذا الأمر للمشرفين فقط")
        return
    
    cursor.execute('UPDATE chat_settings SET is_admin = 1 WHERE chat_id = ?', (message.chat.id,))
    conn.commit()
    
    # إعادة جدولة المهام
    schedule_azkar_jobs()
    
    bot.reply_to(message, "✅ تم تفعيل البوت بنجاح!\n\n📿 سيتم إرسال الأذكار حسب الجدول المحدد.\n\nاستخدم /settings لتخصيص الإعدادات.")

@bot.message_handler(commands=['disable'])
def disable_bot(message):
    """تعطيل البوت في المجموعة"""
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "❌ هذا الأمر يعمل فقط في المجموعات")
        return
    
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ هذا الأمر للمشرفين فقط")
        return
    
    cursor.execute('UPDATE chat_settings SET is_admin = 0 WHERE chat_id = ?', (message.chat.id,))
    conn.commit()
    
    # إعادة جدولة المهام
    schedule_azkar_jobs()
    
    bot.reply_to(message, "✅ تم تعطيل البوت")

@bot.message_handler(commands=['status'])
def show_status(message):
    """عرض حالة البوت"""
    settings = get_chat_settings(message.chat.id)
    
    status = f"""📊 حالة البوت في هذه المجموعة:

🔰 الحالة: {'مفعّل ✅' if settings['is_admin'] else 'معطّل ❌'}

⏰ الإعدادات:
• أذكار الصباح ({settings['morning_time']}): {'✅' if settings['morning_azkar'] else '❌'}
• أذكار المساء ({settings['evening_time']}): {'✅' if settings['evening_azkar'] else '❌'}
• سورة الكهف: {'✅' if settings['friday_sura'] else '❌'}
• أدعية الجمعة: {'✅' if settings['friday_dua'] else '❌'}
• رسالة النوم ({settings['sleep_time']}): {'✅' if settings['sleep_image'] else '❌'}
• محتوى عشوائي: {'✅' if settings['random_content'] else '❌'}

⏱️ الفاصل الزمني: {settings['content_interval']} دقيقة

استخدم /settings لتغيير الإعدادات"""
    
    bot.reply_to(message, status)

@bot.message_handler(commands=['settings'])
def show_settings(message):
    """عرض لوحة التحكم"""
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "❌ هذا الأمر يعمل فقط في المجموعات")
        return
    
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ هذا الأمر للمشرفين فقط")
        return
    
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    
    settings = get_chat_settings(message.chat.id)
    
    # أزرار تفعيل/تعطيل الميزات
    markup.add(
        telebot.types.InlineKeyboardButton(
            f"{'✅' if settings['morning_azkar'] else '❌'} أذكار الصباح",
            callback_data='toggle_morning'
        ),
        telebot.types.InlineKeyboardButton(
            f"{'✅' if settings['evening_azkar'] else '❌'} أذكار المساء",
            callback_data='toggle_evening'
        )
    )
    
    markup.add(
        telebot.types.InlineKeyboardButton(
            f"{'✅' if settings['friday_sura'] else '❌'} سورة الكهف",
            callback_data='toggle_kahf'
        ),
        telebot.types.InlineKeyboardButton(
            f"{'✅' if settings['friday_dua'] else '❌'} أدعية الجمعة",
            callback_data='toggle_friday_dua'
        )
    )
    
    markup.add(
        telebot.types.InlineKeyboardButton(
            f"{'✅' if settings['sleep_image'] else '❌'} رسالة النوم",
            callback_data='toggle_sleep'
        ),
        telebot.types.InlineKeyboardButton(
            f"{'✅' if settings['random_content'] else '❌'} محتوى عشوائي",
            callback_data='toggle_random'
        )
    )
    
    markup.add(
        telebot.types.InlineKeyboardButton(
            "⏱️ تعديل الأوقات",
            callback_data='edit_times'
        ),
        telebot.types.InlineKeyboardButton(
            "⏲️ فاصل المحتوى",
            callback_data='edit_interval'
        )
    )
    
    markup.add(
        telebot.types.InlineKeyboardButton(
            "🔄 حفظ وإعادة تحميل",
            callback_data='reload_schedule'
        )
    )
    
    bot.send_message(
        message.chat.id,
        "⚙️ لوحة التحكم\n\nاضغط على الأزرار لتفعيل أو تعطيل الميزات:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """معالج الأزرار"""
    if not is_user_admin(call.message.chat.id, call.from_user.id):
        bot.answer_callback_query(call.id, "❌ هذا الأمر للمشرفين فقط")
        return
    
    chat_id = call.message.chat.id
    
    # تبديل الميزات
    toggles = {
        'toggle_morning': 'morning_azkar',
        'toggle_evening': 'evening_azkar',
        'toggle_kahf': 'friday_sura',
        'toggle_friday_dua': 'friday_dua',
        'toggle_sleep': 'sleep_image',
        'toggle_random': 'random_content'
    }
    
    if call.data in toggles:
        field = toggles[call.data]
        cursor.execute(f'UPDATE chat_settings SET {field} = 1 - {field} WHERE chat_id = ?', (chat_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ تم التحديث")
        
        # تحديث الرسالة
        settings = get_chat_settings(chat_id)
        markup = call.message.reply_markup
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
        
    elif call.data == 'reload_schedule':
        schedule_azkar_jobs()
        bot.answer_callback_query(call.id, "✅ تم إعادة تحميل الجدول")
        
    elif call.data == 'edit_times':
        bot.answer_callback_query(call.id, "استخدم الأمر: /settime <نوع> <الوقت>\nمثال: /settime morning 06:00")
        
    elif call.data == 'edit_interval':
        bot.answer_callback_query(call.id, "استخدم الأمر: /setinterval <دقائق>\nمثال: /setinterval 120")

@bot.message_handler(commands=['settime'])
def set_time(message):
    """تعديل أوقات الأذكار"""
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "❌ هذا الأمر يعمل فقط في المجموعات")
        return
    
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ هذا الأمر للمشرفين فقط")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            raise ValueError()
        
        time_type = parts[1]
        time_value = parts[2]
        
        # التحقق من صحة الوقت
        datetime.strptime(time_value, '%H:%M')
        
        valid_types = {
            'morning': 'morning_time',
            'evening': 'evening_time',
            'sleep': 'sleep_time'
        }
        
        if time_type not in valid_types:
            raise ValueError()
        
        field = valid_types[time_type]
        cursor.execute(f'UPDATE chat_settings SET {field} = ? WHERE chat_id = ?', (time_value, message.chat.id))
        conn.commit()
        
        schedule_azkar_jobs()
        
        bot.reply_to(message, f"✅ تم تحديث وقت {time_type} إلى {time_value}")
        
    except:
        bot.reply_to(message, "❌ صيغة خاطئة\n\nالاستخدام: /settime <morning/evening/sleep> <HH:MM>\nمثال: /settime morning 06:00")

@bot.message_handler(commands=['setinterval'])
def set_interval(message):
    """تعديل الفاصل الزمني للمحتوى العشوائي"""
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "❌ هذا الأمر يعمل فقط في المجموعات")
        return
    
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ هذا الأمر للمشرفين فقط")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError()
        
        interval = int(parts[1])
        if interval < 0:
            raise ValueError()
        
        cursor.execute('UPDATE chat_settings SET content_interval = ? WHERE chat_id = ?', (interval, message.chat.id))
        conn.commit()
        
        schedule_azkar_jobs()
        
        bot.reply_to(message, f"✅ تم تحديث الفاصل الزمني إلى {interval} دقيقة")
        
    except:
        bot.reply_to(message, "❌ صيغة خاطئة\n\nالاستخدام: /setinterval <دقائق>\nمثال: /setinterval 120")

# معالج للكشف عن إضافة البوت كمشرف
@bot.message_handler(content_types=['new_chat_members'])
def new_member(message):
    """عند إضافة البوت إلى مجموعة"""
    for new_member in message.new_chat_members:
        if new_member.id == bot.get_me().id:
            # البوت تمت إضافته
            settings = get_chat_settings(message.chat.id)
            welcome = """🌟 شكراً لإضافتي إلى المجموعة! 🌟

أنا بوت الأذكار الإسلامية، سأرسل لكم:
📿 أذكار الصباح والمساء
📖 آيات قرآنية وأحاديث نبوية
🕌 سورة الكهف يوم الجمعة
🤲 أدعية متنوعة

للبدء، المشرفون يمكنهم استخدام:
/enable - لتفعيل البوت
/settings - لوحة التحكم
/help - المساعدة

🤲 بارك الله فيكم"""
            bot.send_message(message.chat.id, welcome)

# Flask routes for webhook
@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    """معالج Webhook"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        abort(403)

@app.route('/')
def index():
    """الصفحة الرئيسية"""
    return """
    <html dir="rtl">
    <head>
        <meta charset="utf-8">
        <title>بوت الأذكار الإسلامية</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #2c3e50; }
            .status { color: #27ae60; font-size: 20px; }
        </style>
    </head>
    <body>
        <h1>🌟 بوت الأذكار الإسلامية 🌟</h1>
        <p class="status">✅ البوت يعمل بنجاح</p>
        <p>📿 يرسل الأذكار والأدعية تلقائياً</p>
        <p>🕌 سورة الكهف يوم الجمعة</p>
        <p>🤲 أدعية وآيات متنوعة</p>
    </body>
    </html>
    """, 200

@app.route('/setwebhook')
def set_webhook_route():
    """تعيين Webhook يدوياً"""
    try:
        webhook_url = request.args.get('url')
        if not webhook_url:
            return "❌ يرجى تحديد URL\n\nمثال: /setwebhook?url=https://your-app.vercel.app", 400
        
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url + '/' + BOT_TOKEN)
        return f"✅ تم تعيين Webhook بنجاح:\n{webhook_url}/{BOT_TOKEN}", 200
    except Exception as e:
        return f"❌ خطأ: {str(e)}", 500

@app.route('/removewebhook')
def remove_webhook_route():
    """إزالة Webhook"""
    try:
        bot.remove_webhook()
        return "✅ تم إزالة Webhook", 200
    except Exception as e:
        return f"❌ خطأ: {str(e)}", 500

@app.route('/webhookinfo')
def webhook_info():
    """معلومات Webhook"""
    try:
        info = bot.get_webhook_info()
        return f"""
        📊 معلومات Webhook:
        
        URL: {info.url or 'غير معيّن'}
        Pending: {info.pending_update_count}
        Last Error: {info.last_error_date or 'لا يوجد'}
        Error Message: {info.last_error_message or 'لا يوجد'}
        Max Connections: {info.max_connections}
        """, 200
    except Exception as e:
        return f"❌ خطأ: {str(e)}", 500

def run_polling():
    """تشغيل البوت بوضع Long Polling"""
    print("🚀 بدء تشغيل البوت بوضع Long Polling...")
    
    # إزالة webhook إن وجد
    bot.remove_webhook()
    time.sleep(1)
    
    # بدء المجدول
    if not scheduler.running:
        scheduler.start()
    
    # جدولة المهام الأولية
    schedule_azkar_jobs()
    
    print("✅ البوت جاهز ويعمل!")
    print("📿 سيتم إرسال الأذكار حسب الجدول المحدد")
    
    # بدء استقبال الرسائل
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

def run_webhook():
    """تشغيل البوت بوضع Webhook"""
    print("🚀 بدء تشغيل البوت بوضع Webhook...")
    
    # بدء المجدول
    if not scheduler.running:
        scheduler.start()
    
    # جدولة المهام الأولية
    schedule_azkar_jobs()
    
    print("✅ البوت جاهز!")
    print("📝 تذكير: قم بتعيين Webhook باستخدام /setwebhook?url=YOUR_URL")

if __name__ == '__main__':
    # التحقق من وضع التشغيل
    mode = os.environ.get('BOT_MODE', 'polling').lower()
    
    if mode == 'webhook':
        # وضع Webhook (للإنتاج)
        run_webhook()
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
    else:
        # وضع Long Polling (للتطوير والاختبار)
        run_polling()
