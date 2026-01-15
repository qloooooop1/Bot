# 🚀 دليل البدء السريع | Quick Start Guide

## العربية

### الخطوات السريعة للتشغيل:

#### 1. الحصول على توكن البوت
- افتح تيليجرام وابحث عن [@BotFather](https://t.me/BotFather)
- أرسل الأمر `/newbot`
- اتبع التعليمات لإنشاء بوت جديد
- احتفظ بالتوكن (Token) الذي سيعطيك إياه

#### 2. تثبيت المشروع
```bash
git clone https://github.com/qloooooop1/Bot.git
cd Bot
pip install -r requirements.txt
```

#### 3. إعداد التوكن
افتح ملف `App.py` وابحث عن السطر:
```python
BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'
```
استبدل `YOUR_BOT_TOKEN_HERE` بالتوكن الذي حصلت عليه من BotFather

#### 4. تشغيل البوت
```bash
python App.py
```
أو استخدم السكريبت:
```bash
./start.sh
```

#### 5. إضافة البوت للمجموعة
- أضف البوت إلى مجموعتك على تيليجرام
- تأكد من منح البوت صلاحية إرسال الرسائل
- البوت سيبدأ العمل تلقائياً!

### الأوامر الأساسية للمشرفين:

```
/start - بدء البوت
/help - المساعدة
/settings - عرض الإعدادات
/set_interval <دقائق> - تغيير الفاصل الزمني
/enable_morning - تفعيل أذكار الصباح
/disable_morning - إلغاء أذكار الصباح
/enable_evening - تفعيل أذكار المساء
/disable_evening - إلغاء أذكار المساء
/enable_friday - تفعيل أذكار الجمعة
/disable_friday - إلغاء أذكار الجمعة
/enable_random - تفعيل المحتوى العشوائي
/disable_random - إلغاء المحتوى العشوائي
```

### المواعيد الافتراضية:

- **أذكار الصباح**: 5:00 صباحاً
- **أذكار المساء**: 6:00 مساءً
- **أدعية الجمعة**: 10:00 صباحاً (كل جمعة)
- **سورة الكهف**: 11:00 صباحاً (كل جمعة)
- **تذكير النوم**: 10:00 مساءً
- **محتوى عشوائي**: كل ساعة من 6 صباحاً - 5 مساءً (النصف ساعة)

### تخصيص المواعيد:

افتح ملف `App.py` وابحث عن دالة `setup_scheduler()` لتعديل المواعيد:

```python
# مثال: تغيير موعد أذكار الصباح إلى 6:00 صباحاً
scheduler.add_job(
    send_morning_adhkar,
    CronTrigger(hour=6, minute=0, timezone=TIMEZONE),
    ...
)
```

---

## English

### Quick Setup Steps:

#### 1. Get Bot Token
- Open Telegram and search for [@BotFather](https://t.me/BotFather)
- Send `/newbot` command
- Follow instructions to create a new bot
- Save the Token that BotFather gives you

#### 2. Install Project
```bash
git clone https://github.com/qloooooop1/Bot.git
cd Bot
pip install -r requirements.txt
```

#### 3. Configure Token
Open `App.py` file and find the line:
```python
BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'
```
Replace `YOUR_BOT_TOKEN_HERE` with your bot token from BotFather

#### 4. Run the Bot
```bash
python App.py
```
Or use the startup script:
```bash
./start.sh
```

#### 5. Add Bot to Your Group
- Add the bot to your Telegram group
- Make sure the bot has permission to send messages
- The bot will start working automatically!

### Basic Admin Commands:

```
/start - Start the bot
/help - Show help
/settings - Display settings
/set_interval <minutes> - Change time interval
/enable_morning - Enable morning adhkar
/disable_morning - Disable morning adhkar
/enable_evening - Enable evening adhkar
/disable_evening - Disable evening adhkar
/enable_friday - Enable Friday adhkar
/disable_friday - Disable Friday adhkar
/enable_random - Enable random content
/disable_random - Disable random content
```

### Default Schedule:

- **Morning Adhkar**: 5:00 AM
- **Evening Adhkar**: 6:00 PM
- **Friday Dua**: 10:00 AM (Every Friday)
- **Surah Al-Kahf**: 11:00 AM (Every Friday)
- **Bedtime Reminder**: 10:00 PM
- **Random Content**: Every hour from 6 AM - 5 PM (at half past)

### Customize Schedule:

Open `App.py` and find the `setup_scheduler()` function to modify times:

```python
# Example: Change morning adhkar to 6:00 AM
scheduler.add_job(
    send_morning_adhkar,
    CronTrigger(hour=6, minute=0, timezone=TIMEZONE),
    ...
)
```

---

## 🔧 Troubleshooting | حل المشاكل

### البوت لا يرسل رسائل | Bot doesn't send messages
- تأكد من أن التوكن صحيح | Make sure the token is correct
- تأكد من أن البوت لديه صلاحيات في المجموعة | Ensure bot has permissions in group
- تحقق من السجلات (logs) للأخطاء | Check logs for errors

### تغيير المنطقة الزمنية | Change Timezone
في ملف `App.py` | In `App.py` file:
```python
TIMEZONE = pytz.timezone('Asia/Riyadh')  # غير هذا | Change this
```

أمثلة | Examples:
- `'Asia/Riyadh'` - السعودية
- `'Asia/Dubai'` - الإمارات
- `'Asia/Kuwait'` - الكويت
- `'Asia/Qatar'` - قطر
- `'Africa/Cairo'` - مصر

---

## 📧 الدعم | Support

إذا واجهت مشاكل، افتح Issue في GitHub:
If you face issues, open an Issue on GitHub:

https://github.com/qloooooop1/Bot/issues

---

بارك الله فيكم 🤲
May Allah bless you
