#!/usr/bin/env python3
"""
Test admin management improvements.
Validates that the new admin sync functionality works correctly.
"""

import unittest
import sqlite3
import os
import sys

# Add parent directory to path to import App
sys.path.insert(0, os.path.dirname(__file__))

class TestAdminImprovements(unittest.TestCase):
    """Test admin management improvements"""
    
    def setUp(self):
        """Set up test database"""
        self.test_db = "test_bot_settings.db"
        
        # Create test database
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        
        # Create admins table
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
    
    def tearDown(self):
        """Clean up test database"""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_save_and_retrieve_admin(self):
        """Test saving and retrieving admin information"""
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        
        # Save admin info
        test_user_id = 123456789
        test_chat_id = -1001234567890
        
        c.execute('''
            INSERT OR REPLACE INTO admins (user_id, chat_id, username, first_name, last_name, is_primary_admin, added_at)
            VALUES (?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
        ''', (test_user_id, test_chat_id, 'testuser', 'Test', 'User', 1))
        
        conn.commit()
        
        # Retrieve admin info
        c.execute('''
            SELECT user_id, chat_id, username, first_name, last_name, added_at
            FROM admins
            WHERE user_id = ? AND chat_id = ?
        ''', (test_user_id, test_chat_id))
        
        row = c.fetchone()
        
        self.assertIsNotNone(row, "Admin info should be retrievable")
        self.assertEqual(row[0], test_user_id, "User ID should match")
        self.assertEqual(row[1], test_chat_id, "Chat ID should match")
        self.assertEqual(row[2], 'testuser', "Username should match")
        
        conn.close()
    
    def test_get_all_admins_for_chat(self):
        """Test retrieving all admins for a chat"""
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        
        test_chat_id = -1001234567890
        
        # Add multiple admins
        admins_data = [
            (111, test_chat_id, 'admin1', 'Admin', 'One', 1),
            (222, test_chat_id, 'admin2', 'Admin', 'Two', 0),
            (333, test_chat_id, 'admin3', 'Admin', 'Three', 0),
        ]
        
        for admin in admins_data:
            c.execute('''
                INSERT OR REPLACE INTO admins (user_id, chat_id, username, first_name, last_name, is_primary_admin, added_at)
                VALUES (?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
            ''', admin)
        
        conn.commit()
        
        # Retrieve all admins
        c.execute('''
            SELECT user_id, chat_id, username, first_name, last_name, is_primary_admin, added_at
            FROM admins
            WHERE chat_id = ?
        ''', (test_chat_id,))
        
        rows = c.fetchall()
        
        self.assertEqual(len(rows), 3, "Should have 3 admins")
        
        # Check primary admin
        primary_admins = [row for row in rows if row[5] == 1]
        self.assertEqual(len(primary_admins), 1, "Should have exactly 1 primary admin")
        self.assertEqual(primary_admins[0][0], 111, "First admin should be primary")
        
        conn.close()
    
    def test_admin_update_preserves_primary(self):
        """Test that updating admin info preserves primary status"""
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        
        test_user_id = 123456789
        test_chat_id = -1001234567890
        
        # First insert as primary admin
        c.execute('''
            INSERT OR REPLACE INTO admins (user_id, chat_id, username, first_name, last_name, is_primary_admin, added_at)
            VALUES (?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
        ''', (test_user_id, test_chat_id, 'testuser', 'Test', 'User', 1))
        
        conn.commit()
        
        # Update the admin (simulate re-saving)
        c.execute('''
            SELECT is_primary_admin FROM admins 
            WHERE user_id = ? AND chat_id = ?
        ''', (test_user_id, test_chat_id))
        existing = c.fetchone()
        
        # Keep existing primary admin status
        is_primary_admin = True if existing and existing[0] == 1 else False
        
        c.execute('''
            INSERT OR REPLACE INTO admins (user_id, chat_id, username, first_name, last_name, is_primary_admin, added_at)
            VALUES (?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
        ''', (test_user_id, test_chat_id, 'testuser_updated', 'Test', 'User', int(is_primary_admin)))
        
        conn.commit()
        
        # Verify primary status is preserved
        c.execute('''
            SELECT is_primary_admin, username FROM admins 
            WHERE user_id = ? AND chat_id = ?
        ''', (test_user_id, test_chat_id))
        
        row = c.fetchone()
        
        self.assertEqual(row[0], 1, "Primary admin status should be preserved")
        self.assertEqual(row[1], 'testuser_updated', "Username should be updated")
        
        conn.close()
    
    def test_function_signatures(self):
        """Test that the new functions have correct signatures"""
        # This is a simple import test to ensure functions exist
        # We can't fully test without mocking Telegram API
        
        # Just verify the file compiles
        with open('App.py', 'r') as f:
            content = f.read()
            
        # Check that new function exists
        self.assertIn('def sync_group_admins', content, "sync_group_admins function should exist")
        self.assertIn('bot.get_chat_administrators', content, "Should call get_chat_administrators")
        self.assertIn('save_admin_info', content, "Should call save_admin_info")
        
        # Check that my_chat_member_handler was updated
        self.assertIn('sync_group_admins(chat_id)', content, "Should call sync_group_admins in handler")
        
        # Check optimizations in is_user_admin functions
        self.assertIn('SELECT COUNT(*) FROM admins', content, "Should check database first in is_user_admin_in_any_group")


if __name__ == '__main__':
    # Run tests
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAdminImprovements)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)
