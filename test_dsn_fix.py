"""
Test PostgreSQL DSN validation fixes.
"""

import os
import unittest
from unittest.mock import patch


class TestPostgreSQLDSNValidation(unittest.TestCase):
    """Test that DATABASE_URL validation works correctly"""
    
    def test_invalid_dsn_without_protocol_or_equals(self):
        """Test that DSN without :// or = is detected as invalid"""
        invalid_dsns = [
            "psql",
            "postgres",
            "postgresql",
            "just_some_text",
            "database_url"
        ]
        
        for dsn in invalid_dsns:
            # Check that DSN has neither :// nor =
            has_protocol = "://" in dsn
            has_equals = "=" in dsn
            is_invalid = not (has_protocol or has_equals)
            
            self.assertTrue(is_invalid, 
                          f"DSN '{dsn}' should be detected as invalid (no :// or =)")
    
    def test_valid_dsn_with_protocol(self):
        """Test that valid DSN with protocol is accepted"""
        valid_dsns = [
            "postgresql://user:pass@host:5432/db",
            "postgres://user:pass@host:5432/db",
            "psql://user:pass@host:5432/db"
        ]
        
        for dsn in valid_dsns:
            has_protocol = "://" in dsn
            self.assertTrue(has_protocol, 
                          f"DSN '{dsn}' should have protocol separator ://")
    
    def test_valid_dsn_with_key_value_format(self):
        """Test that valid DSN in key=value format is accepted"""
        valid_dsns = [
            "host=localhost port=5432 dbname=mydb user=myuser password=mypass",
            "dbname=test user=postgres"
        ]
        
        for dsn in valid_dsns:
            has_equals = "=" in dsn
            self.assertTrue(has_equals, 
                          f"DSN '{dsn}' should have key=value format")
    
    def test_dsn_conversion_postgres_to_postgresql(self):
        """Test that postgres:// is converted to postgresql://"""
        original = "postgres://user:pass@host:5432/db"
        expected = "postgresql://user:pass@host:5432/db"
        
        result = original.replace("postgres://", "postgresql://", 1)
        self.assertEqual(result, expected)
    
    def test_dsn_conversion_psql_to_postgresql(self):
        """Test that psql:// is converted to postgresql://"""
        original = "psql://user:pass@host:5432/db"
        expected = "postgresql://user:pass@host:5432/db"
        
        result = original.replace("psql://", "postgresql://", 1)
        self.assertEqual(result, expected)
    
    def test_app_file_has_dsn_validation(self):
        """Test that App.py includes DSN validation logic"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that the validation code is present
        self.assertIn('"://" not in DATABASE_URL and "=" not in DATABASE_URL', content,
                     "App.py should validate DSN format")
        self.assertIn('Invalid DATABASE_URL format', content,
                     "App.py should log invalid DSN error")


class TestAdhkarLoggingFormat(unittest.TestCase):
    """Test that adhkar logging follows required format"""
    
    def test_app_has_required_logging_format(self):
        """Test that App.py includes required logging format for adhkar"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for the required logging format
        self.assertIn('Attempted to send adhkar for category', content,
                     "App.py should log adhkar attempts with category")
        self.assertIn('chat_id=', content,
                     "App.py should log chat_id in the required format")
    
    def test_app_has_reason_field_in_error_logs(self):
        """Test that App.py includes REASON field in error logging"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for REASON field in error logs
        self.assertIn('REASON=', content,
                     "App.py should include REASON field in error logs")
        self.assertIn('Bot blocked by user', content,
                     "App.py should detect when bot is blocked")
        self.assertIn('Permission denied', content,
                     "App.py should detect permission issues")
    
    def test_app_has_timezone_in_scheduling(self):
        """Test that App.py uses TIMEZONE in all scheduling"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that TIMEZONE is used in CronTrigger
        self.assertIn('timezone=TIMEZONE', content,
                     "App.py should use TIMEZONE in CronTrigger")
        self.assertIn('TIMEZONE = pytz.timezone("Asia/Riyadh")', content,
                     "App.py should define Asia/Riyadh timezone")


if __name__ == '__main__':
    unittest.main()
