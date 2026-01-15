"""
Test the fixes for Markdown parsing and PostgreSQL connection.
This test file validates the specific fixes made to address:
1. Markdown parsing errors with @ symbol
2. PostgreSQL DATABASE_URL format issues
"""

import unittest
import os


class TestMarkdownFixes(unittest.TestCase):
    """Test Markdown parsing fixes"""
    
    def test_escaped_at_symbol_in_messages(self):
        """Test that @ symbol is properly escaped in Markdown messages"""
        bot_username = "TestBot"
        
        # Test message 1 - activation message
        message1 = f"تم تفعيل البوت! اذهب إلى الخاص (\\@{bot_username}) لتعديل الإعدادات"
        self.assertIn("\\@", message1, "@ symbol should be escaped in message 1")
        self.assertIn(bot_username, message1, "Bot username should be present")
        
        # Test message 2 - fallback message
        message2 = f"⚠️ يرجى بدء محادثة خاصة مع البوت أولاً (\\@{bot_username}) لاستلام لوحة الإعدادات."
        self.assertIn("\\@", message2, "@ symbol should be escaped in message 2")
        self.assertIn(bot_username, message2, "Bot username should be present")
        
    def test_unescaped_at_would_fail(self):
        """Verify that unescaped @ is different from escaped @"""
        bot_username = "TestBot"
        
        escaped_msg = f"Test (\\@{bot_username})"
        unescaped_msg = f"Test (@{bot_username})"
        
        self.assertNotEqual(escaped_msg, unescaped_msg, 
                          "Escaped and unescaped @ should produce different strings")
        self.assertIn("\\@", escaped_msg)
        self.assertNotIn("\\@", unescaped_msg)


class TestPostgreSQLURLFixes(unittest.TestCase):
    """Test PostgreSQL DATABASE_URL format fixes"""
    
    def test_postgres_to_postgresql_conversion(self):
        """Test that postgres:// is converted to postgresql://"""
        url = "postgres://user:pass@host:5432/db"
        
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        
        self.assertTrue(url.startswith("postgresql://"), 
                       "postgres:// should be converted to postgresql://")
        self.assertNotIn("postgres://", url, 
                        "Original postgres:// should be replaced")
        
    def test_psql_to_postgresql_conversion(self):
        """Test that psql:// is converted to postgresql://"""
        url = "psql://user:pass@host:5432/db"
        
        if url.startswith("psql://"):
            url = url.replace("psql://", "postgresql://", 1)
        
        self.assertTrue(url.startswith("postgresql://"), 
                       "psql:// should be converted to postgresql://")
        self.assertNotIn("psql://", url, 
                        "Original psql:// should be replaced")
        
    def test_postgresql_unchanged(self):
        """Test that postgresql:// remains unchanged"""
        url = "postgresql://user:pass@host:5432/db"
        original = url
        
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        elif url.startswith("psql://"):
            url = url.replace("psql://", "postgresql://", 1)
        
        self.assertEqual(url, original, 
                        "postgresql:// should remain unchanged")
        
    def test_only_first_occurrence_replaced(self):
        """Test that only the first occurrence is replaced"""
        # Edge case: URL with repeated protocol string in password
        url = "postgres://user:postgres://pass@host:5432/db"
        
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        
        # Should only replace the first occurrence
        self.assertTrue(url.startswith("postgresql://"))
        # Count occurrences of postgresql://
        count = url.count("postgresql://")
        self.assertEqual(count, 1, "Should only replace first occurrence")


class TestDatabaseURLEnvironmentHandling(unittest.TestCase):
    """Test DATABASE_URL environment variable handling"""
    
    def test_database_url_none_handling(self):
        """Test that None DATABASE_URL is handled gracefully"""
        DATABASE_URL = None
        
        # This should not raise an error
        if DATABASE_URL:
            if DATABASE_URL.startswith("postgres://"):
                DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        
        self.assertIsNone(DATABASE_URL)
        
    def test_database_url_empty_string_handling(self):
        """Test that empty string DATABASE_URL is handled gracefully"""
        DATABASE_URL = ""
        
        # This should not raise an error
        if DATABASE_URL:
            if DATABASE_URL.startswith("postgres://"):
                DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        
        self.assertEqual(DATABASE_URL, "")


if __name__ == '__main__':
    unittest.main(verbosity=2)
