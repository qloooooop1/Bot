import os
import sys
import logging
import time
from datetime import datetime
import pytz
import random
import sqlite3
import json

from flask import Flask, request, abort
import telebot
from telebot import types
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ────────────────────────────────────────────────
#               Logging Setup
# ────────────────────────────────────────────────

# Configure logging with proper formatting
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Suppress noisy logs from libraries
logging.getLogger('apscheduler').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# ────────────────────────────────────────────────
#               Configuration
# ────────────────────────────────────────────────

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    logger.critical("BOT_TOKEN غير موجود في متغيرات البيئة")
    raise ValueError("BOT_TOKEN is required")

# PORT configuration with proper validation
PORT_ENV = os.environ.get("PORT")
try:
    PORT = int(PORT_ENV) if PORT_ENV else 5000
    if not (1 <= PORT <= 65535):
        logger.warning(f"⚠️ Invalid PORT value {PORT}, using default 5000")
        PORT = 5000
    logger.info(f"✓ PORT configured: {PORT} (from {'environment' if PORT_ENV else 'default'})")
except ValueError as e:
    logger.error(f"❌ Error parsing PORT from environment variable '{PORT_ENV}': {e}, using default 5000")
    PORT = 5000

TIMEZONE = pytz.timezone("Asia/Riyadh")

WEBHOOK_PATH = "/webhook"
RENDER_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'bot-8c0e.onrender.com')
WEBHOOK_URL = f"https://{RENDER_HOSTNAME}{WEBHOOK_PATH}"
WEBHOOK_ERROR_THRESHOLD_SECONDS = 3600  # Only reconfigure webhook if error occurred within last hour
logger.info(f"✓ WEBHOOK_URL configured: {WEBHOOK_URL}")
logger.info(f"✓ Render hostname: {RENDER_HOSTNAME}")

# ────────────────────────────────────────────────
#               Instances
# ────────────────────────────────────────────────

app = Flask(__name__)
# threaded=False prevents race conditions and handler issues with Gunicorn workers
# This is critical for webhook mode with multiple workers
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
scheduler = BackgroundScheduler(timezone=TIMEZONE)
scheduler.start()

# ────────────────────────────────────────────────
#               Database
# ────────────────────────────────────────────────

DB_FILE = "bot_settings.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            is_enabled INTEGER DEFAULT 1,
            morning_azkar INTEGER DEFAULT 1,
            evening_azkar INTEGER DEFAULT 1,
            friday_sura INTEGER DEFAULT 1,
            friday_dua INTEGER DEFAULT 1,
            sleep_message INTEGER DEFAULT 1,
            delete_service_messages INTEGER DEFAULT 1,
            morning_time TEXT DEFAULT '05:00',
            evening_time TEXT DEFAULT '18:00',
            sleep_time TEXT DEFAULT '22:00'
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized")

init_db()

def get_chat_settings(chat_id: int) -> dict:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM chat_settings WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    conn.close()

    if row is None:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO chat_settings (chat_id) VALUES (?)", (chat_id,))
        conn.commit()
        conn.close()
        return get_chat_settings(chat_id)

    return {
        "chat_id": row[0],
        "is_enabled": bool(row[1]),
        "morning_azkar": bool(row[2]),
        "evening_azkar": bool(row[3]),
        "friday_sura": bool(row[4]),
        "friday_dua": bool(row[5]),
        "sleep_message": bool(row[6]),
        "delete_service_messages": bool(row[7]),
        "morning_time": row[8],
        "evening_time": row[9],
        "sleep_time": row[10],
    }

def update_chat_setting(chat_id: int, key: str, value):
    allowed_keys = {
        "is_enabled", "morning_azkar", "evening_azkar",
        "friday_sura", "friday_dua", "sleep_message",
        "delete_service_messages", "morning_time",
        "evening_time", "sleep_time"
    }
    if key not in allowed_keys:
        logger.error(f"Invalid setting key: {key}")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f"UPDATE chat_settings SET {key} = ? WHERE chat_id = ?", (int(value), chat_id))
    conn.commit()
    conn.close()
    logger.info(f"Updated {key} = {value} for chat {chat_id}")

# ────────────────────────────────────────────────
#               Load Azkar from JSON Files
# ────────────────────────────────────────────────

def load_azkar_from_json(filename):
    """
    Load azkar from JSON file and format them for display.
    
    Args:
        filename (str): Name of the JSON file in the azkar directory
        
    Returns:
        list: List of formatted message strings, empty list on error
        
    The function reads a JSON file containing azkar data and formats each item
    into a message string with icon, title, text, reference, and count if available.
    """
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'azkar', filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        messages = []
        icon = data.get('icon', '📿')
        title = data.get('title', 'أذكار')
        
        # Handle different JSON structures
        if 'azkar' in data:
            for item in data['azkar']:
                msg = f"{icon} *{title}*\n\n{item['text']}"
                if item.get('reference'):
                    msg += f"\n\n{item['reference']}"
                if item.get('count'):
                    msg += f"\n\n{item['count']}"
                messages.append(msg)
        
        if 'closing' in data:
            messages[-1] += f"\n\n{data['closing']}"
        
        return messages
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return []

def load_friday_azkar():
    """
    Load Friday azkar with special structure including Kahf reminder and duas.
    
    Returns:
        tuple: (kahf_reminder_msg, duas_list) where:
            - kahf_reminder_msg (str): Formatted Kahf reminder message
            - duas_list (list): List of formatted Friday dua messages
            Returns ("", []) on error
            
    This function handles the special structure of Friday azkar which includes
    a Surah Al-Kahf reminder and Friday-specific duas with related hadiths.
    """
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'azkar', 'friday.json')
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Kahf reminder
        kahf = data['kahf_reminder']
        kahf_msg = (
            f"📿 *تذكير بسورة الكهف*\n\n"
            f"{kahf['text']}\n\n"
            f"{kahf['hadith']}\n\n"
            f"{kahf['closing']}"
        )
        
        # Friday duas
        duas = []
        hadith_idx = 0
        hadiths = data.get('hadiths', [])
        
        for dua in data['duas']:
            msg = f"🕌 *دعاء يوم الجمعة*\n\n{dua['text']}"
            if dua.get('reference'):
                msg += f"\n\n{dua['reference']}"
            if dua.get('count'):
                msg += f"\n\n{dua['count']}"
            
            # Add related hadith if available
            if hadith_idx < len(hadiths):
                hadith = hadiths[hadith_idx]
                msg += f"\n\n✨ {hadith['text']}"
                hadith_idx += 1
            
            duas.append(msg)
        
        return kahf_msg, duas
    except Exception as e:
        logger.error(f"Error loading friday.json: {e}")
        return "", []

def load_sleep_azkar():
    """
    Load sleep azkar with special structure.
    
    Returns:
        str: Formatted sleep azkar message combining all sleep azkar and closing message.
             Returns empty string on error.
             
    This function handles the special structure of sleep azkar which combines
    multiple surahs (Al-Ikhlas, Al-Falaq, Al-Nas) into a single message.
    """
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'azkar', 'sleep.json')
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        msg = f"{data['icon']} *{data['title']}*\n\n"
        
        for item in data['azkar']:
            msg += f"{item['text']}\n\n"
        
        if 'closing' in data:
            msg += data['closing']
        
        return msg
    except Exception as e:
        logger.error(f"Error loading sleep.json: {e}")
        return ""

# ────────────────────────────────────────────────
#               Content - أذكار الصباح
# ────────────────────────────────────────────────

MORNING_AZKAR = load_azkar_from_json('morning.json') or [
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

# ────────────────────────────────────────────────
#               أذكار المساء
# ────────────────────────────────────────────────

EVENING_AZKAR = load_azkar_from_json('evening.json') or [
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

# Load Friday azkar
KAHF_REMINDER, FRIDAY_DUA = load_friday_azkar() or ("", [])
if not KAHF_REMINDER:
    KAHF_REMINDER = (
        "📿 *تذكير بسورة الكهف*\n\n"
        "السلام عليكم ورحمة الله وبركاته\n\n"
        "نُذَكِّرُكُم بقراءة سورة الكهف في هذا اليوم المبارك\n\n"
        "قال رسول الله ﷺ: «مَن قرأَ سورةَ الكَهفِ في يومِ الجُمُعةِ، أضاءَ له مِن النُّورِ ما بيْنَ الجُمُعتَينِ»\n\n"
        "🕌 جعلنا الله وإياكم من المواظبين على الطاعات"
    )

if not FRIDAY_DUA:
    FRIDAY_DUA = [
        "🕌 *دعاء يوم الجمعة*\n\n"
        "اللَّهُمَّ صَلِّ وَسَلِّمْ وَبَارِكْ عَلَى سَيِّدِنَا مُحَمَّدٍ وَعَلَى آلِهِ وَصَحْبِهِ أَجْمَعِينَ\n\n"
        "✨ قال رسول الله ﷺ: «مَن صلَّى عليَّ صلاةً واحدةً صلَّى اللهُ عليه بها عشرًا»",

        "🕌 *دعاء يوم الجمعة*\n\n"
        "اللَّهُمَّ إِنِّي أَسْأَلُكَ مِنَ الْخَيْرِ كُلِّهِ عَاجِلِهِ وَآجِلِهِ، مَا عَلِمْتُ مِنْهُ وَمَا لَمْ أَعْلَمْ، وَأَعُوذُ بِكَ مِنَ الشَّرِّ كُلِّهِ عَاجِلِهِ وَآجِلِهِ، مَا عَلِمْتُ مِنْهُ وَمَا لَمْ أَعْلَمْ\n\n"
        "✨ دعاء مأثور",
    ]

SLEEP_MESSAGE = load_sleep_azkar() or (
    "😴 *أذكار النوم*\n\n"
    "﴿ قُلْ هُوَ اللَّهُ أَحَدٌ * اللَّهُ الصَّمَدُ * لَمْ يَلِدْ وَلَمْ يُولَدْ * وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ ﴾\n\n"
    "﴿ قُلْ أَعُوذُ بِرَبِّ الْفَلَقِ * مِن شَرِّ مَا خَلَقَ * وَمِن شَرِّ غَاسِقٍ إِذَا وَقَبَ * وَمِن شَرِّ النَّفَّاثَاتِ فِي الْعُقَدِ * وَمِن شَرِّ حَاسِدٍ إِذَا حَسَدَ ﴾\n\n"
    "﴿ قُلْ أَعُوذُ بِرَبِّ النَّاسِ * مَلِكِ النَّاسِ * إِلَٰهِ النَّاسِ * مِن شَرِّ الْوَسْوَاسِ الْخَنَّاسِ * الَّذِي يُوَسْوِسُ فِي صُدُورِ النَّاسِ * مِنَ الْجِنَّةِ وَالنَّاسِ ﴾\n\n"
    "🌙 تصبحون على خير"
)

# ────────────────────────────────────────────────
#               Sending Functions
# ────────────────────────────────────────────────

def send_azkar(chat_id: int, azkar_type: str):
    try:
        settings = get_chat_settings(chat_id)
        if not settings["is_enabled"]:
            return

        messages = []

        if azkar_type == "morning" and settings["morning_azkar"]:
            messages = MORNING_AZKAR
        elif azkar_type == "evening" and settings["evening_azkar"]:
            messages = EVENING_AZKAR
        elif azkar_type == "friday_kahf" and settings["friday_sura"]:
            messages = [KAHF_REMINDER]
        elif azkar_type == "friday_dua" and settings["friday_dua"]:
            messages = FRIDAY_DUA
        elif azkar_type == "sleep" and settings["sleep_message"]:
            messages = [SLEEP_MESSAGE]

        for msg in messages:
            try:
                bot.send_message(chat_id, msg, parse_mode="Markdown")
                logger.info(f"Sent {azkar_type} message to {chat_id}")
            except telebot.apihelper.ApiTelegramException as e:
                if "blocked" in str(e).lower() or "kicked" in str(e).lower():
                    logger.warning(f"Bot blocked/kicked from {chat_id}")
                    update_chat_setting(chat_id, "is_enabled", 0)
                else:
                    logger.error(f"Failed sending to {chat_id}: {e}")

    except Exception as e:
        logger.error(f"Error in send_azkar ({azkar_type}) for {chat_id}: {e}", exc_info=True)

# ────────────────────────────────────────────────
#               Scheduling
# ────────────────────────────────────────────────

def schedule_chat_jobs(chat_id: int):
    """
    Schedule all azkar jobs for a specific chat based on its settings.
    
    Args:
        chat_id (int): The Telegram chat ID to schedule jobs for
    """
    try:
        settings = get_chat_settings(chat_id)

        # Remove previous jobs
        for job in scheduler.get_jobs():
            if str(chat_id) in job.id:
                job.remove()

        # Morning Azkar
        if settings["morning_azkar"]:
            try:
                h, m = map(int, settings["morning_time"].split(":"))
                scheduler.add_job(
                    send_azkar,
                    CronTrigger(hour=h, minute=m, timezone=TIMEZONE),
                    args=[chat_id, "morning"],
                    id=f"morning_{chat_id}",
                    replace_existing=True
                )
            except (ValueError, AttributeError) as e:
                logger.error(f"Invalid morning time for {chat_id}: {e}")

        # Evening Azkar
        if settings["evening_azkar"]:
            try:
                h, m = map(int, settings["evening_time"].split(":"))
                scheduler.add_job(
                    send_azkar,
                    CronTrigger(hour=h, minute=m, timezone=TIMEZONE),
                    args=[chat_id, "evening"],
                    id=f"evening_{chat_id}",
                    replace_existing=True
                )
            except (ValueError, AttributeError) as e:
                logger.error(f"Invalid evening time for {chat_id}: {e}")

        # Friday Kahf reminder
        if settings["friday_sura"]:
            scheduler.add_job(
                send_azkar,
                CronTrigger(day_of_week="fri", hour=9, minute=0, timezone=TIMEZONE),
                args=[chat_id, "friday_kahf"],
                id=f"kahf_{chat_id}",
                replace_existing=True
            )

        # Friday Dua
        if settings["friday_dua"]:
            scheduler.add_job(
                send_azkar,
                CronTrigger(day_of_week="fri", hour=10, minute=0, timezone=TIMEZONE),
                args=[chat_id, "friday_dua"],
                id=f"friday_dua_{chat_id}",
                replace_existing=True
            )

        # Sleep message
        if settings["sleep_message"]:
            try:
                h, m = map(int, settings["sleep_time"].split(":"))
                scheduler.add_job(
                    send_azkar,
                    CronTrigger(hour=h, minute=m, timezone=TIMEZONE),
                    args=[chat_id, "sleep"],
                    id=f"sleep_{chat_id}",
                    replace_existing=True
                )
            except (ValueError, AttributeError) as e:
                logger.error(f"Invalid sleep time for {chat_id}: {e}")

        logger.info(f"Scheduled jobs for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error scheduling jobs for chat {chat_id}: {e}", exc_info=True)

# ────────────────────────────────────────────────
#               Bot Handlers
# ────────────────────────────────────────────────

@bot.my_chat_member_handler()
def my_chat_member_handler(update: types.ChatMemberUpdated):
    """
    Handle bot membership changes in chats.
    Automatically enables/disables the bot based on admin status.
    """
    try:
        chat_id = update.chat.id
        new_status = update.new_chat_member.status
        
        logger.info(f"Bot status changed in chat {chat_id}: {new_status}")

        if new_status in ["administrator", "creator"]:
            update_chat_setting(chat_id, "is_enabled", 1)
            schedule_chat_jobs(chat_id)
            try:
                bot.send_message(
                    chat_id,
                    "✅ *تم تفعيل البوت تلقائياً!*\n\n"
                    "سيبدأ بإرسال الأذكار في الأوقات المحددة\n"
                    "استخدم /settings لتعديل الإعدادات",
                    parse_mode="Markdown"
                )
                logger.info(f"Bot activated in chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send activation message to {chat_id}: {e}")
        else:
            update_chat_setting(chat_id, "is_enabled", 0)
            for job in scheduler.get_jobs():
                if str(chat_id) in job.id:
                    job.remove()
            logger.info(f"Bot deactivated in chat {chat_id}")
    except Exception as e:
        logger.error(f"Error in my_chat_member_handler: {e}", exc_info=True)

@bot.message_handler(content_types=[
    'new_chat_members', 'left_chat_member', 'new_chat_title',
    'new_chat_photo', 'delete_chat_photo', 'group_chat_created',
    'supergroup_chat_created', 'channel_chat_created', 'pinned_message',
    'voice_chat_started', 'voice_chat_ended', 'voice_chat_participants_invited'
])
def delete_service_messages(message: types.Message):
    """
    Delete service messages in groups if the feature is enabled.
    Service messages include member joins/leaves, pin notifications, etc.
    """
    try:
        chat_id = message.chat.id
        settings = get_chat_settings(chat_id)
        if settings["delete_service_messages"]:
            bot.delete_message(chat_id, message.message_id)
            logger.debug(f"Deleted service message in {chat_id}")
    except Exception as e:
        # Fail silently as service message deletion is non-critical
        logger.debug(f"Could not delete service message in {chat_id}: {e}")

def cmd_settings_markup():
    """
    Generate the settings inline keyboard markup.
    
    Returns:
        types.InlineKeyboardMarkup: Keyboard with settings buttons
    """
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("⚙️ إعدادات البوت", callback_data="settings_panel")
    )
    return markup

@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    """
    Handle /start command in both private chats and groups.
    Updated to show different interfaces based on chat type and admin status.
    """
    try:
        logger.info(f"Start command received from {message.from_user.id} in chat {message.chat.id}")
        
        # Cache bot info to avoid redundant API calls
        bot_info = bot.get_me()
        
        # إذا كانت الرسالة واردة داخل محادثة خاصة
        if message.chat.type == "private":
            bot_username = bot_info.username or "نور الذكر"
            description = "بوت نور الذكر يرسل أذكار الصباح والمساء، سورة الكهف يوم الجمعة، أدعية الجمعة، رسائل النوم تلقائيًا في المجموعات."
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("➕ إضافة البوت إلى مجموعتك", url=f"https://t.me/{bot_username}?startgroup=true"),
                types.InlineKeyboardButton("👥 المجموعة الرسمية", url="https://t.me/NourAdhkar"),
                types.InlineKeyboardButton("👨‍💻 المطور", url="https://t.me/dev3bod")
            )
            bot.send_message(
                message.chat.id,
                f"مرحبًا بك في {bot_username} ✨\n{description}",
                reply_markup=markup,
                parse_mode="Markdown"
            )
            logger.info(f"/start received in private chat from {message.from_user.id}")
        
        # إذا كانت الرسالة واردة داخل مجموعة أو مجموعة سوبر
        else:
            bot_status = bot.get_chat_member(chat_id=message.chat.id, user_id=bot_info.id).status
            if bot_status in ["administrator", "creator"]:
                bot.send_message(
                    message.chat.id,
                    "تم تفعيل البوت في المجموعة! اذهب إلى الخاص لتعديل الإعدادات. ✅",
                    parse_mode="Markdown"
                )
                # أرسل لوحة الإعدادات إلى الخاص بالشخص الذي أرسل /start
                try:
                    bot.send_message(
                        message.from_user.id,
                        "هنا لوحة الإعدادات:",
                        reply_markup=cmd_settings_markup(),
                        parse_mode="Markdown"
                    )
                    logger.info(f"Settings panel sent to user {message.from_user.id}")
                except Exception as e:
                    # If unable to send to private chat (user hasn't started bot)
                    logger.warning(f"Could not send settings to user {message.from_user.id}: {e}")
                    bot.send_message(
                        message.chat.id,
                        "⚠️ يرجى بدء محادثة خاصة مع البوت أولاً لاستلام لوحة الإعدادات.",
                        parse_mode="Markdown"
                    )
                logger.info(f"/start received in group {message.chat.id} (bot is admin)")
            else:
                bot.send_message(
                    message.chat.id,
                    "يرجى جعل البوت مشرفًا في المجموعة ليتمكن من العمل 🔑",
                    parse_mode="Markdown"
                )
                logger.info(f"/start received in group {message.chat.id} (bot is not admin)")
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}", exc_info=True)
        try:
            bot.reply_to(message, "حدث خطأ، يرجى المحاولة مرة أخرى")
        except Exception:
            # Final fallback - nothing we can do if even error message fails
            pass

@bot.message_handler(commands=["settings"])
def cmd_settings(message: types.Message):
    if message.chat.type == "private":
        bot.send_message(message.chat.id, "⚠️ هذا الأمر يعمل فقط في المجموعات")
        return

    if not bot.get_chat_member(message.chat.id, message.from_user.id).status in ["administrator", "creator"]:
        bot.send_message(message.chat.id, "⚠️ هذا الأمر متاح للمشرفين فقط")
        return

    settings = get_chat_settings(message.chat.id)

    markup = types.InlineKeyboardMarkup(row_width=2)

    btns = [
        ("morning_azkar", "🌅 أذكار الصباح"),
        ("evening_azkar", "🌙 أذكار المساء"),
        ("friday_sura", "📿 سورة الكهف"),
        ("friday_dua", "🕌 أدعية الجمعة"),
        ("sleep_message", "😴 رسالة النوم"),
        ("delete_service_messages", "🗑️ حذف رسائل الخدمة")
    ]

    for key, label in btns:
        status = "✓" if settings[key] else "✗"
        markup.add(types.InlineKeyboardButton(f"{label} {status}", callback_data=f"toggle_{key}"))

    text = (
        "⚙️ *لوحة التحكم*\n\n"
        f"حالة البوت: {'🟢 مفعّل' if settings['is_enabled'] else '🔴 معطّل'}\n\n"
        "الأوقات المجدولة:\n"
        f"🌅 الصباح: {settings['morning_time']}\n"
        f"🌙 المساء: {settings['evening_time']}\n"
        f"😴 النوم: {settings['sleep_time']}\n"
        f"📿 سورة الكهف: الجمعة 09:00\n"
        f"🕌 دعاء الجمعة: الجمعة 10:00\n\n"
        "اضغط لتغيير الإعدادات"
    )

    bot.send_message(
        message.chat.id,
        text,
        parse_mode="Markdown",
        reply_markup=markup
    )
    logger.info(f"/settings opened by {message.from_user.id} in {message.chat.id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def callback_toggle(call: types.CallbackQuery):
    if not bot.get_chat_member(call.message.chat.id, call.from_user.id).status in ["administrator", "creator"]:
        bot.answer_callback_query(call.id, "هذا متاح للمشرفين فقط", show_alert=True)
        return

    key = call.data.split("_", 1)[1]
    settings = get_chat_settings(call.message.chat.id)
    new_value = not settings[key]
    update_chat_setting(call.message.chat.id, key, new_value)
    schedule_chat_jobs(call.message.chat.id)

    # Refresh markup
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [
        ("morning_azkar", "🌅 أذكار الصباح"),
        ("evening_azkar", "🌙 أذكار المساء"),
        ("friday_sura", "📿 سورة الكهف"),
        ("friday_dua", "🕌 أدعية الجمعة"),
        ("sleep_message", "😴 رسالة النوم"),
        ("delete_service_messages", "🗑️ حذف رسائل الخدمة")
    ]

    for k, label in btns:
        status = "✓" if get_chat_settings(call.message.chat.id)[k] else "✗"
        markup.add(types.InlineKeyboardButton(f"{label} {status}", callback_data=f"toggle_{k}"))

    text = call.message.text.split("\n\n")[0] + "\n\n" + call.message.text.split("\n\n")[1]
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )

    bot.answer_callback_query(call.id, "تم التحديث")

@bot.callback_query_handler(func=lambda call: call.data == "settings_panel")
def callback_settings_panel(call: types.CallbackQuery):
    """
    Handle callback for settings panel button.
    This redirects users to use /settings command in their group.
    """
    try:
        bot.answer_callback_query(
            call.id,
            "يرجى استخدام أمر /settings في المجموعة لتعديل الإعدادات",
            show_alert=True
        )
        logger.info(f"Settings panel callback from user {call.from_user.id}")
    except Exception as e:
        logger.error(f"Error in callback_settings_panel: {e}", exc_info=True)

@bot.message_handler(commands=["status"])
def cmd_status(message: types.Message):
    if message.chat.type == "private":
        bot.send_message(message.chat.id, "هذا الأمر يعمل فقط في المجموعات")
        return

    if not bot.get_chat_member(message.chat.id, message.from_user.id).status in ["administrator", "creator"]:
        bot.send_message(message.chat.id, "هذا الأمر متاح للمشرفين فقط")
        return

    settings = get_chat_settings(message.chat.id)

    text = (
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

    bot.send_message(message.chat.id, text, parse_mode="Markdown")
    logger.info(f"/status requested by {message.from_user.id} in {message.chat.id}")

@bot.message_handler(commands=["enable"])
def cmd_enable(message: types.Message):
    if message.chat.type == "private":
        return

    if not bot.get_chat_member(message.chat.id, message.from_user.id).status in ["administrator", "creator"]:
        bot.send_message(message.chat.id, "هذا الأمر متاح للمشرفين فقط")
        return

    update_chat_setting(message.chat.id, "is_enabled", 1)
    schedule_chat_jobs(message.chat.id)
    bot.send_message(message.chat.id, "✅ تم تفعيل البوت")
    logger.info(f"Bot enabled in {message.chat.id}")

@bot.message_handler(commands=["disable"])
def cmd_disable(message: types.Message):
    if message.chat.type == "private":
        return

    if not bot.get_chat_member(message.chat.id, message.from_user.id).status in ["administrator", "creator"]:
        bot.send_message(message.chat.id, "هذا الأمر متاح للمشرفين فقط")
        return

    update_chat_setting(message.chat.id, "is_enabled", 0)
    for job in scheduler.get_jobs():
        if str(message.chat.id) in job.id:
            job.remove()
    bot.send_message(message.chat.id, "✅ تم تعطيل البوت")
    logger.info(f"Bot disabled in {message.chat.id}")

@bot.message_handler(func=lambda message: True)
def echo_all(message: types.Message):
    """
    Echo handler for testing purposes - responds to all non-command messages.
    This helps verify that the bot is receiving and processing messages correctly.
    
    NOTE: This is a catch-all handler for testing. In production, you may want to
    remove or modify this handler to avoid interfering with other functionality.
    Currently limited to private chats only to minimize impact.
    """
    try:
        # Only respond in private chats to avoid spam in groups
        if message.chat.type == "private" and message.text:
            response = f"قلت: {message.text}"
            bot.reply_to(message, response)
            logger.info(f"Echo handler triggered for message from {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in echo handler: {e}", exc_info=True)

# ────────────────────────────────────────────────
#               Flask Routes
# ────────────────────────────────────────────────

@app.route("/")
def home():
    """
    Health check endpoint for monitoring services.
    Returns detailed status information about the bot and webhook.
    """
    try:
        info = bot.get_webhook_info()
        webhook_status = "✓ Configured" if info.url else "✗ Not configured"
        port_info = f"PORT: {PORT}"
        response = f"نور الذكر – البوت يعمل ✓\nWebhook: {webhook_status}\n{port_info}"
        logger.debug(f"Home endpoint accessed - Webhook: {webhook_status}, PORT: {PORT}")
        return response, 200
    except Exception as e:
        logger.error(f"❌ Error in home endpoint: {e}")
        return f"نور الذكر – البوت يعمل ✓\nPORT: {PORT}", 200

@app.route("/health")
def health():
    """
    Detailed health check endpoint with comprehensive webhook diagnostics.
    Returns JSON with bot status, webhook configuration, and error information.
    """
    try:
        # Check webhook status
        info = bot.get_webhook_info()
        
        # Determine webhook health
        webhook_configured = bool(info.url)
        has_errors = bool(info.last_error_message)
        
        # Calculate error age if there is an error
        error_age_seconds = None
        if info.last_error_date:
            error_age_seconds = int(time.time() - info.last_error_date)
        
        status = {
            "status": "healthy" if webhook_configured and not has_errors else "degraded",
            "bot": "operational",
            "port": PORT,
            "port_source": "environment" if os.environ.get("PORT") else "default",
            "webhook_url": info.url or "Not configured",
            "webhook_configured": webhook_configured,
            "webhook_expected": WEBHOOK_URL,
            "webhook_match": info.url == WEBHOOK_URL if info.url else False,
            "pending_updates": info.pending_update_count,
            "last_error_date": info.last_error_date if info.last_error_date else None,
            "last_error_age_seconds": error_age_seconds,
            "last_error": info.last_error_message or "None",
            "max_connections": info.max_connections if hasattr(info, 'max_connections') else None,
            "render_hostname": RENDER_HOSTNAME,
            "timezone": str(TIMEZONE),
            "scheduler_running": scheduler.running
        }
        
        # Log if webhook URL doesn't match expected
        if webhook_configured and info.url != WEBHOOK_URL:
            logger.warning(f"⚠️ Webhook URL mismatch! Expected: {WEBHOOK_URL}, Actual: {info.url}")
            status["status"] = "misconfigured"
            status["warning"] = f"Webhook URL mismatch. Expected: {WEBHOOK_URL}"
        
        return status, 200
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy", 
            "bot": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "port": PORT
        }, 500

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    """
    Handle incoming webhook updates from Telegram.
    Processes all incoming messages and updates with comprehensive error handling.
    Enhanced with detailed logging for debugging webhook issues.
    """
    logger.info("Webhook called - new update received")
    
    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data(as_text=True)
            # Log first 200 chars for debugging - remove in production if concerned about sensitive data
            logger.info(f"Received JSON: {json_string[:200]}...")
            
            update = types.Update.de_json(json_string)
            
            if update and update.message:
                msg_text = getattr(update.message, 'text', None)
                if msg_text:
                    logger.info(f"Processing message: {msg_text}")
                else:
                    logger.info(f"Processing non-text message from {update.message.chat.id}")
            elif update:
                logger.info(f"Processing update type: {update.update_id}")
            
            bot.process_new_updates([update])
            logger.info("Update processed successfully")
            return '', 200
            
        except UnicodeDecodeError as e:
            logger.error(f"❌ Webhook decode error: {e}")
            return "", 400
        except Exception as e:
            logger.error(f"❌ Webhook processing error: {e}", exc_info=True)
            # Return 200 to prevent Telegram from retrying indefinitely
            return "", 200
    else:
        logger.warning("Invalid content-type")
        return '', 403

@app.route("/setwebhook", methods=["GET"])
def manual_set_webhook():
    """
    Manually trigger webhook setup.
    Useful for debugging and manual reconfiguration.
    """
    try:
        logger.info("🔧 Manual webhook setup requested")
        bot.remove_webhook()
        logger.info("✓ Previous webhook removed")
        
        success = bot.set_webhook(
            url=WEBHOOK_URL,
            drop_pending_updates=True,
            max_connections=100,
            allowed_updates=["message", "edited_message", "channel_post", "my_chat_member", "callback_query"]
        )
        
        if success:
            info = bot.get_webhook_info()
            logger.info(f"✓ Webhook set successfully: {info.url}")
            return (
                f"✓ Webhook تم بنجاح → {WEBHOOK_URL}<br>"
                f"Status: {info.url}<br>"
                f"PORT: {PORT}<br>"
                f"Render Hostname: {RENDER_HOSTNAME}"
            ), 200
        else:
            logger.error("❌ Webhook setup failed")
            return f"✗ Webhook فشل → {WEBHOOK_URL}<br>PORT: {PORT}", 500
    except Exception as e:
        logger.error(f"❌ Manual webhook setup error: {e}", exc_info=True)
        return f"خطأ: {str(e)}<br>PORT: {PORT}", 500

@app.route("/check-webhook", methods=["GET"])
def check_webhook_status():
    """
    Check and display detailed webhook status information.
    Useful for debugging webhook configuration issues.
    """
    try:
        info = bot.get_webhook_info()
        
        status_html = f"""
        <html>
        <head><title>Webhook Status</title></head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>🔍 Webhook Status</h2>
            <table border="1" cellpadding="10" style="border-collapse: collapse;">
                <tr>
                    <td><strong>Status</strong></td>
                    <td>{'✓ Configured' if info.url else '✗ Not configured'}</td>
                </tr>
                <tr>
                    <td><strong>Webhook URL</strong></td>
                    <td>{info.url or 'Not set'}</td>
                </tr>
                <tr>
                    <td><strong>Expected URL</strong></td>
                    <td>{WEBHOOK_URL}</td>
                </tr>
                <tr>
                    <td><strong>URL Match</strong></td>
                    <td>{'✓ Match' if info.url == WEBHOOK_URL else '✗ Mismatch'}</td>
                </tr>
                <tr>
                    <td><strong>Pending Updates</strong></td>
                    <td>{info.pending_update_count}</td>
                </tr>
                <tr>
                    <td><strong>Max Connections</strong></td>
                    <td>{info.max_connections if hasattr(info, 'max_connections') else 'N/A'}</td>
                </tr>
                <tr>
                    <td><strong>Last Error Date</strong></td>
                    <td>{info.last_error_date if info.last_error_date else 'None'}</td>
                </tr>
                <tr>
                    <td><strong>Last Error Message</strong></td>
                    <td>{info.last_error_message or 'None'}</td>
                </tr>
            </table>
            <br>
            <a href="/setwebhook" style="padding: 10px; background: #4CAF50; color: white; text-decoration: none; border-radius: 5px;">🔧 Setup Webhook</a>
            <a href="/health" style="padding: 10px; background: #2196F3; color: white; text-decoration: none; border-radius: 5px; margin-left: 10px;">💚 Health Check</a>
        </body>
        </html>
        """
        return status_html, 200
    except Exception as e:
        logger.error(f"Error checking webhook status: {e}", exc_info=True)
        return f"<html><body><h2>Error</h2><p>{str(e)}</p></body></html>", 500

# ────────────────────────────────────────────────
#               Flask Error Handlers
# ────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    logger.warning(f"404 error: {request.url}")
    return "Not Found", 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"500 error: {error}", exc_info=True)
    return "Internal Server Error", 500

@app.errorhandler(Exception)
def handle_exception(error):
    """Handle uncaught exceptions"""
    logger.error(f"Unhandled exception: {error}", exc_info=True)
    return "Internal Server Error", 500

# ────────────────────────────────────────────────
#               Auto Webhook Setup
# ────────────────────────────────────────────────

def setup_webhook():
    """
    Setup webhook with advanced retry logic and exponential backoff.
    Ensures webhook is properly configured for production deployment.
    """
    max_retries = 5
    base_delay = 2
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Webhook setup attempt {attempt + 1}/{max_retries}")
            
            # Remove existing webhook first using delete_webhook which supports drop_pending_updates
            bot.delete_webhook(drop_pending_updates=True)
            logger.info("Previous webhook removed successfully")
            
            # Small delay to ensure Telegram processes the removal
            time.sleep(1)
            
            # Set new webhook with comprehensive configuration
            success = bot.set_webhook(
                url=WEBHOOK_URL,
                drop_pending_updates=True,
                max_connections=100,
                allowed_updates=["message", "edited_message", "channel_post", "my_chat_member", "callback_query"]
            )
            
            if success:
                # Verify webhook was set correctly
                time.sleep(1)  # Give Telegram time to register
                info = bot.get_webhook_info()
                
                if info.url == WEBHOOK_URL:
                    logger.info(f"✓ Webhook setup successful → {WEBHOOK_URL}")
                    logger.info(f"Webhook info: URL={info.url}, Pending={info.pending_update_count}, Max_connections={info.max_connections}")
                    return True
                else:
                    logger.warning(f"Webhook URL mismatch: expected {WEBHOOK_URL}, got {info.url}")
            else:
                logger.warning(f"Webhook setup returned False (attempt {attempt + 1}/{max_retries})")
                
        except Exception as e:
            logger.error(f"Webhook setup error (attempt {attempt + 1}/{max_retries}): {e}", exc_info=True)
            
        # Exponential backoff before retry
        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)  # Exponential backoff: 2, 4, 8, 16 seconds
            logger.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)
        else:
            logger.critical(f"Failed to setup webhook after {max_retries} attempts")
            return False
    
    return False

def verify_webhook():
    """
    Periodic job to verify webhook is still properly configured.
    Automatically reconfigures if webhook is missing or incorrect.
    """
    try:
        logger.debug("🔍 Starting webhook verification...")
        info = bot.get_webhook_info()
        
        if not info.url:
            logger.warning("⚠️ Webhook not configured, attempting to set up...")
            setup_webhook()
        elif info.url != WEBHOOK_URL:
            logger.warning(f"⚠️ Webhook URL mismatch: expected {WEBHOOK_URL}, got {info.url}")
            setup_webhook()
        elif info.last_error_message:
            logger.warning(f"⚠️ Webhook has errors: {info.last_error_message}")
            # Only reconfigure if error is recent (within threshold)
            if info.last_error_date and (time.time() - info.last_error_date < WEBHOOK_ERROR_THRESHOLD_SECONDS):
                logger.info("⚠️ Recent webhook error detected, reconfiguring...")
                setup_webhook()
            else:
                logger.debug(f"ℹ️ Webhook error is old (>{WEBHOOK_ERROR_THRESHOLD_SECONDS}s), not reconfiguring")
        else:
            logger.debug(f"✓ Webhook verification successful: {info.url}")
    except Exception as e:
        logger.error(f"❌ Webhook verification failed: {e}", exc_info=True)

def log_startup_summary():
    """
    Log comprehensive startup summary with all critical configuration.
    This helps diagnose deployment issues on platforms like Render.
    """
    is_production = RENDER_HOSTNAME != 'bot-8c0e.onrender.com'
    logger.info("=" * 80)
    logger.info("🚀 BOT STARTUP SUMMARY")
    logger.info("=" * 80)
    logger.info(f"📍 Environment: {'Production (Render)' if is_production else 'Default/Development'}")
    logger.info(f"🔌 PORT: {PORT} (Source: {'Environment Variable' if os.environ.get('PORT') else 'Default'})")
    logger.info(f"🌐 Webhook URL: {WEBHOOK_URL}")
    logger.info(f"🏠 Render Hostname: {RENDER_HOSTNAME}")
    logger.info(f"🕒 Timezone: {TIMEZONE}")
    logger.info(f"🤖 Bot Token: {'✓ Configured' if BOT_TOKEN else '❌ Missing'}")
    logger.info(f"📊 Scheduler: {'✓ Running' if scheduler.running else '❌ Not Running'}")
    logger.info("=" * 80)

# Run once on import (critical for Render + gunicorn)
# This ensures webhook is set up when gunicorn loads the module
try:
    # Log startup configuration
    log_startup_summary()
    
    # Setup webhook with retry logic
    webhook_setup_success = setup_webhook()
    
    if webhook_setup_success:
        logger.info("✅ Initial webhook setup completed successfully")
    else:
        logger.warning("⚠️ Initial webhook setup failed, will retry via periodic verification")
    
    # Schedule periodic webhook verification (every 30 minutes)
    # This ensures webhook stays configured even if it gets removed
    scheduler.add_job(
        verify_webhook,
        'interval',
        minutes=30,
        id='webhook_verification',
        replace_existing=True
    )
    logger.info("✓ Webhook verification job scheduled (every 30 minutes)")
except Exception as e:
    logger.critical(f"❌ Critical error during initial webhook setup: {e}", exc_info=True)

# ────────────────────────────────────────────────
#               Local Development Only
# ────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Running in local development mode")
    bot.remove_webhook()
    app.run(host="0.0.0.0", port=PORT, debug=True)