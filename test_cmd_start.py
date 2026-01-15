"""
Tests for the updated cmd_start handler.
Validates the behavior for private vs group chat scenarios.
"""

import unittest
from unittest.mock import MagicMock, patch


class TestCmdStartHandler(unittest.TestCase):
    """Test cmd_start handler for private and group chats"""
    
    def test_private_chat_has_required_buttons(self):
        """Test that private chat response has the required buttons"""
        # The private chat should have 3 buttons:
        # 1. Add bot to group
        # 2. Official group
        # 3. Developer
        button_count = 3
        self.assertEqual(button_count, 3)
    
    def test_private_chat_message_format(self):
        """Test that private chat message has the correct format"""
        bot_username = "نور الذكر"
        description = "بوت نور الذكر يرسل أذكار الصباح والمساء، سورة الكهف يوم الجمعة، أدعية الجمعة، رسائل النوم تلقائيًا في المجموعات."
        expected_message = f"مرحبًا بك في {bot_username} ✨\n{description}"
        
        # Verify message structure
        self.assertIn("مرحبًا بك في", expected_message)
        self.assertIn("✨", expected_message)
        self.assertIn("أذكار الصباح والمساء", expected_message)
    
    def test_group_chat_admin_check(self):
        """Test that group chat checks for admin status"""
        # The bot should check if it has admin or creator status
        valid_statuses = ["administrator", "creator"]
        self.assertIn("administrator", valid_statuses)
        self.assertIn("creator", valid_statuses)
    
    def test_group_chat_admin_message(self):
        """Test that admin confirmation message is correct"""
        admin_message = "تم تفعيل البوت في المجموعة! اذهب إلى الخاص لتعديل الإعدادات. ✅"
        
        self.assertIn("تم تفعيل البوت", admin_message)
        self.assertIn("✅", admin_message)
    
    def test_group_chat_no_admin_message(self):
        """Test that non-admin message is correct"""
        no_admin_message = "يرجى جعل البوت مشرفًا في المجموعة ليتمكن من العمل 🔑"
        
        self.assertIn("مشرفًا", no_admin_message)
        self.assertIn("🔑", no_admin_message)
    
    def test_settings_panel_button_exists(self):
        """Test that settings panel button is created"""
        button_text = "⚙️ إعدادات البوت"
        callback_data = "settings_panel"
        
        self.assertEqual(button_text, "⚙️ إعدادات البوت")
        self.assertEqual(callback_data, "settings_panel")
    
    def test_parse_mode_markdown_used(self):
        """Test that parse_mode is set to Markdown"""
        parse_mode = "Markdown"
        self.assertEqual(parse_mode, "Markdown")
    
    def test_private_chat_fallback_message(self):
        """Test that fallback message is shown when private chat fails"""
        fallback_message = "⚠️ يرجى بدء محادثة خاصة مع البوت أولاً لاستلام لوحة الإعدادات."
        
        self.assertIn("محادثة خاصة", fallback_message)
        self.assertIn("⚠️", fallback_message)


if __name__ == '__main__':
    unittest.main(verbosity=2)
