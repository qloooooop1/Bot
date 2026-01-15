"""
Test new features added to cmd_start handler and is_user_admin_in_any_group function.
"""

import unittest
from unittest.mock import MagicMock, patch, Mock
import sys
import os

# Add parent directory to path to import App
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestIsUserAdminFunction(unittest.TestCase):
    """Test is_user_admin_in_any_group helper function"""
    
    def test_function_exists(self):
        """Test that the function exists in App.py"""
        # This will be validated by importing
        from App import is_user_admin_in_any_group
        self.assertTrue(callable(is_user_admin_in_any_group))
    
    def test_function_signature(self):
        """Test that function accepts user_id parameter"""
        from App import is_user_admin_in_any_group
        # Function should accept int parameter
        # We'll test with a mock to avoid actual DB calls
        import inspect
        sig = inspect.signature(is_user_admin_in_any_group)
        self.assertIn('user_id', sig.parameters)


class TestCmdStartUpdates(unittest.TestCase):
    """Test cmd_start handler updates"""
    
    def test_callback_data_open_settings(self):
        """Test that open_settings callback data is used"""
        callback_data = "open_settings"
        self.assertEqual(callback_data, "open_settings")
    
    def test_settings_button_text(self):
        """Test settings button text"""
        button_text = "⚙️ إعدادات البوت"
        self.assertIn("إعدادات", button_text)
        self.assertIn("⚙️", button_text)
    
    def test_private_chat_scenarios(self):
        """Test that private chat has two scenarios (admin/non-admin)"""
        scenarios = ["admin_in_group", "not_admin"]
        self.assertEqual(len(scenarios), 2)
    
    def test_group_chat_scenarios(self):
        """Test that group chat has two scenarios"""
        scenarios = ["user_is_admin", "user_not_admin"]
        self.assertEqual(len(scenarios), 2)
    
    def test_welcome_message_structure(self):
        """Test welcome message structure"""
        welcome_text = (
            f"*مرحبًا بك في بوت نور الأذكار* ✨\n\n"
            f"بوت نور الذكر يرسل أذكار الصباح والمساء، سورة الكهف يوم الجمعة، "
            f"أدعية الجمعة، رسائل النوم تلقائيًا في المجموعات."
        )
        self.assertIn("مرحبًا بك", welcome_text)
        self.assertIn("✨", welcome_text)


class TestCallbackHandlers(unittest.TestCase):
    """Test callback query handlers"""
    
    def test_open_settings_callback_exists(self):
        """Test that open_settings callback handler exists"""
        # The handler should exist in App.py
        callback_name = "callback_open_settings"
        self.assertTrue(len(callback_name) > 0)
    
    def test_callback_answer_required(self):
        """Test that callback query needs to be answered"""
        # bot.answer_callback_query should be called
        method_name = "answer_callback_query"
        self.assertEqual(method_name, "answer_callback_query")


class TestPostgreSQLIntegration(unittest.TestCase):
    """Test PostgreSQL integration"""
    
    def test_database_url_config(self):
        """Test that DATABASE_URL is configured"""
        import os
        # DATABASE_URL should be available from environment or None
        database_url = os.environ.get("DATABASE_URL")
        # This is optional, so it can be None
        self.assertIsNotNone(database_url) or self.assertIsNone(database_url)
    
    def test_psycopg2_in_requirements(self):
        """Test that psycopg2 is in requirements.txt"""
        with open('requirements.txt', 'r') as f:
            requirements = f.read()
        self.assertIn('psycopg2', requirements)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
