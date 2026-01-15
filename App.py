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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

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
            sleep_time TEXT DEFAULT '22:00',
            azkar_format TEXT DEFAULT 'text',
            azkar_interval INTEGER DEFAULT 180,
            random_azkar INTEGER DEFAULT 1
        )
    ''')
    
    # Migrate existing tables if needed
    try:
        c.execute("ALTER TABLE chat_settings ADD COLUMN azkar_format TEXT DEFAULT 'text'")
    except:
        pass
    try:
        c.execute("ALTER TABLE chat_settings ADD COLUMN azkar_interval INTEGER DEFAULT 180")
    except:
        pass
    try:
        c.execute("ALTER TABLE chat_settings ADD COLUMN random_azkar INTEGER DEFAULT 1")
    except:
        pass
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

init_db()

# ────────────────────────────────────────────────
#               JSON Data Loading
# ────────────────────────────────────────────────

def load_json_data(filename):
    """Load azkar data from JSON file"""
    try:
        filepath = os.path.join(os.path.dirname(__file__), "data", filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"JSON file not found: {filename}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON file {filename}: {e}")
        return None

# Load all azkar data
MORNING_AZKAR_DATA = load_json_data("morning_azkar.json")
EVENING_AZKAR_DATA = load_json_data("evening_azkar.json")
FRIDAY_AZKAR_DATA = load_json_data("friday_azkar.json")
RAMADAN_AZKAR_DATA = load_json_data("ramadan_azkar.json")
HAJJ_AZKAR_DATA = load_json_data("hajj_azkar.json")
EID_AZKAR_DATA = load_json_data("eid_azkar.json")
ARAFAH_AZKAR_DATA = load_json_data("arafah_azkar.json")
LAYLAT_ALQADR_DATA = load_json_data("laylat_alqadr.json")
LAST_TEN_DAYS_DATA = load_json_data("last_ten_days.json")
HADITHS_DATA = load_json_data("hadiths.json")


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
        "azkar_format": row[11] if len(row) > 11 else "text",
        "azkar_interval": row[12] if len(row) > 12 else 180,
        "random_azkar": bool(row[13]) if len(row) > 13 else True,
    }

def update_chat_setting(chat_id: int, key: str, value):
    allowed_keys = {
        "is_enabled", "morning_azkar", "evening_azkar",
        "friday_sura", "friday_dua", "sleep_message",
        "delete_service_messages", "morning_time",
        "evening_time", "sleep_time", "azkar_format",
        "azkar_interval", "random_azkar"
    }
    if key not in allowed_keys:
        logger.error(f"Invalid setting key: {key}")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Handle different value types
    if key in ["morning_time", "evening_time", "sleep_time", "azkar_format"]:
        c.execute(f"UPDATE chat_settings SET {key} = ? WHERE chat_id = ?", (str(value), chat_id))
    elif key == "azkar_interval":
        c.execute(f"UPDATE chat_settings SET {key} = ? WHERE chat_id = ?", (int(value), chat_id))
    else:
        c.execute(f"UPDATE chat_settings SET {key} = ? WHERE chat_id = ?", (int(value), chat_id))
    
    conn.commit()
    conn.close()
    logger.info(f"Updated {key} = {value} for chat {chat_id}")

# ────────────────────────────────────────────────
#               Content - أذكار الصباح
# ────────────────────────────────────────────────

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

# ────────────────────────────────────────────────
#               أذكار المساء
# ────────────────────────────────────────────────

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

FRIDAY_DUA = [
    "🕌 *دعاء يوم الجمعة*\n\n"
    "اللَّهُمَّ صَلِّ وَسَلِّمْ وَبَارِكْ عَلَى سَيِّدِنَا مُحَمَّدٍ وَعَلَى آلِهِ وَصَحْبِهِ أَجْمَعِينَ\n\n"
    "✨ قال رسول الله ﷺ: «مَن صلَّى عليَّ صلاةً واحدةً صلَّى اللهُ عليه بها عشرًا»",

    "🕌 *دعاء يوم الجمعة*\n\n"
    "اللَّهُمَّ إِنِّي أَسْأَلُكَ مِنَ الْخَيْرِ كُلِّهِ عَاجِلِهِ وَآجِلِهِ، مَا عَلِمْتُ مِنْهُ وَمَا لَمْ أَعْلَمْ، وَأَعُوذُ بِكَ مِنَ الشَّرِّ كُلِّهِ عَاجِلِهِ وَآجِلِهِ، مَا عَلِمْتُ مِنْهُ وَمَا لَمْ أَعْلَمْ\n\n"
    "✨ دعاء مأثور",
]

KAHF_REMINDER = (
    "📿 *تذكير بسورة الكهف*\n\n"
    "السلام عليكم ورحمة الله وبركاته\n\n"
    "نُذَكِّرُكُم بقراءة سورة الكهف في هذا اليوم المبارك\n\n"
    "قال رسول الله ﷺ: «مَن قرأَ سورةَ الكَهفِ في يومِ الجُمُعةِ، أضاءَ له مِن النُّورِ ما بيْنَ الجُمُعتَينِ»\n\n"
    "🕌 جعلنا الله وإياكم من المواظبين على الطاعات"
)

SLEEP_MESSAGE = (
    "😴 *أذكار النوم*\n\n"
    "﴿ قُلْ هُوَ اللَّهُ أَحَدٌ * اللَّهُ الصَّمَدُ * لَمْ يَلِدْ وَلَمْ يُولَدْ * وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ ﴾\n\n"
    "﴿ قُلْ أَعُوذُ بِرَبِّ الْفَلَقِ * مِن شَرِّ مَا خَلَقَ * وَمِن شَرِّ غَاسِقٍ إِذَا وَقَبَ * وَمِن شَرِّ النَّفَّاثَاتِ فِي الْعُقَدِ * وَمِن شَرِّ حَاسِدٍ إِذَا حَسَدَ ﴾\n\n"
    "﴿ قُلْ أَعُوذُ بِرَبِّ النَّاسِ * مَلِكِ النَّاسِ * إِلَٰهِ النَّاسِ * مِن شَرِّ الْوَسْوَاسِ الْخَنَّاسِ * الَّذِي يُوَسْوِسُ فِي صُدُورِ النَّاسِ * مِنَ الْجِنَّةِ وَالنَّاسِ ﴾\n\n"
    "🌙 تصبحون على خير"
)

# ────────────────────────────────────────────────
#               Sending Functions
# ────────────────────────────────────────────────

def format_zikr_message(zikr, icon="📿"):
    """Format a single zikr from JSON data into a message"""
    message = f"{icon} *{zikr.get('text', '')}*\n\n"
    
    if 'reference' in zikr and zikr['reference']:
        message += f"📚 {zikr['reference']}\n"
    
    if 'repetitions' in zikr and zikr['repetitions']:
        message += f"✨ ({zikr['repetitions']})\n"
    
    if 'virtue' in zikr and zikr['virtue']:
        message += f"\n💎 {zikr['virtue']}"
    
    return message

def send_azkar(chat_id: int, azkar_type: str):
    try:
        settings = get_chat_settings(chat_id)
        if not settings["is_enabled"]:
            return

        messages = []
        icon = "📿"

        # Load from JSON data
        if azkar_type == "morning" and settings["morning_azkar"]:
            if MORNING_AZKAR_DATA and 'azkar' in MORNING_AZKAR_DATA:
                icon = MORNING_AZKAR_DATA.get('icon', '🌅')
                messages = [format_zikr_message(zikr, icon) for zikr in MORNING_AZKAR_DATA['azkar']]
            else:
                messages = MORNING_AZKAR  # Fallback to old data
                
        elif azkar_type == "evening" and settings["evening_azkar"]:
            if EVENING_AZKAR_DATA and 'azkar' in EVENING_AZKAR_DATA:
                icon = EVENING_AZKAR_DATA.get('icon', '🌙')
                messages = [format_zikr_message(zikr, icon) for zikr in EVENING_AZKAR_DATA['azkar']]
            else:
                messages = EVENING_AZKAR  # Fallback to old data
                
        elif azkar_type == "friday_kahf" and settings["friday_sura"]:
            if FRIDAY_AZKAR_DATA and 'kahf_reminder' in FRIDAY_AZKAR_DATA:
                messages = [FRIDAY_AZKAR_DATA['kahf_reminder']['text']]
            else:
                messages = [KAHF_REMINDER]  # Fallback
                
        elif azkar_type == "friday_dua" and settings["friday_dua"]:
            if FRIDAY_AZKAR_DATA and 'azkar' in FRIDAY_AZKAR_DATA:
                icon = FRIDAY_AZKAR_DATA.get('icon', '🕌')
                messages = [format_zikr_message(zikr, icon) for zikr in FRIDAY_AZKAR_DATA['azkar']]
            else:
                messages = FRIDAY_DUA  # Fallback
                
        elif azkar_type == "sleep" and settings["sleep_message"]:
            messages = [SLEEP_MESSAGE]

        # Send messages
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

def send_random_azkar(chat_id: int):
    """Send random azkar/hadith based on settings"""
    try:
        settings = get_chat_settings(chat_id)
        if not settings["is_enabled"] or not settings.get("random_azkar", True):
            return
        
        # Collect all available azkar
        all_azkar = []
        
        # Add hadiths
        if HADITHS_DATA and 'hadiths' in HADITHS_DATA:
            for hadith in HADITHS_DATA['hadiths']:
                msg = f"📖 *الحديث الشريف*\n\n{hadith['text']}\n\n📚 {hadith['reference']}"
                if 'virtue' in hadith:
                    msg += f"\n\n💎 {hadith['virtue']}"
                all_azkar.append(msg)
        
        # Add various category azkar (for special occasions)
        if RAMADAN_AZKAR_DATA and 'azkar' in RAMADAN_AZKAR_DATA:
            for zikr in RAMADAN_AZKAR_DATA['azkar']:
                all_azkar.append(format_zikr_message(zikr, '🌙'))
        
        if HAJJ_AZKAR_DATA and 'azkar' in HAJJ_AZKAR_DATA:
            for zikr in HAJJ_AZKAR_DATA['azkar']:
                all_azkar.append(format_zikr_message(zikr, '🕋'))
        
        # Randomly select and send one
        if all_azkar:
            msg = random.choice(all_azkar)
            bot.send_message(chat_id, msg, parse_mode="Markdown")
            logger.info(f"Sent random azkar to {chat_id}")
            
    except Exception as e:
        logger.error(f"Error sending random azkar to {chat_id}: {e}", exc_info=True)

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
    
    # Random azkar with interval
    if settings.get("random_azkar", True):
        interval = settings.get("azkar_interval", 180)
        scheduler.add_job(
            send_random_azkar,
            'interval',
            minutes=interval,
            args=[chat_id],
            id=f"random_azkar_{chat_id}",
            replace_existing=True
        )
        logger.info(f"Scheduled random azkar every {interval} minutes for {chat_id}")

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

@bot.message_handler(commands=["start", "ستارت"])
def cmd_start(message: types.Message):
    chat_type = message.chat.type
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if chat_type == "private":
        # Private chat - show welcome message with buttons
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("👨‍💻 المطور", url="https://t.me/dev3bod"),
            types.InlineKeyboardButton("👥 المجموعة الرئيسية", url="https://t.me/NourAdhkar"),
            types.InlineKeyboardButton("➕ أضفني للمجموعة", url=f"https://t.me/{bot.get_me().username}?startgroup=true")
        )
        bot.reply_to(
            message,
            "🌟 *مرحبًا، أنا بوت نور الذكر* 🌟\n\n"
            "📿 أقوم بنشر الأذكار اليومية والآيات والأحاديث بشكل تلقائي في المجموعات.\n\n"
            "✨ *للتفعيل:*\n"
            "أضفني كمشرف في مجموعتك لكي أعمل بشكل صحيح.\n\n"
            "⚙️ *الميزات:*\n"
            "• أذكار الصباح والمساء\n"
            "• سورة الكهف يوم الجمعة\n"
            "• أدعية وأذكار متنوعة\n"
            "• أحاديث نبوية شريفة\n"
            "• أذكار خاصة بالمناسبات الإسلامية\n\n"
            "📊 استخدم /help للمساعدة",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        logger.info(f"/start received in private chat from {user_id}")
    else:
        # Group chat - check if user is admin
        try:
            member = bot.get_chat_member(chat_id, user_id)
            is_admin = member.status in ['creator', 'administrator']
            
            if is_admin:
                # Admin in group - show control panel button
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="open_settings")
                )
                bot.reply_to(
                    message,
                    "✅ *مرحباً بك أيها المشرف!*\n\n"
                    "البوت جاهز للعمل في هذه المجموعة.\n"
                    "اضغط على الزر أدناه لفتح لوحة التحكم.",
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
            else:
                # Regular user in group
                bot.reply_to(
                    message,
                    "🌟 *بوت نور الذكر يعمل بنجاح!* 🌟\n\n"
                    "سيتم إرسال الأذكار والأدعية تلقائياً حسب الإعدادات.\n\n"
                    "📿 بارك الله فيكم"
                )
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            bot.reply_to(message, "✅ البوت يعمل بنجاح!")
        
        logger.info(f"/start received in group {chat_id} from user {user_id}")

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
        ("random_azkar", "🎲 أذكار متنوعة"),
        ("delete_service_messages", "🗑️ حذف رسائل الخدمة")
    ]

    for key, label in btns:
        status = "✓" if settings[key] else "✗"
        markup.add(types.InlineKeyboardButton(f"{label} {status}", callback_data=f"toggle_{key}"))
    
    # Add format selection button
    format_labels = {
        "text": "📝 نصي",
        "audio": "🎵 صوتي",
        "image": "🖼️ صورة",
        "pdf": "📄 PDF",
        "random": "🎲 عشوائي"
    }
    current_format = settings.get('azkar_format', 'text')
    markup.add(types.InlineKeyboardButton(
        f"📑 تنسيق الأذكار: {format_labels.get(current_format, '📝 نصي')}", 
        callback_data="change_format"
    ))
    
    # Add interval setting button
    markup.add(types.InlineKeyboardButton(
        f"⏱️ الفاصل الزمني: {settings.get('azkar_interval', 180)} دقيقة",
        callback_data="change_interval"
    ))

    format_desc = {
        "text": "نصي فقط",
        "audio": "ملفات صوتية",
        "image": "صور",
        "pdf": "ملفات PDF",
        "random": "تنسيق عشوائي"
    }

    text = (
        "⚙️ *لوحة التحكم الرئيسية*\n\n"
        f"حالة البوت: {'🟢 مفعّل' if settings['is_enabled'] else '🔴 معطّل'}\n\n"
        "📅 *الأوقات المجدولة:*\n"
        f"🌅 الصباح: {settings['morning_time']}\n"
        f"🌙 المساء: {settings['evening_time']}\n"
        f"😴 النوم: {settings['sleep_time']}\n"
        f"📿 سورة الكهف: الجمعة 09:00\n"
        f"🕌 دعاء الجمعة: الجمعة 10:00\n\n"
        f"📑 *التنسيق الحالي:* {format_desc.get(current_format, 'نصي')}\n"
        f"⏱️ *الفاصل الزمني:* {settings.get('azkar_interval', 180)} دقيقة\n\n"
        "💡 اضغط على الأزرار أدناه لتغيير الإعدادات"
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
    settings = get_chat_settings(call.message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [
        ("morning_azkar", "🌅 أذكار الصباح"),
        ("evening_azkar", "🌙 أذكار المساء"),
        ("friday_sura", "📿 سورة الكهف"),
        ("friday_dua", "🕌 أدعية الجمعة"),
        ("sleep_message", "😴 رسالة النوم"),
        ("random_azkar", "🎲 أذكار متنوعة"),
        ("delete_service_messages", "🗑️ حذف رسائل الخدمة")
    ]

    for k, label in btns:
        status = "✓" if settings[k] else "✗"
        markup.add(types.InlineKeyboardButton(f"{label} {status}", callback_data=f"toggle_{k}"))
    
    # Add format and interval buttons
    format_labels = {
        "text": "📝 نصي",
        "audio": "🎵 صوتي",
        "image": "🖼️ صورة",
        "pdf": "📄 PDF",
        "random": "🎲 عشوائي"
    }
    current_format = settings.get('azkar_format', 'text')
    markup.add(types.InlineKeyboardButton(
        f"📑 تنسيق الأذكار: {format_labels.get(current_format, '📝 نصي')}", 
        callback_data="change_format"
    ))
    markup.add(types.InlineKeyboardButton(
        f"⏱️ الفاصل الزمني: {settings.get('azkar_interval', 180)} دقيقة",
        callback_data="change_interval"
    ))

    format_desc = {
        "text": "نصي فقط",
        "audio": "ملفات صوتية",
        "image": "صور",
        "pdf": "ملفات PDF",
        "random": "تنسيق عشوائي"
    }

    text = (
        "⚙️ *لوحة التحكم الرئيسية*\n\n"
        f"حالة البوت: {'🟢 مفعّل' if settings['is_enabled'] else '🔴 معطّل'}\n\n"
        "📅 *الأوقات المجدولة:*\n"
        f"🌅 الصباح: {settings['morning_time']}\n"
        f"🌙 المساء: {settings['evening_time']}\n"
        f"😴 النوم: {settings['sleep_time']}\n"
        f"📿 سورة الكهف: الجمعة 09:00\n"
        f"🕌 دعاء الجمعة: الجمعة 10:00\n\n"
        f"📑 *التنسيق الحالي:* {format_desc.get(current_format, 'نصي')}\n"
        f"⏱️ *الفاصل الزمني:* {settings.get('azkar_interval', 180)} دقيقة\n\n"
        "💡 اضغط على الأزرار أدناه لتغيير الإعدادات"
    )
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )

    bot.answer_callback_query(call.id, "✅ تم التحديث")

@bot.callback_query_handler(func=lambda call: call.data == "open_settings")
def callback_open_settings(call: types.CallbackQuery):
    """Handle the open_settings callback from /start command in groups"""
    if not bot.get_chat_member(call.message.chat.id, call.from_user.id).status in ["administrator", "creator"]:
        bot.answer_callback_query(call.id, "⚠️ هذا متاح للمشرفين فقط", show_alert=True)
        return
    
    # Redirect to settings in same message
    settings = get_chat_settings(call.message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    btns = [
        ("morning_azkar", "🌅 أذكار الصباح"),
        ("evening_azkar", "🌙 أذكار المساء"),
        ("friday_sura", "📿 سورة الكهف"),
        ("friday_dua", "🕌 أدعية الجمعة"),
        ("sleep_message", "😴 رسالة النوم"),
        ("random_azkar", "🎲 أذكار متنوعة"),
        ("delete_service_messages", "🗑️ حذف رسائل الخدمة")
    ]
    
    for key, label in btns:
        status = "✓" if settings[key] else "✗"
        markup.add(types.InlineKeyboardButton(f"{label} {status}", callback_data=f"toggle_{key}"))
    
    format_labels = {
        "text": "📝 نصي",
        "audio": "🎵 صوتي",
        "image": "🖼️ صورة",
        "pdf": "📄 PDF",
        "random": "🎲 عشوائي"
    }
    current_format = settings.get('azkar_format', 'text')
    markup.add(types.InlineKeyboardButton(
        f"📑 تنسيق الأذكار: {format_labels.get(current_format, '📝 نصي')}", 
        callback_data="change_format"
    ))
    markup.add(types.InlineKeyboardButton(
        f"⏱️ الفاصل الزمني: {settings.get('azkar_interval', 180)} دقيقة",
        callback_data="change_interval"
    ))
    
    format_desc = {
        "text": "نصي فقط",
        "audio": "ملفات صوتية",
        "image": "صور",
        "pdf": "ملفات PDF",
        "random": "تنسيق عشوائي"
    }
    
    text = (
        "⚙️ *لوحة التحكم الرئيسية*\n\n"
        f"حالة البوت: {'🟢 مفعّل' if settings['is_enabled'] else '🔴 معطّل'}\n\n"
        "📅 *الأوقات المجدولة:*\n"
        f"🌅 الصباح: {settings['morning_time']}\n"
        f"🌙 المساء: {settings['evening_time']}\n"
        f"😴 النوم: {settings['sleep_time']}\n"
        f"📿 سورة الكهف: الجمعة 09:00\n"
        f"🕌 دعاء الجمعة: الجمعة 10:00\n\n"
        f"📑 *التنسيق الحالي:* {format_desc.get(current_format, 'نصي')}\n"
        f"⏱️ *الفاصل الزمني:* {settings.get('azkar_interval', 180)} دقيقة\n\n"
        "💡 اضغط على الأزرار أدناه لتغيير الإعدادات"
    )
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.answer_callback_query(call.id, "✅ تم فتح لوحة التحكم")

@bot.callback_query_handler(func=lambda call: call.data == "change_format")
def callback_change_format(call: types.CallbackQuery):
    """Handle format selection"""
    if not bot.get_chat_member(call.message.chat.id, call.from_user.id).status in ["administrator", "creator"]:
        bot.answer_callback_query(call.id, "⚠️ هذا متاح للمشرفين فقط", show_alert=True)
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📝 نصي", callback_data="format_text"),
        types.InlineKeyboardButton("🎵 صوتي", callback_data="format_audio"),
        types.InlineKeyboardButton("🖼️ صورة", callback_data="format_image"),
        types.InlineKeyboardButton("📄 PDF", callback_data="format_pdf"),
        types.InlineKeyboardButton("🎲 عشوائي", callback_data="format_random"),
        types.InlineKeyboardButton("◀️ رجوع", callback_data="open_settings")
    )
    
    text = (
        "📑 *تخصيص تنسيق الأذكار*\n\n"
        "اختر التنسيق المفضل لإرسال الأذكار:\n\n"
        "• *نصي:* رسائل نصية فقط\n"
        "• *صوتي:* ملفات صوتية (للصباح والمساء)\n"
        "• *صورة:* صور تحتوي على الأذكار\n"
        "• *PDF:* ملفات PDF\n"
        "• *عشوائي:* اختيار عشوائي بين جميع التنسيقات\n\n"
        "💡 ملاحظة: التنسيق الصوتي متاح حالياً للأذكار الصباحية والمسائية فقط"
    )
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("format_"))
def callback_set_format(call: types.CallbackQuery):
    """Set the selected format"""
    if not bot.get_chat_member(call.message.chat.id, call.from_user.id).status in ["administrator", "creator"]:
        bot.answer_callback_query(call.id, "⚠️ هذا متاح للمشرفين فقط", show_alert=True)
        return
    
    format_type = call.data.split("_")[1]
    update_chat_setting(call.message.chat.id, "azkar_format", format_type)
    
    format_labels = {
        "text": "📝 نصي",
        "audio": "🎵 صوتي",
        "image": "🖼️ صورة",
        "pdf": "📄 PDF",
        "random": "🎲 عشوائي"
    }
    
    bot.answer_callback_query(call.id, f"✅ تم تحديد التنسيق: {format_labels.get(format_type, 'نصي')}")
    
    # Return to main settings
    callback_open_settings(call)

@bot.callback_query_handler(func=lambda call: call.data == "change_interval")
def callback_change_interval(call: types.CallbackQuery):
    """Handle interval selection"""
    if not bot.get_chat_member(call.message.chat.id, call.from_user.id).status in ["administrator", "creator"]:
        bot.answer_callback_query(call.id, "⚠️ هذا متاح للمشرفين فقط", show_alert=True)
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⏱️ 60 دقيقة", callback_data="interval_60"),
        types.InlineKeyboardButton("⏱️ 90 دقيقة", callback_data="interval_90"),
        types.InlineKeyboardButton("⏱️ 120 دقيقة", callback_data="interval_120"),
        types.InlineKeyboardButton("⏱️ 180 دقيقة", callback_data="interval_180"),
        types.InlineKeyboardButton("⏱️ 240 دقيقة", callback_data="interval_240"),
        types.InlineKeyboardButton("⏱️ 360 دقيقة", callback_data="interval_360"),
        types.InlineKeyboardButton("◀️ رجوع", callback_data="open_settings")
    )
    
    text = (
        "⏱️ *تخصيص الفاصل الزمني*\n\n"
        "اختر الفاصل الزمني بين إرسال الأذكار المتنوعة:\n\n"
        "• 60 دقيقة = ساعة واحدة\n"
        "• 90 دقيقة = ساعة ونصف\n"
        "• 120 دقيقة = ساعتان\n"
        "• 180 دقيقة = 3 ساعات (الافتراضي)\n"
        "• 240 دقيقة = 4 ساعات\n"
        "• 360 دقيقة = 6 ساعات\n\n"
        "💡 الفاصل الزمني يتحكم في تكرار الأذكار المتنوعة والأحاديث"
    )
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("interval_"))
def callback_set_interval(call: types.CallbackQuery):
    """Set the selected interval"""
    if not bot.get_chat_member(call.message.chat.id, call.from_user.id).status in ["administrator", "creator"]:
        bot.answer_callback_query(call.id, "⚠️ هذا متاح للمشرفين فقط", show_alert=True)
        return
    
    interval = int(call.data.split("_")[1])
    update_chat_setting(call.message.chat.id, "azkar_interval", interval)
    schedule_chat_jobs(call.message.chat.id)
    
    bot.answer_callback_query(call.id, f"✅ تم تحديد الفاصل الزمني: {interval} دقيقة")
    
    # Return to main settings
    callback_open_settings(call)

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
    return "نور الذكر – البوت يعمل ✓"

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    if request.headers.get("content-type") == "application/json":
        try:
            json_string = request.get_data().decode("utf-8")
            update = types.Update.de_json(json_string)
            if update:
                bot.process_new_updates([update])
            return "", 200
        except Exception as e:
            logger.error(f"Webhook processing error: {e}", exc_info=True)
            return "", 200
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
#               Auto Webhook Setup
# ────────────────────────────────────────────────

def setup_webhook():
    try:
        bot.remove_webhook()
        success = bot.set_webhook(
            url=WEBHOOK_URL,
            drop_pending_updates=True,
            allow_updates=["message", "edited_message", "channel_post", "my_chat_member"]
        )
        logger.info(f"Webhook auto-setup → {WEBHOOK_URL} | Success: {success}")
    except Exception as e:
        logger.critical(f"Webhook setup failed: {str(e)}", exc_info=True)

# Run once on import (critical for Render + gunicorn)
setup_webhook()

# ────────────────────────────────────────────────
#               Local Development Only
# ────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Running in local development mode")
    bot.remove_webhook()
    app.run(host="0.0.0.0", port=PORT, debug=True)