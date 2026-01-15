#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validation script for new features implementation:
1. Check that handlers are defined
2. Check code structure
3. Verify callback patterns
"""

import re
import sys

def check_file_contains(filename, patterns, description):
    """Check if file contains all patterns."""
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"\nChecking: {description}")
    all_found = True
    for pattern in patterns:
        if isinstance(pattern, str):
            found = pattern in content
        else:
            # regex pattern
            found = pattern.search(content) is not None
        
        pattern_str = pattern if isinstance(pattern, str) else pattern.pattern
        status = "✓" if found else "✗"
        print(f"  {status} {pattern_str[:80]}")
        if not found:
            all_found = False
    
    return all_found

def main():
    """Run validation checks."""
    all_checks_passed = True
    
    # Check 1: Diverse azkar settings handler
    patterns = [
        '@bot.callback_query_handler(func=lambda call: call.data.startswith("diverse_azkar_settings")',
        'def callback_diverse_azkar_settings(call: types.CallbackQuery):',
        'diverse_interval_{chat_id}_',
        'toggle_diverse_azkar_{chat_id}',
    ]
    if not check_file_contains('App.py', patterns, 
                               "Diverse azkar settings handler with chat_id support"):
        all_checks_passed = False
    
    # Check 2: Morning/evening time preset handlers
    patterns = [
        '@bot.callback_query_handler(func=lambda call: call.data.startswith("morning_time_presets")',
        'def callback_morning_time_presets(call: types.CallbackQuery):',
        '@bot.callback_query_handler(func=lambda call: call.data.startswith("evening_time_presets")',
        'def callback_evening_time_presets(call: types.CallbackQuery):',
        'morning_time_presets_{chat_id}',
        'evening_time_presets_{chat_id}',
    ]
    if not check_file_contains('App.py', patterns, 
                               "Morning/evening time preset handlers with chat_id support"):
        all_checks_passed = False
    
    # Check 3: Friday time settings
    patterns = [
        '@bot.callback_query_handler(func=lambda call: call.data.startswith("friday_time_settings_")',
        'def callback_friday_time_settings(call: types.CallbackQuery):',
        '"⏰ تخصيص أوقات الجمعة"',
    ]
    if not check_file_contains('App.py', patterns, 
                               "Friday time settings handler"):
        all_checks_passed = False
    
    # Check 4: Developer and official group buttons
    patterns = [
        'def add_support_buttons(markup: types.InlineKeyboardMarkup):',
        '"👨‍💻 الدعم الفني"',
        '"👥 المجموعة الرسمية"',
        'add_support_buttons(markup)',
    ]
    if not check_file_contains('App.py', patterns, 
                               "Support buttons (developer and official group)"):
        all_checks_passed = False
    
    # Check 5: Diverse azkar in control panel
    patterns = [
        '"✨ أذكار متنوعة"',
        'diverse_azkar_settings_{chat_id}',
    ]
    if not check_file_contains('App.py', patterns, 
                               "Diverse azkar button in control panel"):
        all_checks_passed = False
    
    # Check 6: Toggle diverse azkar handler
    patterns = [
        '@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_diverse_azkar_")',
        'def callback_toggle_diverse_azkar(call: types.CallbackQuery):',
    ]
    if not check_file_contains('App.py', patterns, 
                               "Toggle diverse azkar handler"):
        all_checks_passed = False
    
    # Check 7: Diverse interval handler with chat_id support
    patterns = [
        'def callback_diverse_interval(call: types.CallbackQuery):',
        'diverse_interval_{chat_id}_{minutes}',
        'update_diverse_azkar_setting',
    ]
    if not check_file_contains('App.py', patterns, 
                               "Diverse interval handler with chat_id support"):
        all_checks_passed = False
    
    # Check 8: Fixed toggle handler to exclude chat_id toggles
    patterns = [
        'is_simple_toggle_callback',
        'Toggle commands with chat_id are handled by specific handlers',
    ]
    if not check_file_contains('App.py', patterns, 
                               "Fixed toggle handler to exclude chat_id-specific toggles"):
        all_checks_passed = False
    
    # Print summary
    print("\n" + "="*60)
    if all_checks_passed:
        print("✓ All validation checks passed!")
        return 0
    else:
        print("✗ Some validation checks failed!")
        return 1

if __name__ == '__main__':
    sys.exit(main())
