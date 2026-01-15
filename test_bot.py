#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for Islamic Adhkar Bot
تشغيل الاختبارات للتأكد من عمل البوت
"""

import sys
import os

# Set test bot token for testing (valid format but won't actually connect)
os.environ['BOT_TOKEN'] = '123456789:ABCdefGHIjklMNOpqrsTUVwxyz-1234567890'

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import App

def test_database():
    """اختبار قاعدة البيانات"""
    print("=" * 50)
    print("🔍 اختبار قاعدة البيانات")
    print("=" * 50)
    
    # Initialize database
    App.init_database()
    print("✓ تم تهيئة قاعدة البيانات")
    
    # Test group settings
    test_chat_id = -1001234567890
    settings = App.get_group_settings(test_chat_id)
    print(f"✓ إعدادات المجموعة: الفاصل الزمني = {settings[1]} دقيقة")
    
    # Check content counts
    tables = [
        ('morning_adhkar', 'أذكار الصباح'),
        ('evening_adhkar', 'أذكار المساء'),
        ('random_dua', 'الأدعية العشوائية'),
        ('quran_verses', 'الآيات القرآنية'),
        ('friday_dua', 'أدعية الجمعة')
    ]
    
    for table, name in tables:
        App.cursor.execute(f'SELECT COUNT(*) FROM {table}')
        count = App.cursor.fetchone()[0]
        print(f"✓ {name}: {count} عنصر")
    
    print()

def test_content_display():
    """اختبار عرض المحتوى"""
    print("=" * 50)
    print("📖 عرض عينة من المحتوى")
    print("=" * 50)
    
    # Display sample morning adhkar
    print("\n🌅 عينة من أذكار الصباح:")
    print("-" * 50)
    App.cursor.execute('SELECT content FROM morning_adhkar LIMIT 2')
    for (content,) in App.cursor.fetchall():
        print(content[:80] + "..." if len(content) > 80 else content)
        print()
    
    # Display sample evening adhkar
    print("🌙 عينة من أذكار المساء:")
    print("-" * 50)
    App.cursor.execute('SELECT content FROM evening_adhkar LIMIT 2')
    for (content,) in App.cursor.fetchall():
        print(content[:80] + "..." if len(content) > 80 else content)
        print()
    
    # Display sample dua
    print("💫 عينة من الأدعية:")
    print("-" * 50)
    App.cursor.execute('SELECT content FROM random_dua LIMIT 2')
    for (content,) in App.cursor.fetchall():
        print(content)
        print()
    
    # Display sample Quran verse
    print("📖 عينة من الآيات القرآنية:")
    print("-" * 50)
    App.cursor.execute('SELECT content, surah_name, verse_number FROM quran_verses LIMIT 2')
    for content, surah, verse in App.cursor.fetchall():
        print(f"{content}")
        print(f"﴿ سورة {surah} - آية {verse} ﴾")
        print()

def test_scheduler_setup():
    """اختبار إعداد المجدول"""
    print("=" * 50)
    print("⏰ اختبار المجدول")
    print("=" * 50)
    
    try:
        scheduler = App.setup_scheduler()
        jobs = scheduler.get_jobs()
        
        print(f"✓ تم إنشاء المجدول بنجاح")
        print(f"✓ عدد المهام المجدولة: {len(jobs)}")
        
        print("\nالمهام المجدولة:")
        for job in jobs:
            print(f"  - {job.id}: {job.next_run_time}")
        
        scheduler.shutdown()
        print("\n✓ تم إيقاف المجدول بنجاح")
        
    except Exception as e:
        print(f"✗ خطأ في المجدول: {e}")
    
    print()

def main():
    """الدالة الرئيسية للاختبارات"""
    print("\n" + "=" * 50)
    print("🕌 اختبار بوت الأذكار الإسلامية")
    print("=" * 50)
    print()
    
    try:
        test_database()
        test_content_display()
        test_scheduler_setup()
        
        print("=" * 50)
        print("✅ جميع الاختبارات نجحت!")
        print("=" * 50)
        print()
        print("📝 ملاحظة: لتشغيل البوت الفعلي، استخدم:")
        print("   python App.py")
        print()
        
        return 0
        
    except Exception as e:
        print(f"\n❌ فشل الاختبار: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
