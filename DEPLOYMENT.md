# دليل النشر - بوت الأذكار الإسلامية

## نظرة عامة

يدعم البوت طريقتين للتشغيل:
1. **Long Polling**: للتطوير والاختبار المحلي
2. **Webhook**: للإنتاج والنشر على الخوادم

## النشر على Vercel

### 1. الإعداد

قم بإنشاء ملف `vercel.json` (موجود بالفعل):

```json
{
  "version": 2,
  "builds": [
    {
      "src": "App.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "App.py"
    }
  ]
}
```

### 2. متغيرات البيئة

في لوحة تحكم Vercel، أضف:
- `BOT_TOKEN`: توكن البوت
- `BOT_MODE`: `webhook`

### 3. النشر

```bash
# تثبيت Vercel CLI
npm i -g vercel

# النشر
vercel --prod
```

### 4. تعيين Webhook

بعد النشر، افتح:
```
https://your-project.vercel.app/setwebhook?url=https://your-project.vercel.app
```

## النشر على Heroku

### 1. إنشاء ملف Procfile

```
web: python App.py
```

### 2. متغيرات البيئة

```bash
heroku config:set BOT_TOKEN=your_token_here
heroku config:set BOT_MODE=webhook
```

### 3. النشر

```bash
# تسجيل الدخول
heroku login

# إنشاء تطبيق
heroku create your-app-name

# دفع الكود
git push heroku main

# تعيين webhook
heroku open /setwebhook?url=https://your-app.herokuapp.com
```

## النشر على Render

### 1. إنشاء Web Service

في لوحة تحكم Render:
- اختر "New Web Service"
- اربط مستودع GitHub
- اختر Python 3

### 2. إعدادات البيئة

```
BOT_TOKEN=your_token_here
BOT_MODE=webhook
```

### 3. أمر البدء

```
python App.py
```

### 4. تعيين Webhook

افتح:
```
https://your-service.onrender.com/setwebhook?url=https://your-service.onrender.com
```

## النشر على VPS (Ubuntu/Debian)

### 1. تثبيت المتطلبات

```bash
# تحديث النظام
sudo apt update && sudo apt upgrade -y

# تثبيت Python و pip
sudo apt install python3 python3-pip -y

# استنساخ المشروع
git clone https://github.com/yourusername/Bot.git
cd Bot

# تثبيت المتطلبات
pip3 install -r requirements.txt
```

### 2. إنشاء ملف خدمة systemd

```bash
sudo nano /etc/systemd/system/azkar-bot.service
```

محتوى الملف:

```ini
[Unit]
Description=Islamic Azkar Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/Bot
Environment="BOT_TOKEN=your_token_here"
Environment="BOT_MODE=polling"
ExecStart=/usr/bin/python3 App.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### 3. تشغيل الخدمة

```bash
# إعادة تحميل systemd
sudo systemctl daemon-reload

# تفعيل الخدمة
sudo systemctl enable azkar-bot

# بدء الخدمة
sudo systemctl start azkar-bot

# التحقق من الحالة
sudo systemctl status azkar-bot

# عرض السجلات
journalctl -u azkar-bot -f
```

## النشر باستخدام Docker

### 1. إنشاء Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "App.py"]
```

### 2. إنشاء docker-compose.yml

```yaml
version: '3.8'

services:
  azkar-bot:
    build: .
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - BOT_MODE=polling
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

### 3. التشغيل

```bash
# بناء الصورة
docker-compose build

# تشغيل الحاوية
docker-compose up -d

# عرض السجلات
docker-compose logs -f

# إيقاف الحاوية
docker-compose down
```

## النشر على Railway

### 1. إعداد المشروع

في لوحة تحكم Railway:
- اختر "New Project"
- اختر "Deploy from GitHub repo"
- حدد المستودع

### 2. متغيرات البيئة

```
BOT_TOKEN=your_token_here
BOT_MODE=webhook
```

### 3. Railway سيقوم بالنشر تلقائياً

### 4. تعيين Webhook

```
https://your-project.railway.app/setwebhook?url=https://your-project.railway.app
```

## اختيار وضع التشغيل

### Long Polling (polling)
**المزايا:**
- سهل الإعداد
- لا يحتاج إلى domain أو SSL
- مثالي للتطوير والاختبار

**العيوب:**
- يستهلك موارد أكثر
- اتصال مستمر بالخوادم

**متى تستخدمه:**
- التطوير المحلي
- VPS الخاص
- عدم توفر domain

### Webhook (webhook)
**المزايا:**
- كفاءة أعلى
- استهلاك موارد أقل
- الخيار الأمثل للإنتاج

**العيوب:**
- يحتاج إلى HTTPS
- يحتاج إلى domain

**متى تستخدمه:**
- النشر على Vercel/Heroku
- المواقع الإنتاجية
- عند توفر domain

## نصائح مهمة

### الأمان
1. **لا تشارك توكن البوت أبداً**
2. استخدم متغيرات البيئة
3. أضف `.env` إلى `.gitignore`

### الأداء
1. استخدم webhook للإنتاج
2. راقب استخدام الذاكرة
3. استخدم قاعدة بيانات خارجية للمشاريع الكبيرة

### الصيانة
1. راقب السجلات بانتظام
2. احتفظ بنسخة احتياطية من قاعدة البيانات
3. قم بتحديث المكتبات بانتظام

## استكشاف الأخطاء

### البوت لا يستجيب
```bash
# تحقق من السجلات
journalctl -u azkar-bot -n 50

# تحقق من webhook
curl https://your-domain.com/webhookinfo
```

### أخطاء الجدولة
```bash
# أعد تشغيل البوت
sudo systemctl restart azkar-bot

# تحقق من التوقيت الزمني
timedatectl
```

### مشاكل قاعدة البيانات
```bash
# النسخ الاحتياطي
cp azkar_bot.db azkar_bot.db.backup

# إعادة الإنشاء
rm azkar_bot.db
sudo systemctl restart azkar-bot
```

## الدعم

إذا واجهت أي مشاكل:
1. راجع السجلات
2. تحقق من متغيرات البيئة
3. تأكد من صلاحيات البوت في المجموعة

---

**بالتوفيق في نشر البوت! 🚀**
