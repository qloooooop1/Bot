# دليل الميزات الجديدة - New Features Guide

## نظرة عامة (Overview)

تم إضافة مجموعة من الميزات الجديدة لبوت نور الأذكار لتوفير إعدادات منفصلة لكل مجموعة وإضافة أدعية متنوعة مع مواعيد نشر محددة.

Several new features have been added to the Nour Adhkar bot to provide separate settings for each group and add diverse duas with specific posting schedules.

---

## 1. إعدادات منفصلة لكل مجموعة (Separate Settings per Group)

### قاعدة البيانات (Database)

تم إنشاء جداول جديدة في قاعدة البيانات:

- `diverse_azkar_settings`: إعدادات الأدعية المتنوعة
- `ramadan_settings`: إعدادات رمضان
- `hajj_eid_settings`: إعدادات الحج والعيد

كل مجموعة لها إعداداتها الخاصة المستقلة عن المجموعات الأخرى.

### لوحة التحكم (Control Panel)

يمكن للمشرفين استخدام الأمر `/settings` في المجموعة لتعديل الإعدادات الخاصة بها.

---

## 2. الأدعية المتنوعة (Diverse Azkar)

### الوصف (Description)

ميزة جديدة لإرسال أدعية وآيات وأحاديث متنوعة بشكل دوري.

### الفواصل الزمنية المتاحة (Available Intervals)

- 1 دقيقة (1 minute)
- 5 دقائق (5 minutes)
- 15 دقيقة (15 minutes)
- 1 ساعة (1 hour)
- 2 ساعة (2 hours)
- 4 ساعات (4 hours)
- 8 ساعات (8 hours)
- 12 ساعة (12 hours)
- 24 ساعة (24 hours / 1 day)

### التفعيل (Activation)

1. استخدم `/settings` في المجموعة
2. اضغط على "✨ الأدعية المتنوعة"
3. اختر الفاصل الزمني المناسب
4. سيتم تفعيل الميزة تلقائياً

### المحتوى (Content)

- أدعية مأثورة 🤲
- آيات قرآنية 📖
- أحاديث نبوية ✨

الملف: `azkar/diverse_azkar.json`

---

## 3. إعدادات رمضان (Ramadan Settings)

### الأقسام المتاحة (Available Sections)

#### 3.1 أذكار رمضان العامة
- دعاء الإفطار
- أدعية رمضانية عامة

#### 3.2 ليلة القدر
- أدعية خاصة بليلة القدر
- "اللهم إنك عفو تحب العفو فاعف عني"

#### 3.3 العشر الأواخر
- أدعية خاصة بالعشر الأواخر من رمضان

#### 3.4 دعاء الإفطار
- يُرسل قبل أذان المغرب

### الملفات (Files)

- `azkar/ramadan.json`
- `azkar/laylat_alqadr.json`
- `azkar/last_ten_days.json`

---

## 4. إعدادات الحج والعيد (Hajj & Eid Settings)

### أقسام الحج (Hajj Sections)

#### 4.1 يوم عرفة
- أدعية يوم عرفة (9 ذو الحجة)
- "خير الدعاء دعاء يوم عرفة"
- الملف: `azkar/arafah.json`

#### 4.2 أذكار الحج
- التلبية
- أدعية الحج والعمرة
- الملف: `azkar/hajj.json`

### أقسام العيد (Eid Sections)

#### 4.3 ليلة العيد
- أدعية ليلة العيد المباركة
- تُرسل في ليلة 29 أو 30 رمضان

#### 4.4 يوم العيد
- تكبيرات العيد
- أدعية يوم العيد
- الملف: `azkar/eid.json`

#### 4.5 عيد الأضحى
- تكبيرات وأدعية خاصة بعيد الأضحى (10 ذو الحجة)

---

## 5. هيكلية الوسائط (Media Structure)

### ملفات JSON الجديدة (New JSON Files)

#### 5.1 audio.json
هيكلية الملفات الصوتية:
```json
{
  "audio": [
    {
      "id": "audio_001",
      "category": "حج",
      "url": "",
      "file_id": "",
      "title": "تلبية الحج",
      "description": "لبيك اللهم لبيك",
      "duration_seconds": 0,
      "enabled": true
    }
  ]
}
```

الفئات المتاحة:
- حج
- عيد
- رمضان
- عرفة
- ليلة القدر
- أذكار

#### 5.2 images.json
هيكلية الصور:
```json
{
  "images": [
    {
      "id": "img_hajj_001",
      "category": "حج",
      "url": "",
      "file_id": "",
      "title": "الكعبة المشرفة",
      "description": "صورة للكعبة",
      "enabled": true
    }
  ]
}
```

الفئات المتاحة:
- حج
- عيد
- رمضان
- إسلامي

### كيفية إضافة الوسائط (How to Add Media)

1. أرسل الوسيط (صورة/صوت) للبوت في محادثة خاصة
2. احصل على `file_id` من Telegram
3. أضف `file_id` إلى الملف المناسب (audio.json أو images.json)
4. حدد الفئة المناسبة (`category`)
5. تأكد من تفعيل الوسيط (`"enabled": true`)

---

## 6. دوال الإرسال التلقائي (Automated Sending Functions)

### send_diverse_azkar(chat_id)
إرسال أذكار متنوعة حسب الفاصل الزمني المحدد

### send_special_azkar(chat_id, azkar_type)
إرسال أذكار خاصة بالمناسبات:
- `ramadan`: أذكار رمضان
- `laylat_alqadr`: ليلة القدر
- `last_ten_days`: العشر الأواخر
- `arafah`: يوم عرفة
- `hajj`: أذكار الحج
- `eid`: يوم العيد
- `eid_adha`: عيد الأضحى

---

## 7. الأوامر المتاحة (Available Commands)

### للمشرفين في المجموعات (For Admins in Groups)

- `/settings` - فتح لوحة التحكم
- `/status` - عرض حالة البوت
- `/enable` - تفعيل البوت
- `/disable` - تعطيل البوت
- `/settime <type> <time>` - تعديل الأوقات

### في المحادثات الخاصة (In Private Chats)

- `/start` - بدء المحادثة مع البوت

---

## 8. ملاحظات مهمة (Important Notes)

### الأمان (Security)

- جميع الإعدادات محمية بصلاحيات المشرفين فقط
- كل مجموعة لها إعداداتها المستقلة
- لا يمكن للمستخدمين العاديين تعديل الإعدادات

### الأداء (Performance)

- يستخدم البوت جدولة ذكية لتقليل الحمل على الخادم
- الوسائط يتم اختيارها عشوائياً من القاعدة
- يتم حفظ آخر وقت إرسال لتجنب التكرار

### التخصيص (Customization)

- يمكن تعديل الفواصل الزمنية لكل مجموعة على حدة
- يمكن تفعيل/تعطيل أي قسم بشكل منفصل
- يمكن اختيار نوع الوسائط (نص، صور، صوت)

---

## 9. التطويرات المستقبلية (Future Enhancements)

- [ ] إضافة تفعيل تلقائي حسب التاريخ الهجري
- [ ] دعم التقويم الإسلامي للمناسبات
- [ ] إضافة المزيد من الأدعية والأحاديث
- [ ] دعم لغات إضافية
- [ ] إحصائيات مفصلة للمشرفين

---

## 10. الدعم (Support)

للمساعدة والدعم:
- المجموعة الرسمية: https://t.me/NourAdhkar
- المطور: https://t.me/dev3bod

---

## Technical Implementation Details

### Database Schema

#### diverse_azkar_settings
```sql
CREATE TABLE diverse_azkar_settings (
    chat_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    interval_minutes INTEGER DEFAULT 60,
    media_type TEXT DEFAULT 'text',
    last_sent_timestamp INTEGER DEFAULT 0,
    FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id)
)
```

#### ramadan_settings
```sql
CREATE TABLE ramadan_settings (
    chat_id INTEGER PRIMARY KEY,
    ramadan_enabled INTEGER DEFAULT 1,
    laylat_alqadr_enabled INTEGER DEFAULT 1,
    last_ten_days_enabled INTEGER DEFAULT 1,
    iftar_dua_enabled INTEGER DEFAULT 1,
    media_type TEXT DEFAULT 'images',
    FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id)
)
```

#### hajj_eid_settings
```sql
CREATE TABLE hajj_eid_settings (
    chat_id INTEGER PRIMARY KEY,
    arafah_day_enabled INTEGER DEFAULT 1,
    eid_eve_enabled INTEGER DEFAULT 1,
    eid_day_enabled INTEGER DEFAULT 1,
    eid_adha_enabled INTEGER DEFAULT 1,
    hajj_enabled INTEGER DEFAULT 1,
    media_type TEXT DEFAULT 'images',
    FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id)
)
```

### API Functions

#### Helper Functions
- `get_diverse_azkar_settings(chat_id)`: Get diverse azkar settings
- `update_diverse_azkar_setting(chat_id, key, value)`: Update setting
- `get_ramadan_settings(chat_id)`: Get Ramadan settings
- `update_ramadan_setting(chat_id, key, value)`: Update setting
- `get_hajj_eid_settings(chat_id)`: Get Hajj/Eid settings
- `update_hajj_eid_setting(chat_id, key, value)`: Update setting

#### Content Loading
- `load_diverse_azkar()`: Load diverse azkar from JSON
- `get_random_diverse_azkar()`: Get random diverse azkar item
- `load_ramadan_azkar()`: Load Ramadan azkar
- `load_laylat_alqadr_azkar()`: Load Laylat al-Qadr azkar
- `load_last_ten_days_azkar()`: Load Last Ten Days azkar
- `load_arafah_azkar()`: Load Arafah azkar
- `load_hajj_azkar()`: Load Hajj azkar
- `load_eid_azkar()`: Load Eid azkar

#### Media Functions
- `load_audio_database()`: Load audio.json
- `load_images_database()`: Load images.json
- `get_random_media_by_category(category, media_type)`: Get media by category

#### Sending Functions
- `send_diverse_azkar(chat_id)`: Send diverse azkar
- `send_special_azkar(chat_id, azkar_type)`: Send special occasion azkar

---

تم بحمد الله ✨
