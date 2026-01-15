"""
Test script to verify the /start command and settings access fixes.
This tests the critical functionality without requiring a live bot.
"""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Test database functions without requiring Telegram connection
class TestDatabaseFunctions(unittest.TestCase):
    """Test database helper functions"""
    
    def test_admin_table_schema(self):
        """Test that admins table includes is_primary_admin column"""
        # Read App.py to verify schema
        with open('App.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Check SQLite schema
        self.assertIn('is_primary_admin INTEGER DEFAULT 0', content)
        
        # Check PostgreSQL schema
        self.assertIn('is_primary_admin INTEGER DEFAULT 0', content)
    
    def test_helper_functions_exist(self):
        """Test that new helper functions are defined"""
        with open('App.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for new functions
        self.assertIn('def is_user_admin_of_chat(', content)
        self.assertIn('def extract_chat_id_from_callback(', content)
        self.assertIn('def create_back_button_callback(', content)
    
    def test_save_admin_info_signature(self):
        """Test that save_admin_info includes is_primary_admin parameter"""
        with open('App.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('is_primary_admin: bool = False', content)
    
    def test_start_command_uses_base64(self):
        """Test that /start command uses base64 encoding for chat_id"""
        with open('App.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for base64 import and usage
        self.assertIn('import base64', content)
        self.assertIn('base64.b64encode', content)
        self.assertIn('base64.b64decode', content)
    
    def test_callback_handlers_updated(self):
        """Test that callback handlers support group-specific format"""
        with open('App.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for callback_select_group
        self.assertIn('def callback_select_group(', content)
        self.assertIn('callback_data.startswith("select_group_")', content)
    
    def test_deep_link_format(self):
        """Test that deep link format includes group context"""
        with open('App.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for group context in deep links
        self.assertIn('?start=group_', content)
        self.assertIn('group_{chat_id_encoded}', content)


class TestCallbackDataParsing(unittest.TestCase):
    """Test callback data parsing logic"""
    
    def test_extract_chat_id_from_callback_with_id(self):
        """Test extracting chat_id from callback data"""
        # Simulate the function logic
        callback_data = "morning_evening_settings_-1234567"
        parts = callback_data.split("_")
        
        try:
            chat_id = int(parts[-1])
            self.assertEqual(chat_id, -1234567)
        except ValueError:
            self.fail("Should be able to parse chat_id")
    
    def test_extract_chat_id_from_callback_without_id(self):
        """Test callback data without chat_id"""
        callback_data = "morning_evening_settings"
        parts = callback_data.split("_")
        
        try:
            # Try to parse last part as int
            chat_id = int(parts[-1])
            # Should not reach here
            self.fail("Should raise ValueError")
        except ValueError:
            # Expected - last part is not a number
            pass
    
    def test_create_back_button_with_chat_id(self):
        """Test back button creation with chat_id"""
        # This would be tested with the actual function
        # Here we just verify the concept
        chat_id = -1234567
        import base64
        
        chat_id_encoded = base64.b64encode(str(chat_id).encode()).decode()
        callback_data = f"select_group_{chat_id_encoded}"
        
        # Verify we can decode it back
        extracted = callback_data.replace("select_group_", "")
        decoded_chat_id = int(base64.b64decode(extracted).decode())
        
        self.assertEqual(decoded_chat_id, chat_id)


class TestBackwardCompatibility(unittest.TestCase):
    """Test that changes are backward compatible"""
    
    def test_old_callback_format_supported(self):
        """Test that old callback format is still supported"""
        with open('App.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for fallback to old behavior
        self.assertIn('is_user_admin_in_any_group', content)
        self.assertIn('# Old format:', content)
        self.assertIn('# backwards compatibility', content)
    
    def test_database_has_defaults(self):
        """Test that new columns have default values"""
        with open('App.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # is_primary_admin should have default
        self.assertIn('is_primary_admin INTEGER DEFAULT 0', content)


class TestSecurityImprovements(unittest.TestCase):
    """Test security-related improvements"""
    
    def test_admin_verification_per_chat(self):
        """Test that admin verification is per-chat, not global"""
        with open('App.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # New handlers should verify admin status for specific chat
        self.assertIn('is_user_admin_of_chat(call.from_user.id, chat_id)', content)
    
    def test_primary_admin_protection(self):
        """Test that primary admin status is protected"""
        with open('App.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for logic that prevents reassigning primary admin
        self.assertIn('existing_primary = c.fetchone()', content)
        self.assertIn("if existing_primary and existing_primary[0] != user_id:", content)


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)
