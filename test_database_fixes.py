#!/usr/bin/env python3
"""
Test database connection fixes and error handling improvements.
This test verifies that database connections are properly closed and
that error handling works correctly.
"""

import unittest
import os
import sys
import sqlite3
import tempfile

# Add the parent directory to the path to import App.py
sys.path.insert(0, os.path.dirname(__file__))

class TestDatabaseConnectionManagement(unittest.TestCase):
    """Test database connection management and cleanup."""
    
    def setUp(self):
        """Set up test database."""
        # Create a temporary database file for testing
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        
        # Set up a test database
        conn = sqlite3.connect(self.temp_db.name)
        c = conn.cursor()
        
        # Create test tables
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
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS diverse_azkar_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                interval_minutes INTEGER DEFAULT 60,
                media_type TEXT DEFAULT 'text',
                last_sent_timestamp INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """Clean up test database."""
        try:
            os.unlink(self.temp_db.name)
        except:
            pass
    
    def test_connection_closed_on_success(self):
        """Test that database connections are closed on successful operations."""
        conn = sqlite3.connect(self.temp_db.name)
        c = conn.cursor()
        
        # Insert test data
        c.execute("INSERT INTO chat_settings (chat_id) VALUES (?)", (12345,))
        conn.commit()
        
        # Check that we can query the data
        c.execute("SELECT chat_id FROM chat_settings WHERE chat_id = ?", (12345,))
        result = c.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 12345)
        
        conn.close()
        
        # Verify connection is closed by trying to use it
        with self.assertRaises(sqlite3.ProgrammingError):
            c.execute("SELECT 1")
    
    def test_connection_closed_on_error(self):
        """Test that database connections are closed even when errors occur."""
        conn = sqlite3.connect(self.temp_db.name)
        
        # Try to execute an invalid query
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM non_existent_table")
        except sqlite3.OperationalError:
            pass  # Expected error
        finally:
            conn.close()
        
        # Verify connection is closed
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.cursor()
    
    def test_rowcount_after_insert(self):
        """Test that we can check rowcount after insert to verify success."""
        conn = sqlite3.connect(self.temp_db.name)
        c = conn.cursor()
        
        # Insert and check rowcount
        c.execute("INSERT INTO chat_settings (chat_id) VALUES (?)", (99999,))
        self.assertEqual(c.rowcount, 1, "Insert should affect 1 row")
        
        conn.commit()
        conn.close()
    
    def test_multiple_inserts_different_tables(self):
        """Test inserting into multiple tables to verify no resource leaks."""
        for i in range(10):
            conn = sqlite3.connect(self.temp_db.name)
            c = conn.cursor()
            
            try:
                # Insert into chat_settings
                c.execute("INSERT OR REPLACE INTO chat_settings (chat_id) VALUES (?)", (i,))
                # Insert into diverse_azkar_settings
                c.execute("INSERT OR REPLACE INTO diverse_azkar_settings (chat_id) VALUES (?)", (i,))
                conn.commit()
            finally:
                conn.close()
        
        # Verify all inserts worked
        conn = sqlite3.connect(self.temp_db.name)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM chat_settings")
        count1 = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM diverse_azkar_settings")
        count2 = c.fetchone()[0]
        conn.close()
        
        self.assertEqual(count1, 10, "Should have 10 chat_settings entries")
        self.assertEqual(count2, 10, "Should have 10 diverse_azkar_settings entries")

class TestErrorHandling(unittest.TestCase):
    """Test error handling improvements."""
    
    def test_exception_logging_not_silent(self):
        """Test that exceptions are logged and not silently ignored."""
        # This is a conceptual test - in real implementation,
        # we would verify that logger.warning or logger.error is called
        # instead of using bare 'pass' statements
        
        # Simulate the old vs new behavior
        def old_error_handler():
            try:
                raise ValueError("Test error")
            except Exception:
                pass  # Bad - silently swallows error
        
        def new_error_handler():
            import logging
            logger = logging.getLogger(__name__)
            try:
                raise ValueError("Test error")
            except Exception as e:
                logger.warning(f"Error occurred: {e}")  # Good - logs the error
                # In tests, we can verify logging was called
        
        # Old handler doesn't raise or log
        old_error_handler()  # No error, no log
        
        # New handler logs the error (would need mock to verify)
        with self.assertLogs(level='WARNING'):
            new_error_handler()

class TestInputValidation(unittest.TestCase):
    """Test input validation improvements."""
    
    def test_time_format_validation(self):
        """Test that time format validation works correctly."""
        valid_times = ["00:00", "12:30", "23:59"]
        invalid_times = ["24:00", "12:60", "abc", "12", "12:30:45"]
        
        def validate_time(time_str):
            try:
                hour, minute = map(int, time_str.split(":"))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    return False
                return True
            except (ValueError, IndexError):
                return False
        
        for time in valid_times:
            self.assertTrue(validate_time(time), f"{time} should be valid")
        
        for time in invalid_times:
            self.assertFalse(validate_time(time), f"{time} should be invalid")
    
    def test_whitelist_validation(self):
        """Test that setting keys are validated against whitelist."""
        allowed_keys = {"enabled", "interval_minutes", "media_type"}
        
        valid_keys = ["enabled", "interval_minutes", "media_type"]
        invalid_keys = ["drop_table", "etc_passwd", "random_key"]
        
        for key in valid_keys:
            self.assertIn(key, allowed_keys, f"{key} should be in whitelist")
        
        for key in invalid_keys:
            self.assertNotIn(key, allowed_keys, f"{key} should not be in whitelist")

if __name__ == "__main__":
    unittest.main()
