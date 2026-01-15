import os
import sys
import logging
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

PORT = int(os.environ.get("PORT", 5000))
TIMEZONE = pytz.timezone("Asia/Riyadh")

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'bot-8c0e.onrender.com')}{WEBHOOK_PATH}"

# ────────────────────────────────────────────────
#               Instances
# ────────────────────────────────────────────────

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)
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
        except:
            logger.error(f"Invalid morning time for {chat_id}")

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
        except:
            logger.error(f"Invalid evening time for {chat_id}")

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
        except:
            logger.error(f"Invalid sleep time for {chat_id}")

    logger.info(f"Scheduled jobs for chat {chat_id}")

# ────────────────────────────────────────────────
#               Bot Handlers
# ────────────────────────────────────────────────

@bot.my_chat_member_handler()
def my_chat_member_handler(update: types.ChatMemberUpdated):
    chat_id = update.chat.id
    new_status = update.new_chat_member.status

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

@bot.message_handler(content_types=[
    'new_chat_members', 'left_chat_member', 'new_chat_title',
    'new_chat_photo', 'delete_chat_photo', 'group_chat_created',
    'supergroup_chat_created', 'channel_chat_created', 'pinned_message',
    'voice_chat_started', 'voice_chat_ended', 'voice_chat_participants_invited'
])
def delete_service_messages(message: types.Message):
    try:
        chat_id = message.chat.id
        settings = get_chat_settings(chat_id)
        if settings["delete_service_messages"]:
            bot.delete_message(chat_id, message.message_id)
            logger.debug(f"Deleted service message in {chat_id}")
    except:
        pass

@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    if message.chat.type == "private":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("👨‍💻 المطور", url="https://t.me/dev3bod"),
            types.InlineKeyboardButton("👥 المجموعة الرسمية", url="https://t.me/NourAdhkar"),
            types.InlineKeyboardButton("➕ إضافة البوت إلى مجموعة", url=f"https://t.me/{bot.get_me().username}?startgroup=true")
        )
        bot.reply_to(
            message,
            "مرحباً، أنا بوت نور الذكر.\n\n"
            "أقوم بنشر الأذكار اليومية والآيات والأحاديث بشكل تلقائي في المجموعات. "
            "أضفني كمشرف لكي أعمل بشكل صحيح.",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        logger.info(f"/start received in private chat from {message.from_user.id}")
    else:
        bot.reply_to(message, "تم التفعيل! استخدم /settings للإعدادات")
        logger.info(f"/start received in group {message.chat.id}")

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
# ────────────────────────────────────────────────
#               Flask Routes
# ────────────────────────────────────────────────

@app.route("/")
def home():
    """Health check endpoint for monitoring services"""
    return "نور الذكر – البوت يعمل ✓", 200

@app.route("/health")
def health():
    """Detailed health check endpoint"""
    try:
        # Check webhook status
        info = bot.get_webhook_info()
        status = {
            "status": "healthy",
            "webhook_url": info.url,
            "pending_updates": info.pending_update_count,
            "last_error": info.last_error_message or "None"
        }
        return status, 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}, 500

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    """Handle incoming webhook updates from Telegram"""
    if request.headers.get("content-type") == "application/json":
        try:
            json_string = request.get_data().decode("utf-8")
            update = types.Update.de_json(json_string)
            if update:
                bot.process_new_updates([update])
            return "", 200
        except UnicodeDecodeError as e:
            logger.error(f"Webhook decode error: {e}")
            return "", 400
        except Exception as e:
            logger.error(f"Webhook processing error: {e}", exc_info=True)
            # Return 200 to prevent Telegram from retrying
            return "", 200
    else:
        logger.warning(f"Invalid content-type: {request.headers.get('content-type')}")
        abort(403)

@app.route("/setwebhook", methods=["GET"])
def manual_set_webhook():
    try:
        bot.remove_webhook()
        success = bot.set_webhook(url=WEBHOOK_URL)
        return f"Webhook {'تم بنجاح' if success else 'فشل'} → {WEBHOOK_URL}"
    except Exception as e:
        return f"خطأ: {str(e)}"

@app.route("/check-webhook", methods=["GET"])
def check_webhook_status():
    try:
        info = bot.get_webhook_info()
        return f"""
        <pre>
Webhook URL           : {info.url or 'غير مضبوط'}
Pending updates       : {info.pending_update_count}
Last error date       : {info.last_error_date}
Last error message    : {info.last_error_message or 'لا يوجد'}
        </pre>
        """
    except Exception as e:
        return f"خطأ: {str(e)}"

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
    """Setup webhook with retry logic for gunicorn compatibility"""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Remove existing webhook first
            bot.remove_webhook(drop_pending_updates=True)
            logger.info("Previous webhook removed successfully")
            
            # Set new webhook
            success = bot.set_webhook(
                url=WEBHOOK_URL,
                drop_pending_updates=True,
                max_connections=100,
                allowed_updates=["message", "edited_message", "channel_post", "my_chat_member", "callback_query"]
            )
            
            if success:
                logger.info(f"✓ Webhook setup successful → {WEBHOOK_URL}")
                # Verify webhook was set correctly
                info = bot.get_webhook_info()
                logger.info(f"Webhook info: URL={info.url}, Pending={info.pending_update_count}")
                return True
            else:
                logger.warning(f"Webhook setup returned False (attempt {attempt + 1}/{max_retries})")
                
        except Exception as e:
            logger.error(f"Webhook setup error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
            else:
                logger.critical(f"Failed to setup webhook after {max_retries} attempts", exc_info=True)
                return False
    
    return False

# Run once on import (critical for Render + gunicorn)
# This ensures webhook is set up when gunicorn loads the module
try:
    setup_webhook()
except Exception as e:
    logger.critical(f"Critical error during initial webhook setup: {e}", exc_info=True)

# ────────────────────────────────────────────────
#               Local Development Only
# ────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Running in local development mode")
    bot.remove_webhook()
    app.run(host="0.0.0.0", port=PORT, debug=True)