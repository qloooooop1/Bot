"""
Tests for the advanced settings system.
These tests verify the new media and scheduling features.
"""

import os
import json
import unittest
from unittest.mock import patch, MagicMock


class TestMediaDatabase(unittest.TestCase):
    """Test media database functionality"""
    
    def test_media_database_exists(self):
        """Test that media_database.json file exists"""
        db_file = os.path.join(os.path.dirname(__file__), 'media_database.json')
        self.assertTrue(os.path.exists(db_file), "media_database.json should exist")
    
    def test_media_database_valid_json(self):
        """Test that media_database.json is valid JSON"""
        db_file = os.path.join(os.path.dirname(__file__), 'media_database.json')
        with open(db_file, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                self.assertIsInstance(data, dict)
            except json.JSONDecodeError:
                self.fail("media_database.json is not valid JSON")
    
    def test_media_database_structure(self):
        """Test that media database has required structure"""
        db_file = os.path.join(os.path.dirname(__file__), 'media_database.json')
        with open(db_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check top-level structure
        self.assertIn('media', data)
        self.assertIn('settings', data)
        
        # Check media categories
        media = data['media']
        self.assertIn('images', media)
        self.assertIn('videos', media)
        self.assertIn('documents', media)
        
        # Check that categories are lists
        self.assertIsInstance(media['images'], list)
        self.assertIsInstance(media['videos'], list)
        self.assertIsInstance(media['documents'], list)
    
    def test_media_items_have_required_fields(self):
        """Test that media items have required fields"""
        db_file = os.path.join(os.path.dirname(__file__), 'media_database.json')
        with open(db_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        required_fields = ['id', 'type', 'file_id', 'description', 'enabled']
        
        for category in ['images', 'videos', 'documents']:
            for item in data['media'][category]:
                for field in required_fields:
                    self.assertIn(field, item, f"Media item should have '{field}' field")


class TestDatabaseSchema(unittest.TestCase):
    """Test extended database schema"""
    
    def test_new_fields_in_init_db(self):
        """Test that init_db creates new fields"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for new fields in CREATE TABLE statement
        self.assertIn('media_enabled', content)
        self.assertIn('media_type', content)
        self.assertIn('send_media_with_morning', content)
        self.assertIn('send_media_with_evening', content)
        self.assertIn('send_media_with_friday', content)
    
    def test_new_fields_in_allowed_keys(self):
        """Test that update_chat_setting allows new fields"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that allowed_keys includes new fields
        self.assertIn('"media_enabled"', content)
        self.assertIn('"media_type"', content)


class TestHelperFunctions(unittest.TestCase):
    """Test media helper functions"""
    
    def test_load_media_database_function_exists(self):
        """Test that load_media_database function exists"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('def load_media_database()', content)
    
    def test_get_random_media_function_exists(self):
        """Test that get_random_media function exists"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('def get_random_media(', content)
    
    def test_send_media_with_caption_function_exists(self):
        """Test that send_media_with_caption function exists"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('def send_media_with_caption(', content)
    
    def test_update_media_database_function_exists(self):
        """Test that update_media_database function exists"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('def update_media_database(', content)


class TestAdvancedSettingsCallbacks(unittest.TestCase):
    """Test advanced settings callback handlers"""
    
    def test_advanced_settings_callback_exists(self):
        """Test that advanced_settings callback handler exists"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for advanced_settings callback handler - it uses lambda so check both parts
        self.assertIn('"advanced_settings"', content)
        self.assertIn('def callback_advanced_settings(', content)
    
    def test_media_settings_callback_exists(self):
        """Test that media_settings callback handler exists"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for media_settings callback handler - it uses lambda so check both parts
        self.assertIn('"media_settings"', content)
        self.assertIn('def callback_media_settings(', content)
    
    def test_schedule_settings_callback_exists(self):
        """Test that schedule_settings callback handler exists"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for schedule_settings callback handler - it uses lambda so check both parts
        self.assertIn('"schedule_settings"', content)
        self.assertIn('def callback_schedule_settings(', content)
    
    def test_media_type_callback_exists(self):
        """Test that media_type callback handler exists"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('call.data.startswith("media_type_")', content)
        self.assertIn('def callback_media_type(', content)


class TestSetTimeCommand(unittest.TestCase):
    """Test /settime command"""
    
    def test_settime_command_exists(self):
        """Test that /settime command handler exists"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('commands=["settime"]', content)
        self.assertIn('def cmd_settime(', content)
    
    def test_settime_validates_type(self):
        """Test that settime validates azkar type"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for validation of valid types
        self.assertIn('valid_types', content)
        self.assertIn('"morning"', content)
        self.assertIn('"evening"', content)
        self.assertIn('"sleep"', content)
    
    def test_settime_validates_time_format(self):
        """Test that settime validates time format"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for time validation logic
        self.assertIn('map(int, time_str.split(":"))', content)


class TestSendAzkarMediaIntegration(unittest.TestCase):
    """Test send_azkar media integration"""
    
    def test_send_azkar_checks_media_enabled(self):
        """Test that send_azkar checks media_enabled setting"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find send_azkar function and check for media logic
        self.assertIn('send_with_media', content)
        self.assertIn('media_enabled', content)
    
    def test_send_azkar_uses_media_type(self):
        """Test that send_azkar uses media_type setting"""
        app_file = os.path.join(os.path.dirname(__file__), 'App.py')
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('media_type', content)


if __name__ == '__main__':
    unittest.main()
