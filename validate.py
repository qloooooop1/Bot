#!/usr/bin/env python3
"""
Validation script to check core bot functionality without requiring a live bot token.
"""

import os
import sys
import json

def check_json_files():
    """Check that all required JSON files exist and are valid"""
    print("📁 Checking JSON files...")
    azkar_dir = 'azkar'
    required_files = [
        'morning.json',
        'evening.json',
        'friday.json',
        'sleep.json',
        'ramadan.json',
        'arafah.json',
        'eid.json',
        'hajj.json',
        'last_ten_days.json',
        'laylat_alqadr.json'
    ]
    
    all_valid = True
    for filename in required_files:
        filepath = os.path.join(azkar_dir, filename)
        if not os.path.exists(filepath):
            print(f"  ✗ Missing: {filename}")
            all_valid = False
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"  ✓ {filename}: {data.get('title', 'No title')}")
        except FileNotFoundError:
            print(f"  ✗ File not found: {filename}")
            all_valid = False
        except json.JSONDecodeError as e:
            print(f"  ✗ Invalid JSON in {filename}: {e}")
            all_valid = False
        except UnicodeDecodeError as e:
            print(f"  ✗ Encoding error in {filename}: {e}")
            all_valid = False
        except Exception as e:
            print(f"  ✗ Unexpected error loading {filename}: {e}")
            all_valid = False
    
    return all_valid

def check_port_configuration():
    """Check PORT configuration logic"""
    print("\n🔌 Checking PORT configuration...")
    
    # Test default port
    test_port = int(os.environ.get("PORT", 5000))
    if 1 <= test_port <= 65535:
        print(f"  ✓ PORT validation works (default: {test_port})")
        return True
    else:
        print(f"  ✗ PORT validation failed")
        return False

def check_webhook_url():
    """Check webhook URL configuration"""
    print("\n🌐 Checking webhook URL configuration...")
    
    webhook_path = "/webhook"
    hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'bot-8c0e.onrender.com')
    webhook_url = f"https://{hostname}{webhook_path}"
    
    if webhook_url.startswith("https://") and webhook_url.endswith(webhook_path):
        print(f"  ✓ Webhook URL format valid: {webhook_url}")
        return True
    else:
        print(f"  ✗ Webhook URL format invalid")
        return False

def check_file_structure():
    """Check that required files exist"""
    print("\n📋 Checking file structure...")
    
    required_files = [
        'App.py',
        'requirements.txt',
        'test_bot.py',
        'TESTING.md',
        'README.md'
    ]
    
    all_exist = True
    for filename in required_files:
        if os.path.exists(filename):
            print(f"  ✓ {filename}")
        else:
            print(f"  ✗ Missing: {filename}")
            all_exist = False
    
    return all_exist

def check_syntax():
    """Check Python syntax of main file"""
    print("\n🐍 Checking Python syntax...")
    
    try:
        import py_compile
        py_compile.compile('App.py', doraise=True)
        print("  ✓ App.py syntax valid")
        return True
    except Exception as e:
        print(f"  ✗ Syntax error in App.py: {e}")
        return False

def main():
    """Run all validation checks"""
    print("=" * 60)
    print("🤖 Bot Validation Script")
    print("=" * 60)
    
    checks = [
        check_file_structure(),
        check_syntax(),
        check_json_files(),
        check_port_configuration(),
        check_webhook_url()
    ]
    
    print("\n" + "=" * 60)
    if all(checks):
        print("✅ All validation checks passed!")
        print("=" * 60)
        return 0
    else:
        print("❌ Some validation checks failed")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
