import os
import sys
import logging
import time
import base64
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

# PostgreSQL support
try:
    import psycopg2
    import psycopg2.extras
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning("psycopg2 not available, PostgreSQL features disabled")

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
#               Constants
# ────────────────────────────────────────────────

# Message sending delays (in seconds)
MESSAGE_DELAY_SECONDS = 0.05  # Small delay between messages to avoid flood limits
FLOOD_WAIT_DELAY_SECONDS = 1  # Delay after FloodWait error before continuing

# Error detection keywords
ERROR_BLOCKED = "blocked"
ERROR_KICKED = "kicked"
ERROR_FLOOD = "flood"
ERROR_RETRY_AFTER = "retry after"
ERROR_CHAT_NOT_FOUND = "chat not found"
ERROR_FORBIDDEN = "forbidden"
ERROR_DEACTIVATED = "deactivated"

# Azkar category display names for logging
AZKAR_CATEGORY_NAMES = {
    "morning": "Morning Azkar",
    "evening": "Evening Azkar",
    "friday_kahf": "Friday Kahf",
    "friday_dua": "Friday Dua",
    "sleep": "Sleep Message",
    "diverse": "Adhkar Diverse"
}

# ────────────────────────────────────────────────
#               Configuration
# ────────────────────────────────────────────────

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    logger.critical("BOT_TOKEN غير موجود في متغيرات البيئة")
    raise ValueError("BOT_TOKEN is required")

# DATABASE_URL for PostgreSQL connection
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    # Validate and fix common DATABASE_URL format issues
    # Render and some providers use "postgres://" which is deprecated
    # psycopg2 requires "postgresql://"
    
    # Check for valid DSN format (should contain :// for URI format or = for key-value format)
    if "://" not in DATABASE_URL and "=" not in DATABASE_URL:
        # Don't log the actual value to avoid exposing credentials
        logger.error("❌ Invalid DATABASE_URL format. Expected format: postgresql://user:password@host:port/database")
        logger.warning("PostgreSQL features disabled due to invalid DSN. Using SQLite fallback.")
        DATABASE_URL = None
    elif DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        logger.info("✓ DATABASE_URL format corrected (postgres:// → postgresql://)")
    elif DATABASE_URL.startswith("psql://"):
        # Handle incorrect "psql://" format
        DATABASE_URL = DATABASE_URL.replace("psql://", "postgresql://", 1)
        logger.info("✓ DATABASE_URL format corrected (psql:// → postgresql://)")
    
    if DATABASE_URL:
        logger.info("✓ DATABASE_URL configured for PostgreSQL")
else:
    logger.info("ℹ️ DATABASE_URL not set, PostgreSQL features disabled")

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
    
    # Main chat settings table
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
            media_enabled INTEGER DEFAULT 0,
            media_type TEXT DEFAULT 'images',
            send_media_with_morning INTEGER DEFAULT 0,
            send_media_with_evening INTEGER DEFAULT 0,
            send_media_with_friday INTEGER DEFAULT 0
        )
    ''')
    
    # Diverse azkar settings table for interval-based sending
    c.execute('''
        CREATE TABLE IF NOT EXISTS diverse_azkar_settings (
            chat_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            interval_minutes INTEGER DEFAULT 60,
            media_type TEXT DEFAULT 'text',
            last_sent_timestamp INTEGER DEFAULT 0,
            FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id)
        )
    ''')
    
    # Ramadan settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS ramadan_settings (
            chat_id INTEGER PRIMARY KEY,
            ramadan_enabled INTEGER DEFAULT 1,
            laylat_alqadr_enabled INTEGER DEFAULT 1,
            last_ten_days_enabled INTEGER DEFAULT 1,
            iftar_dua_enabled INTEGER DEFAULT 1,
            media_type TEXT DEFAULT 'images',
            FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id)
        )
    ''')
    
    # Hajj and Eid settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS hajj_eid_settings (
            chat_id INTEGER PRIMARY KEY,
            arafah_day_enabled INTEGER DEFAULT 1,
            eid_eve_enabled INTEGER DEFAULT 1,
            eid_day_enabled INTEGER DEFAULT 1,
            eid_adha_enabled INTEGER DEFAULT 1,
            hajj_enabled INTEGER DEFAULT 1,
            media_type TEXT DEFAULT 'images',
            FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id)
        )
    ''')
    
    # Fasting reminders settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS fasting_reminders (
            chat_id INTEGER PRIMARY KEY,
            monday_thursday_enabled INTEGER DEFAULT 1,
            arafah_reminder_enabled INTEGER DEFAULT 1,
            reminder_time TEXT DEFAULT '21:00',
            FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id)
        )
    ''')
    
    # Admin/supervisor information table
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_primary_admin INTEGER DEFAULT 0,
            added_at INTEGER DEFAULT (strftime('%s', 'now')),
            UNIQUE(user_id, chat_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized with all tables")

def migrate_db():
    """Apply database migrations for new fields."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    try:
        # Check if media format fields exist in diverse_azkar_settings
        c.execute("PRAGMA table_info(diverse_azkar_settings)")
        columns = [col[1] for col in c.fetchall()]
        
        # Add new media format fields if they don't exist
        if 'enable_audio' not in columns:
            c.execute("ALTER TABLE diverse_azkar_settings ADD COLUMN enable_audio INTEGER DEFAULT 1")
            logger.info("Added enable_audio column to diverse_azkar_settings")
        
        if 'enable_images' not in columns:
            c.execute("ALTER TABLE diverse_azkar_settings ADD COLUMN enable_images INTEGER DEFAULT 1")
            logger.info("Added enable_images column to diverse_azkar_settings")
        
        if 'enable_pdf' not in columns:
            c.execute("ALTER TABLE diverse_azkar_settings ADD COLUMN enable_pdf INTEGER DEFAULT 1")
            logger.info("Added enable_pdf column to diverse_azkar_settings")
        
        if 'enable_text' not in columns:
            c.execute("ALTER TABLE diverse_azkar_settings ADD COLUMN enable_text INTEGER DEFAULT 1")
            logger.info("Added enable_text column to diverse_azkar_settings")
        
        conn.commit()
        logger.info("Database migration completed successfully")
    except Exception as e:
        logger.error(f"Error during database migration: {e}", exc_info=True)
        try:
            conn.rollback()
            logger.warning("Database migration rolled back")
        except Exception:
            pass
    finally:
        if conn:
            conn.close()

init_db()
migrate_db()

def init_postgres_db():
    """Initialize PostgreSQL database tables if DATABASE_URL is configured."""
    if not (DATABASE_URL and POSTGRES_AVAILABLE):
        return
    
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # Main chat settings table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS chat_settings (
                        chat_id BIGINT PRIMARY KEY,
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
                        media_enabled INTEGER DEFAULT 0,
                        media_type TEXT DEFAULT 'images',
                        send_media_with_morning INTEGER DEFAULT 0,
                        send_media_with_evening INTEGER DEFAULT 0,
                        send_media_with_friday INTEGER DEFAULT 0
                    )
                ''')
                
                # Diverse azkar settings table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS diverse_azkar_settings (
                        chat_id BIGINT PRIMARY KEY,
                        enabled INTEGER DEFAULT 0,
                        interval_minutes INTEGER DEFAULT 60,
                        media_type TEXT DEFAULT 'text',
                        last_sent_timestamp BIGINT DEFAULT 0,
                        FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id)
                    )
                ''')
                
                # Ramadan settings table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS ramadan_settings (
                        chat_id BIGINT PRIMARY KEY,
                        ramadan_enabled INTEGER DEFAULT 1,
                        laylat_alqadr_enabled INTEGER DEFAULT 1,
                        last_ten_days_enabled INTEGER DEFAULT 1,
                        iftar_dua_enabled INTEGER DEFAULT 1,
                        media_type TEXT DEFAULT 'images',
                        FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id)
                    )
                ''')
                
                # Hajj and Eid settings table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS hajj_eid_settings (
                        chat_id BIGINT PRIMARY KEY,
                        arafah_day_enabled INTEGER DEFAULT 1,
                        eid_eve_enabled INTEGER DEFAULT 1,
                        eid_day_enabled INTEGER DEFAULT 1,
                        eid_adha_enabled INTEGER DEFAULT 1,
                        hajj_enabled INTEGER DEFAULT 1,
                        media_type TEXT DEFAULT 'images',
                        FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id)
                    )
                ''')
                
                # Fasting reminders settings table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS fasting_reminders (
                        chat_id BIGINT PRIMARY KEY,
                        monday_thursday_enabled INTEGER DEFAULT 1,
                        arafah_reminder_enabled INTEGER DEFAULT 1,
                        reminder_time TEXT DEFAULT '21:00',
                        FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id)
                    )
                ''')
                
                # Admin/supervisor information table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS admins (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        chat_id BIGINT NOT NULL,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        is_primary_admin INTEGER DEFAULT 0,
                        added_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                        UNIQUE(user_id, chat_id)
                    )
                ''')
                
                conn.commit()
                logger.info("✓ PostgreSQL database initialized with all tables")
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL database: {e}", exc_info=True)
        logger.info("Continuing with SQLite fallback")

# Initialize PostgreSQL if available
init_postgres_db()

def migrate_postgres_db():
    """Apply database migrations for PostgreSQL."""
    if not (DATABASE_URL and POSTGRES_AVAILABLE):
        return
    
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # Check if media format fields exist in diverse_azkar_settings
                c.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='diverse_azkar_settings'
                """)
                columns = [col[0] for col in c.fetchall()]
                
                # Add new media format fields if they don't exist
                if 'enable_audio' not in columns:
                    c.execute("ALTER TABLE diverse_azkar_settings ADD COLUMN enable_audio INTEGER DEFAULT 1")
                    logger.info("Added enable_audio column to diverse_azkar_settings (PostgreSQL)")
                
                if 'enable_images' not in columns:
                    c.execute("ALTER TABLE diverse_azkar_settings ADD COLUMN enable_images INTEGER DEFAULT 1")
                    logger.info("Added enable_images column to diverse_azkar_settings (PostgreSQL)")
                
                if 'enable_pdf' not in columns:
                    c.execute("ALTER TABLE diverse_azkar_settings ADD COLUMN enable_pdf INTEGER DEFAULT 1")
                    logger.info("Added enable_pdf column to diverse_azkar_settings (PostgreSQL)")
                
                if 'enable_text' not in columns:
                    c.execute("ALTER TABLE diverse_azkar_settings ADD COLUMN enable_text INTEGER DEFAULT 1")
                    logger.info("Added enable_text column to diverse_azkar_settings (PostgreSQL)")
                
                conn.commit()
                logger.info("PostgreSQL database migration completed")
    except Exception as e:
        logger.error(f"Error during PostgreSQL database migration: {e}", exc_info=True)

# Run migrations
migrate_postgres_db()

# ────────────────────────────────────────────────
#               Database Helper Functions
# ────────────────────────────────────────────────

def get_db_connection():
    """
    Get database connection - PostgreSQL if available, otherwise SQLite.
    
    Returns:
        tuple: (connection, cursor, is_postgres)
    """
    if DATABASE_URL and POSTGRES_AVAILABLE:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            return conn, cursor, True
        except Exception as e:
            logger.warning(f"PostgreSQL connection failed, using SQLite: {e}")
    
    # Fallback to SQLite
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    return conn, cursor, False

# ────────────────────────────────────────────────
#               Helper Functions
# ────────────────────────────────────────────────

# ────────────────────────────────────────────────
#               Helper Functions
# ────────────────────────────────────────────────

def validate_time_format(time_str: str) -> tuple:
    """
    Validate time string format and return hour and minute.
    
    Args:
        time_str (str): Time string in HH:MM format
        
    Returns:
        tuple: (hour, minute, is_valid, error_message)
               If valid: (h, m, True, None)
               If invalid: (None, None, False, error_message)
    """
    if not time_str:
        return (None, None, False, "Empty time string")
    
    if ':' not in time_str:
        return (None, None, False, "Missing ':' separator")
    
    parts = time_str.split(":")
    if len(parts) != 2:
        return (None, None, False, f"Invalid format: expected HH:MM, got '{time_str}'")
    
    try:
        h = int(parts[0])
        m = int(parts[1])
    except ValueError:
        return (None, None, False, f"Non-numeric values in '{time_str}'")
    
    if not (0 <= h <= 23):
        return (None, None, False, f"Invalid hour: {h} (must be 0-23)")
    
    if not (0 <= m <= 59):
        return (None, None, False, f"Invalid minute: {m} (must be 0-59)")
    
    return (h, m, True, None)

def is_user_admin_in_any_group(user_id: int) -> bool:
    """
    Check if a user is an administrator in any group that has the bot.
    
    Args:
        user_id (int): The Telegram user ID to check
        
    Returns:
        bool: True if user is admin/creator in any group, False otherwise
        
    This function:
    - First checks the admins database for efficiency
    - Falls back to Telegram API check if database is empty or user not found
    - Connects to PostgreSQL database if DATABASE_URL is available, falls back to SQLite
    
    Note: Database connections are opened and closed for each call. This is by design
    to avoid connection state issues in the multi-threaded Flask + Gunicorn environment.
    For high-volume scenarios, consider implementing connection pooling.
    """
    try:
        # First, check the admins database for efficiency
        # Note: Connection is opened/closed per call to avoid threading issues
        conn, c, is_postgres = get_db_connection()
        
        try:
            placeholder = "%s" if is_postgres else "?"
            c.execute(f'''
                SELECT COUNT(*) FROM admins 
                WHERE user_id = {placeholder}
            ''', (user_id,))
            
            count = c.fetchone()[0]
            
            if count > 0:
                logger.debug(f"User {user_id} found in admins database ({count} groups)")
                return True
        finally:
            conn.close()
        
        # If not found in database, fall back to Telegram API check
        # This ensures we don't miss admins who haven't used /start yet
        chat_ids = []
        
        # Try PostgreSQL first if available
        if DATABASE_URL and POSTGRES_AVAILABLE:
            try:
                with psycopg2.connect(DATABASE_URL) as conn:
                    with conn.cursor() as cursor:
                        # Get all group chat_ids (negative IDs indicate groups)
                        cursor.execute("SELECT chat_id FROM chat_settings WHERE chat_id < 0")
                        chat_ids = [row[0] for row in cursor.fetchall()]
                        logger.debug(f"Retrieved {len(chat_ids)} group chat_ids from PostgreSQL")
            except Exception as e:
                logger.warning(f"PostgreSQL query failed, falling back to SQLite: {e}")
                # Fall through to SQLite fallback
        
        # Fallback to SQLite if PostgreSQL not available or failed
        if not chat_ids:
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("SELECT chat_id FROM chat_settings WHERE chat_id < 0")
                chat_ids = [row[0] for row in c.fetchall()]
            logger.debug(f"Retrieved {len(chat_ids)} group chat_ids from SQLite")
        
        # Check admin status in each group via Telegram API
        for chat_id in chat_ids:
            try:
                member = bot.get_chat_member(chat_id, user_id)
                if member.status in ["administrator", "creator"]:
                    logger.info(f"User {user_id} is admin in group {chat_id} (API check)")
                    # Save to database for future efficiency
                    try:
                        save_admin_info(
                            user_id=user_id,
                            chat_id=chat_id,
                            username=member.user.username,
                            first_name=member.user.first_name,
                            last_name=member.user.last_name
                        )
                    except Exception as e:
                        # Don't fail the check if save fails, but log it
                        logger.debug(f"Could not save admin info for user {user_id} in chat {chat_id}: {e}")
                    return True
            except Exception as e:
                # User might not be in this group, or bot might have been removed
                logger.debug(f"Could not check admin status for user {user_id} in chat {chat_id}: {e}")
                continue
        
        logger.debug(f"User {user_id} is not an admin in any group")
        return False
        
    except Exception as e:
        logger.error(f"Error in is_user_admin_in_any_group: {e}", exc_info=True)
        return False

def get_chat_settings(chat_id: int) -> dict:
    """Get chat settings from database (PostgreSQL preferred, SQLite fallback)."""
    conn, c, is_postgres = get_db_connection()
    
    try:
        # Use appropriate placeholder for database type
        placeholder = "%s" if is_postgres else "?"
        c.execute(f"SELECT * FROM chat_settings WHERE chat_id = {placeholder}", (chat_id,))
        row = c.fetchone()
        
        if row is None:
            # Create default settings for new chat
            c.execute(f"INSERT INTO chat_settings (chat_id) VALUES ({placeholder})", (chat_id,))
            conn.commit()
            
            # Fetch the newly created row instead of recursion
            c.execute(f"SELECT * FROM chat_settings WHERE chat_id = {placeholder}", (chat_id,))
            row = c.fetchone()
        
        # Handle both old and new schema for backward compatibility
        result = {
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
            "media_enabled": bool(row[11]) if len(row) > 11 else False,
            "media_type": row[12] if len(row) > 12 else "images",
            "send_media_with_morning": bool(row[13]) if len(row) > 13 else False,
            "send_media_with_evening": bool(row[14]) if len(row) > 14 else False,
            "send_media_with_friday": bool(row[15]) if len(row) > 15 else False,
        }
        return result
    except Exception as e:
        logger.error(f"Error getting chat settings: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

def update_chat_setting(chat_id: int, key: str, value):
    """Update chat setting in database (PostgreSQL preferred, SQLite fallback)."""
    allowed_keys = {
        "is_enabled", "morning_azkar", "evening_azkar",
        "friday_sura", "friday_dua", "sleep_message",
        "delete_service_messages", "morning_time",
        "evening_time", "sleep_time", "media_enabled",
        "media_type", "send_media_with_morning",
        "send_media_with_evening", "send_media_with_friday"
    }
    if key not in allowed_keys:
        logger.error(f"Invalid setting key: {key}")
        return

    conn, c, is_postgres = get_db_connection()
    
    try:
        # Convert value to appropriate type based on key
        if key in ["morning_time", "evening_time", "sleep_time", "media_type"]:
            # String values - no conversion needed
            final_value = value
        else:
            # Boolean/integer values - convert to int
            final_value = int(value)
        
        # Use appropriate placeholder for database type
        placeholder = "%s" if is_postgres else "?"
        c.execute(f"UPDATE chat_settings SET {key} = {placeholder} WHERE chat_id = {placeholder}", (final_value, chat_id))
        conn.commit()
        logger.info(f"Updated {key} = {value} for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error updating chat setting: {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            conn.close()

# ────────────────────────────────────────────────
#               Diverse Azkar Settings Functions
# ────────────────────────────────────────────────

def get_diverse_azkar_settings(chat_id: int) -> dict:
    """Get diverse azkar settings for a chat, creating default if not exists."""
    conn, c, is_postgres = get_db_connection()
    
    try:
        placeholder = "%s" if is_postgres else "?"
        c.execute(f"SELECT * FROM diverse_azkar_settings WHERE chat_id = {placeholder}", (chat_id,))
        row = c.fetchone()
        
        if row is None:
            # Create default settings for new chat
            c.execute(f"INSERT INTO diverse_azkar_settings (chat_id) VALUES ({placeholder})", (chat_id,))
            conn.commit()
            
            # Fetch the newly created row instead of recursion
            c.execute(f"SELECT * FROM diverse_azkar_settings WHERE chat_id = {placeholder}", (chat_id,))
            row = c.fetchone()
        
        result = {
            "chat_id": row[0],
            "enabled": bool(row[1]),
            "interval_minutes": row[2],
            "media_type": row[3],
            "last_sent_timestamp": row[4],
            "enable_audio": bool(row[5]) if len(row) > 5 else True,
            "enable_images": bool(row[6]) if len(row) > 6 else True,
            "enable_pdf": bool(row[7]) if len(row) > 7 else True,
            "enable_text": bool(row[8]) if len(row) > 8 else True
        }
        return result
    except Exception as e:
        logger.error(f"Error getting diverse azkar settings: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

def update_diverse_azkar_setting(chat_id: int, key: str, value):
    """Update a specific diverse azkar setting."""
    # Whitelist validation to prevent SQL injection
    allowed_keys = {"enabled", "interval_minutes", "media_type", "last_sent_timestamp", 
                    "enable_audio", "enable_images", "enable_pdf", "enable_text"}
    if key not in allowed_keys:
        logger.error(f"Invalid diverse azkar setting key: {key}")
        return
    
    conn, c, is_postgres = get_db_connection()
    
    try:
        placeholder = "%s" if is_postgres else "?"
        
        # Ensure settings exist
        c.execute(f"SELECT chat_id FROM diverse_azkar_settings WHERE chat_id = {placeholder}", (chat_id,))
        if not c.fetchone():
            c.execute(f"INSERT INTO diverse_azkar_settings (chat_id) VALUES ({placeholder})", (chat_id,))
        
        # Convert value based on key type
        if key == "media_type":
            final_value = value
        else:
            final_value = int(value)
        
        # Safe to use f-string here as key is validated against whitelist above
        c.execute(f"UPDATE diverse_azkar_settings SET {key} = {placeholder} WHERE chat_id = {placeholder}", (final_value, chat_id))
        conn.commit()
        logger.info(f"Updated diverse azkar {key} = {value} for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error updating diverse azkar setting: {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            conn.close()

# ────────────────────────────────────────────────
#               Ramadan Settings Functions
# ────────────────────────────────────────────────

def get_ramadan_settings(chat_id: int) -> dict:
    """Get Ramadan settings for a chat, creating default if not exists."""
    conn, c, is_postgres = get_db_connection()
    
    try:
        placeholder = "%s" if is_postgres else "?"
        c.execute(f"SELECT * FROM ramadan_settings WHERE chat_id = {placeholder}", (chat_id,))
        row = c.fetchone()
        
        if row is None:
            # Create default settings for new chat
            c.execute(f"INSERT INTO ramadan_settings (chat_id) VALUES ({placeholder})", (chat_id,))
            conn.commit()
            
            # Fetch the newly created row instead of recursion
            c.execute(f"SELECT * FROM ramadan_settings WHERE chat_id = {placeholder}", (chat_id,))
            row = c.fetchone()
        
        result = {
            "chat_id": row[0],
            "ramadan_enabled": bool(row[1]),
            "laylat_alqadr_enabled": bool(row[2]),
            "last_ten_days_enabled": bool(row[3]),
            "iftar_dua_enabled": bool(row[4]),
            "media_type": row[5]
        }
        return result
    except Exception as e:
        logger.error(f"Error getting ramadan settings: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

def update_ramadan_setting(chat_id: int, key: str, value):
    """Update a specific Ramadan setting."""
    # Whitelist validation to prevent SQL injection
    allowed_keys = {
        "ramadan_enabled", "laylat_alqadr_enabled",
        "last_ten_days_enabled", "iftar_dua_enabled", "media_type"
    }
    if key not in allowed_keys:
        logger.error(f"Invalid ramadan setting key: {key}")
        return
    
    conn, c, is_postgres = get_db_connection()
    
    try:
        placeholder = "%s" if is_postgres else "?"
        
        # Ensure settings exist
        c.execute(f"SELECT chat_id FROM ramadan_settings WHERE chat_id = {placeholder}", (chat_id,))
        if not c.fetchone():
            c.execute(f"INSERT INTO ramadan_settings (chat_id) VALUES ({placeholder})", (chat_id,))
        
        # Convert value based on key type
        if key == "media_type":
            final_value = value
        else:
            final_value = int(value)
        
        # Safe to use f-string here as key is validated against whitelist above
        c.execute(f"UPDATE ramadan_settings SET {key} = {placeholder} WHERE chat_id = {placeholder}", (final_value, chat_id))
        conn.commit()
        logger.info(f"Updated ramadan {key} = {value} for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error updating ramadan setting: {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            conn.close()

# ────────────────────────────────────────────────
#               Hajj & Eid Settings Functions
# ────────────────────────────────────────────────

def get_hajj_eid_settings(chat_id: int) -> dict:
    """Get Hajj and Eid settings for a chat, creating default if not exists."""
    conn, c, is_postgres = get_db_connection()
    
    try:
        placeholder = "%s" if is_postgres else "?"
        c.execute(f"SELECT * FROM hajj_eid_settings WHERE chat_id = {placeholder}", (chat_id,))
        row = c.fetchone()
        
        if row is None:
            # Create default settings for new chat
            c.execute(f"INSERT INTO hajj_eid_settings (chat_id) VALUES ({placeholder})", (chat_id,))
            conn.commit()
            
            # Fetch the newly created row instead of recursion
            c.execute(f"SELECT * FROM hajj_eid_settings WHERE chat_id = {placeholder}", (chat_id,))
            row = c.fetchone()
        
        result = {
            "chat_id": row[0],
            "arafah_day_enabled": bool(row[1]),
            "eid_eve_enabled": bool(row[2]),
            "eid_day_enabled": bool(row[3]),
            "eid_adha_enabled": bool(row[4]),
            "hajj_enabled": bool(row[5]),
            "media_type": row[6]
        }
        return result
    except Exception as e:
        logger.error(f"Error getting hajj_eid settings: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

def update_hajj_eid_setting(chat_id: int, key: str, value):
    """Update a specific Hajj/Eid setting."""
    # Whitelist validation to prevent SQL injection
    allowed_keys = {
        "arafah_day_enabled", "eid_eve_enabled", "eid_day_enabled",
        "eid_adha_enabled", "hajj_enabled", "media_type"
    }
    if key not in allowed_keys:
        logger.error(f"Invalid hajj_eid setting key: {key}")
        return
    
    conn, c, is_postgres = get_db_connection()
    
    try:
        placeholder = "%s" if is_postgres else "?"
        
        # Ensure settings exist
        c.execute(f"SELECT chat_id FROM hajj_eid_settings WHERE chat_id = {placeholder}", (chat_id,))
        if not c.fetchone():
            c.execute(f"INSERT INTO hajj_eid_settings (chat_id) VALUES ({placeholder})", (chat_id,))
        
        # Convert value based on key type
        if key == "media_type":
            final_value = value
        else:
            final_value = int(value)
        
        # Safe to use f-string here as key is validated against whitelist above
        c.execute(f"UPDATE hajj_eid_settings SET {key} = {placeholder} WHERE chat_id = {placeholder}", (final_value, chat_id))
        conn.commit()
        logger.info(f"Updated hajj_eid {key} = {value} for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error updating hajj_eid setting: {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            conn.close()

# ────────────────────────────────────────────────
#               Fasting Reminders Settings Functions
# ────────────────────────────────────────────────

def get_fasting_reminders_settings(chat_id: int) -> dict:
    """Get fasting reminders settings for a chat, creating default if not exists."""
    conn, c, is_postgres = get_db_connection()
    
    try:
        placeholder = "%s" if is_postgres else "?"
        c.execute(f"SELECT * FROM fasting_reminders WHERE chat_id = {placeholder}", (chat_id,))
        row = c.fetchone()
        
        if row is None:
            # Create default settings for new chat
            c.execute(f"INSERT INTO fasting_reminders (chat_id) VALUES ({placeholder})", (chat_id,))
            conn.commit()
            
            # Fetch the newly created row instead of recursion
            c.execute(f"SELECT * FROM fasting_reminders WHERE chat_id = {placeholder}", (chat_id,))
            row = c.fetchone()
        
        result = {
            "chat_id": row[0],
            "monday_thursday_enabled": bool(row[1]),
            "arafah_reminder_enabled": bool(row[2]),
            "reminder_time": row[3]
        }
        return result
    except Exception as e:
        logger.error(f"Error getting fasting reminders settings: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

def update_fasting_reminder_setting(chat_id: int, key: str, value):
    """Update a specific fasting reminder setting."""
    # Whitelist validation to prevent SQL injection
    allowed_keys = {
        "monday_thursday_enabled", "arafah_reminder_enabled", "reminder_time"
    }
    if key not in allowed_keys:
        logger.error(f"Invalid fasting reminder setting key: {key}")
        return
    
    conn, c, is_postgres = get_db_connection()
    
    try:
        placeholder = "%s" if is_postgres else "?"
        
        # Ensure settings exist
        c.execute(f"SELECT chat_id FROM fasting_reminders WHERE chat_id = {placeholder}", (chat_id,))
        if not c.fetchone():
            c.execute(f"INSERT INTO fasting_reminders (chat_id) VALUES ({placeholder})", (chat_id,))
        
        # Convert value based on key type
        if key == "reminder_time":
            final_value = value
        else:
            final_value = int(value)
        
        # Safe to use f-string here as key is validated against whitelist above
        c.execute(f"UPDATE fasting_reminders SET {key} = {placeholder} WHERE chat_id = {placeholder}", (final_value, chat_id))
        conn.commit()
        logger.info(f"Updated fasting reminder {key} = {value} for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error updating fasting reminder setting: {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            conn.close()

# ────────────────────────────────────────────────
#               Admin Management Functions
# ────────────────────────────────────────────────

def save_admin_info(user_id: int, chat_id: int, username: str = None, first_name: str = None, last_name: str = None, is_primary_admin: bool = False):
    """
    Save or update admin/supervisor information in the database.
    
    Args:
        user_id (int): Telegram user ID
        chat_id (int): Chat ID where user is admin
        username (str): User's username (optional)
        first_name (str): User's first name (optional)
        last_name (str): User's last name (optional)
        is_primary_admin (bool): Whether this is the primary admin (first to press /start)
    """
    conn, c, is_postgres = get_db_connection()
    
    try:
        placeholder = "%s" if is_postgres else "?"
        
        # Check if this is the first admin for this chat
        if is_primary_admin:
            # Check if there's already a primary admin
            c.execute(f'''
                SELECT user_id FROM admins 
                WHERE chat_id = {placeholder} AND is_primary_admin = 1
            ''', (chat_id,))
            existing_primary = c.fetchone()
            
            # If there's already a primary admin and it's not this user, don't set as primary
            if existing_primary and existing_primary[0] != user_id:
                is_primary_admin = False
        
        # Try to insert, on conflict update
        if is_postgres:
            c.execute(f'''
                INSERT INTO admins (user_id, chat_id, username, first_name, last_name, is_primary_admin, added_at)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, EXTRACT(EPOCH FROM NOW()))
                ON CONFLICT (user_id, chat_id)
                DO UPDATE SET username = EXCLUDED.username, 
                             first_name = EXCLUDED.first_name, 
                             last_name = EXCLUDED.last_name,
                             is_primary_admin = CASE 
                                 WHEN admins.is_primary_admin = 1 THEN 1 
                                 ELSE EXCLUDED.is_primary_admin 
                             END
            ''', (user_id, chat_id, username, first_name, last_name, int(is_primary_admin)))
        else:
            # SQLite - check if entry exists first
            c.execute(f'''
                SELECT is_primary_admin FROM admins 
                WHERE user_id = {placeholder} AND chat_id = {placeholder}
            ''', (user_id, chat_id))
            existing = c.fetchone()
            
            if existing and existing[0] == 1:
                # Keep existing primary admin status
                is_primary_admin = True
            
            # SQLite - use INSERT OR REPLACE
            c.execute(f'''
                INSERT OR REPLACE INTO admins (user_id, chat_id, username, first_name, last_name, is_primary_admin, added_at)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, strftime('%s', 'now'))
            ''', (user_id, chat_id, username, first_name, last_name, int(is_primary_admin)))
        
        conn.commit()
        logger.info(f"Saved admin info for user {user_id} in chat {chat_id} (primary: {is_primary_admin})")
    except Exception as e:
        logger.error(f"Error saving admin info: {e}", exc_info=True)
    finally:
        conn.close()

def get_admin_info(user_id: int, chat_id: int) -> dict:
    """
    Get admin information for a specific user in a chat.
    
    Args:
        user_id (int): Telegram user ID
        chat_id (int): Chat ID
        
    Returns:
        dict: Admin information or None if not found
    """
    conn, c, is_postgres = get_db_connection()
    
    try:
        placeholder = "%s" if is_postgres else "?"
        c.execute(f'''
            SELECT user_id, chat_id, username, first_name, last_name, added_at
            FROM admins
            WHERE user_id = {placeholder} AND chat_id = {placeholder}
        ''', (user_id, chat_id))
        
        row = c.fetchone()
        
        if row:
            return {
                "user_id": row[0],
                "chat_id": row[1],
                "username": row[2],
                "first_name": row[3],
                "last_name": row[4],
                "added_at": row[5]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting admin info: {e}", exc_info=True)
        return None
    finally:
        conn.close()

def get_all_admins_for_chat(chat_id: int) -> list:
    """
    Get all admins for a specific chat.
    
    Args:
        chat_id (int): Chat ID
        
    Returns:
        list: List of admin dictionaries
    """
    conn, c, is_postgres = get_db_connection()
    
    try:
        placeholder = "%s" if is_postgres else "?"
        c.execute(f'''
            SELECT user_id, chat_id, username, first_name, last_name, is_primary_admin, added_at
            FROM admins
            WHERE chat_id = {placeholder}
        ''', (chat_id,))
        
        rows = c.fetchall()
        
        admins = []
        for row in rows:
            admins.append({
                "user_id": row[0],
                "chat_id": row[1],
                "username": row[2],
                "first_name": row[3],
                "last_name": row[4],
                "is_primary_admin": bool(row[5]),
                "added_at": row[6]
            })
        return admins
    except Exception as e:
        logger.error(f"Error getting admins for chat: {e}", exc_info=True)
        return []
    finally:
        conn.close()

def is_user_admin_of_chat(user_id: int, chat_id: int) -> bool:
    """
    Check if a user is an admin of a specific chat.
    
    This function first checks the database for efficiency, then falls back
    to Telegram API if not found in database.
    
    Args:
        user_id (int): The Telegram user ID to check
        chat_id (int): The chat ID to check against
        
    Returns:
        bool: True if user is admin of this chat, False otherwise
    """
    # First check database
    admin_info = get_admin_info(user_id, chat_id)
    if admin_info is not None:
        return True
    
    # If not in database, check via Telegram API
    try:
        member = bot.get_chat_member(chat_id, user_id)
        is_admin = member.status in ["administrator", "creator"]
        
        if is_admin:
            # Save to database for future efficiency
            try:
                save_admin_info(
                    user_id=user_id,
                    chat_id=chat_id,
                    username=member.user.username,
                    first_name=member.user.first_name,
                    last_name=member.user.last_name
                )
            except Exception as e:
                logger.warning(f"Could not save admin info: {e}")
        
        return is_admin
    except Exception as e:
        logger.warning(f"Could not check admin status via API: {e}")
        return False

def sync_group_admins(chat_id: int) -> int:
    """
    Fetch and save all current administrators from a group.
    
    This function queries Telegram for all administrators in a group
    and saves their information to the database. It's called:
    - When bot is added to a group as admin
    - When /start is used in a group
    - Periodically to keep admin list up-to-date
    
    Args:
        chat_id (int): The group chat ID
        
    Returns:
        int: Number of admins synced, or -1 on error
    """
    try:
        # Get all administrators from Telegram
        admins = bot.get_chat_administrators(chat_id)
        
        if not admins:
            logger.warning(f"No admins found for chat {chat_id}")
            return 0
        
        # Check if this is the first sync (no existing admins in database)
        existing_admins = get_all_admins_for_chat(chat_id)
        is_first_sync = len(existing_admins) == 0
        
        synced_count = 0
        for admin in admins:
            # Skip bot accounts (don't save bots as admins)
            if admin.user.is_bot:
                continue
            
            # Mark as primary if this is the group creator
            # or if this is the first admin in the first sync and no creator was found
            is_primary = False
            if is_first_sync:
                if admin.status == "creator":
                    # Group creator is always the primary admin
                    is_primary = True
                elif synced_count == 0:
                    # Fallback: if no creator found yet, mark first admin as primary
                    is_primary = True
            
            # Save admin info
            save_admin_info(
                user_id=admin.user.id,
                chat_id=chat_id,
                username=admin.user.username,
                first_name=admin.user.first_name,
                last_name=admin.user.last_name,
                is_primary_admin=is_primary
            )
            synced_count += 1
        
        logger.info(f"Synced {synced_count} admins for chat {chat_id}")
        return synced_count
        
    except Exception as e:
        logger.error(f"Error syncing admins for chat {chat_id}: {e}", exc_info=True)
        return -1

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
#               Media Database Functions
# ────────────────────────────────────────────────

def load_media_database():
    """
    Load media database from JSON file.
    
    Returns:
        dict: Media database with images, videos, and documents
        Returns empty structure on error
    """
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'media_database.json')
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info("Media database loaded successfully")
        return data
    except Exception as e:
        logger.error(f"Error loading media database: {e}")
        return {"media": {"images": [], "videos": [], "documents": []}, "settings": {}}

def get_random_media(media_type: str = "all"):
    """
    Get a random media item from the database.
    
    Args:
        media_type (str): Type of media to get - 'images', 'videos', 'documents', or 'all'
        
    Returns:
        dict: Random media item with type and file_id, or None if no media available
    """
    try:
        db = load_media_database()
        media_items = []
        
        if media_type == "all":
            for category in ["images", "videos", "documents"]:
                media_items.extend([
                    {**item, "category_type": category}
                    for item in db["media"].get(category, [])
                    if item.get("enabled", True) and item.get("file_id") and item.get("file_id").strip()
                ])
        else:
            media_items = [
                {**item, "category_type": media_type}
                for item in db["media"].get(media_type, [])
                if item.get("enabled", True) and item.get("file_id") and item.get("file_id").strip()
            ]
        
        if not media_items:
            logger.debug(f"No enabled media found for type: {media_type}")
            return None
        
        selected = random.choice(media_items)
        logger.debug(f"Selected random media: {selected.get('id', 'unknown')}")
        return selected
        
    except Exception as e:
        logger.error(f"Error getting random media: {e}")
        return None

def send_media_with_caption(chat_id: int, caption: str, media_type: str = "all"):
    """
    Send a media message with azkar caption.
    
    Args:
        chat_id (int): The chat ID to send to
        caption (str): The caption text (azkar content)
        media_type (str): Type of media to send
        
    Returns:
        bool: True if sent successfully, False otherwise
    """
    try:
        media = get_random_media(media_type)
        
        if not media:
            logger.info(f"No media available for type {media_type}, sending text only")
            bot.send_message(chat_id, caption, parse_mode="Markdown")
            return True
        
        file_id = media.get("file_id")
        category = media.get("category_type", "images")
        
        if category == "images":
            bot.send_photo(chat_id, file_id, caption=caption, parse_mode="Markdown")
        elif category == "videos":
            bot.send_video(chat_id, file_id, caption=caption, parse_mode="Markdown")
        elif category == "documents":
            bot.send_document(chat_id, file_id, caption=caption, parse_mode="Markdown")
        else:
            # Fallback to text message
            bot.send_message(chat_id, caption, parse_mode="Markdown")
        
        logger.info(f"Sent media ({category}) with caption to {chat_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending media with caption: {e}")
        # Fallback to text message on error
        try:
            bot.send_message(chat_id, caption, parse_mode="Markdown")
            return True
        except Exception as e2:
            logger.error(f"Error sending fallback text message: {e2}")
            return False

def update_media_database(media_item: dict):
    """
    Add or update a media item in the database.
    
    Args:
        media_item (dict): Media item with type, file_id, description, etc.
        
    Returns:
        bool: True if updated successfully, False otherwise
    """
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'media_database.json')
        
        # Load existing database
        with open(filepath, 'r', encoding='utf-8') as f:
            db = json.load(f)
        
        # Determine category
        category = media_item.get("type", "images")
        if category not in ["images", "videos", "documents"]:
            category = "images"
        
        # Add to appropriate category
        if category not in db["media"]:
            db["media"][category] = []
        
        db["media"][category].append(media_item)
        
        # Save updated database
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Added media item to database: {media_item.get('id', 'unknown')}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating media database: {e}")
        return False

# ────────────────────────────────────────────────
#               Diverse Azkar & Specialized Media Functions
# ────────────────────────────────────────────────

def load_diverse_azkar():
    """
    Load diverse azkar from JSON file.
    
    Returns:
        list: List of azkar items with type, text, reference, and category
    """
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'azkar', 'diverse_azkar.json')
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('azkar', [])
    except Exception as e:
        logger.error(f"Error loading diverse_azkar.json: {e}")
        return []

def get_random_diverse_azkar():
    """
    Get a random diverse azkar item.
    
    Returns:
        str: Formatted azkar message or None if error
    """
    try:
        azkar_list = load_diverse_azkar()
        if not azkar_list:
            return None
        
        item = random.choice(azkar_list)
        
        # Format based on type
        type_icons = {
            'dua': '🤲',
            'ayah': '📖',
            'hadith': '✨'
        }
        
        icon = type_icons.get(item.get('type', 'dua'), '✨')
        text = item.get('text', '')
        reference = item.get('reference', '')
        
        msg = f"{icon} *الأدعية والأذكار المتنوعة*\n\n{text}"
        if reference:
            msg += f"\n\n{reference}"
        
        return msg
    except Exception as e:
        logger.error(f"Error getting random diverse azkar: {e}")
        return None

def load_audio_database():
    """Load audio database from JSON file."""
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'audio.json')
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info("Audio database loaded successfully")
        return data
    except Exception as e:
        logger.error(f"Error loading audio database: {e}")
        return {"audio": []}

def load_images_database():
    """Load images database from JSON file."""
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'images.json')
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info("Images database loaded successfully")
        return data
    except Exception as e:
        logger.error(f"Error loading images database: {e}")
        return {"images": []}

def get_random_media_by_category(category: str, media_type: str = "all"):
    """
    Get random media item filtered by category (e.g., 'حج', 'رمضان', 'عيد').
    
    Args:
        category (str): Category to filter by
        media_type (str): Type of media - 'images', 'audio', 'all'
        
    Returns:
        dict: Random media item or None
    """
    try:
        media_items = []
        
        if media_type in ["images", "all"]:
            img_db = load_images_database()
            for item in img_db.get("images", []):
                if item.get("enabled", True) and item.get("category") == category:
                    if item.get("file_id") and item.get("file_id").strip():
                        media_items.append({**item, "media_type": "photo"})
        
        if media_type in ["audio", "all"]:
            audio_db = load_audio_database()
            for item in audio_db.get("audio", []):
                if item.get("enabled", True) and item.get("category") == category:
                    if item.get("file_id") and item.get("file_id").strip():
                        media_items.append({**item, "media_type": "audio"})
        
        if not media_items:
            logger.debug(f"No media found for category: {category}")
            return None
        
        return random.choice(media_items)
        
    except Exception as e:
        logger.error(f"Error getting media by category: {e}")
        return None

def send_diverse_azkar(chat_id: int):
    """
    Send a random diverse azkar to a chat with media format preferences.
    Includes comprehensive error handling and logging.
    
    Args:
        chat_id (int): Chat ID to send to
    """
    # Get current time for logging
    current_time = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
    
    try:
        # Log the attempt as required
        category_name = AZKAR_CATEGORY_NAMES["diverse"]
        logger.info(f"[{current_time}] Attempted to send adhkar for category [{category_name}] to chat_id=[{chat_id}]")
        
        # Get diverse azkar settings
        settings = get_diverse_azkar_settings(chat_id)
        
        if not settings["enabled"]:
            logger.info(f"[{current_time}] Skipped diverse azkar for chat {chat_id}: Feature disabled")
            return
        
        # Verify chat is still enabled globally
        chat_settings = get_chat_settings(chat_id)
        if not chat_settings["is_enabled"]:
            logger.info(f"[{current_time}] Skipped diverse azkar for chat {chat_id}: Chat disabled globally")
            return
        
        logger.info(f"[{current_time}] Diverse azkar enabled for chat {chat_id} (interval: {settings['interval_minutes']}min)")
        
        # Get random azkar message
        msg = get_random_diverse_azkar()
        if not msg:
            logger.warning(f"[{current_time}] ✗ No diverse azkar available for chat {chat_id}")
            return
        
        # Check media format preferences
        enable_audio = settings.get("enable_audio", True)
        enable_images = settings.get("enable_images", True)
        enable_pdf = settings.get("enable_pdf", True)
        enable_text = settings.get("enable_text", True)
        
        logger.info(f"[{current_time}] Media preferences for chat {chat_id}: audio={enable_audio}, images={enable_images}, pdf={enable_pdf}, text={enable_text}")
        
        # Build list of allowed media types
        allowed_media_types = []
        if enable_audio:
            allowed_media_types.append("audio")
        if enable_images:
            allowed_media_types.append("images")
        if enable_pdf:
            allowed_media_types.append("documents")  # PDF files are documents
        
        # Try to send with media if any media type is enabled
        sent = False
        error_occurred = False
        
        if allowed_media_types:
            # Try to send with random allowed media type
            media_type = random.choice(allowed_media_types)
            logger.info(f"[{current_time}] Attempting to send diverse azkar with media type: {media_type}")
            
            try:
                sent = send_media_with_caption(chat_id, msg, media_type)
            except telebot.apihelper.ApiTelegramException as e:
                error_description = str(e)
                error_occurred = True
                
                # Handle specific error types with detailed logging
                if "blocked" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Bot blocked by user")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    return
                    
                elif "kicked" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Bot kicked from chat")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    return
                    
                elif "flood" in error_description.lower() or "retry after" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=FloodWait - {error_description}")
                    # Don't disable, just skip this send
                    return
                    
                elif "chat not found" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Chat not found")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    return
                    
                elif "forbidden" in error_description.lower() or "not enough rights" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Permission denied (bot not admin or insufficient rights)")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    return
                    
                elif "deactivated" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=User/chat deactivated")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    return
                    
                else:
                    logger.error(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON={error_description}")
        
        # Fallback to text if media failed or text is preferred
        if not sent and enable_text and not error_occurred:
            logger.info(f"[{current_time}] Sending diverse azkar as text to chat {chat_id}")
            
            try:
                bot.send_message(chat_id, msg, parse_mode="Markdown")
                sent = True
                logger.info(f"[{current_time}] ✓ Sent diverse azkar (text) to chat {chat_id}")
                
            except telebot.apihelper.ApiTelegramException as e:
                error_description = str(e)
                
                if "blocked" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Bot blocked by user")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    
                elif "kicked" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Bot kicked from chat")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    
                elif "flood" in error_description.lower() or "retry after" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=FloodWait - {error_description}")
                    
                elif "chat not found" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Chat not found")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    
                elif "forbidden" in error_description.lower() or "not enough rights" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Permission denied (bot not admin or insufficient rights)")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    
                elif "deactivated" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=User/chat deactivated")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    
                else:
                    logger.error(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON={error_description}")
        
        if sent:
            # Update last sent timestamp
            update_diverse_azkar_setting(chat_id, "last_sent_timestamp", int(time.time()))
            logger.info(f"[{current_time}] ✓ Successfully sent [{category_name}] to chat_id=[{chat_id}]")
        else:
            if not enable_text and not allowed_media_types:
                logger.warning(f"[{current_time}] ✗ Cannot send [{category_name}] to chat_id=[{chat_id}]: REASON=All media types disabled in settings")
            elif error_occurred:
                logger.warning(f"[{current_time}] ✗ Failed to send [{category_name}] to chat_id=[{chat_id}]: REASON=Error occurred during send attempt")
        
    except Exception as e:
        logger.error(f"[{current_time}] ✗ Critical error sending [{category_name}] to chat_id=[{chat_id}]: {e}", exc_info=True)

# ────────────────────────────────────────────────
#               Ramadan, Hajj, Eid Azkar Functions
# ────────────────────────────────────────────────

def load_ramadan_azkar():
    """Load Ramadan azkar from JSON file."""
    return load_azkar_from_json('ramadan.json') or []

def load_laylat_alqadr_azkar():
    """Load Laylat al-Qadr azkar from JSON file."""
    return load_azkar_from_json('laylat_alqadr.json') or []

def load_last_ten_days_azkar():
    """Load Last Ten Days azkar from JSON file."""
    return load_azkar_from_json('last_ten_days.json') or []

def load_arafah_azkar():
    """Load Arafah day azkar from JSON file."""
    return load_azkar_from_json('arafah.json') or []

def load_hajj_azkar():
    """Load Hajj azkar from JSON file."""
    return load_azkar_from_json('hajj.json') or []

def load_eid_azkar():
    """Load Eid azkar from JSON file."""
    return load_azkar_from_json('eid.json') or []

def send_special_azkar(chat_id: int, azkar_type: str):
    """
    Send special azkar (Ramadan, Hajj, Eid) to a chat with comprehensive error handling.
    
    Args:
        chat_id (int): Chat ID to send to
        azkar_type (str): Type of special azkar to send
    """
    # Get current time for logging
    current_time = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
    
    try:
        logger.info(f"[{current_time}] Attempting to send {azkar_type} special azkar to chat {chat_id}")
        
        messages = []
        media_type = "images"  # Default
        settings = get_chat_settings(chat_id)
        
        if not settings["is_enabled"]:
            logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Chat disabled")
            return
        
        # Load appropriate azkar based on type and verify setting is enabled
        if azkar_type == "ramadan":
            ramadan_settings = get_ramadan_settings(chat_id)
            if not ramadan_settings["ramadan_enabled"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Ramadan azkar disabled")
                return
            messages = load_ramadan_azkar()
            media_type = ramadan_settings.get("media_type", "images")
        
        elif azkar_type == "laylat_alqadr":
            ramadan_settings = get_ramadan_settings(chat_id)
            if not ramadan_settings["laylat_alqadr_enabled"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Laylat al-Qadr disabled")
                return
            messages = load_laylat_alqadr_azkar()
            media_type = ramadan_settings.get("media_type", "images")
        
        elif azkar_type == "last_ten_days":
            ramadan_settings = get_ramadan_settings(chat_id)
            if not ramadan_settings["last_ten_days_enabled"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Last ten days disabled")
                return
            messages = load_last_ten_days_azkar()
            media_type = ramadan_settings.get("media_type", "images")
        
        elif azkar_type == "arafah":
            hajj_eid_settings = get_hajj_eid_settings(chat_id)
            if not hajj_eid_settings["arafah_day_enabled"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Arafah day disabled")
                return
            messages = load_arafah_azkar()
            media_type = hajj_eid_settings.get("media_type", "images")
        
        elif azkar_type == "hajj":
            hajj_eid_settings = get_hajj_eid_settings(chat_id)
            if not hajj_eid_settings["hajj_enabled"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Hajj azkar disabled")
                return
            messages = load_hajj_azkar()
            media_type = hajj_eid_settings.get("media_type", "images")
        
        elif azkar_type == "eid":
            hajj_eid_settings = get_hajj_eid_settings(chat_id)
            if not hajj_eid_settings["eid_day_enabled"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Eid day disabled")
                return
            messages = load_eid_azkar()
            media_type = hajj_eid_settings.get("media_type", "images")
        
        elif azkar_type == "eid_adha":
            hajj_eid_settings = get_hajj_eid_settings(chat_id)
            if not hajj_eid_settings["eid_adha_enabled"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Eid al-Adha disabled")
                return
            messages = load_eid_azkar()  # Can use same eid azkar or create separate
            media_type = hajj_eid_settings.get("media_type", "images")
        
        else:
            logger.warning(f"[{current_time}] ✗ Unknown special azkar type: {azkar_type}")
            return
        
        if not messages:
            logger.warning(f"[{current_time}] ✗ No messages loaded for {azkar_type}")
            return
        
        logger.info(f"[{current_time}] Sending {len(messages)} {azkar_type} messages to chat {chat_id}")
        
        # Send messages
        for idx, msg in enumerate(messages):
            try:
                # Send first message with media if enabled
                if idx == 0 and settings.get("media_enabled", False):
                    # Try to get category-specific media
                    category_map = {
                        "ramadan": "رمضان",
                        "laylat_alqadr": "ليلة القدر",
                        "arafah": "عرفة",
                        "hajj": "حج",
                        "eid": "عيد",
                        "eid_adha": "عيد"
                    }
                    category = category_map.get(azkar_type, "إسلامي")
                    
                    # Try category-specific media first, fallback to general media
                    media_item = get_random_media_by_category(category, media_type)
                    if media_item:
                        file_id = media_item.get("file_id")
                        media_kind = media_item.get("media_type", "photo")
                        
                        if media_kind == "photo":
                            bot.send_photo(chat_id, file_id, caption=msg, parse_mode="Markdown")
                        elif media_kind == "audio":
                            bot.send_audio(chat_id, file_id, caption=msg, parse_mode="Markdown")
                        else:
                            bot.send_message(chat_id, msg, parse_mode="Markdown")
                    else:
                        # Fallback to generic media with caption
                        send_media_with_caption(chat_id, msg, media_type)
                else:
                    bot.send_message(chat_id, msg, parse_mode="Markdown")
                    
                logger.info(f"[{current_time}] ✓ Sent {azkar_type} message {idx+1}/{len(messages)} to chat {chat_id}")
                
                # Small delay between messages
                if idx < len(messages) - 1:
                    time.sleep(0.05)
                
            except telebot.apihelper.ApiTelegramException as e:
                error_description = str(e)
                
                # Handle specific error types
                if "blocked" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed {azkar_type} to chat {chat_id}: Bot blocked by user")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    break
                    
                elif "kicked" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed {azkar_type} to chat {chat_id}: Bot kicked from chat")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    break
                    
                elif "flood" in error_description.lower() or "retry after" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed {azkar_type} to chat {chat_id}: FloodWait - {error_description}")
                    time.sleep(1)  # Wait before continuing
                    
                elif "chat not found" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed {azkar_type} to chat {chat_id}: Chat not found")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    break
                    
                elif "forbidden" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed {azkar_type} to chat {chat_id}: Forbidden/No permission")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    break
                    
                else:
                    logger.error(f"[{current_time}] ✗ Failed {azkar_type} message {idx+1}/{len(messages)} to chat {chat_id}: {error_description}")
        
        logger.info(f"[{current_time}] Completed sending {azkar_type} to chat {chat_id}")
        
    except Exception as e:
        logger.error(f"[{current_time}] ✗ Critical error sending {azkar_type} azkar to chat {chat_id}: {e}", exc_info=True)

def send_fasting_reminder(chat_id: int, reminder_type: str):
    """
    Send fasting reminder to a chat.
    
    Args:
        chat_id (int): Chat ID to send to
        reminder_type (str): Type of reminder - 'monday_thursday' or 'arafah'
    """
    try:
        settings = get_chat_settings(chat_id)
        
        if not settings["is_enabled"]:
            return
        
        fasting_settings = get_fasting_reminders_settings(chat_id)
        
        if reminder_type == "monday_thursday" and not fasting_settings["monday_thursday_enabled"]:
            return
        
        if reminder_type == "arafah" and not fasting_settings["arafah_reminder_enabled"]:
            return
        
        # Prepare reminder message
        if reminder_type == "monday_thursday":
            # Determine which day - reminder is sent day before fasting
            # Scheduled on: Sunday (6) evening -> Fasting: Monday (0)
            # Scheduled on: Wednesday (2) evening -> Fasting: Thursday (3)
            today = datetime.now(TIMEZONE)
            # If today is Sunday (6), tomorrow is Monday
            # If today is Wednesday (2), tomorrow is Thursday
            if today.weekday() == 6:
                day_name = "الإثنين"
            elif today.weekday() == 2:
                day_name = "الخميس"
            else:
                # Fallback - shouldn't happen with correct scheduling
                day_name = "الإثنين أو الخميس"
            
            message = (
                f"🌙 *تذكير بصيام {day_name}*\n\n"
                f"غداً هو يوم {day_name} المبارك\n\n"
                "عن أبي قتادة رضي الله عنه أن رسول الله ﷺ سُئِل عن صوم يوم الاثنين، فقال:\n"
                '"ذاك يوم وُلِدتُ فيه، ويوم بُعِثتُ فيه، أو أُنزِل عليَّ فيه"\n'
                "رواه مسلم\n\n"
                "📿 *فضل صيام الاثنين والخميس:*\n"
                "• تُعرض الأعمال على الله يومي الاثنين والخميس\n"
                "• كان النبي ﷺ يحرص على صيامهما\n"
                "• صيامهما سنة مستحبة\n\n"
                "اللهم تقبل منا الصيام والقيام وصالح الأعمال 🤲"
            )
        else:  # arafah
            message = (
                "🕋 *تذكير بصيام يوم عرفة*\n\n"
                "غداً هو يوم عرفة المبارك - التاسع من ذي الحجة\n\n"
                "قال رسول الله ﷺ:\n"
                '"صيام يوم عرفة، أحتسب على الله أن يكفر السنة التي قبله، والسنة التي بعده"\n'
                "رواه مسلم\n\n"
                "📿 *فضل صيام يوم عرفة:*\n"
                "• يكفر ذنوب سنتين (السنة الماضية والقادمة)\n"
                "• من أفضل الأيام عند الله\n"
                "• خير الدعاء دعاء يوم عرفة\n\n"
                "🤲 *أفضل دعاء يوم عرفة:*\n"
                "لا إله إلا الله وحده لا شريك له، له الملك وله الحمد، وهو على كل شيء قدير\n\n"
                "اللهم تقبل منا الصيام والدعاء 🌙"
            )
        
        bot.send_message(chat_id, message, parse_mode="Markdown")
        logger.info(f"Sent {reminder_type} fasting reminder to {chat_id}")
        
    except telebot.apihelper.ApiTelegramException as e:
        if "blocked" in str(e).lower() or "kicked" in str(e).lower():
            logger.warning(f"Bot blocked/kicked from {chat_id}")
            update_chat_setting(chat_id, "is_enabled", 0)
        else:
            logger.error(f"Failed sending {reminder_type} reminder to {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Error sending {reminder_type} reminder to chat {chat_id}: {e}", exc_info=True)

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
    """
    Send scheduled azkar to a chat with comprehensive error handling and logging.
    
    Args:
        chat_id (int): Target chat ID
        azkar_type (str): Type of azkar (morning, evening, friday_kahf, friday_dua, sleep)
    """
    # Get current time for logging
    current_time = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
    
    try:
        # Get friendly category name for logging
        category_name = AZKAR_CATEGORY_NAMES.get(azkar_type, azkar_type)
        
        # Log the attempt as required
        logger.info(f"[{current_time}] Attempted to send adhkar for category [{category_name}] to chat_id=[{chat_id}]")
        
        settings = get_chat_settings(chat_id)
        if not settings["is_enabled"]:
            logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Chat disabled")
            return

        messages = []
        send_with_media = False

        # Select messages based on azkar type and verify setting is enabled
        if azkar_type == "morning":
            if not settings["morning_azkar"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Morning azkar disabled")
                return
            messages = MORNING_AZKAR
            send_with_media = settings.get("send_media_with_morning", False)
            
        elif azkar_type == "evening":
            if not settings["evening_azkar"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Evening azkar disabled")
                return
            messages = EVENING_AZKAR
            send_with_media = settings.get("send_media_with_evening", False)
            
        elif azkar_type == "friday_kahf":
            if not settings["friday_sura"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Friday sura disabled")
                return
            messages = [KAHF_REMINDER]
            send_with_media = settings.get("send_media_with_friday", False)
            
        elif azkar_type == "friday_dua":
            if not settings["friday_dua"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Friday dua disabled")
                return
            messages = FRIDAY_DUA
            send_with_media = settings.get("send_media_with_friday", False)
            
        elif azkar_type == "sleep":
            if not settings["sleep_message"]:
                logger.info(f"[{current_time}] Skipped {azkar_type} for chat {chat_id}: Sleep message disabled")
                return
            messages = [SLEEP_MESSAGE]

        if not messages:
            logger.warning(f"[{current_time}] No messages available for {azkar_type}, chat {chat_id}")
            return

        # Check if media is enabled globally
        media_enabled = settings.get("media_enabled", False) and send_with_media
        media_type = settings.get("media_type", "images")

        logger.info(f"[{current_time}] Sending {len(messages)} {azkar_type} messages to chat {chat_id} (media: {media_enabled})")

        for idx, msg in enumerate(messages):
            try:
                # Send first message with media if enabled
                if media_enabled and idx == 0:
                    send_media_with_caption(chat_id, msg, media_type)
                else:
                    bot.send_message(chat_id, msg, parse_mode="Markdown")
                logger.info(f"[{current_time}] ✓ Sent {azkar_type} message {idx+1}/{len(messages)} to chat {chat_id}")
                
                # Small delay between messages to avoid flood limits
                if idx < len(messages) - 1:
                    time.sleep(0.05)
                    
            except telebot.apihelper.ApiTelegramException as e:
                error_description = str(e)
                
                # Handle specific error types with detailed logging
                if "blocked" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Bot blocked by user")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    break  # Stop sending remaining messages
                    
                elif "kicked" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Bot kicked from chat")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    break  # Stop sending remaining messages
                    
                elif "flood" in error_description.lower() or "retry after" in error_description.lower():
                    # Extract retry time if available
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=FloodWait - {error_description}")
                    # Continue with remaining messages after a longer delay
                    time.sleep(1)
                    
                elif "chat not found" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Chat not found")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    break
                    
                elif "forbidden" in error_description.lower() or "not enough rights" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=Permission denied (bot not admin or insufficient rights)")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    break
                    
                elif "deactivated" in error_description.lower():
                    logger.warning(f"[{current_time}] ✗ Failed [{category_name}] to chat_id=[{chat_id}]: REASON=User/chat deactivated")
                    update_chat_setting(chat_id, "is_enabled", 0)
                    break
                    
                else:
                    logger.error(f"[{current_time}] ✗ Failed [{category_name}] message {idx+1}/{len(messages)} to chat_id=[{chat_id}]: REASON={error_description}")
                    # Continue with remaining messages for unknown errors
                    
            except Exception as e:
                logger.error(f"[{current_time}] ✗ Unexpected error sending [{category_name}] message {idx+1}/{len(messages)} to chat_id=[{chat_id}]: {e}", exc_info=True)

        logger.info(f"[{current_time}] ✓ Completed sending [{category_name}] to chat_id=[{chat_id}]")

    except Exception as e:
        category_name = AZKAR_CATEGORY_NAMES.get(azkar_type, azkar_type)
        logger.error(f"[{current_time}] ✗ Critical error in send_azkar ([{category_name}]) for chat_id=[{chat_id}]: {e}", exc_info=True)

# ────────────────────────────────────────────────
#               Scheduling
# ────────────────────────────────────────────────

def schedule_chat_jobs(chat_id: int):
    """
    Schedule all azkar jobs for a specific chat based on its settings.
    Includes comprehensive validation and logging for each scheduled job.
    
    Args:
        chat_id (int): The Telegram chat ID to schedule jobs for
    """
    current_time = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
    
    try:
        logger.info(f"[{current_time}] Scheduling jobs for chat {chat_id}")
        
        settings = get_chat_settings(chat_id)
        
        # Validate that chat is enabled
        if not settings["is_enabled"]:
            logger.info(f"[{current_time}] Chat {chat_id} is disabled, clearing all scheduled jobs")
            # Remove all jobs for this chat
            for job in scheduler.get_jobs():
                if str(chat_id) in job.id:
                    job.remove()
            return

        # Remove previous jobs to avoid duplicates
        jobs_removed = 0
        for job in scheduler.get_jobs():
            if str(chat_id) in job.id:
                job.remove()
                jobs_removed += 1
        
        if jobs_removed > 0:
            logger.info(f"[{current_time}] Removed {jobs_removed} existing jobs for chat {chat_id}")

        jobs_scheduled = 0
        
        # Morning Azkar - scheduled based on user-defined time
        if settings["morning_azkar"]:
            morning_time = settings["morning_time"]
            h, m, is_valid, error_msg = validate_time_format(morning_time)
            
            if is_valid:
                scheduler.add_job(
                    send_azkar,
                    CronTrigger(hour=h, minute=m, timezone=TIMEZONE),
                    args=[chat_id, "morning"],
                    id=f"morning_{chat_id}",
                    replace_existing=True
                )
                jobs_scheduled += 1
                logger.info(f"[{current_time}] ✓ Scheduled morning azkar for chat {chat_id} at {h:02d}:{m:02d} {TIMEZONE}")
            else:
                logger.error(f"[{current_time}] ✗ Invalid morning_time for chat {chat_id}: {error_msg}")

        # Evening Azkar - scheduled based on user-defined time
        if settings["evening_azkar"]:
            evening_time = settings["evening_time"]
            h, m, is_valid, error_msg = validate_time_format(evening_time)
            
            if is_valid:
                scheduler.add_job(
                    send_azkar,
                    CronTrigger(hour=h, minute=m, timezone=TIMEZONE),
                    args=[chat_id, "evening"],
                    id=f"evening_{chat_id}",
                    replace_existing=True
                )
                jobs_scheduled += 1
                logger.info(f"[{current_time}] ✓ Scheduled evening azkar for chat {chat_id} at {h:02d}:{m:02d} {TIMEZONE}")
            else:
                logger.error(f"[{current_time}] ✗ Invalid evening_time for chat {chat_id}: {error_msg}")

        # Friday Kahf reminder - fixed time (Friday 9:00 AM)
        if settings["friday_sura"]:
            scheduler.add_job(
                send_azkar,
                CronTrigger(day_of_week="fri", hour=9, minute=0, timezone=TIMEZONE),
                args=[chat_id, "friday_kahf"],
                id=f"kahf_{chat_id}",
                replace_existing=True
            )
            jobs_scheduled += 1
            logger.info(f"[{current_time}] ✓ Scheduled Friday Kahf for chat {chat_id} at Fri 09:00 {TIMEZONE}")

        # Friday Dua - fixed time (Friday 10:00 AM)
        if settings["friday_dua"]:
            scheduler.add_job(
                send_azkar,
                CronTrigger(day_of_week="fri", hour=10, minute=0, timezone=TIMEZONE),
                args=[chat_id, "friday_dua"],
                id=f"friday_dua_{chat_id}",
                replace_existing=True
            )
            jobs_scheduled += 1
            logger.info(f"[{current_time}] ✓ Scheduled Friday Dua for chat {chat_id} at Fri 10:00 {TIMEZONE}")

        # Sleep message - scheduled based on user-defined time
        if settings["sleep_message"]:
            try:
                sleep_time = settings["sleep_time"]
                # Validate time format
                if not sleep_time or ':' not in sleep_time:
                    logger.error(f"[{current_time}] ✗ Invalid sleep_time format for chat {chat_id}: '{sleep_time}'")
                else:
                    h, m = map(int, sleep_time.split(":"))
                    # Validate hour and minute ranges
                    if not (0 <= h <= 23 and 0 <= m <= 59):
                        logger.error(f"[{current_time}] ✗ Invalid sleep_time values for chat {chat_id}: {h}:{m}")
                    else:
                        scheduler.add_job(
                            send_azkar,
                            CronTrigger(hour=h, minute=m, timezone=TIMEZONE),
                            args=[chat_id, "sleep"],
                            id=f"sleep_{chat_id}",
                            replace_existing=True
                        )
                        jobs_scheduled += 1
                        logger.info(f"[{current_time}] ✓ Scheduled sleep message for chat {chat_id} at {h:02d}:{m:02d} {TIMEZONE}")
            except (ValueError, AttributeError) as e:
                logger.error(f"[{current_time}] ✗ Error scheduling sleep message for chat {chat_id}: {e}")
        
        # Diverse Azkar (interval-based) - uses interval_minutes from DB
        diverse_settings = get_diverse_azkar_settings(chat_id)
        logger.info(f"[{current_time}] Diverse azkar settings for chat {chat_id}: enabled={diverse_settings['enabled']}, interval_minutes={diverse_settings['interval_minutes']}")
        
        if diverse_settings["enabled"]:
            interval_min = diverse_settings.get("interval_minutes", 60)
            
            # Validate interval
            if interval_min <= 0:
                logger.error(f"[{current_time}] ✗ Invalid interval_minutes for chat {chat_id}: {interval_min} (must be > 0)")
            else:
                # Remove any existing diverse azkar job first
                for job in scheduler.get_jobs():
                    if job.id == f"diverse_azkar_{chat_id}":
                        job.remove()
                        logger.info(f"[{current_time}] Removed existing diverse azkar job for chat {chat_id}")
                
                # Add new job with interval-based trigger
                job = scheduler.add_job(
                    send_diverse_azkar,
                    'interval',
                    minutes=interval_min,
                    args=[chat_id],
                    id=f"diverse_azkar_{chat_id}",
                    replace_existing=True,
                    next_run_time=datetime.now(TIMEZONE)  # Run once immediately, then on interval
                )
                jobs_scheduled += 1
                logger.info(f"[{current_time}] ✓ Scheduled diverse azkar every {interval_min} minutes for chat {chat_id}, next run: {job.next_run_time}")
        else:
            logger.info(f"[{current_time}] Diverse azkar not scheduled for chat {chat_id}: disabled")
        
        # Fasting Reminders
        fasting_settings = get_fasting_reminders_settings(chat_id)
        
        # Monday/Thursday fasting reminders
        if fasting_settings["monday_thursday_enabled"]:
            try:
                reminder_time = fasting_settings["reminder_time"]
                # Validate time format
                if not reminder_time or ':' not in reminder_time:
                    logger.error(f"[{current_time}] ✗ Invalid reminder_time format for chat {chat_id}: '{reminder_time}'")
                else:
                    h, m = map(int, reminder_time.split(":"))
                    # Validate hour and minute ranges
                    if not (0 <= h <= 23 and 0 <= m <= 59):
                        logger.error(f"[{current_time}] ✗ Invalid reminder_time values for chat {chat_id}: {h}:{m}")
                    else:
                        # Schedule for Sunday (day before Monday) and Wednesday (day before Thursday)
                        scheduler.add_job(
                            send_fasting_reminder,
                            CronTrigger(day_of_week="sun", hour=h, minute=m, timezone=TIMEZONE),
                            args=[chat_id, "monday_thursday"],
                            id=f"monday_reminder_{chat_id}",
                            replace_existing=True
                        )
                        scheduler.add_job(
                            send_fasting_reminder,
                            CronTrigger(day_of_week="wed", hour=h, minute=m, timezone=TIMEZONE),
                            args=[chat_id, "monday_thursday"],
                            id=f"thursday_reminder_{chat_id}",
                            replace_existing=True
                        )
                        jobs_scheduled += 2
                        logger.info(f"[{current_time}] ✓ Scheduled Monday/Thursday fasting reminders for chat {chat_id} at {h:02d}:{m:02d} {TIMEZONE}")
            except (ValueError, AttributeError) as e:
                logger.error(f"[{current_time}] ✗ Error scheduling fasting reminders for chat {chat_id}: {e}")
        
        logger.info(f"[{current_time}] ✓ Successfully scheduled {jobs_scheduled} jobs for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"[{current_time}] ✗ Critical error scheduling jobs for chat {chat_id}: {e}", exc_info=True)

def schedule_all_chats():
    """
    Schedule jobs for all enabled chats in the database.
    This should be called on bot startup to initialize all scheduled jobs.
    """
    try:
        conn, c, is_postgres = get_db_connection()
        
        try:
            c.execute("SELECT chat_id FROM chat_settings WHERE is_enabled = 1")
            chat_ids = [row[0] for row in c.fetchall()]
            
            logger.info(f"Scheduling jobs for {len(chat_ids)} enabled chats...")
            
            for chat_id in chat_ids:
                try:
                    schedule_chat_jobs(chat_id)
                except Exception as e:
                    logger.error(f"Error scheduling jobs for chat {chat_id}: {e}")
            
            logger.info(f"✓ Completed scheduling jobs for {len(chat_ids)} chats")
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error in schedule_all_chats: {e}", exc_info=True)

# ────────────────────────────────────────────────
#               Bot Handlers
# ────────────────────────────────────────────────

@bot.my_chat_member_handler()
def my_chat_member_handler(update: types.ChatMemberUpdated):
    """
    Handle bot membership changes in chats.
    Automatically enables/disables the bot and schedules jobs based on admin status.
    Also syncs all group admins when bot is added as admin.
    """
    current_time = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
    
    try:
        chat_id = update.chat.id
        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status
        
        logger.info(f"[{current_time}] Bot status changed in chat {chat_id}: {old_status} → {new_status}")

        if new_status in ["administrator", "creator"]:
            # Bot promoted to admin - enable and schedule
            logger.info(f"[{current_time}] ✓ Bot promoted to admin in chat {chat_id}, enabling and scheduling jobs")
            
            # Enable the chat
            update_chat_setting(chat_id, "is_enabled", 1)
            
            # Schedule all jobs for this chat
            schedule_chat_jobs(chat_id)
            
            # Sync all group admins when bot is added as admin
            logger.info(f"[{current_time}] Syncing admins for chat {chat_id} after bot was added as admin")
            try:
                synced_count = sync_group_admins(chat_id)
                if synced_count > 0:
                    logger.info(f"[{current_time}] ✓ Successfully synced {synced_count} admins for chat {chat_id}")
            except Exception as e:
                logger.error(f"[{current_time}] ✗ Error syncing admins for chat {chat_id}: {e}")
            
            # Send activation message to the group
            try:
                bot.send_message(
                    chat_id,
                    "✅ *تم تفعيل البوت تلقائياً!*\n\n"
                    "سيبدأ بإرسال الأذكار في الأوقات المحددة\n"
                    "استخدم /start لتعديل الإعدادات",
                    parse_mode="Markdown"
                )
                logger.info(f"[{current_time}] ✓ Activation message sent to chat {chat_id}")
            except Exception as e:
                logger.error(f"[{current_time}] ✗ Failed to send activation message to chat {chat_id}: {e}")
                
        elif old_status in ["administrator", "creator"] and new_status in ["member", "left", "kicked"]:
            # Bot demoted or removed - disable and clear jobs
            logger.info(f"[{current_time}] ✗ Bot demoted/removed from chat {chat_id}, disabling and clearing jobs")
            
            # Disable the chat
            update_chat_setting(chat_id, "is_enabled", 0)
            
            # Remove all scheduled jobs for this chat
            jobs_removed = 0
            for job in scheduler.get_jobs():
                if str(chat_id) in job.id:
                    job.remove()
                    jobs_removed += 1
            
            logger.info(f"[{current_time}] ✓ Removed {jobs_removed} scheduled jobs for chat {chat_id}")
            
    except Exception as e:
        logger.error(f"[{current_time}] ✗ Critical error in my_chat_member_handler: {e}", exc_info=True)

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

# ────────────────────────────────────────────────
#               Helper Functions for Callbacks
# ────────────────────────────────────────────────

def extract_chat_id_from_callback(callback_data: str) -> tuple:
    """
    Extract chat_id from callback data if present.
    
    Args:
        callback_data (str): The callback data string
        
    Returns:
        tuple: (chat_id, has_chat_id) where chat_id is int or None, has_chat_id is bool
        
    Example:
        "morning_evening_settings_-123456" -> (-123456, True)
        "morning_evening_settings" -> (None, False)
    """
    parts = callback_data.split("_")
    
    # Check if last part looks like a chat_id (starts with - or is numeric)
    if len(parts) > 0:
        try:
            potential_chat_id = parts[-1]
            # Try to parse as integer
            chat_id = int(potential_chat_id)
            return (chat_id, True)
        except ValueError:
            # Last part is not a number, no chat_id embedded
            return (None, False)
    
    return (None, False)

def create_back_button_callback(chat_id: int = None) -> str:
    """
    Create appropriate callback data for back button based on context.
    
    Args:
        chat_id (int): The chat ID if in group-specific context, None otherwise
        
    Returns:
        str: Callback data string
    """
    if chat_id:
        import base64
        chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
        return f"select_group_{chat_id_encoded}"
    else:
        return "open_settings"

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

def add_support_buttons(markup: types.InlineKeyboardMarkup):
    """
    Add developer and official group support buttons to a markup.
    
    Args:
        markup: The InlineKeyboardMarkup to add buttons to
    """
    markup.add(
        types.InlineKeyboardButton("👨‍💻 الدعم الفني", url="https://t.me/dev3bod"),
        types.InlineKeyboardButton("👥 المجموعة الرسمية", url="https://t.me/NourAdhkar")
    )
    return markup

def extract_chat_id_from_callback(callback_data: str, min_underscore_count: int = 3) -> tuple:
    """
    Extract chat_id from callback data if present.
    
    Args:
        callback_data: The callback data string (e.g., "morning_time_presets_{chat_id}")
        min_underscore_count: Minimum number of underscores expected for chat_id format
    
    Returns:
        tuple: (chat_id, has_chat_id) where chat_id is int or None, has_chat_id is bool
    """
    if "_" in callback_data and callback_data.count("_") >= min_underscore_count:
        parts = callback_data.split("_")
        try:
            chat_id = int(parts[-1])
            return (chat_id, True)
        except (ValueError, IndexError):
            return (None, False)
    return (None, False)

def is_simple_toggle_callback(call_data: str) -> bool:
    """
    Check if callback data is a simple toggle command (without chat_id suffix).
    
    Args:
        call_data: The callback data string
    
    Returns:
        bool: True if it's a simple toggle (no chat_id), False otherwise
    """
    return call_data.startswith("toggle_") and not any(char.isdigit() for char in call_data.split("_")[-1])

@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    """
    Handle /start command - replaces /settings functionality.
    Shows advanced control panel based on chat type and admin status.
    
    Scenarios:
    1. Private Chat - User is admin: Show welcome + advanced settings panel
    2. Private Chat - User is not admin: Show welcome + guidance to add bot as admin
    3. Private Chat - With group context (deep link): Open settings for specific group
    4. Group Chat - User is admin: Show settings panel in group
    5. Group Chat - User is not admin: Request to make bot admin with buttons
    """
    try:
        logger.info(f"Start command received from {message.from_user.id} in chat {message.chat.id}")
        
        # Cache bot info to avoid redundant API calls
        bot_info = bot.get_me()
        bot_username = bot_info.username or "NourAdhkarBot"
        
        # ──────────────────────────────────────────────────────────────
        # Scenario 1, 2 & 3: Private Chat
        # ──────────────────────────────────────────────────────────────
        if message.chat.type == "private":
            # Check if this is a deep link with group context
            # Format: /start group_<base64_encoded_chat_id>
            if message.text and len(message.text.split()) > 1:
                start_param = message.text.split()[1]
                
                if start_param.startswith("group_"):
                    # Extract and decode the chat_id with validation
                    try:
                        chat_id_encoded = start_param.replace("group_", "")
                        
                        # Decode and validate
                        decoded_str = base64.b64decode(chat_id_encoded).decode('utf-8')
                        chat_id = int(decoded_str)
                        
                        # Validate chat_id format
                        # Telegram group chat IDs are negative and typically start with -100
                        # Private chat IDs are positive
                        if chat_id >= 0:
                            logger.warning(f"Invalid group chat_id (must be negative): {chat_id}")
                            bot.send_message(
                                message.chat.id,
                                "⚠️ *خطأ في الوصول*\n\nمعرف المجموعة غير صحيح.",
                                parse_mode="Markdown"
                            )
                            return
                        
                        # Check if user is admin of this specific chat
                        if is_user_admin_of_chat(message.from_user.id, chat_id):
                            # Open settings for this specific group
                            logger.info(f"Opening settings for group {chat_id} for user {message.from_user.id}")
                            
                            # Store the chat_id in a way that callback handlers can access it
                            # We'll use callback_data to pass the chat_id
                            settings_text = (
                                "⚙️ *لوحة التحكم*\n\n"
                                f"إعدادات المجموعة (ID: {chat_id})\n\n"
                                "*اختر القسم الذي تريد تعديله:*"
                            )
                            
                            # Create keyboard with main sections - encode chat_id in callback data
                            markup = types.InlineKeyboardMarkup(row_width=2)
                            markup.add(
                                types.InlineKeyboardButton("🌅🌙 أذكار الصباح والمساء", callback_data=f"morning_evening_settings_{chat_id}"),
                                types.InlineKeyboardButton("📿 أدعية الجمعة", callback_data=f"friday_settings_{chat_id}"),
                                types.InlineKeyboardButton("🌙 إعدادات رمضان", callback_data=f"ramadan_settings_{chat_id}"),
                                types.InlineKeyboardButton("🕋 إعدادات الحج", callback_data=f"hajj_eid_settings_{chat_id}"),
                                types.InlineKeyboardButton("🌙 تذكيرات الصيام", callback_data=f"fasting_reminders_{chat_id}")
                            )
                            
                            bot.send_message(
                                message.chat.id,
                                settings_text,
                                reply_markup=markup,
                                parse_mode="Markdown"
                            )
                            return
                        else:
                            bot.send_message(
                                message.chat.id,
                                "⚠️ *خطأ في الوصول*\n\n"
                                "لست مشرفًا في هذه المجموعة.\n"
                                "يجب أن تكون مشرفًا في المجموعة للوصول إلى إعداداتها.",
                                parse_mode="Markdown"
                            )
                            return
                    except Exception as e:
                        logger.error(f"Error decoding group context: {e}")
                        # Fall through to normal /start handling
            
            # Normal private chat handling
            # Check if user is admin in any group
            is_admin = is_user_admin_in_any_group(message.from_user.id)
            
            if is_admin:
                # Get all groups where this user is an admin and show settings directly
                conn, c, is_postgres = get_db_connection()
                
                try:
                    placeholder = "%s" if is_postgres else "?"
                    c.execute(f'''
                        SELECT DISTINCT chat_id FROM admins 
                        WHERE user_id = {placeholder}
                    ''', (message.from_user.id,))
                    
                    user_groups = [row[0] for row in c.fetchall()]
                finally:
                    conn.close()
                
                if not user_groups:
                    # No groups found - show welcome with guidance
                    welcome_text = (
                        f"*مرحبًا بك في بوت نور الأذكار* ✨\n\n"
                        f"بوت نور الذكر يرسل أذكار الصباح والمساء، سورة الكهف يوم الجمعة، "
                        f"أدعية الجمعة، رسائل النوم تلقائيًا في المجموعات.\n\n"
                        f"⚠️ *للبدء:*\n"
                        f"يرجى استخدام /start في إحدى المجموعات أولاً"
                    )
                    
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    markup.add(
                        types.InlineKeyboardButton("➕ إضافة البوت إلى مجموعتك", url=f"https://t.me/{bot_username}?startgroup=true"),
                        types.InlineKeyboardButton("👥 المجموعة الرسمية", url="https://t.me/NourAdhkar"),
                        types.InlineKeyboardButton("👨‍💻 المطور", url="https://t.me/dev3bod")
                    )
                    
                    bot.send_message(
                        message.chat.id,
                        welcome_text,
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                else:
                    # Show control panel directly - group selection
                    settings_text = (
                        "⚙️ *لوحة التحكم المتقدمة*\n\n"
                        "*اختر المجموعة التي تريد إدارتها:*\n\n"
                    )
                    
                    # Create keyboard with group buttons
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    
                    for chat_id in user_groups:
                        try:
                            # Get chat title
                            chat_info = bot.get_chat(chat_id)
                            chat_title = chat_info.title or f"Group {chat_id}"
                            
                            # Encode chat_id for callback data
                            chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
                            
                            markup.add(
                                types.InlineKeyboardButton(
                                    f"📱 {chat_title}",
                                    callback_data=f"select_group_{chat_id_encoded}"
                                )
                            )
                        except Exception as e:
                            logger.warning(f"Could not get info for chat {chat_id}: {e}")
                            continue
                    
                    bot.send_message(
                        message.chat.id,
                        settings_text,
                        parse_mode="Markdown",
                        reply_markup=markup
                    )
                    logger.info(f"/start in private chat - showing control panel directly for admin {message.from_user.id} with {len(user_groups)} groups")
            else:
                # Non-admin user - show guidance
                welcome_text = (
                    f"*مرحبًا بك في بوت نور الأذكار* ✨\n\n"
                    f"بوت نور الذكر يرسل أذكار الصباح والمساء، سورة الكهف يوم الجمعة، "
                    f"أدعية الجمعة، رسائل النوم تلقائيًا في المجموعات.\n\n"
                    f"⚠️ *للوصول إلى لوحة التحكم:*\n"
                    f"يجب عليك أولاً إضافة البوت كمشرف في إحدى المجموعات"
                )
                
                # Action buttons
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(
                    types.InlineKeyboardButton("➕ إضافة البوت إلى مجموعتك", url=f"https://t.me/{bot_username}?startgroup=true"),
                    types.InlineKeyboardButton("👥 المجموعة الرسمية", url="https://t.me/NourAdhkar"),
                    types.InlineKeyboardButton("👨‍💻 المطور", url="https://t.me/dev3bod")
                )
                
                bot.send_message(
                    message.chat.id,
                    welcome_text,
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
                logger.info(f"/start in private chat from non-admin user {message.from_user.id}")
        
        # ──────────────────────────────────────────────────────────────
        # Scenario 3 & 4: Group or Supergroup Chat
        # ──────────────────────────────────────────────────────────────
        else:
            # Check if user is admin in the group
            try:
                user_status = bot.get_chat_member(message.chat.id, message.from_user.id).status
                user_is_admin = user_status in ["administrator", "creator"]
            except Exception as e:
                logger.warning(f"Could not check user admin status: {e}")
                user_is_admin = False
            
            if user_is_admin:
                # Sync all admins from the group to keep database up-to-date
                try:
                    logger.info(f"Syncing admins for chat {message.chat.id} from /start command")
                    sync_group_admins(message.chat.id)
                except Exception as e:
                    logger.error(f"Error syncing admins in /start: {e}")
                
                # Save the user who invoked /start as well (in case sync missed them)
                try:
                    user = message.from_user
                    # Check if there are any existing admins for this chat
                    existing_admins = get_all_admins_for_chat(message.chat.id)
                    is_primary = len(existing_admins) == 0  # First admin becomes primary
                    
                    save_admin_info(
                        user_id=user.id,
                        chat_id=message.chat.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        is_primary_admin=is_primary
                    )
                    logger.info(f"Saved admin {user.id} for chat {message.chat.id} (primary: {is_primary})")
                except Exception as e:
                    logger.error(f"Error saving admin info: {e}")
                
                # Send message in group prompting admin to open private chat with group context
                try:
                    bot_info = bot.get_me()
                    bot_username = bot_info.username or "NourAdhkarBot"
                    
                    # Create a deep link with group chat_id encoded
                    # Format: ?start=group_<chat_id>
                    # We need to encode the chat_id to avoid negative numbers in deep links
                    # Use base64 encoding to handle negative chat IDs
                    chat_id_encoded = base64.b64encode(str(message.chat.id).encode()).decode()
                    start_link = f"https://t.me/{bot_username}?start=group_{chat_id_encoded}"
                    
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    markup.add(
                        types.InlineKeyboardButton(
                            "⚙️ فتح لوحة التحكم (الخاص)",
                            url=start_link
                        )
                    )
                    
                    bot.send_message(
                        message.chat.id,
                        "⚙️ *إعدادات البوت*\n\n"
                        "للحفاظ على خصوصية الإعدادات، يرجى فتح لوحة التحكم في الدردشة الخاصة.\n\n"
                        "اضغط على الزر أدناه لفتح الإعدادات:",
                        parse_mode="Markdown",
                        reply_markup=markup
                    )
                    logger.info(f"/start in group {message.chat.id} - redirected admin {message.from_user.id} to private chat with context")
                except Exception as e:
                    logger.error(f"Error redirecting admin to private chat: {e}")
                    bot.send_message(
                        message.chat.id,
                        "⚠️ حدث خطأ. يرجى المحاولة مرة أخرى",
                        parse_mode="Markdown"
                    )
            else:
                # User is not admin - show guidance with buttons
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(
                    types.InlineKeyboardButton("➕ إضافة البوت كمشرف", url=f"https://t.me/{bot_username}?startgroup=true"),
                    types.InlineKeyboardButton("👥 المجموعة الرسمية", url="https://t.me/NourAdhkar"),
                    types.InlineKeyboardButton("👨‍💻 المطور", url="https://t.me/dev3bod")
                )
                
                bot.send_message(
                    message.chat.id,
                    "⚠️ *يرجى تثبيت البوت كمشرف في المجموعة*\n\n"
                    "لتتمكن من استخدام جميع ميزات البوت، يجب تثبيته كمشرف في المجموعة.\n\n"
                    "*الميزات المتاحة:*\n"
                    "• 🌅 أذكار الصباح والمساء\n"
                    "• 📿 سورة الكهف يوم الجمعة\n"
                    "• 🕌 أدعية الجمعة\n"
                    "• 🌙 إعدادات رمضان والحج\n"
                    "• ✨ أدعية متنوعة قابلة للتخصيص",
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
                logger.info(f"/start in group {message.chat.id} from non-admin user {message.from_user.id}")
                
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}", exc_info=True)
        try:
            bot.reply_to(message, "حدث خطأ، يرجى المحاولة مرة أخرى")
        except Exception:
            # Final fallback - nothing we can do if even error message fails
            pass

@bot.message_handler(commands=["settings"])
def cmd_settings(message: types.Message):
    """
    Legacy /settings command - redirects to /start.
    The /start command now handles all settings functionality.
    """
    try:
        bot.send_message(
            message.chat.id,
            "ℹ️ *تم دمج الإعدادات مع الأمر /start*\n\n"
            "يرجى استخدام الأمر `/start` للوصول إلى لوحة التحكم المتقدمة",
            parse_mode="Markdown"
        )
        logger.info(f"/settings redirect message sent to {message.from_user.id} in {message.chat.id}")
    except Exception as e:
        logger.error(f"Error in cmd_settings: {e}", exc_info=True)


@bot.callback_query_handler(func=lambda call: is_simple_toggle_callback(call.data))
def callback_toggle(call: types.CallbackQuery):
    """
    Handle toggle callbacks for settings when used directly in group chats.
    This handler only processes simple toggle commands without chat_id suffix.
    Toggle commands with chat_id are handled by specific handlers.
    """
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
        status = "✅" if get_chat_settings(call.message.chat.id)[k] else "❌"
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

@bot.callback_query_handler(func=lambda call: call.data == "open_settings")
def callback_open_settings(call: types.CallbackQuery):
    """
    Handle callback for open_settings button.
    Displays a list of groups that the user can manage, or the full advanced settings panel.
    """
    try:
        # Get all groups where this user is an admin
        conn, c, is_postgres = get_db_connection()
        
        try:
            placeholder = "%s" if is_postgres else "?"
            c.execute(f'''
                SELECT DISTINCT chat_id FROM admins 
                WHERE user_id = {placeholder}
            ''', (call.from_user.id,))
            
            user_groups = [row[0] for row in c.fetchall()]
        finally:
            conn.close()
        
        if not user_groups:
            bot.answer_callback_query(
                call.id,
                "⚠️ لم يتم العثور على مجموعات. يرجى استخدام /start في مجموعة أولاً.",
                show_alert=True
            )
            return
        
        # Answer the callback query
        bot.answer_callback_query(call.id, "اختر المجموعة")
        
        # Build group selection panel
        settings_text = (
            "⚙️ *لوحة التحكم المتقدمة*\n\n"
            "*اختر المجموعة التي تريد إدارتها:*\n\n"
        )
        
        # Create keyboard with group buttons
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for chat_id in user_groups:
            try:
                # Get chat title
                chat_info = bot.get_chat(chat_id)
                chat_title = chat_info.title or f"Group {chat_id}"
                
                # Encode chat_id for callback data
                chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
                
                markup.add(
                    types.InlineKeyboardButton(
                        f"📱 {chat_title}",
                        callback_data=f"select_group_{chat_id_encoded}"
                    )
                )
            except Exception as e:
                logger.warning(f"Could not get info for chat {chat_id}: {e}")
                continue
        
        # Edit the message to show group selection
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Group selection displayed for user {call.from_user.id} ({len(user_groups)} groups)")
        
    except Exception as e:
        logger.error(f"Error in callback_open_settings: {e}", exc_info=True)
        # Only answer callback if not already answered
        try:
            bot.answer_callback_query(
                call.id,
                "حدث خطأ أثناء تحميل الإعدادات",
                show_alert=True
            )
        except Exception:
            # Callback already answered
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_group_"))
def callback_select_group(call: types.CallbackQuery):
    """
    Handle group selection from the list.
    Opens the settings panel for the selected group.
    """
    try:
        # Extract and decode the chat_id with validation
        chat_id_encoded = call.data.replace("select_group_", "")
        
        try:
            decoded_str = base64.b64decode(chat_id_encoded).decode('utf-8')
            chat_id = int(decoded_str)
        except (ValueError, UnicodeDecodeError) as e:
            logger.error(f"Invalid chat_id encoding in callback: {e}")
            bot.answer_callback_query(
                call.id,
                "⚠️ خطأ في معرف المجموعة",
                show_alert=True
            )
            return
        
        # Verify user is admin of this chat
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(
                call.id,
                "⚠️ لست مشرفًا في هذه المجموعة",
                show_alert=True
            )
            return
        
        bot.answer_callback_query(call.id, "تم تحميل إعدادات المجموعة")
        
        # Get group info
        try:
            chat_info = bot.get_chat(chat_id)
            chat_title = chat_info.title or f"Group {chat_id}"
        except Exception as e:
            logger.debug(f"Could not get chat info for {chat_id}: {e}")
            chat_title = f"Group {chat_id}"
        
        # Build settings panel for this group
        settings_text = (
            f"⚙️ *لوحة التحكم*\n\n"
            f"📱 المجموعة: *{chat_title}*\n\n"
            "*اختر القسم الذي تريد تعديله:*"
        )
        
        # Create keyboard with main sections - encode chat_id in callback data
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🌅🌙 أذكار الصباح والمساء", callback_data=f"morning_evening_settings_{chat_id}"),
            types.InlineKeyboardButton("📿 أدعية الجمعة", callback_data=f"friday_settings_{chat_id}"),
            types.InlineKeyboardButton("✨ أذكار متنوعة", callback_data=f"diverse_azkar_settings_{chat_id}"),
            types.InlineKeyboardButton("⚙️ إعدادات عامة", callback_data=f"general_settings_{chat_id}"),
            types.InlineKeyboardButton("🌙 إعدادات رمضان", callback_data=f"ramadan_settings_{chat_id}"),
            types.InlineKeyboardButton("🕋 إعدادات الحج", callback_data=f"hajj_eid_settings_{chat_id}"),
            types.InlineKeyboardButton("🌙 تذكيرات الصيام", callback_data=f"fasting_reminders_{chat_id}")
        )
        markup.add(
            types.InlineKeyboardButton("« العودة للمجموعات", callback_data="open_settings")
        )
        # Add developer and official group buttons
        add_support_buttons(markup)
        
        # Edit the message to show settings
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Settings panel for group {chat_id} displayed to user {call.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error in callback_select_group: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data == "settings_panel")
def callback_settings_panel(call: types.CallbackQuery):
    """
    Handle callback for settings_panel button.
    Redirects to main settings panel (open_settings).
    """
    try:
        # Redirect to open_settings
        call.data = "open_settings"
        callback_open_settings(call)
    except Exception as e:
        logger.error(f"Error in callback_settings_panel: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data == "advanced_settings")
def callback_advanced_settings(call: types.CallbackQuery):
    """
    Handle callback for advanced settings panel - DEPRECATED.
    Redirects to main settings panel.
    """
    try:
        # Redirect to open_settings
        call.data = "open_settings"
        callback_open_settings(call)
    except Exception as e:
        logger.error(f"Error in callback_advanced_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("morning_evening_settings"))
def callback_morning_evening_settings(call: types.CallbackQuery):
    """
    Handle callback for morning and evening azkar settings.
    Shows options to enable/disable and configure timing with toggle controls.
    Supports both old format (morning_evening_settings) and new format (morning_evening_settings_{chat_id})
    """
    try:
        # Extract chat_id from callback data if present
        if "_" in call.data and call.data.count("_") >= 3:
            # New format: morning_evening_settings_{chat_id}
            parts = call.data.split("_")
            try:
                chat_id = int(parts[-1])
                # Verify user is admin of this chat
                if not is_user_admin_of_chat(call.from_user.id, chat_id):
                    bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
                    return
            except (ValueError, IndexError):
                # Fallback to old behavior
                chat_id = None
                is_admin = is_user_admin_in_any_group(call.from_user.id)
                if not is_admin:
                    bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
                    return
        else:
            # Old format: morning_evening_settings (backwards compatibility)
            chat_id = None
            is_admin = is_user_admin_in_any_group(call.from_user.id)
            if not is_admin:
                bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
                return
        
        bot.answer_callback_query(call.id, "أذكار الصباح والمساء")
        
        # Get settings for this specific chat (or show general info)
        if chat_id:
            settings = get_chat_settings(chat_id)
            morning_status = "✅ مفعّل" if settings.get('morning_azkar', 1) else "❌ معطّل"
            evening_status = "✅ مفعّل" if settings.get('evening_azkar', 1) else "❌ معطّل"
            morning_time = settings.get('morning_time', '05:00')
            evening_time = settings.get('evening_time', '18:00')
            
            settings_text = (
                "🌅🌙 *إعدادات أذكار الصباح والمساء*\n\n"
                f"*الحالة الحالية:*\n"
                f"• أذكار الصباح: {morning_status} (الوقت: {morning_time})\n"
                f"• أذكار المساء: {evening_status} (الوقت: {evening_time})\n\n"
                "*أذكار الصباح:*\n"
                "• يتم إرسالها تلقائياً في الوقت المحدد\n"
                "• الوقت الافتراضي: 05:00\n"
                "• قابلة للتخصيص لكل مجموعة\n\n"
                "*أذكار المساء:*\n"
                "• يتم إرسالها تلقائياً في الوقت المحدد\n"
                "• الوقت الافتراضي: 18:00\n"
                "• قابلة للتخصيص لكل مجموعة\n\n"
                "*التحكم:*\n"
                "استخدم الأزرار أدناه للتفعيل/التعطيل"
            )
        else:
            settings_text = (
                "🌅🌙 *إعدادات أذكار الصباح والمساء*\n\n"
                "*أذكار الصباح:*\n"
                "• يتم إرسالها تلقائياً في الوقت المحدد\n"
                "• الوقت الافتراضي: 05:00\n"
                "• قابلة للتخصيص لكل مجموعة\n\n"
                "*أذكار المساء:*\n"
                "• يتم إرسالها تلقائياً في الوقت المحدد\n"
                "• الوقت الافتراضي: 18:00\n"
                "• قابلة للتخصيص لكل مجموعة\n\n"
                "*الميزات:*\n"
                "• ✅/❌ تفعيل أو تعطيل لكل مجموعة\n"
                "• دعم الوسائط (صور، فيديو، ملفات)\n"
                "• تخصيص الأوقات باستخدام `/settime` في المجموعة\n\n"
                "*أمثلة لتخصيص الأوقات:*\n"
                "`/settime morning 06:30`\n"
                "`/settime evening 19:00`\n\n"
                "*للتعديل في مجموعة معينة:*\n"
                "استخدم الأوامر المذكورة في المجموعة التي تريد تخصيص أوقاتها"
            )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        # Add toggle buttons if chat_id is specified
        if chat_id:
            settings = get_chat_settings(chat_id)
            morning_icon = "✅" if settings.get('morning_azkar', 1) else "❌"
            evening_icon = "✅" if settings.get('evening_azkar', 1) else "❌"
            
            markup.add(
                types.InlineKeyboardButton(
                    f"{morning_icon} أذكار الصباح", 
                    callback_data=f"toggle_morning_azkar_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    f"{evening_icon} أذكار المساء", 
                    callback_data=f"toggle_evening_azkar_{chat_id}"
                )
            )
            
            # Add time preset buttons
            markup.add(
                types.InlineKeyboardButton("⏰ أوقات شائعة للصباح", callback_data=f"morning_time_presets_{chat_id}"),
                types.InlineKeyboardButton("🌙 أوقات شائعة للمساء", callback_data=f"evening_time_presets_{chat_id}")
            )
            
            # Add back button with chat_id encoded
            chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
            markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        else:
            markup.add(
                types.InlineKeyboardButton("⏰ أوقات شائعة للصباح", callback_data="morning_time_presets"),
                types.InlineKeyboardButton("🌙 أوقات شائعة للمساء", callback_data="evening_time_presets")
            )
            # Old format: go back to general settings
            markup.add(types.InlineKeyboardButton("« العودة", callback_data="open_settings"))
        
        # Only add support buttons in main settings (not group-specific)
        if chat_id is None:
            add_support_buttons(markup)
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Morning/Evening settings displayed for user {call.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error in callback_morning_evening_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("general_settings"))
def callback_general_settings(call: types.CallbackQuery):
    """
    Handle callback for general settings panel.
    Shows sleep message and service message deletion controls.
    """
    try:
        # Extract chat_id from callback data if present
        chat_id, has_chat_id = extract_chat_id_from_callback(call.data)
        
        if has_chat_id and chat_id:
            # Verify user is admin of this chat
            if not is_user_admin_of_chat(call.from_user.id, chat_id):
                bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
                return
        else:
            bot.answer_callback_query(call.id, "⚠️ يرجى تحديد مجموعة أولاً", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "الإعدادات العامة")
        
        # Get settings
        settings = get_chat_settings(chat_id)
        sleep_status = "✅ مفعّل" if settings.get('sleep_message', 1) else "❌ معطّل"
        sleep_time = settings.get('sleep_time', '22:00')
        delete_service_status = "✅ مفعّل" if settings.get('delete_service_messages', 1) else "❌ معطّل"
        
        settings_text = (
            "⚙️ *الإعدادات العامة*\n\n"
            f"*الحالة الحالية:*\n"
            f"• رسالة النوم: {sleep_status} (الوقت: {sleep_time})\n"
            f"• حذف رسائل النظام: {delete_service_status}\n\n"
            "*رسالة النوم:*\n"
            "• يتم إرسال رسالة مساء الخير مع أذكار النوم\n"
            "• الوقت الافتراضي: 22:00\n"
            "• قابلة للتخصيص\n\n"
            "*حذف رسائل النظام:*\n"
            "• عند التفعيل، يتم حذف رسائل النظام تلقائياً\n"
            "• الرسائل المشمولة:\n"
            "  - رسائل انضمام/مغادرة الأعضاء\n"
            "  - رسائل تغيير اسم المجموعة\n"
            "  - رسائل تثبيت الرسائل\n"
            "  - رسائل بدء/انتهاء المكالمات الصوتية\n"
            "  - وغيرها من رسائل النظام\n\n"
            "*التحكم:*\n"
            "استخدم الأزرار أدناه للتفعيل/التعطيل وتخصيص الأوقات"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        # Add toggle buttons
        sleep_icon = "✅" if settings.get('sleep_message', 1) else "❌"
        delete_icon = "✅" if settings.get('delete_service_messages', 1) else "❌"
        
        markup.add(
            types.InlineKeyboardButton(
                f"{sleep_icon} رسالة النوم", 
                callback_data=f"toggle_sleep_message_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{delete_icon} حذف رسائل النظام", 
                callback_data=f"toggle_delete_service_messages_{chat_id}"
            )
        )
        
        # Add time preset button for sleep message
        markup.add(
            types.InlineKeyboardButton("😴 أوقات شائعة للنوم", callback_data=f"sleep_time_presets_{chat_id}")
        )
        
        # Add back button
        chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
        markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"General settings displayed for user {call.from_user.id} in chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_general_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("sleep_time_presets"))
def callback_sleep_time_presets(call: types.CallbackQuery):
    """Show preset times for sleep message with clickable time buttons."""
    try:
        # Extract chat_id from callback data if present
        chat_id, has_chat_id = extract_chat_id_from_callback(call.data)
        
        if has_chat_id and chat_id:
            # Verify user is admin of this chat
            if not is_user_admin_of_chat(call.from_user.id, chat_id):
                bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
                return
        else:
            bot.answer_callback_query(call.id, "⚠️ يرجى تحديد مجموعة أولاً", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "اختر الوقت")
        
        # Get current time setting
        settings = get_chat_settings(chat_id)
        current_time = settings.get('sleep_time', '22:00')
        
        settings_text = (
            "😴 *تخصيص وقت رسالة النوم*\n\n"
            f"الوقت الحالي: *{current_time}*\n\n"
            "*اختر وقتاً من الأوقات الشائعة:*\n"
            "• 21:00 - مساءً\n"
            "• 22:00 - الافتراضي\n"
            "• 23:00 - ليلاً\n"
            "• 00:00 - منتصف الليل\n\n"
            "*أو استخدم الأمر في المجموعة:*\n"
            "`/settime sleep HH:MM`"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # Add clickable time buttons
        time_options = [
            ("21:00", "21:00 🌙"),
            ("22:00", "22:00 ⭐"),
            ("23:00", "23:00 🌃"),
            ("00:00", "00:00 🌌")
        ]
        
        for time_value, time_label in time_options:
            # Highlight current time
            if time_value == current_time:
                time_label = f"✅ {time_label}"
            markup.add(
                types.InlineKeyboardButton(
                    time_label,
                    callback_data=f"set_sleep_time_{time_value.replace(':', '')}_{chat_id}"
                )
            )
        
        # Add back button
        markup.add(
            types.InlineKeyboardButton("« العودة", callback_data=f"general_settings_{chat_id}")
        )
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in callback_sleep_time_presets: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_sleep_time_"))
def callback_set_sleep_time(call: types.CallbackQuery):
    """Handle setting sleep message time from preset buttons."""
    try:
        # Parse callback data: set_sleep_time_HHMM_chat_id
        parts = call.data.split("_")
        if len(parts) < 5:
            bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
            return
        
        time_str = parts[3]  # e.g., "2100"
        chat_id = int(parts[4] if len(parts) == 5 else parts[-1])  # Handle variable format
        
        # Convert time string to HH:MM format
        time_formatted = f"{time_str[:2]}:{time_str[2:]}"
        
        # Verify user is admin of this chat
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        # Update the time setting
        update_chat_setting(chat_id, "sleep_time", time_formatted)
        schedule_chat_jobs(chat_id)
        
        bot.answer_callback_query(call.id, f"✅ تم تعيين وقت النوم: {time_formatted}")
        
        # Refresh the time presets view
        call.data = f"sleep_time_presets_{chat_id}"
        callback_sleep_time_presets(call)
        
    except Exception as e:
        logger.error(f"Error in callback_set_sleep_time: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_sleep_message_") or call.data.startswith("toggle_delete_service_messages_"))
def callback_toggle_general_settings(call: types.CallbackQuery):
    """
    Handle toggle callbacks for sleep message and service message deletion.
    Format: toggle_sleep_message_{chat_id} or toggle_delete_service_messages_{chat_id}
    """
    try:
        # Parse callback data
        parts = call.data.split("_")
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
            return
        
        chat_id = int(parts[-1])
        
        # Determine the setting type
        if "sleep" in call.data:
            setting_key = "sleep_message"
            setting_name = "رسالة النوم"
        elif "delete" in call.data:
            setting_key = "delete_service_messages"
            setting_name = "حذف رسائل النظام"
        else:
            bot.answer_callback_query(call.id, "⚠️ إعداد غير معروف", show_alert=True)
            return
        
        # Verify user is admin of this chat
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        # Get current settings and toggle
        settings = get_chat_settings(chat_id)
        new_value = not settings.get(setting_key, 1)
        update_chat_setting(chat_id, setting_key, new_value)
        
        # Reschedule jobs if it's sleep_message
        if setting_key == "sleep_message":
            schedule_chat_jobs(chat_id)
        
        # Prepare updated message
        settings = get_chat_settings(chat_id)
        sleep_status = "✅ مفعّل" if settings.get('sleep_message', 1) else "❌ معطّل"
        sleep_time = settings.get('sleep_time', '22:00')
        delete_service_status = "✅ مفعّل" if settings.get('delete_service_messages', 1) else "❌ معطّل"
        
        settings_text = (
            "⚙️ *الإعدادات العامة*\n\n"
            f"*الحالة الحالية:*\n"
            f"• رسالة النوم: {sleep_status} (الوقت: {sleep_time})\n"
            f"• حذف رسائل النظام: {delete_service_status}\n\n"
            "*رسالة النوم:*\n"
            "• يتم إرسال رسالة مساء الخير مع أذكار النوم\n"
            "• الوقت الافتراضي: 22:00\n"
            "• قابلة للتخصيص\n\n"
            "*حذف رسائل النظام:*\n"
            "• عند التفعيل، يتم حذف رسائل النظام تلقائياً\n"
            "• الرسائل المشمولة:\n"
            "  - رسائل انضمام/مغادرة الأعضاء\n"
            "  - رسائل تغيير اسم المجموعة\n"
            "  - رسائل تثبيت الرسائل\n"
            "  - رسائل بدء/انتهاء المكالمات الصوتية\n"
            "  - وغيرها من رسائل النظام\n\n"
            "*التحكم:*\n"
            "استخدم الأزرار أدناه للتفعيل/التعطيل وتخصيص الأوقات"
        )
        
        # Update markup with new status
        markup = types.InlineKeyboardMarkup(row_width=1)
        sleep_icon = "✅" if settings.get('sleep_message', 1) else "❌"
        delete_icon = "✅" if settings.get('delete_service_messages', 1) else "❌"
        
        markup.add(
            types.InlineKeyboardButton(
                f"{sleep_icon} رسالة النوم", 
                callback_data=f"toggle_sleep_message_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{delete_icon} حذف رسائل النظام", 
                callback_data=f"toggle_delete_service_messages_{chat_id}"
            )
        )
        
        # Add time preset button for sleep message
        markup.add(
            types.InlineKeyboardButton("😴 أوقات شائعة للنوم", callback_data=f"sleep_time_presets_{chat_id}")
        )
        
        # Add back button
        chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
        markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        
        # Edit message with updated status
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        # Answer callback with confirmation
        status_text = "تم التفعيل ✅" if new_value else "تم التعطيل ❌"
        bot.answer_callback_query(call.id, f"{setting_name}: {status_text}")
        
        logger.info(f"User {call.from_user.id} toggled {setting_key} to {new_value} for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_toggle_general_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("morning_time_presets"))
def callback_morning_time_presets(call: types.CallbackQuery):
    """Show preset times for morning azkar with clickable time buttons."""
    try:
        # Extract chat_id from callback data if present
        chat_id, has_chat_id = extract_chat_id_from_callback(call.data)
        
        if has_chat_id and chat_id:
            # Verify user is admin of this chat
            if not is_user_admin_of_chat(call.from_user.id, chat_id):
                bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
                return
        
        # If no chat_id, verify user is admin in any group
        if not has_chat_id:
            is_admin = is_user_admin_in_any_group(call.from_user.id)
            if not is_admin:
                bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
                return
            # Show error if no chat_id
            bot.answer_callback_query(call.id, "⚠️ يرجى تحديد مجموعة أولاً", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "اختر الوقت")
        
        # Get current time setting
        current_time = "05:00"
        if chat_id:
            settings = get_chat_settings(chat_id)
            current_time = settings.get('morning_time', '05:00')
        
        settings_text = (
            "⏰ *تخصيص وقت أذكار الصباح*\n\n"
            f"الوقت الحالي: *{current_time}*\n\n"
            "*اختر وقتاً من الأوقات الشائعة:*\n"
            "• 04:30 - بعد صلاة الفجر مباشرة\n"
            "• 05:00 - الافتراضي\n"
            "• 06:00 - مع شروق الشمس تقريباً\n"
            "• 07:00 - صباحاً\n\n"
            "*أو استخدم الأمر في المجموعة:*\n"
            "`/settime morning HH:MM`"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # Add clickable time buttons
        time_options = [
            ("04:30", "04:30 🌄"),
            ("05:00", "05:00 ⭐"),
            ("06:00", "06:00 ☀️"),
            ("07:00", "07:00 🌅")
        ]
        
        for time_value, time_label in time_options:
            # Highlight current time
            if time_value == current_time:
                time_label = f"✅ {time_label}"
            markup.add(
                types.InlineKeyboardButton(
                    time_label,
                    callback_data=f"set_morning_time_{time_value.replace(':', '')}_{chat_id}"
                )
            )
        
        # Add back button
        markup.add(
            types.InlineKeyboardButton("« العودة", callback_data=f"morning_evening_settings_{chat_id}")
        )
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in callback_morning_time_presets: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("evening_time_presets"))
def callback_evening_time_presets(call: types.CallbackQuery):
    """Show preset times for evening azkar with clickable time buttons."""
    try:
        # Extract chat_id from callback data if present
        chat_id, has_chat_id = extract_chat_id_from_callback(call.data)
        
        if has_chat_id and chat_id:
            # Verify user is admin of this chat
            if not is_user_admin_of_chat(call.from_user.id, chat_id):
                bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
                return
        
        # If no chat_id, verify user is admin in any group
        if not has_chat_id:
            is_admin = is_user_admin_in_any_group(call.from_user.id)
            if not is_admin:
                bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
                return
            # Show error if no chat_id
            bot.answer_callback_query(call.id, "⚠️ يرجى تحديد مجموعة أولاً", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "اختر الوقت")
        
        # Get current time setting
        current_time = "18:00"
        if chat_id:
            settings = get_chat_settings(chat_id)
            current_time = settings.get('evening_time', '18:00')
        
        settings_text = (
            "🌙 *تخصيص وقت أذكار المساء*\n\n"
            f"الوقت الحالي: *{current_time}*\n\n"
            "*اختر وقتاً من الأوقات الشائعة:*\n"
            "• 15:30 - بعد صلاة العصر\n"
            "• 17:00 - قبل المغرب\n"
            "• 18:00 - الافتراضي\n"
            "• 19:00 - مساءً\n\n"
            "*أو استخدم الأمر في المجموعة:*\n"
            "`/settime evening HH:MM`"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # Add clickable time buttons
        time_options = [
            ("15:30", "15:30 🕌"),
            ("17:00", "17:00 🌆"),
            ("18:00", "18:00 ⭐"),
            ("19:00", "19:00 🌙")
        ]
        
        for time_value, time_label in time_options:
            # Highlight current time
            if time_value == current_time:
                time_label = f"✅ {time_label}"
            markup.add(
                types.InlineKeyboardButton(
                    time_label,
                    callback_data=f"set_evening_time_{time_value.replace(':', '')}_{chat_id}"
                )
            )
        
        # Add back button
        markup.add(
            types.InlineKeyboardButton("« العودة", callback_data=f"morning_evening_settings_{chat_id}")
        )
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in callback_evening_time_presets: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_morning_time_"))
def callback_set_morning_time(call: types.CallbackQuery):
    """Handle setting morning azkar time from preset buttons."""
    try:
        # Parse callback data: set_morning_time_HHMM_chat_id
        parts = call.data.split("_")
        if len(parts) < 5:
            bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
            return
        
        time_str = parts[3]  # e.g., "0430"
        chat_id = int(parts[4] if len(parts) == 5 else parts[-1])  # Handle variable format
        
        # Convert time string to HH:MM format
        time_formatted = f"{time_str[:2]}:{time_str[2:]}"
        
        # Verify user is admin of this chat
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        # Update the time setting
        update_chat_setting(chat_id, "morning_time", time_formatted)
        schedule_chat_jobs(chat_id)
        
        bot.answer_callback_query(call.id, f"✅ تم تعيين وقت الصباح: {time_formatted}")
        
        # Refresh the time presets view
        call.data = f"morning_time_presets_{chat_id}"
        callback_morning_time_presets(call)
        
    except Exception as e:
        logger.error(f"Error in callback_set_morning_time: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_evening_time_"))
def callback_set_evening_time(call: types.CallbackQuery):
    """Handle setting evening azkar time from preset buttons."""
    try:
        # Parse callback data: set_evening_time_HHMM_chat_id
        parts = call.data.split("_")
        if len(parts) < 5:
            bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
            return
        
        time_str = parts[3]  # e.g., "1530"
        chat_id = int(parts[4] if len(parts) == 5 else parts[-1])  # Handle variable format
        
        # Convert time string to HH:MM format
        time_formatted = f"{time_str[:2]}:{time_str[2:]}"
        
        # Verify user is admin of this chat
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        # Update the time setting
        update_chat_setting(chat_id, "evening_time", time_formatted)
        schedule_chat_jobs(chat_id)
        
        bot.answer_callback_query(call.id, f"✅ تم تعيين وقت المساء: {time_formatted}")
        
        # Refresh the time presets view
        call.data = f"evening_time_presets_{chat_id}"
        callback_evening_time_presets(call)
        
    except Exception as e:
        logger.error(f"Error in callback_set_evening_time: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("friday_settings"))
def callback_friday_settings(call: types.CallbackQuery):
    """
    Handle callback for Friday prayers settings.
    Shows options for Surat Al-Kahf and Friday duas with toggle controls.
    Supports both old format (friday_settings) and new format (friday_settings_{chat_id})
    """
    try:
        # Extract chat_id from callback data if present
        chat_id = None
        if "_" in call.data and call.data.count("_") >= 2:
            # New format: friday_settings_{chat_id}
            parts = call.data.split("_")
            try:
                chat_id = int(parts[-1])
                # Verify user is admin of this chat
                if not is_user_admin_of_chat(call.from_user.id, chat_id):
                    bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
                    return
            except (ValueError, IndexError):
                # Fallback to old behavior
                chat_id = None
        
        # If no chat_id, verify user is admin in any group
        if chat_id is None:
            is_admin = is_user_admin_in_any_group(call.from_user.id)
            if not is_admin:
                bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
                return
        
        # Get settings for this specific chat (or show general info)
        if chat_id:
            settings = get_chat_settings(chat_id)
            friday_sura_status = "✅ مفعّل" if settings.get('friday_sura', 1) else "❌ معطّل"
            friday_dua_status = "✅ مفعّل" if settings.get('friday_dua', 1) else "❌ معطّل"
            
            settings_text = (
                "📿🕌 *إعدادات أدعية الجمعة*\n\n"
                f"*الحالة الحالية:*\n"
                f"• سورة الكهف: {friday_sura_status}\n"
                f"• أدعية الجمعة: {friday_dua_status}\n\n"
                "*سورة الكهف:*\n"
                "• تُرسل تلقائياً كل يوم جمعة\n"
                "• الوقت: الجمعة 09:00\n"
                "• يمكن إرسالها مع صور أو فيديو إسلامي\n\n"
                "*أدعية الجمعة:*\n"
                "• أدعية وأذكار خاصة بيوم الجمعة\n"
                "• الوقت: الجمعة 10:00\n"
                "• تشمل أدعية مستجابة في ساعة الإجابة\n\n"
                "*التحكم:*\n"
                "استخدم الأزرار أدناه للتفعيل/التعطيل"
            )
        else:
            settings_text = (
                "📿🕌 *إعدادات أدعية الجمعة*\n\n"
                "*سورة الكهف:*\n"
                "• تُرسل تلقائياً كل يوم جمعة\n"
                "• الوقت: الجمعة 09:00\n"
                "• يمكن إرسالها مع صور أو فيديو إسلامي\n\n"
                "*أدعية الجمعة:*\n"
                "• أدعية وأذكار خاصة بيوم الجمعة\n"
                "• الوقت: الجمعة 10:00\n"
                "• تشمل أدعية مستجابة في ساعة الإجابة\n\n"
                "*الميزات:*\n"
                "• ✅/❌ تفعيل أو تعطيل كل ميزة على حدة\n"
                "• دعم إرسال الوسائط المتعددة\n"
                "• إعدادات مستقلة لكل مجموعة\n\n"
                "*للتعديل في مجموعة معينة:*\n"
                "استخدم `/start` في المجموعة واختر الميزات المطلوبة"
            )
        
        bot.answer_callback_query(call.id, "أدعية الجمعة")
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        # Add toggle buttons if chat_id is specified
        if chat_id:
            settings = get_chat_settings(chat_id)
            friday_sura_icon = "✅" if settings.get('friday_sura', 1) else "❌"
            friday_dua_icon = "✅" if settings.get('friday_dua', 1) else "❌"
            
            markup.add(
                types.InlineKeyboardButton(
                    f"{friday_sura_icon} سورة الكهف", 
                    callback_data=f"toggle_friday_sura_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    f"{friday_dua_icon} أدعية الجمعة", 
                    callback_data=f"toggle_friday_dua_{chat_id}"
                )
            )
            # Add button for customizing Friday times
            markup.add(
                types.InlineKeyboardButton("⏰ تخصيص أوقات الجمعة", callback_data=f"friday_time_settings_{chat_id}")
            )
            # Add back button with chat_id encoded
            chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
            markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        else:
            markup.add(types.InlineKeyboardButton("« العودة", callback_data="open_settings"))
        
        # Only add support buttons in main settings (not group-specific)
        if chat_id is None:
            add_support_buttons(markup)
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Friday settings displayed for user {call.from_user.id}, chat_id={chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_friday_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("friday_time_settings_"))
def callback_friday_time_settings(call: types.CallbackQuery):
    """
    Show information about customizing Friday times.
    Format: friday_time_settings_{chat_id}
    """
    try:
        # Extract chat_id from callback data
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
            return
        
        chat_id = int(parts[-1])
        
        # Verify user is admin of this chat
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "تخصيص أوقات الجمعة")
        
        settings_text = (
            "⏰ *تخصيص أوقات الجمعة*\n\n"
            "*الأوقات الافتراضية:*\n"
            "• سورة الكهف: الجمعة 09:00\n"
            "• أدعية الجمعة: الجمعة 10:00\n\n"
            "*ملاحظة:*\n"
            "حالياً، أوقات الجمعة ثابتة ولا يمكن تخصيصها.\n"
            "سيتم إضافة خاصية تخصيص الأوقات في التحديثات القادمة.\n\n"
            "*للتفعيل أو التعطيل:*\n"
            "استخدم الأزرار في شاشة إعدادات الجمعة الرئيسية"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("« العودة", callback_data=f"friday_settings_{chat_id}")
        )
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Friday time settings displayed for user {call.from_user.id}, chat_id={chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_friday_time_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data == "media_settings")
def callback_media_settings(call: types.CallbackQuery):
    """
    Handle callback for media settings panel.
    Allows user to configure media sending options.
    """
    try:
        is_admin = is_user_admin_in_any_group(call.from_user.id)
        
        if not is_admin:
            bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "إعدادات الوسائط")
        
        # Note: Media settings are global placeholders
        # In reality, each group should have its own settings
        settings_text = (
            "📷 *إعدادات الوسائط*\n\n"
            "*تفعيل الوسائط مع الأذكار:*\n"
            "يمكنك اختيار إرسال صور أو مقاطع فيديو مع الأذكار\n\n"
            "*أنواع الوسائط المتاحة:*\n"
            "• صور إسلامية\n"
            "• مقاطع فيديو\n"
            "• ملفات PDF\n\n"
            "*ملاحظة:* يتم اختيار الوسائط عشوائياً من قاعدة البيانات\n\n"
            "للتفعيل في مجموعة معينة:\n"
            "1. اذهب للمجموعة\n"
            "2. استخدم `/start`\n"
            "3. فعّل الميزات المطلوبة"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📸 نوع الوسائط: صور", callback_data="media_type_images"),
            types.InlineKeyboardButton("🎥 نوع الوسائط: فيديو", callback_data="media_type_videos"),
            types.InlineKeyboardButton("📄 نوع الوسائط: ملفات", callback_data="media_type_documents"),
            types.InlineKeyboardButton("🎲 نوع الوسائط: عشوائي", callback_data="media_type_all"),
            types.InlineKeyboardButton("« العودة", callback_data="open_settings")
        )
        add_support_buttons(markup)
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Media settings displayed for user {call.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error in callback_media_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("media_type_"))
def callback_media_type(call: types.CallbackQuery):
    """
    Handle media type selection callbacks.
    """
    try:
        media_type = call.data.replace("media_type_", "")
        
        media_names = {
            "images": "صور",
            "videos": "فيديو",
            "documents": "ملفات",
            "all": "عشوائي"
        }
        
        bot.answer_callback_query(
            call.id,
            f"✓ تم اختيار: {media_names.get(media_type, 'عشوائي')}",
            show_alert=False
        )
        
        logger.info(f"User {call.from_user.id} selected media type: {media_type}")
        
        # Note: This is a demonstration. In a full implementation,
        # you would save this preference to a user settings table
        
    except Exception as e:
        logger.error(f"Error in callback_media_type: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_friday_"))
def callback_toggle_friday(call: types.CallbackQuery):
    """
    Handle toggle callbacks for Friday settings (Sura Al-Kahf and Friday duas).
    Format: toggle_friday_sura_{chat_id} or toggle_friday_dua_{chat_id}
    """
    try:
        # Parse callback data to extract setting name and chat_id
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
            return
        
        # Extract setting type and chat_id
        # Format: toggle_friday_sura_{chat_id} or toggle_friday_dua_{chat_id}
        setting_type = parts[2]  # 'sura' or 'dua'
        chat_id = int(parts[3])
        
        # Verify user is admin of this chat
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        # Get current settings
        settings = get_chat_settings(chat_id)
        
        # Determine the setting key
        if setting_type == "sura":
            setting_key = "friday_sura"
            setting_name = "سورة الكهف"
        elif setting_type == "dua":
            setting_key = "friday_dua"
            setting_name = "أدعية الجمعة"
        else:
            bot.answer_callback_query(call.id, "⚠️ إعداد غير معروف", show_alert=True)
            return
        
        # Toggle the setting
        new_value = not settings.get(setting_key, 1)
        update_chat_setting(chat_id, setting_key, new_value)
        
        # Reschedule jobs
        schedule_chat_jobs(chat_id)
        
        # Prepare updated message
        settings = get_chat_settings(chat_id)
        friday_sura_status = "✅ مفعّل" if settings.get('friday_sura', 1) else "❌ معطّل"
        friday_dua_status = "✅ مفعّل" if settings.get('friday_dua', 1) else "❌ معطّل"
        
        settings_text = (
            "📿🕌 *إعدادات أدعية الجمعة*\n\n"
            f"*الحالة الحالية:*\n"
            f"• سورة الكهف: {friday_sura_status}\n"
            f"• أدعية الجمعة: {friday_dua_status}\n\n"
            "*سورة الكهف:*\n"
            "• تُرسل تلقائياً كل يوم جمعة\n"
            "• الوقت: الجمعة 09:00\n"
            "• يمكن إرسالها مع صور أو فيديو إسلامي\n\n"
            "*أدعية الجمعة:*\n"
            "• أدعية وأذكار خاصة بيوم الجمعة\n"
            "• الوقت: الجمعة 10:00\n"
            "• تشمل أدعية مستجابة في ساعة الإجابة\n\n"
            "*التحكم:*\n"
            "استخدم الأزرار أدناه للتفعيل/التعطيل"
        )
        
        # Update markup with new status
        markup = types.InlineKeyboardMarkup(row_width=1)
        friday_sura_icon = "✅" if settings.get('friday_sura', 1) else "❌"
        friday_dua_icon = "✅" if settings.get('friday_dua', 1) else "❌"
        
        markup.add(
            types.InlineKeyboardButton(
                f"{friday_sura_icon} سورة الكهف", 
                callback_data=f"toggle_friday_sura_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{friday_dua_icon} أدعية الجمعة", 
                callback_data=f"toggle_friday_dua_{chat_id}"
            )
        )
        
        # Add back button
        chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
        markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        
        # Edit message with updated status
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        # Answer callback with confirmation
        status_text = "تم التفعيل ✅" if new_value else "تم التعطيل ❌"
        bot.answer_callback_query(call.id, f"{setting_name}: {status_text}")
        
        logger.info(f"User {call.from_user.id} toggled {setting_key} to {new_value} for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_toggle_friday: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_morning_azkar_") or call.data.startswith("toggle_evening_azkar_"))
def callback_toggle_morning_evening(call: types.CallbackQuery):
    """
    Handle toggle callbacks for morning and evening azkar.
    Format: toggle_morning_azkar_{chat_id} or toggle_evening_azkar_{chat_id}
    """
    try:
        # Parse callback data to extract setting name and chat_id
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
            return
        
        # Extract setting type and chat_id
        # Format: toggle_morning_azkar_{chat_id} or toggle_evening_azkar_{chat_id}
        setting_type = parts[1]  # 'morning' or 'evening'
        chat_id = int(parts[-1])
        
        # Verify user is admin of this chat
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        # Get current settings
        settings = get_chat_settings(chat_id)
        
        # Determine the setting key
        if setting_type == "morning":
            setting_key = "morning_azkar"
            setting_name = "أذكار الصباح"
        elif setting_type == "evening":
            setting_key = "evening_azkar"
            setting_name = "أذكار المساء"
        else:
            bot.answer_callback_query(call.id, "⚠️ إعداد غير معروف", show_alert=True)
            return
        
        # Toggle the setting
        new_value = not settings.get(setting_key, 1)
        update_chat_setting(chat_id, setting_key, new_value)
        
        # Reschedule jobs
        schedule_chat_jobs(chat_id)
        
        # Prepare updated message
        settings = get_chat_settings(chat_id)
        morning_status = "✅ مفعّل" if settings.get('morning_azkar', 1) else "❌ معطّل"
        evening_status = "✅ مفعّل" if settings.get('evening_azkar', 1) else "❌ معطّل"
        morning_time = settings.get('morning_time', '05:00')
        evening_time = settings.get('evening_time', '18:00')
        
        settings_text = (
            "🌅🌙 *إعدادات أذكار الصباح والمساء*\n\n"
            f"*الحالة الحالية:*\n"
            f"• أذكار الصباح: {morning_status} (الوقت: {morning_time})\n"
            f"• أذكار المساء: {evening_status} (الوقت: {evening_time})\n\n"
            "*أذكار الصباح:*\n"
            "• يتم إرسالها تلقائياً في الوقت المحدد\n"
            "• الوقت الافتراضي: 05:00\n"
            "• قابلة للتخصيص لكل مجموعة\n\n"
            "*أذكار المساء:*\n"
            "• يتم إرسالها تلقائياً في الوقت المحدد\n"
            "• الوقت الافتراضي: 18:00\n"
            "• قابلة للتخصيص لكل مجموعة\n\n"
            "*التحكم:*\n"
            "استخدم الأزرار أدناه للتفعيل/التعطيل"
        )
        
        # Update markup with new status
        markup = types.InlineKeyboardMarkup(row_width=1)
        morning_icon = "✅" if settings.get('morning_azkar', 1) else "❌"
        evening_icon = "✅" if settings.get('evening_azkar', 1) else "❌"
        
        markup.add(
            types.InlineKeyboardButton(
                f"{morning_icon} أذكار الصباح", 
                callback_data=f"toggle_morning_azkar_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{evening_icon} أذكار المساء", 
                callback_data=f"toggle_evening_azkar_{chat_id}"
            )
        )
        
        # Add time preset buttons
        markup.add(
            types.InlineKeyboardButton("⏰ أوقات شائعة للصباح", callback_data=f"morning_time_presets_{chat_id}"),
            types.InlineKeyboardButton("🌙 أوقات شائعة للمساء", callback_data=f"evening_time_presets_{chat_id}")
        )
        
        # Add back button
        chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
        markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        
        # Edit message with updated status
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        # Answer callback with confirmation
        status_text = "تم التفعيل ✅" if new_value else "تم التعطيل ❌"
        bot.answer_callback_query(call.id, f"{setting_name}: {status_text}")
        
        logger.info(f"User {call.from_user.id} toggled {setting_key} to {new_value} for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_toggle_morning_evening: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data == "schedule_settings")
def callback_schedule_settings(call: types.CallbackQuery):
    """
    Handle callback for schedule settings panel.
    Allows user to configure timing options.
    """
    try:
        is_admin = is_user_admin_in_any_group(call.from_user.id)
        
        if not is_admin:
            bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "إعدادات المواعيد")
        
        settings_text = (
            "🕐 *إعدادات المواعيد*\n\n"
            "*الأوقات الافتراضية:*\n"
            "• أذكار الصباح: 05:00\n"
            "• أذكار المساء: 18:00\n"
            "• رسالة النوم: 22:00\n"
            "• سورة الكهف: الجمعة 09:00\n"
            "• دعاء الجمعة: الجمعة 10:00\n\n"
            "*لتخصيص الأوقات:*\n"
            "استخدم الأوامر التالية في المجموعة:\n"
            "`/settime morning HH:MM`\n"
            "`/settime evening HH:MM`\n"
            "`/settime sleep HH:MM`\n\n"
            "*مثال:*\n"
            "`/settime morning 06:30`"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("« العودة", callback_data="open_settings")
        )
        add_support_buttons(markup)
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Schedule settings displayed for user {call.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error in callback_schedule_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("diverse_azkar_settings"))
def callback_diverse_azkar_settings(call: types.CallbackQuery):
    """
    Handle callback for diverse azkar settings panel.
    Supports both old format (diverse_azkar_settings) and new format (diverse_azkar_settings_{chat_id})
    """
    try:
        # Extract chat_id from callback data if present
        chat_id, has_chat_id = extract_chat_id_from_callback(call.data)
        
        if has_chat_id and chat_id:
            # Verify user is admin of this chat
            if not is_user_admin_of_chat(call.from_user.id, chat_id):
                bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
                return
        
        # If no chat_id, verify user is admin in any group
        if not has_chat_id:
            is_admin = is_user_admin_in_any_group(call.from_user.id)
            if not is_admin:
                bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
                return
        
        bot.answer_callback_query(call.id, "إعدادات الأدعية المتنوعة")
        
        # Get settings for this specific chat (or show general info)
        if chat_id:
            diverse_settings = get_diverse_azkar_settings(chat_id)
            enabled_status = "✅ مفعّل" if diverse_settings.get('enabled', 0) else "❌ معطّل"
            interval = diverse_settings.get('interval_minutes', 60)
            
            # Convert interval to readable format
            if interval < 60:
                interval_text = f"{interval} دقيقة"
            elif interval == 60:
                interval_text = "ساعة واحدة"
            elif interval < 1440:
                interval_text = f"{interval // 60} ساعات"
            else:
                interval_text = "يوم كامل"
            
            settings_text = (
                "✨ *إعدادات الأدعية المتنوعة*\n\n"
                f"*الحالة الحالية:*\n"
                f"• الحالة: {enabled_status}\n"
                f"• الفاصل الزمني: {interval_text}\n\n"
                "*ما هي الأدعية المتنوعة؟*\n"
                "مجموعة من الأدعية والآيات والأحاديث المتنوعة "
                "يتم إرسالها بشكل دوري حسب الفاصل الزمني المحدد\n\n"
                "*الفواصل الزمنية المتاحة:*\n"
                "• دقيقة واحدة\n"
                "• 5 دقائق\n"
                "• 15 دقيقة\n"
                "• ساعة واحدة\n"
                "• ساعتين\n"
                "• 4 ساعات\n"
                "• 8 ساعات\n"
                "• 12 ساعة\n"
                "• 24 ساعة (يوم كامل)\n\n"
                "*التحكم:*\n"
                "استخدم الأزرار أدناه للتفعيل/التعطيل واختيار الفاصل الزمني"
            )
        else:
            settings_text = (
                "✨ *إعدادات الأدعية المتنوعة*\n\n"
                "*ما هي الأدعية المتنوعة؟*\n"
                "مجموعة من الأدعية والآيات والأحاديث المتنوعة "
                "يتم إرسالها بشكل دوري حسب الفاصل الزمني المحدد\n\n"
                "*الفواصل الزمنية المتاحة:*\n"
                "• دقيقة واحدة\n"
                "• 5 دقائق\n"
                "• 15 دقيقة\n"
                "• ساعة واحدة\n"
                "• ساعتين\n"
                "• 4 ساعات\n"
                "• 8 ساعات\n"
                "• 12 ساعة\n"
                "• 24 ساعة (يوم كامل)\n\n"
                "*للتفعيل في مجموعة:*\n"
                "استخدم `/start` في المجموعة واختر الفاصل الزمني المناسب"
            )
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # Add toggle button and interval buttons if chat_id is specified
        if chat_id:
            diverse_settings = get_diverse_azkar_settings(chat_id)
            enabled_icon = "✅" if diverse_settings.get('enabled', 0) else "❌"
            
            markup.add(
                types.InlineKeyboardButton(
                    f"{enabled_icon} تفعيل/تعطيل", 
                    callback_data=f"toggle_diverse_azkar_{chat_id}"
                )
            )
            
            # Add interval selection buttons
            markup.add(
                types.InlineKeyboardButton("1 دقيقة", callback_data=f"diverse_interval_{chat_id}_1"),
                types.InlineKeyboardButton("5 دقائق", callback_data=f"diverse_interval_{chat_id}_5")
            )
            markup.add(
                types.InlineKeyboardButton("15 دقيقة", callback_data=f"diverse_interval_{chat_id}_15"),
                types.InlineKeyboardButton("1 ساعة", callback_data=f"diverse_interval_{chat_id}_60")
            )
            markup.add(
                types.InlineKeyboardButton("2 ساعة", callback_data=f"diverse_interval_{chat_id}_120"),
                types.InlineKeyboardButton("4 ساعات", callback_data=f"diverse_interval_{chat_id}_240")
            )
            markup.add(
                types.InlineKeyboardButton("8 ساعات", callback_data=f"diverse_interval_{chat_id}_480"),
                types.InlineKeyboardButton("12 ساعة", callback_data=f"diverse_interval_{chat_id}_720")
            )
            markup.add(
                types.InlineKeyboardButton("24 ساعة", callback_data=f"diverse_interval_{chat_id}_1440")
            )
            
            # Add media format settings button
            markup.add(
                types.InlineKeyboardButton("🎨 إعدادات التنسيق", callback_data=f"diverse_media_format_{chat_id}")
            )
            
            # Add back button with chat_id encoded
            chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
            markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        else:
            markup.add(
                types.InlineKeyboardButton("1 دقيقة", callback_data="diverse_interval_1"),
                types.InlineKeyboardButton("5 دقائق", callback_data="diverse_interval_5"),
                types.InlineKeyboardButton("15 دقيقة", callback_data="diverse_interval_15"),
                types.InlineKeyboardButton("1 ساعة", callback_data="diverse_interval_60"),
                types.InlineKeyboardButton("2 ساعة", callback_data="diverse_interval_120"),
                types.InlineKeyboardButton("4 ساعات", callback_data="diverse_interval_240"),
                types.InlineKeyboardButton("8 ساعات", callback_data="diverse_interval_480"),
                types.InlineKeyboardButton("12 ساعة", callback_data="diverse_interval_720"),
                types.InlineKeyboardButton("24 ساعة", callback_data="diverse_interval_1440")
            )
            markup.add(types.InlineKeyboardButton("« العودة", callback_data="open_settings"))
        
        # Only add support buttons in main settings (not group-specific)
        if chat_id is None:
            add_support_buttons(markup)
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Diverse azkar settings displayed for user {call.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error in callback_diverse_azkar_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("diverse_interval_"))
def callback_diverse_interval(call: types.CallbackQuery):
    """
    Handle diverse azkar interval selection.
    Supports both old format (diverse_interval_{minutes}) and new format (diverse_interval_{chat_id}_{minutes})
    """
    try:
        # Parse callback data
        parts = call.data.replace("diverse_interval_", "").split("_")
        
        chat_id = None
        interval_minutes = None
        
        if len(parts) == 2:
            # New format: diverse_interval_{chat_id}_{minutes}
            try:
                chat_id = int(parts[0])
                interval_minutes = int(parts[1])
                
                # Verify user is admin of this chat
                if not is_user_admin_of_chat(call.from_user.id, chat_id):
                    bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
                    return
            except (ValueError, IndexError):
                bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
                return
        elif len(parts) == 1:
            # Old format: diverse_interval_{minutes}
            try:
                interval_minutes = int(parts[0])
            except ValueError:
                bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
                return
        else:
            bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
            return
        
        interval_names = {
            1: "دقيقة واحدة",
            5: "5 دقائق",
            15: "15 دقيقة",
            60: "ساعة واحدة",
            120: "ساعتين",
            240: "4 ساعات",
            480: "8 ساعات",
            720: "12 ساعة",
            1440: "24 ساعة"
        }
        
        # If chat_id is provided, update the settings
        if chat_id:
            update_diverse_azkar_setting(chat_id, 'interval_minutes', interval_minutes)
            # Enable diverse azkar if not already enabled
            diverse_settings = get_diverse_azkar_settings(chat_id)
            if not diverse_settings.get('enabled', 0):
                update_diverse_azkar_setting(chat_id, 'enabled', 1)
            
            # Reschedule jobs
            schedule_chat_jobs(chat_id)
            
            bot.answer_callback_query(
                call.id,
                f"✓ تم تحديث الفاصل الزمني: {interval_names.get(interval_minutes, str(interval_minutes))}",
                show_alert=False
            )
            
            # Refresh the settings view
            call.data = f"diverse_azkar_settings_{chat_id}"
            callback_diverse_azkar_settings(call)
        else:
            bot.answer_callback_query(
                call.id,
                f"✓ تم اختيار الفاصل الزمني: {interval_names.get(interval_minutes, str(interval_minutes))}",
                show_alert=False
            )
        
        logger.info(f"User {call.from_user.id} selected diverse interval: {interval_minutes} minutes for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_diverse_interval: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_diverse_azkar_"))
def callback_toggle_diverse_azkar(call: types.CallbackQuery):
    """
    Handle toggle callbacks for diverse azkar.
    Format: toggle_diverse_azkar_{chat_id}
    """
    try:
        # Parse callback data to extract chat_id
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
            return
        
        chat_id = int(parts[-1])
        
        # Verify user is admin of this chat
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        # Get current settings
        diverse_settings = get_diverse_azkar_settings(chat_id)
        
        # Toggle the enabled setting
        new_value = not diverse_settings.get('enabled', 0)
        update_diverse_azkar_setting(chat_id, 'enabled', new_value)
        
        # Reschedule jobs
        schedule_chat_jobs(chat_id)
        
        # Answer callback with confirmation
        status_text = "تم التفعيل ✅" if new_value else "تم التعطيل ❌"
        bot.answer_callback_query(call.id, f"أذكار متنوعة: {status_text}")
        
        # Refresh the settings view
        call.data = f"diverse_azkar_settings_{chat_id}"
        callback_diverse_azkar_settings(call)
        
        logger.info(f"User {call.from_user.id} toggled diverse azkar to {new_value} for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_toggle_diverse_azkar: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("diverse_media_format_"))
def callback_diverse_media_format(call: types.CallbackQuery):
    """
    Handle callback for diverse azkar media format settings.
    Format: diverse_media_format_{chat_id}
    """
    try:
        # Parse callback data to extract chat_id
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
            return
        
        chat_id = int(parts[-1])
        
        # Verify user is admin of this chat
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "إعدادات التنسيق")
        
        # Get current settings
        diverse_settings = get_diverse_azkar_settings(chat_id)
        audio_status = "✅ مفعّل" if diverse_settings.get('enable_audio', 1) else "❌ معطّل"
        images_status = "✅ مفعّل" if diverse_settings.get('enable_images', 1) else "❌ معطّل"
        pdf_status = "✅ مفعّل" if diverse_settings.get('enable_pdf', 1) else "❌ معطّل"
        text_status = "✅ مفعّل" if diverse_settings.get('enable_text', 1) else "❌ معطّل"
        
        settings_text = (
            "🎨 *إعدادات تنسيق الأدعية المتنوعة*\n\n"
            f"*الحالة الحالية:*\n"
            f"• الصوت: {audio_status}\n"
            f"• الصور: {images_status}\n"
            f"• ملفات PDF: {pdf_status}\n"
            f"• النص العادي: {text_status}\n\n"
            "*ما هو تنسيق الإرسال؟*\n"
            "يمكنك اختيار نوع أو أكثر من أنواع الوسائط التالية:\n\n"
            "*🎵 الصوت:*\n"
            "• ملفات صوتية للأدعية والقرآن\n"
            "• تشغيل مباشر في التليجرام\n\n"
            "*🖼️ الصور:*\n"
            "• صور ملهمة مع الأدعية\n"
            "• تصميمات جميلة للآيات\n\n"
            "*📄 ملفات PDF:*\n"
            "• كتب ومطويات\n"
            "• نشرات دعوية\n\n"
            "*📝 النص العادي:*\n"
            "• نص بسيط بدون وسائط\n"
            "• سهل القراءة والنسخ\n\n"
            "*التحكم:*\n"
            "استخدم الأزرار أدناه لتفعيل أو تعطيل كل نوع"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        # Add toggle buttons for each media type
        audio_icon = "✅" if diverse_settings.get('enable_audio', 1) else "❌"
        images_icon = "✅" if diverse_settings.get('enable_images', 1) else "❌"
        pdf_icon = "✅" if diverse_settings.get('enable_pdf', 1) else "❌"
        text_icon = "✅" if diverse_settings.get('enable_text', 1) else "❌"
        
        markup.add(
            types.InlineKeyboardButton(
                f"{audio_icon} الصوت", 
                callback_data=f"toggle_diverse_audio_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{images_icon} الصور", 
                callback_data=f"toggle_diverse_images_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{pdf_icon} ملفات PDF", 
                callback_data=f"toggle_diverse_pdf_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{text_icon} النص العادي", 
                callback_data=f"toggle_diverse_text_{chat_id}"
            )
        )
        
        # Add back button
        markup.add(
            types.InlineKeyboardButton("« العودة", callback_data=f"diverse_azkar_settings_{chat_id}")
        )
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Diverse media format settings displayed for user {call.from_user.id} in chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_diverse_media_format: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_diverse_audio_") or 
                                              call.data.startswith("toggle_diverse_images_") or
                                              call.data.startswith("toggle_diverse_pdf_") or
                                              call.data.startswith("toggle_diverse_text_"))
def callback_toggle_diverse_media(call: types.CallbackQuery):
    """
    Handle toggle callbacks for diverse azkar media types.
    Format: toggle_diverse_{type}_{chat_id}
    """
    try:
        # Parse callback data
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "⚠️ خطأ في البيانات", show_alert=True)
            return
        
        media_type = parts[2]  # 'audio', 'images', 'pdf', or 'text'
        chat_id = int(parts[-1])
        
        # Verify user is admin of this chat
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        # Map media types to setting keys and names
        setting_map = {
            "audio": ("enable_audio", "الصوت"),
            "images": ("enable_images", "الصور"),
            "pdf": ("enable_pdf", "ملفات PDF"),
            "text": ("enable_text", "النص العادي")
        }
        
        if media_type not in setting_map:
            bot.answer_callback_query(call.id, "⚠️ نوع غير معروف", show_alert=True)
            return
        
        setting_key, setting_name = setting_map[media_type]
        
        # Get current settings and toggle
        diverse_settings = get_diverse_azkar_settings(chat_id)
        new_value = not diverse_settings.get(setting_key, 1)
        update_diverse_azkar_setting(chat_id, setting_key, new_value)
        
        # Answer callback with confirmation
        status_text = "تم التفعيل ✅" if new_value else "تم التعطيل ❌"
        bot.answer_callback_query(call.id, f"{setting_name}: {status_text}")
        
        # Refresh the media format settings view
        call.data = f"diverse_media_format_{chat_id}"
        callback_diverse_media_format(call)
        
        logger.info(f"User {call.from_user.id} toggled {setting_key} to {new_value} for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_toggle_diverse_media: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("ramadan_settings"))
def callback_ramadan_settings(call: types.CallbackQuery):
    """
    Handle callback for Ramadan settings panel.
    Supports both old format (ramadan_settings) and new format (ramadan_settings_{chat_id})
    """
    try:
        # Extract chat_id from callback data if present
        chat_id = None
        if "_" in call.data and call.data.count("_") >= 2:
            # New format: ramadan_settings_{chat_id}
            parts = call.data.split("_")
            try:
                chat_id = int(parts[-1])
                # Verify user is admin of this chat
                if not is_user_admin_of_chat(call.from_user.id, chat_id):
                    bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
                    return
            except (ValueError, IndexError):
                # Fallback to old behavior
                chat_id = None
        
        # If no chat_id, verify user is admin in any group
        if chat_id is None:
            is_admin = is_user_admin_in_any_group(call.from_user.id)
            if not is_admin:
                bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
                return
        
        bot.answer_callback_query(call.id, "إعدادات رمضان")
        
        # Get settings for this specific chat (or show general info)
        if chat_id:
            ramadan_settings = get_ramadan_settings(chat_id)
            ramadan_status = "✅ مفعّل" if ramadan_settings.get('ramadan_enabled', 1) else "❌ معطّل"
            laylat_alqadr_status = "✅ مفعّل" if ramadan_settings.get('laylat_alqadr_enabled', 1) else "❌ معطّل"
            last_ten_status = "✅ مفعّل" if ramadan_settings.get('last_ten_days_enabled', 1) else "❌ معطّل"
            iftar_status = "✅ مفعّل" if ramadan_settings.get('iftar_dua_enabled', 1) else "❌ معطّل"
            
            settings_text = (
                "🌙 *إعدادات رمضان*\n\n"
                f"*الحالة الحالية:*\n"
                f"• أدعية رمضان: {ramadan_status}\n"
                f"• ليلة القدر: {laylat_alqadr_status}\n"
                f"• العشر الأواخر: {last_ten_status}\n"
                f"• دعاء الإفطار: {iftar_status}\n\n"
                "*الأقسام المتاحة:*\n\n"
                "*1. ليلة القدر:*\n"
                "أدعية خاصة بليلة القدر المباركة\n"
                "يتم إرسالها في الليالي الوترية من العشر الأواخر\n\n"
                "*2. العشر الأواخر من رمضان:*\n"
                "أذكار وأدعية خاصة بالعشر الأواخر\n"
                "تبدأ من اليوم 21 من رمضان\n\n"
                "*3. دعاء الإفطار:*\n"
                "يتم إرسال دعاء الإفطار قبل أذان المغرب\n\n"
                "*التحكم:*\n"
                "استخدم الأزرار أدناه للتفعيل/التعطيل"
            )
        else:
            settings_text = (
                "🌙 *إعدادات رمضان*\n\n"
                "*الأقسام المتاحة:*\n\n"
                "*1. ليلة القدر:*\n"
                "أدعية خاصة بليلة القدر المباركة\n"
                "يتم إرسالها في الليالي الوترية من العشر الأواخر\n\n"
                "*2. العشر الأواخر من رمضان:*\n"
                "أذكار وأدعية خاصة بالعشر الأواخر\n"
                "تبدأ من اليوم 21 من رمضان\n\n"
                "*3. دعاء الإفطار:*\n"
                "يتم إرسال دعاء الإفطار قبل أذان المغرب\n\n"
                "*للتفعيل:*\n"
                "استخدم `/start` في المجموعة وفعّل الميزات المطلوبة"
            )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        # Add toggle buttons if chat_id is specified
        if chat_id:
            ramadan_settings = get_ramadan_settings(chat_id)
            ramadan_icon = "✅" if ramadan_settings.get('ramadan_enabled', 1) else "❌"
            laylat_alqadr_icon = "✅" if ramadan_settings.get('laylat_alqadr_enabled', 1) else "❌"
            last_ten_icon = "✅" if ramadan_settings.get('last_ten_days_enabled', 1) else "❌"
            iftar_icon = "✅" if ramadan_settings.get('iftar_dua_enabled', 1) else "❌"
            
            markup.add(
                types.InlineKeyboardButton(
                    f"{ramadan_icon} أدعية رمضان", 
                    callback_data=f"toggle_ramadan_enabled_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    f"{laylat_alqadr_icon} ليلة القدر", 
                    callback_data=f"toggle_ramadan_laylat_alqadr_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    f"{last_ten_icon} العشر الأواخر", 
                    callback_data=f"toggle_ramadan_last_ten_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    f"{iftar_icon} دعاء الإفطار", 
                    callback_data=f"toggle_ramadan_iftar_{chat_id}"
                )
            )
            # Add back button with chat_id encoded
            chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
            markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        else:
            markup.add(types.InlineKeyboardButton("« العودة", callback_data="open_settings"))
        
        # Only add support buttons in main settings (not group-specific)
        if chat_id is None:
            add_support_buttons(markup)
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Ramadan settings displayed for user {call.from_user.id}, chat_id={chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_ramadan_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("hajj_eid_settings"))
def callback_hajj_eid_settings(call: types.CallbackQuery):
    """
    Handle callback for Hajj and Eid settings panel.
    Supports both old format (hajj_eid_settings) and new format (hajj_eid_settings_{chat_id})
    """
    try:
        # Extract chat_id from callback data if present
        chat_id = None
        if "_" in call.data and call.data.count("_") >= 3:
            # New format: hajj_eid_settings_{chat_id}
            parts = call.data.split("_")
            try:
                chat_id = int(parts[-1])
                # Verify user is admin of this chat
                if not is_user_admin_of_chat(call.from_user.id, chat_id):
                    bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
                    return
            except (ValueError, IndexError):
                # Fallback to old behavior
                chat_id = None
        
        # If no chat_id, verify user is admin in any group
        if chat_id is None:
            is_admin = is_user_admin_in_any_group(call.from_user.id)
            if not is_admin:
                bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
                return
        
        bot.answer_callback_query(call.id, "إعدادات الحج والعيد")
        
        # Get settings for this specific chat (or show general info)
        if chat_id:
            hajj_settings = get_hajj_eid_settings(chat_id)
            arafah_status = "✅ مفعّل" if hajj_settings.get('arafah_day_enabled', 1) else "❌ معطّل"
            eid_eve_status = "✅ مفعّل" if hajj_settings.get('eid_eve_enabled', 1) else "❌ معطّل"
            eid_day_status = "✅ مفعّل" if hajj_settings.get('eid_day_enabled', 1) else "❌ معطّل"
            eid_adha_status = "✅ مفعّل" if hajj_settings.get('eid_adha_enabled', 1) else "❌ معطّل"
            hajj_status = "✅ مفعّل" if hajj_settings.get('hajj_enabled', 1) else "❌ معطّل"
            
            settings_text = (
                "🕋 *إعدادات الحج والعيد*\n\n"
                f"*الحالة الحالية:*\n"
                f"• يوم عرفة: {arafah_status}\n"
                f"• ليلة العيد: {eid_eve_status}\n"
                f"• يوم العيد: {eid_day_status}\n"
                f"• عيد الأضحى: {eid_adha_status}\n"
                f"• أذكار الحج: {hajj_status}\n\n"
                "*أقسام الحج:*\n\n"
                "*1. يوم عرفة:*\n"
                "أدعية خاصة بيوم عرفة المبارك (9 ذو الحجة)\n"
                "خير الدعاء دعاء يوم عرفة\n\n"
                "*2. أذكار الحج:*\n"
                "التلبية وأدعية الحج والعمرة\n\n"
                "*أقسام العيد:*\n\n"
                "*1. ليلة العيد:*\n"
                "أدعية ليلة العيد المباركة\n"
                "تُرسل في ليلة 29 أو 30 رمضان\n\n"
                "*2. يوم العيد:*\n"
                "تكبيرات العيد وأدعية يوم العيد\n"
                "تُرسل في أول أيام العيد\n\n"
                "*3. عيد الأضحى:*\n"
                "تكبيرات وأدعية خاصة بعيد الأضحى (10 ذو الحجة)\n\n"
                "*التحكم:*\n"
                "استخدم الأزرار أدناه للتفعيل/التعطيل"
            )
        else:
            settings_text = (
                "🕋 *إعدادات الحج والعيد*\n\n"
                "*أقسام الحج:*\n\n"
                "*1. يوم عرفة:*\n"
                "أدعية خاصة بيوم عرفة المبارك (9 ذو الحجة)\n"
                "خير الدعاء دعاء يوم عرفة\n\n"
                "*2. أذكار الحج:*\n"
                "التلبية وأدعية الحج والعمرة\n\n"
                "*أقسام العيد:*\n\n"
                "*1. ليلة العيد:*\n"
                "أدعية ليلة العيد المباركة\n"
                "تُرسل في ليلة 29 أو 30 رمضان\n\n"
                "*2. يوم العيد:*\n"
                "تكبيرات العيد وأدعية يوم العيد\n"
                "تُرسل في أول أيام العيد\n\n"
                "*3. عيد الأضحى:*\n"
                "تكبيرات وأدعية خاصة بعيد الأضحى (10 ذو الحجة)\n\n"
                "*للتفعيل:*\n"
                "استخدم `/start` في المجموعة"
            )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        # Add toggle buttons if chat_id is specified
        if chat_id:
            hajj_settings = get_hajj_eid_settings(chat_id)
            arafah_icon = "✅" if hajj_settings.get('arafah_day_enabled', 1) else "❌"
            eid_eve_icon = "✅" if hajj_settings.get('eid_eve_enabled', 1) else "❌"
            eid_day_icon = "✅" if hajj_settings.get('eid_day_enabled', 1) else "❌"
            eid_adha_icon = "✅" if hajj_settings.get('eid_adha_enabled', 1) else "❌"
            hajj_icon = "✅" if hajj_settings.get('hajj_enabled', 1) else "❌"
            
            markup.add(
                types.InlineKeyboardButton(
                    f"{arafah_icon} يوم عرفة", 
                    callback_data=f"toggle_hajj_eid_arafah_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    f"{eid_eve_icon} ليلة العيد", 
                    callback_data=f"toggle_hajj_eid_eve_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    f"{eid_day_icon} يوم العيد", 
                    callback_data=f"toggle_hajj_eid_day_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    f"{eid_adha_icon} عيد الأضحى", 
                    callback_data=f"toggle_hajj_eid_adha_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    f"{hajj_icon} أذكار الحج", 
                    callback_data=f"toggle_hajj_eid_hajj_{chat_id}"
                )
            )
            # Add back button with chat_id encoded
            chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
            markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        else:
            markup.add(types.InlineKeyboardButton("« العودة", callback_data="open_settings"))
        
        # Only add support buttons in main settings (not group-specific)
        if chat_id is None:
            add_support_buttons(markup)
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Hajj/Eid settings displayed for user {call.from_user.id}, chat_id={chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_hajj_eid_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("fasting_reminders"))
def callback_fasting_reminders_settings(call: types.CallbackQuery):
    """
    Handle callback for fasting reminders settings panel.
    Supports both old format (fasting_reminders_settings) and new format (fasting_reminders_{chat_id})
    """
    try:
        # Extract chat_id from callback data if present
        chat_id = None
        # Check if this is the group-specific format (fasting_reminders_{chat_id})
        # vs the general settings format (fasting_reminders_settings)
        if call.data != "fasting_reminders_settings":
            # New format: fasting_reminders_{chat_id}
            parts = call.data.split("_")
            try:
                chat_id = int(parts[-1])
                # Verify user is admin of this chat
                if not is_user_admin_of_chat(call.from_user.id, chat_id):
                    bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
                    return
            except (ValueError, IndexError):
                # Fallback to old behavior
                chat_id = None
        
        # If no chat_id, verify user is admin in any group
        if chat_id is None:
            is_admin = is_user_admin_in_any_group(call.from_user.id)
            if not is_admin:
                bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
                return
        
        bot.answer_callback_query(call.id, "تذكيرات الصيام")
        
        # Get settings for this specific chat (or show general info)
        if chat_id:
            fasting_settings = get_fasting_reminders_settings(chat_id)
            monday_thursday_status = "✅ مفعّل" if fasting_settings.get('monday_thursday_enabled', 1) else "❌ معطّل"
            arafah_status = "✅ مفعّل" if fasting_settings.get('arafah_reminder_enabled', 1) else "❌ معطّل"
            reminder_time = fasting_settings.get('reminder_time', '21:00')
            
            settings_text = (
                "🌙 *تذكيرات الصيام*\n\n"
                f"*الحالة الحالية:*\n"
                f"• صيام الاثنين والخميس: {monday_thursday_status}\n"
                f"• صيام يوم عرفة: {arafah_status}\n"
                f"• وقت التذكير: {reminder_time}\n\n"
                "*تذكير بصيام الاثنين والخميس:*\n"
                "• يتم إرسال تذكير في المساء قبل يوم الصيام\n"
                "• الوقت الافتراضي: 21:00 (9 مساءً)\n"
                "• قابل للتخصيص من خلال الأمر `/setfastingtime`\n\n"
                "*فضل صيام الاثنين والخميس:*\n"
                "قال رسول الله ﷺ: \"تُعرض الأعمال يوم الاثنين والخميس، "
                "فأحب أن يُعرض عملي وأنا صائم\"\n\n"
                "*تذكير بصيام يوم عرفة:*\n"
                "• يتم إرسال تذكير في المساء قبل يوم عرفة\n"
                "• يوم عرفة هو التاسع من ذي الحجة\n\n"
                "*فضل صيام يوم عرفة:*\n"
                "قال رسول الله ﷺ: \"صيام يوم عرفة، أحتسب على الله أن يكفر "
                "السنة التي قبله، والسنة التي بعده\"\n\n"
                "*التحكم:*\n"
                "استخدم الأزرار أدناه للتفعيل/التعطيل"
            )
        else:
            settings_text = (
                "🌙 *تذكيرات الصيام*\n\n"
                "*تذكير بصيام الاثنين والخميس:*\n"
                "• يتم إرسال تذكير في المساء قبل يوم الصيام\n"
                "• الوقت الافتراضي: 21:00 (9 مساءً)\n"
                "• قابل للتخصيص من خلال الأمر `/setfastingtime`\n\n"
                "*فضل صيام الاثنين والخميس:*\n"
                "قال رسول الله ﷺ: \"تُعرض الأعمال يوم الاثنين والخميس، "
                "فأحب أن يُعرض عملي وأنا صائم\"\n\n"
                "*تذكير بصيام يوم عرفة:*\n"
                "• يتم إرسال تذكير في المساء قبل يوم عرفة\n"
                "• يوم عرفة هو التاسع من ذي الحجة\n\n"
                "*فضل صيام يوم عرفة:*\n"
                "قال رسول الله ﷺ: \"صيام يوم عرفة، أحتسب على الله أن يكفر "
                "السنة التي قبله، والسنة التي بعده\"\n\n"
                "*لتخصيص وقت التذكير:*\n"
                "استخدم الأمر في المجموعة:\n"
                "`/setfastingtime HH:MM`\n\n"
                "*مثال:*\n"
                "`/setfastingtime 20:00`\n\n"
                "*للتفعيل في مجموعة:*\n"
                "سيتم إضافة خيارات التفعيل/التعطيل في القائمة أدناه"
            )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        # Add toggle buttons if chat_id is specified
        if chat_id:
            fasting_settings = get_fasting_reminders_settings(chat_id)
            monday_thursday_icon = "✅" if fasting_settings.get('monday_thursday_enabled', 1) else "❌"
            arafah_icon = "✅" if fasting_settings.get('arafah_reminder_enabled', 1) else "❌"
            
            markup.add(
                types.InlineKeyboardButton(
                    f"{monday_thursday_icon} تذكير صيام الاثنين والخميس", 
                    callback_data=f"toggle_fasting_monday_thursday_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    f"{arafah_icon} تذكير صيام يوم عرفة", 
                    callback_data=f"toggle_fasting_arafah_{chat_id}"
                )
            )
            
            # Add time preset button
            markup.add(
                types.InlineKeyboardButton("⏰ أوقات شائعة للتذكير", callback_data=f"fasting_time_presets_{chat_id}")
            )
            
            # Add back button with chat_id encoded
            chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
            markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        else:
            markup.add(
                types.InlineKeyboardButton("⏰ أوقات شائعة للتذكير", callback_data="fasting_time_presets"),
                types.InlineKeyboardButton("« العودة", callback_data="open_settings")
            )
        
        # Only add support buttons in main settings (not group-specific)
        if chat_id is None:
            add_support_buttons(markup)
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Fasting reminders settings displayed for user {call.from_user.id}, chat_id={chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_fasting_reminders_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data == "fasting_time_presets")
def callback_fasting_time_presets(call: types.CallbackQuery):
    """Show preset times for fasting reminders as information."""
    try:
        is_admin = is_user_admin_in_any_group(call.from_user.id)
        
        if not is_admin:
            bot.answer_callback_query(call.id, "⚠️ يجب أن تكون مشرفًا", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "أوقات شائعة للتذكير")
        
        settings_text = (
            "⏰ *أوقات شائعة لتذكير الصيام*\n\n"
            "*الأوقات المقترحة:*\n"
            "• 20:00 - مساءً (بعد العشاء)\n"
            "• 21:00 - الافتراضي\n"
            "• 22:00 - قبل النوم\n"
            "• 23:00 - ليلاً\n\n"
            "*ملاحظة:*\n"
            "يُرسل التذكير في المساء قبل يوم الصيام:\n"
            "• الأحد مساءً → تذكير بصيام الإثنين\n"
            "• الأربعاء مساءً → تذكير بصيام الخميس\n\n"
            "*لتخصيص الوقت:*\n"
            "استخدم الأمر في المجموعة:\n"
            "`/setfastingtime HH:MM`\n\n"
            "*مثال:*\n"
            "`/setfastingtime 20:30`"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("« العودة", callback_data="fasting_reminders_settings")
        )
        
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in callback_fasting_time_presets: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data == "group_diverse_settings")
def callback_group_diverse_settings(call: types.CallbackQuery):
    """
    Handle diverse azkar settings for a specific group.
    """
    try:
        chat_id = call.message.chat.id
        
        if not bot.get_chat_member(chat_id, call.from_user.id).status in ["administrator", "creator"]:
            bot.answer_callback_query(call.id, "هذا متاح للمشرفين فقط", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "إعدادات الأدعية المتنوعة")
        
        diverse_settings = get_diverse_azkar_settings(chat_id)
        
        settings_text = (
            "✨ *إعدادات الأدعية المتنوعة*\n\n"
            f"الحالة: {'🟢 مفعّل' if diverse_settings['enabled'] else '🔴 معطّل'}\n"
            f"الفاصل الزمني: {diverse_settings['interval_minutes']} دقيقة\n\n"
            "*اختر الفاصل الزمني:*"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("1 دقيقة", callback_data="set_diverse_1"),
            types.InlineKeyboardButton("5 دقائق", callback_data="set_diverse_5"),
            types.InlineKeyboardButton("15 دقيقة", callback_data="set_diverse_15"),
            types.InlineKeyboardButton("1 ساعة", callback_data="set_diverse_60"),
            types.InlineKeyboardButton("2 ساعة", callback_data="set_diverse_120"),
            types.InlineKeyboardButton("4 ساعات", callback_data="set_diverse_240"),
            types.InlineKeyboardButton("8 ساعات", callback_data="set_diverse_480"),
            types.InlineKeyboardButton("12 ساعة", callback_data="set_diverse_720"),
            types.InlineKeyboardButton("24 ساعة", callback_data="set_diverse_1440")
        )
        
        toggle_text = "⏸ تعطيل" if diverse_settings['enabled'] else "▶️ تفعيل"
        markup.add(types.InlineKeyboardButton(toggle_text, callback_data="toggle_diverse_enabled"))
        
        bot.edit_message_text(
            settings_text,
            chat_id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Group diverse settings displayed for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_group_diverse_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_diverse_"))
def callback_set_diverse_interval(call: types.CallbackQuery):
    """
    Set diverse azkar interval for a group.
    """
    try:
        chat_id = call.message.chat.id
        
        if not bot.get_chat_member(chat_id, call.from_user.id).status in ["administrator", "creator"]:
            bot.answer_callback_query(call.id, "هذا متاح للمشرفين فقط", show_alert=True)
            return
        
        interval_minutes = int(call.data.replace("set_diverse_", ""))
        
        update_diverse_azkar_setting(chat_id, "interval_minutes", interval_minutes)
        update_diverse_azkar_setting(chat_id, "enabled", 1)  # Auto-enable when selecting interval
        schedule_chat_jobs(chat_id)
        
        bot.answer_callback_query(call.id, f"✓ تم تعيين الفاصل الزمني: {interval_minutes} دقيقة")
        
        # Refresh the settings view
        callback_group_diverse_settings(call)
        
    except Exception as e:
        logger.error(f"Error in callback_set_diverse_interval: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "toggle_diverse_enabled")
def callback_toggle_diverse_enabled(call: types.CallbackQuery):
    """
    Toggle diverse azkar enabled status for a group.
    """
    try:
        chat_id = call.message.chat.id
        
        if not bot.get_chat_member(chat_id, call.from_user.id).status in ["administrator", "creator"]:
            bot.answer_callback_query(call.id, "هذا متاح للمشرفين فقط", show_alert=True)
            return
        
        diverse_settings = get_diverse_azkar_settings(chat_id)
        new_value = not diverse_settings["enabled"]
        
        update_diverse_azkar_setting(chat_id, "enabled", new_value)
        schedule_chat_jobs(chat_id)
        
        status_text = "تم التفعيل" if new_value else "تم التعطيل"
        bot.answer_callback_query(call.id, f"✓ {status_text}")
        
        # Refresh the settings view
        callback_group_diverse_settings(call)
        
    except Exception as e:
        logger.error(f"Error in callback_toggle_diverse_enabled: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "group_ramadan_settings")
def callback_group_ramadan_settings(call: types.CallbackQuery):
    """
    Handle Ramadan settings for a specific group.
    """
    try:
        chat_id = call.message.chat.id
        
        if not bot.get_chat_member(chat_id, call.from_user.id).status in ["administrator", "creator"]:
            bot.answer_callback_query(call.id, "هذا متاح للمشرفين فقط", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "إعدادات رمضان")
        
        ramadan_settings = get_ramadan_settings(chat_id)
        
        settings_text = (
            "🌙 *إعدادات رمضان*\n\n"
            "قم بتفعيل أو تعطيل الأقسام المختلفة:"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        ramadan_btns = [
            ("ramadan_enabled", "🌙 أذكار رمضان"),
            ("laylat_alqadr_enabled", "✨ ليلة القدر"),
            ("last_ten_days_enabled", "📿 العشر الأواخر"),
            ("iftar_dua_enabled", "🍽️ دعاء الإفطار")
        ]
        
        for key, label in ramadan_btns:
            status = "✅" if ramadan_settings[key] else "❌"
            markup.add(types.InlineKeyboardButton(f"{label} {status}", callback_data=f"toggle_ramadan_{key}"))
        
        bot.edit_message_text(
            settings_text,
            chat_id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Group Ramadan settings displayed for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_group_ramadan_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_ramadan_"))
def callback_toggle_ramadan(call: types.CallbackQuery):
    """
    Toggle Ramadan setting for a group.
    Supports both in-group format (toggle_ramadan_{key}) and private chat format (toggle_ramadan_{key}_{chat_id})
    """
    try:
        # Parse callback data to extract key and possibly chat_id
        parts = call.data.replace("toggle_ramadan_", "").split("_")
        
        # Validate parts is not empty
        if not parts or not parts[0]:
            logger.error(f"Invalid callback data format: {call.data}")
            bot.answer_callback_query(call.id, "❌ خطأ في البيانات")
            return
        
        # Check if chat_id is in the callback data (private chat with group context)
        chat_id = None
        setting_key = None
        
        if len(parts) >= 2:
            # Try to parse last part as chat_id
            try:
                chat_id = int(parts[-1])
                # The key is everything except the last part (chat_id)
                setting_key = "_".join(parts[:-1])
            except ValueError:
                # Last part is not a number, so it's part of the key
                chat_id = call.message.chat.id
                setting_key = "_".join(parts)
        else:
            # Single part - use as key, chat_id from message
            chat_id = call.message.chat.id
            setting_key = parts[0]
        
        # Map common keys to database column names
        key_mapping = {
            "enabled": "ramadan_enabled",
            "laylat_alqadr": "laylat_alqadr_enabled",
            "last_ten": "last_ten_days_enabled",
            "iftar": "iftar_dua_enabled"
        }
        db_key = key_mapping.get(setting_key, setting_key)
        
        # Verify user is admin
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        # Get current settings and toggle
        ramadan_settings = get_ramadan_settings(chat_id)
        new_value = not ramadan_settings.get(db_key, 1)
        
        update_ramadan_setting(chat_id, db_key, new_value)
        
        # Prepare updated message with current status
        ramadan_settings = get_ramadan_settings(chat_id)
        ramadan_status = "✅ مفعّل" if ramadan_settings.get('ramadan_enabled', 1) else "❌ معطّل"
        laylat_alqadr_status = "✅ مفعّل" if ramadan_settings.get('laylat_alqadr_enabled', 1) else "❌ معطّل"
        last_ten_status = "✅ مفعّل" if ramadan_settings.get('last_ten_days_enabled', 1) else "❌ معطّل"
        iftar_status = "✅ مفعّل" if ramadan_settings.get('iftar_dua_enabled', 1) else "❌ معطّل"
        
        settings_text = (
            "🌙 *إعدادات رمضان*\n\n"
            f"*الحالة الحالية:*\n"
            f"• أدعية رمضان: {ramadan_status}\n"
            f"• ليلة القدر: {laylat_alqadr_status}\n"
            f"• العشر الأواخر: {last_ten_status}\n"
            f"• دعاء الإفطار: {iftar_status}\n\n"
            "*الأقسام المتاحة:*\n\n"
            "*1. ليلة القدر:*\n"
            "أدعية خاصة بليلة القدر المباركة\n"
            "يتم إرسالها في الليالي الوترية من العشر الأواخر\n\n"
            "*2. العشر الأواخر من رمضان:*\n"
            "أذكار وأدعية خاصة بالعشر الأواخر\n"
            "تبدأ من اليوم 21 من رمضان\n\n"
            "*3. دعاء الإفطار:*\n"
            "يتم إرسال دعاء الإفطار قبل أذان المغرب\n\n"
            "*التحكم:*\n"
            "استخدم الأزرار أدناه للتفعيل/التعطيل"
        )
        
        # Update markup with new status
        markup = types.InlineKeyboardMarkup(row_width=1)
        ramadan_icon = "✅" if ramadan_settings.get('ramadan_enabled', 1) else "❌"
        laylat_alqadr_icon = "✅" if ramadan_settings.get('laylat_alqadr_enabled', 1) else "❌"
        last_ten_icon = "✅" if ramadan_settings.get('last_ten_days_enabled', 1) else "❌"
        iftar_icon = "✅" if ramadan_settings.get('iftar_dua_enabled', 1) else "❌"
        
        markup.add(
            types.InlineKeyboardButton(
                f"{ramadan_icon} أدعية رمضان", 
                callback_data=f"toggle_ramadan_enabled_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{laylat_alqadr_icon} ليلة القدر", 
                callback_data=f"toggle_ramadan_laylat_alqadr_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{last_ten_icon} العشر الأواخر", 
                callback_data=f"toggle_ramadan_last_ten_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{iftar_icon} دعاء الإفطار", 
                callback_data=f"toggle_ramadan_iftar_{chat_id}"
            )
        )
        
        # Add back button
        chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
        markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        
        # Edit message with updated status
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        # Answer callback with confirmation
        status_text = "تم التفعيل ✅" if new_value else "تم التعطيل ❌"
        setting_names = {
            "enabled": "أدعية رمضان",
            "laylat_alqadr": "ليلة القدر",
            "last_ten": "العشر الأواخر",
            "iftar": "دعاء الإفطار"
        }
        setting_name = setting_names.get(setting_key, setting_key)
        bot.answer_callback_query(call.id, f"{setting_name}: {status_text}")
        
        logger.info(f"User {call.from_user.id} toggled {db_key} to {new_value} for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_toggle_ramadan: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data == "group_hajj_eid_settings")
def callback_group_hajj_eid_settings(call: types.CallbackQuery):
    """
    Handle Hajj and Eid settings for a specific group.
    """
    try:
        chat_id = call.message.chat.id
        
        if not bot.get_chat_member(chat_id, call.from_user.id).status in ["administrator", "creator"]:
            bot.answer_callback_query(call.id, "هذا متاح للمشرفين فقط", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "إعدادات الحج والعيد")
        
        hajj_eid_settings = get_hajj_eid_settings(chat_id)
        
        settings_text = (
            "🕋 *إعدادات الحج والعيد*\n\n"
            "قم بتفعيل أو تعطيل الأقسام المختلفة:"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        hajj_eid_btns = [
            ("arafah_day_enabled", "🕋 يوم عرفة"),
            ("hajj_enabled", "🕋 أذكار الحج"),
            ("eid_eve_enabled", "🌙 ليلة العيد"),
            ("eid_day_enabled", "🎉 يوم العيد"),
            ("eid_adha_enabled", "🐑 عيد الأضحى")
        ]
        
        for key, label in hajj_eid_btns:
            status = "✅" if hajj_eid_settings[key] else "❌"
            markup.add(types.InlineKeyboardButton(f"{label} {status}", callback_data=f"toggle_hajj_eid_{key}"))
        
        bot.edit_message_text(
            settings_text,
            chat_id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Group Hajj/Eid settings displayed for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_group_hajj_eid_settings: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_hajj_eid_"))
def callback_toggle_hajj_eid(call: types.CallbackQuery):
    """
    Toggle Hajj/Eid setting for a group.
    Supports both in-group format (toggle_hajj_eid_{key}) and private chat format (toggle_hajj_eid_{key}_{chat_id})
    """
    try:
        # Parse callback data to extract key and possibly chat_id
        parts = call.data.replace("toggle_hajj_eid_", "").split("_")
        
        # Validate parts is not empty
        if not parts or not parts[0]:
            logger.error(f"Invalid callback data format: {call.data}")
            bot.answer_callback_query(call.id, "❌ خطأ في البيانات")
            return
        
        # Check if chat_id is in the callback data (private chat with group context)
        chat_id = None
        setting_key = None
        
        if len(parts) >= 2:
            # Try to parse last part as chat_id
            try:
                chat_id = int(parts[-1])
                # The key is everything except the last part (chat_id)
                setting_key = "_".join(parts[:-1])
            except ValueError:
                # Last part is not a number, so it's part of the key
                chat_id = call.message.chat.id
                setting_key = "_".join(parts)
        else:
            # Single part - use as key, chat_id from message
            chat_id = call.message.chat.id
            setting_key = parts[0]
        
        # Map common keys to database column names
        key_mapping = {
            "arafah": "arafah_day_enabled",
            "eve": "eid_eve_enabled",
            "day": "eid_day_enabled",
            "adha": "eid_adha_enabled",
            "hajj": "hajj_enabled"
        }
        db_key = key_mapping.get(setting_key, setting_key)
        
        # Verify user is admin
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        # Get current settings and toggle
        hajj_eid_settings = get_hajj_eid_settings(chat_id)
        new_value = not hajj_eid_settings.get(db_key, 1)
        
        update_hajj_eid_setting(chat_id, db_key, new_value)
        
        # Prepare updated message with current status
        hajj_settings = get_hajj_eid_settings(chat_id)
        arafah_status = "✅ مفعّل" if hajj_settings.get('arafah_day_enabled', 1) else "❌ معطّل"
        eid_eve_status = "✅ مفعّل" if hajj_settings.get('eid_eve_enabled', 1) else "❌ معطّل"
        eid_day_status = "✅ مفعّل" if hajj_settings.get('eid_day_enabled', 1) else "❌ معطّل"
        eid_adha_status = "✅ مفعّل" if hajj_settings.get('eid_adha_enabled', 1) else "❌ معطّل"
        hajj_status = "✅ مفعّل" if hajj_settings.get('hajj_enabled', 1) else "❌ معطّل"
        
        settings_text = (
            "🕋 *إعدادات الحج والعيد*\n\n"
            f"*الحالة الحالية:*\n"
            f"• يوم عرفة: {arafah_status}\n"
            f"• ليلة العيد: {eid_eve_status}\n"
            f"• يوم العيد: {eid_day_status}\n"
            f"• عيد الأضحى: {eid_adha_status}\n"
            f"• أذكار الحج: {hajj_status}\n\n"
            "*أقسام الحج:*\n\n"
            "*1. يوم عرفة:*\n"
            "أدعية خاصة بيوم عرفة المبارك (9 ذو الحجة)\n"
            "خير الدعاء دعاء يوم عرفة\n\n"
            "*2. أذكار الحج:*\n"
            "التلبية وأدعية الحج والعمرة\n\n"
            "*أقسام العيد:*\n\n"
            "*1. ليلة العيد:*\n"
            "أدعية ليلة العيد المباركة\n"
            "تُرسل في ليلة 29 أو 30 رمضان\n\n"
            "*2. يوم العيد:*\n"
            "تكبيرات العيد وأدعية يوم العيد\n"
            "تُرسل في أول أيام العيد\n\n"
            "*3. عيد الأضحى:*\n"
            "تكبيرات وأدعية خاصة بعيد الأضحى (10 ذو الحجة)\n\n"
            "*التحكم:*\n"
            "استخدم الأزرار أدناه للتفعيل/التعطيل"
        )
        
        # Update markup with new status
        markup = types.InlineKeyboardMarkup(row_width=1)
        arafah_icon = "✅" if hajj_settings.get('arafah_day_enabled', 1) else "❌"
        eid_eve_icon = "✅" if hajj_settings.get('eid_eve_enabled', 1) else "❌"
        eid_day_icon = "✅" if hajj_settings.get('eid_day_enabled', 1) else "❌"
        eid_adha_icon = "✅" if hajj_settings.get('eid_adha_enabled', 1) else "❌"
        hajj_icon = "✅" if hajj_settings.get('hajj_enabled', 1) else "❌"
        
        markup.add(
            types.InlineKeyboardButton(
                f"{arafah_icon} يوم عرفة", 
                callback_data=f"toggle_hajj_eid_arafah_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{eid_eve_icon} ليلة العيد", 
                callback_data=f"toggle_hajj_eid_eve_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{eid_day_icon} يوم العيد", 
                callback_data=f"toggle_hajj_eid_day_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{eid_adha_icon} عيد الأضحى", 
                callback_data=f"toggle_hajj_eid_adha_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{hajj_icon} أذكار الحج", 
                callback_data=f"toggle_hajj_eid_hajj_{chat_id}"
            )
        )
        
        # Add back button
        chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
        markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        
        # Edit message with updated status
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        # Answer callback with confirmation
        status_text = "تم التفعيل ✅" if new_value else "تم التعطيل ❌"
        setting_names = {
            "arafah": "يوم عرفة",
            "eve": "ليلة العيد",
            "day": "يوم العيد",
            "adha": "عيد الأضحى",
            "hajj": "أذكار الحج"
        }
        setting_name = setting_names.get(setting_key, setting_key)
        bot.answer_callback_query(call.id, f"{setting_name}: {status_text}")
        
        logger.info(f"User {call.from_user.id} toggled {db_key} to {new_value} for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_toggle_hajj_eid: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data == "group_fasting_reminders")
def callback_group_fasting_reminders(call: types.CallbackQuery):
    """
    Handle fasting reminders settings for a specific group.
    """
    try:
        chat_id = call.message.chat.id
        
        if not bot.get_chat_member(chat_id, call.from_user.id).status in ["administrator", "creator"]:
            bot.answer_callback_query(call.id, "هذا متاح للمشرفين فقط", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "تذكيرات الصيام")
        
        fasting_settings = get_fasting_reminders_settings(chat_id)
        
        settings_text = (
            "🌙 *تذكيرات الصيام*\n\n"
            f"وقت التذكير: {fasting_settings['reminder_time']}\n\n"
            "قم بتفعيل أو تعطيل التذكيرات المطلوبة:"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        fasting_btns = [
            ("monday_thursday_enabled", "🌙 تذكير صيام الاثنين والخميس"),
            ("arafah_reminder_enabled", "🕋 تذكير صيام يوم عرفة")
        ]
        
        for key, label in fasting_btns:
            status = "✅" if fasting_settings[key] else "❌"
            markup.add(types.InlineKeyboardButton(f"{label} {status}", callback_data=f"toggle_fasting_{key}"))
        
        bot.edit_message_text(
            settings_text,
            chat_id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        logger.info(f"Group fasting reminders settings displayed for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_group_fasting_reminders: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_fasting_"))
def callback_toggle_fasting(call: types.CallbackQuery):
    """
    Toggle fasting reminder setting for a group.
    Supports both in-group format (toggle_fasting_{key}) and private chat format (toggle_fasting_{key}_{chat_id})
    """
    try:
        # Parse callback data to extract key and possibly chat_id
        parts = call.data.replace("toggle_fasting_", "").split("_")
        
        # Validate parts is not empty
        if not parts or not parts[0]:
            logger.error(f"Invalid callback data format: {call.data}")
            bot.answer_callback_query(call.id, "❌ خطأ في البيانات")
            return
        
        # Check if chat_id is in the callback data (private chat with group context)
        chat_id = None
        setting_key = None
        
        if len(parts) >= 2:
            # Try to parse last part as chat_id
            try:
                chat_id = int(parts[-1])
                # The key is everything except the last part (chat_id)
                setting_key = "_".join(parts[:-1])
            except ValueError:
                # Last part is not a number, so it's part of the key
                chat_id = call.message.chat.id
                setting_key = "_".join(parts)
        else:
            # Single part - use as key, chat_id from message
            chat_id = call.message.chat.id
            setting_key = parts[0]
        
        # Map common keys to database column names
        key_mapping = {
            "monday_thursday": "monday_thursday_enabled",
            "arafah": "arafah_reminder_enabled"
        }
        db_key = key_mapping.get(setting_key, setting_key)
        
        # Verify user is admin
        if not is_user_admin_of_chat(call.from_user.id, chat_id):
            bot.answer_callback_query(call.id, "⚠️ لست مشرفًا في هذه المجموعة", show_alert=True)
            return
        
        # Get current settings and toggle
        fasting_settings = get_fasting_reminders_settings(chat_id)
        new_value = not fasting_settings.get(db_key, 1)
        
        update_fasting_reminder_setting(chat_id, db_key, new_value)
        schedule_chat_jobs(chat_id)
        
        # Prepare updated message with current status
        fasting_settings = get_fasting_reminders_settings(chat_id)
        monday_thursday_status = "✅ مفعّل" if fasting_settings.get('monday_thursday_enabled', 1) else "❌ معطّل"
        arafah_status = "✅ مفعّل" if fasting_settings.get('arafah_reminder_enabled', 1) else "❌ معطّل"
        reminder_time = fasting_settings.get('reminder_time', '21:00')
        
        settings_text = (
            "🌙 *تذكيرات الصيام*\n\n"
            f"*الحالة الحالية:*\n"
            f"• صيام الاثنين والخميس: {monday_thursday_status}\n"
            f"• صيام يوم عرفة: {arafah_status}\n"
            f"• وقت التذكير: {reminder_time}\n\n"
            "*تذكير بصيام الاثنين والخميس:*\n"
            "• يتم إرسال تذكير في المساء قبل يوم الصيام\n"
            "• الوقت الافتراضي: 21:00 (9 مساءً)\n"
            "• قابل للتخصيص من خلال الأمر `/setfastingtime`\n\n"
            "*فضل صيام الاثنين والخميس:*\n"
            "قال رسول الله ﷺ: \"تُعرض الأعمال يوم الاثنين والخميس، "
            "فأحب أن يُعرض عملي وأنا صائم\"\n\n"
            "*تذكير بصيام يوم عرفة:*\n"
            "• يتم إرسال تذكير في المساء قبل يوم عرفة\n"
            "• يوم عرفة هو التاسع من ذي الحجة\n\n"
            "*فضل صيام يوم عرفة:*\n"
            "قال رسول الله ﷺ: \"صيام يوم عرفة، أحتسب على الله أن يكفر "
            "السنة التي قبله، والسنة التي بعده\"\n\n"
            "*التحكم:*\n"
            "استخدم الأزرار أدناه للتفعيل/التعطيل"
        )
        
        # Update markup with new status
        markup = types.InlineKeyboardMarkup(row_width=1)
        monday_thursday_icon = "✅" if fasting_settings.get('monday_thursday_enabled', 1) else "❌"
        arafah_icon = "✅" if fasting_settings.get('arafah_reminder_enabled', 1) else "❌"
        
        markup.add(
            types.InlineKeyboardButton(
                f"{monday_thursday_icon} تذكير صيام الاثنين والخميس", 
                callback_data=f"toggle_fasting_monday_thursday_{chat_id}"
            ),
            types.InlineKeyboardButton(
                f"{arafah_icon} تذكير صيام يوم عرفة", 
                callback_data=f"toggle_fasting_arafah_{chat_id}"
            )
        )
        
        # Add time preset button
        markup.add(
            types.InlineKeyboardButton("⏰ أوقات شائعة للتذكير", callback_data=f"fasting_time_presets_{chat_id}")
        )
        
        # Add back button
        chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
        markup.add(types.InlineKeyboardButton("« العودة", callback_data=f"select_group_{chat_id_encoded}"))
        
        # Edit message with updated status
        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        # Answer callback with confirmation
        status_text = "تم التفعيل ✅" if new_value else "تم التعطيل ❌"
        setting_name = "صيام الاثنين والخميس" if setting_key == "monday_thursday" else "صيام يوم عرفة"
        bot.answer_callback_query(call.id, f"{setting_name}: {status_text}")
        
        logger.info(f"User {call.from_user.id} toggled {db_key} to {new_value} for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in callback_toggle_fasting: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "حدث خطأ", show_alert=True)
        except Exception:
            pass

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
        f"🌅 أذكار الصباح: {'✅' if settings['morning_azkar'] else '❌'}\n"
        f"🌙 أذكار المساء: {'✅' if settings['evening_azkar'] else '❌'}\n"
        f"📿 سورة الكهف: {'✅' if settings['friday_sura'] else '❌'}\n"
        f"🕌 أدعية الجمعة: {'✅' if settings['friday_dua'] else '❌'}\n"
        f"😴 رسالة النوم: {'✅' if settings['sleep_message'] else '❌'}\n"
        f"🗑️ حذف رسائل الخدمة: {'✅' if settings['delete_service_messages'] else '❌'}\n\n"
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

@bot.message_handler(commands=["settime"])
def cmd_settime(message: types.Message):
    """
    Set custom time for azkar sending.
    Usage: /settime <type> <time>
    Example: /settime morning 06:00
    """
    if message.chat.type == "private":
        bot.send_message(message.chat.id, "⚠️ هذا الأمر يعمل فقط في المجموعات")
        return

    if not bot.get_chat_member(message.chat.id, message.from_user.id).status in ["administrator", "creator"]:
        bot.send_message(message.chat.id, "⚠️ هذا الأمر متاح للمشرفين فقط")
        return

    try:
        # Parse command arguments
        parts = message.text.split()
        if len(parts) != 3:
            bot.send_message(
                message.chat.id,
                "⚠️ *الاستخدام الصحيح:*\n"
                "`/settime <نوع> <وقت>`\n\n"
                "*الأنواع المتاحة:*\n"
                "• `morning` - أذكار الصباح\n"
                "• `evening` - أذكار المساء\n"
                "• `sleep` - رسالة النوم\n\n"
                "*مثال:*\n"
                "`/settime morning 06:00`",
                parse_mode="Markdown"
            )
            return

        azkar_type = parts[1].lower()
        time_str = parts[2]

        # Validate type
        valid_types = {
            "morning": "morning_time",
            "evening": "evening_time",
            "sleep": "sleep_time"
        }

        if azkar_type not in valid_types:
            bot.send_message(
                message.chat.id,
                f"⚠️ نوع غير صحيح: `{azkar_type}`\n"
                "الأنواع المتاحة: morning, evening, sleep",
                parse_mode="Markdown"
            )
            return

        # Validate time format
        try:
            hour, minute = map(int, time_str.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time range")
        except (ValueError, IndexError):
            bot.send_message(
                message.chat.id,
                "⚠️ صيغة الوقت غير صحيحة\n"
                "استخدم الصيغة: `HH:MM` (مثال: `06:30`)",
                parse_mode="Markdown"
            )
            return

        # Update setting
        setting_key = valid_types[azkar_type]
        update_chat_setting(message.chat.id, setting_key, time_str)
        schedule_chat_jobs(message.chat.id)

        type_names = {
            "morning": "أذكار الصباح",
            "evening": "أذكار المساء",
            "sleep": "رسالة النوم"
        }

        bot.send_message(
            message.chat.id,
            f"✅ تم تحديث وقت {type_names[azkar_type]} إلى `{time_str}`",
            parse_mode="Markdown"
        )
        logger.info(f"Time updated for {azkar_type} in chat {message.chat.id}: {time_str}")

    except Exception as e:
        logger.error(f"Error in cmd_settime: {e}", exc_info=True)
        bot.send_message(message.chat.id, "حدث خطأ أثناء تحديث الوقت")

@bot.message_handler(commands=["setfastingtime"])
def cmd_setfastingtime(message: types.Message):
    """
    Set custom time for fasting reminders.
    Usage: /setfastingtime <time>
    Example: /setfastingtime 20:00
    """
    if message.chat.type == "private":
        bot.send_message(message.chat.id, "⚠️ هذا الأمر يعمل فقط في المجموعات")
        return

    if not bot.get_chat_member(message.chat.id, message.from_user.id).status in ["administrator", "creator"]:
        bot.send_message(message.chat.id, "⚠️ هذا الأمر متاح للمشرفين فقط")
        return

    try:
        # Parse command arguments
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(
                message.chat.id,
                "⚠️ *الاستخدام الصحيح:*\n"
                "`/setfastingtime <وقت>`\n\n"
                "*مثال:*\n"
                "`/setfastingtime 20:00`\n\n"
                "*ملاحظة:*\n"
                "سيتم إرسال التذكير في المساء قبل يوم الصيام",
                parse_mode="Markdown"
            )
            return

        time_str = parts[1]

        # Validate time format
        try:
            hour, minute = map(int, time_str.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time range")
        except (ValueError, IndexError):
            bot.send_message(
                message.chat.id,
                "⚠️ صيغة الوقت غير صحيحة\n"
                "استخدم الصيغة: `HH:MM` (مثال: `20:30`)",
                parse_mode="Markdown"
            )
            return

        # Update setting
        update_fasting_reminder_setting(message.chat.id, "reminder_time", time_str)
        schedule_chat_jobs(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ تم تحديث وقت تذكير الصيام إلى `{time_str}`\n\n"
            "سيتم إرسال التذكير:\n"
            "• الأحد مساءً للتذكير بصيام الإثنين\n"
            "• الأربعاء مساءً للتذكير بصيام الخميس",
            parse_mode="Markdown"
        )
        logger.info(f"Fasting reminder time updated in chat {message.chat.id}: {time_str}")

    except Exception as e:
        logger.error(f"Error in cmd_setfastingtime: {e}", exc_info=True)
        bot.send_message(message.chat.id, "حدث خطأ أثناء تحديث الوقت")

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
    
    # Schedule jobs for all enabled chats on startup
    # This fixes the issue where diverse azkar and other scheduled jobs don't run after restart
    logger.info("🔄 Initializing scheduled jobs for all enabled chats...")
    schedule_all_chats()
    logger.info("✅ All chat jobs initialized successfully")
    
except Exception as e:
    logger.critical(f"❌ Critical error during initial webhook setup: {e}", exc_info=True)

# ────────────────────────────────────────────────
#               Local Development Only
# ────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Running in local development mode")
    bot.remove_webhook()
    app.run(host="0.0.0.0", port=PORT, debug=True)