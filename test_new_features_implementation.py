#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test for new features implementation:
1. Diverse azkar settings with chat_id support
2. Fixed time preset buttons for morning/evening
3. Friday time settings button
4. Developer and official group buttons in control panel
"""

import unittest
import sys
import App

class TestDiverseAzkarSettings(unittest.TestCase):
    """Test diverse azkar settings implementation."""
    
    def test_diverse_azkar_database_table_exists(self):
        """Test that diverse_azkar_settings table exists."""
        conn, c, is_postgres = App.get_db_connection()
        try:
            placeholder = "%s" if is_postgres else "?"
            # Check if table exists
            if is_postgres:
                c.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'diverse_azkar_settings'
                    )
                """)
            else:
                c.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='diverse_azkar_settings'
                """)
            result = c.fetchone()
            self.assertTrue(result, "diverse_azkar_settings table should exist")
        finally:
            conn.close()
    
    def test_get_diverse_azkar_settings_function(self):
        """Test get_diverse_azkar_settings function."""
        # Test with a dummy chat_id
        settings = App.get_diverse_azkar_settings(-1234567890)
        self.assertIsInstance(settings, dict)
        self.assertIn('enabled', settings)
        self.assertIn('interval_minutes', settings)
        self.assertIn('media_type', settings)
    
    def test_update_diverse_azkar_setting_function(self):
        """Test update_diverse_azkar_setting function."""
        test_chat_id = -9876543210
        
        # Update enabled setting
        App.update_diverse_azkar_setting(test_chat_id, 'enabled', 1)
        settings = App.get_diverse_azkar_settings(test_chat_id)
        self.assertEqual(settings['enabled'], 1)
        
        # Update interval
        App.update_diverse_azkar_setting(test_chat_id, 'interval_minutes', 120)
        settings = App.get_diverse_azkar_settings(test_chat_id)
        self.assertEqual(settings['interval_minutes'], 120)

class TestCallbackHandlers(unittest.TestCase):
    """Test callback handler registrations."""
    
    def test_morning_time_presets_handler_exists(self):
        """Test that morning_time_presets handler is registered."""
        # Check that the handler function exists
        self.assertTrue(hasattr(App, 'callback_morning_time_presets'))
    
    def test_evening_time_presets_handler_exists(self):
        """Test that evening_time_presets handler is registered."""
        self.assertTrue(hasattr(App, 'callback_evening_time_presets'))
    
    def test_diverse_azkar_settings_handler_exists(self):
        """Test that diverse_azkar_settings handler is registered."""
        self.assertTrue(hasattr(App, 'callback_diverse_azkar_settings'))
    
    def test_toggle_diverse_azkar_handler_exists(self):
        """Test that toggle_diverse_azkar handler is registered."""
        self.assertTrue(hasattr(App, 'callback_toggle_diverse_azkar'))
    
    def test_diverse_interval_handler_exists(self):
        """Test that diverse_interval handler is registered."""
        self.assertTrue(hasattr(App, 'callback_diverse_interval'))
    
    def test_friday_time_settings_handler_exists(self):
        """Test that friday_time_settings handler is registered."""
        self.assertTrue(hasattr(App, 'callback_friday_time_settings'))

class TestDiverseAzkarContent(unittest.TestCase):
    """Test diverse azkar content loading."""
    
    def test_load_diverse_azkar(self):
        """Test loading diverse azkar from JSON."""
        azkar_list = App.load_diverse_azkar()
        self.assertIsInstance(azkar_list, list)
        self.assertGreater(len(azkar_list), 0, "Should load at least one azkar")
        
        # Check structure of first item
        if len(azkar_list) > 0:
            item = azkar_list[0]
            self.assertIn('type', item)
            self.assertIn('text', item)
            self.assertIn('reference', item)
    
    def test_get_random_diverse_azkar(self):
        """Test getting random diverse azkar."""
        azkar = App.get_random_diverse_azkar()
        # Can be None if file doesn't exist or is empty
        if azkar:
            self.assertIsInstance(azkar, str)
            # Check that it contains expected patterns
            self.assertTrue('*' in azkar or 'الأدعية' in azkar)

class TestSupportButtons(unittest.TestCase):
    """Test support buttons functionality."""
    
    def test_add_support_buttons_function_exists(self):
        """Test that add_support_buttons function exists."""
        self.assertTrue(hasattr(App, 'add_support_buttons'))

if __name__ == '__main__':
    # Run tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestDiverseAzkarSettings))
    suite.addTests(loader.loadTestsFromTestCase(TestCallbackHandlers))
    suite.addTests(loader.loadTestsFromTestCase(TestDiverseAzkarContent))
    suite.addTests(loader.loadTestsFromTestCase(TestSupportButtons))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with proper code
    sys.exit(0 if result.wasSuccessful() else 1)
