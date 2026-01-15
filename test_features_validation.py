#!/usr/bin/env python3
"""
Test script for new database features and JSON files
Tests the new tables and media structure
"""

import sys
import os
import sqlite3
import json

# Test configuration
DB_FILE = "test_features_db.db"
TEST_CHAT_ID = -1234567890

def cleanup():
    """Remove test database if it exists"""
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print("✓ Cleanup completed")

def test_database_schema():
    """Test that all new tables can be created"""
    print("\n=== Testing Database Schema ===")
    
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Create main chat_settings table
        c.execute('''
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                is_enabled INTEGER DEFAULT 1
            )
        ''')
        print("✓ chat_settings table created")
        
        # Create diverse_azkar_settings table
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
        print("✓ diverse_azkar_settings table created")
        
        # Create ramadan_settings table
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
        print("✓ ramadan_settings table created")
        
        # Create hajj_eid_settings table
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
        print("✓ hajj_eid_settings table created")
        
        conn.commit()
        conn.close()
        
        print("✅ Database schema test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Database schema test failed: {e}")
        return False

def test_data_operations():
    """Test inserting and retrieving data"""
    print("\n=== Testing Data Operations ===")
    
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Insert test data
        c.execute('INSERT INTO chat_settings (chat_id) VALUES (?)', (TEST_CHAT_ID,))
        c.execute('INSERT INTO diverse_azkar_settings (chat_id, enabled, interval_minutes) VALUES (?, 1, 120)', (TEST_CHAT_ID,))
        c.execute('INSERT INTO ramadan_settings (chat_id) VALUES (?)', (TEST_CHAT_ID,))
        c.execute('INSERT INTO hajj_eid_settings (chat_id) VALUES (?)', (TEST_CHAT_ID,))
        
        conn.commit()
        print("✓ Test data inserted")
        
        # Verify data
        c.execute('SELECT * FROM diverse_azkar_settings WHERE chat_id = ?', (TEST_CHAT_ID,))
        row = c.fetchone()
        if row and row[1] == 1 and row[2] == 120:  # enabled=1, interval=120
            print("✓ Diverse azkar settings verified")
        else:
            raise Exception("Diverse azkar data mismatch")
        
        c.execute('SELECT * FROM ramadan_settings WHERE chat_id = ?', (TEST_CHAT_ID,))
        if c.fetchone():
            print("✓ Ramadan settings verified")
        else:
            raise Exception("Ramadan settings not found")
        
        c.execute('SELECT * FROM hajj_eid_settings WHERE chat_id = ?', (TEST_CHAT_ID,))
        if c.fetchone():
            print("✓ Hajj/Eid settings verified")
        else:
            raise Exception("Hajj/Eid settings not found")
        
        conn.close()
        
        print("✅ Data operations test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Data operations test failed: {e}")
        return False

def test_json_files():
    """Test that all JSON files are valid"""
    print("\n=== Testing JSON Files ===")
    
    json_files = {
        'audio.json': 'audio',
        'images.json': 'images',
        'azkar/diverse_azkar.json': 'azkar'
    }
    
    all_passed = True
    
    for filepath, key in json_files.items():
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if key in data:
                count = len(data[key])
                print(f"✓ {filepath} - {count} items")
            else:
                print(f"⚠️  {filepath} - Key '{key}' not found")
                all_passed = False
                    
        except FileNotFoundError:
            print(f"❌ {filepath} - File not found")
            all_passed = False
        except json.JSONDecodeError as e:
            print(f"❌ {filepath} - Invalid JSON: {e}")
            all_passed = False
        except Exception as e:
            print(f"❌ {filepath} - Error: {e}")
            all_passed = False
    
    if all_passed:
        print("✅ JSON files test passed!")
    else:
        print("❌ JSON files test has issues!")
    
    return all_passed

def main():
    """Run all tests"""
    print("=" * 60)
    print("New Features Test Suite")
    print("=" * 60)
    
    # Clean up before starting
    cleanup()
    
    # Run tests
    results = {
        'Database Schema': test_database_schema(),
        'Data Operations': test_data_operations(),
        'JSON Files': test_json_files()
    }
    
    # Clean up after tests
    cleanup()
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    sys.exit(0 if passed == total else 1)

if __name__ == "__main__":
    main()
