#!/bin/bash
# Startup script for Islamic Adhkar Bot
# سكريبت تشغيل بوت الأذكار الإسلامية

echo "=================================================="
echo "🕌 بوت الأذكار الإسلامية"
echo "   Islamic Adhkar Bot"
echo "=================================================="
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 غير مثبت / Python 3 is not installed"
    echo "   يرجى تثبيت Python 3.7 أو أحدث"
    echo "   Please install Python 3.7 or newer"
    exit 1
fi

echo "✓ Python version: $(python3 --version)"

# Check if requirements are installed
echo ""
echo "📦 التحقق من المتطلبات / Checking requirements..."

if ! python3 -c "import telebot" &> /dev/null; then
    echo "⚠️  المتطلبات غير مثبتة / Requirements not installed"
    echo "   جاري التثبيت... / Installing..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ فشل تثبيت المتطلبات / Failed to install requirements"
        exit 1
    fi
else
    echo "✓ جميع المتطلبات مثبتة / All requirements installed"
fi

# Check if .env file exists
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo ""
        echo "⚠️  ملف .env غير موجود / .env file not found"
        echo "   يرجى نسخ .env.example إلى .env وتعديل الإعدادات"
        echo "   Please copy .env.example to .env and update settings"
        echo ""
        echo "   cp .env.example .env"
        echo "   ثم عدل ملف .env بتوكن البوت الخاص بك"
        echo ""
    fi
fi

# Check if BOT_TOKEN is set in App.py
if grep -q "YOUR_BOT_TOKEN_HERE" App.py 2>/dev/null; then
    echo ""
    echo "⚠️  تحذير: لم يتم تعيين توكن البوت!"
    echo "   Warning: Bot token not configured!"
    echo ""
    echo "   يرجى تعديل ملف App.py واستبدال:"
    echo "   Please edit App.py and replace:"
    echo "   BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'"
    echo "   مع توكن البوت الخاص بك من @BotFather"
    echo "   with your bot token from @BotFather"
    echo ""
fi

echo ""
echo "=================================================="
echo "🚀 بدء تشغيل البوت / Starting bot..."
echo "=================================================="
echo ""
echo "للإيقاف: اضغط Ctrl+C / To stop: press Ctrl+C"
echo ""

# Run the bot
python3 App.py
