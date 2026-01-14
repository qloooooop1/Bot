# 📋 Deployment Guide - Islamic Telegram Bot

## Quick Start

### 1. Prerequisites
- Python 3.7+
- Telegram Bot Token (from @BotFather)
- Group Chat ID
- Vercel Account (for deployment)

### 2. Local Testing

```bash
# Clone repository
git clone https://github.com/qloooooop1/Bot.git
cd Bot

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export BOT_TOKEN="your-bot-token"
export ALLOWED_CHAT_ID="-1001234567890"
export WEBHOOK_DOMAIN="localhost:5000"  # For local testing

# Run locally
python App.py
```

### 3. Vercel Deployment

#### Step 1: Configure Environment Variables in Vercel
```bash
vercel env add BOT_TOKEN
# Enter your bot token when prompted

vercel env add WEBHOOK_DOMAIN
# Enter your-app-name.vercel.app when prompted

# Optional: For multiple environments
vercel env add DATABASE_FILE
# Enter bot_database.db or custom path
```

#### Step 2: Deploy
```bash
vercel --prod
```

#### Step 3: Initialize Bot
1. Visit: `https://your-app-name.vercel.app/`
2. This will set the webhook automatically
3. Bot is now ready!

### 4. Bot Configuration

#### Add Bot to Group
1. Add bot to your Telegram group
2. Make bot an admin with these permissions:
   - Delete messages
   - Restrict members
   - Pin messages (optional)
   - Invite users via link (optional)

#### Configure Location for Prayer Times
```
/ضبط_الموقع 24.7136 46.6753
```
(Example: Riyadh coordinates)

#### Add Offensive Words (Optional)
```
/اضافة_كلمة_محظورة word_to_filter
```

### 5. Enable Automated Features

To enable scheduled messages, add these settings to database:

```sql
INSERT INTO admin_settings (setting_key, setting_value) VALUES
('auto_morning_azkar', '1'),
('auto_evening_azkar', '1'),
('auto_daily_tip', '1');
```

Or wait for admin panel commands to be added.

### 6. Testing Commands

Try these commands in your group:

```
/start - Welcome message
/اذكار_الصباح - Morning azkar
/سؤال - Quiz question
/مواقيت_الصلاة - Prayer times
/التقويم_الهجري - Hijri calendar
/نقاطي - Check your points
/ترتيب - View leaderboard
```

## Configuration Files

### vercel.json
Already configured in `Json.JSON`:
```json
{
  "version": 2,
  "builds": [
    {
      "src": "app.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "app.py"
    }
  ]
}
```

**Note:** You may need to rename `App.py` to `app.py` (lowercase) to match the vercel.json configuration.

### Environment Variables (Vercel Dashboard)

| Variable | Description | Example |
|----------|-------------|---------|
| `BOT_TOKEN` | Your Telegram bot token | `123456:ABC-DEF...` |
| `WEBHOOK_DOMAIN` | Your Vercel app domain | `mybot.vercel.app` |
| `ALLOWED_CHAT_ID` | Your group chat ID | `-1001234567890` |
| `DATABASE_FILE` | Database filename (optional) | `bot_database.db` |

## Troubleshooting

### Bot doesn't respond
1. Check if webhook is set: Visit your app URL
2. Verify bot is admin in the group
3. Check ALLOWED_CHAT_ID matches your group
4. View Vercel logs for errors

### Prayer times not showing
1. Make sure location is configured: `/ضبط_الموقع lat lon`
2. Check internet connectivity (API call)
3. Verify coordinates are correct

### Scheduled tasks not running
1. Vercel free tier has limitations
2. Consider using cron jobs for scheduled tasks
3. Or upgrade to Vercel Pro

### Database not persisting
1. Vercel serverless functions are stateless
2. Consider using external database (PostgreSQL, MongoDB)
3. Or use Vercel KV storage

## Production Best Practices

### Security
1. ✅ Use environment variables (not hardcoded values)
2. ✅ Keep bot token secret
3. ✅ Restrict to specific chat ID
4. ✅ Admin permission checks in place

### Performance
1. Database connection pooling
2. Cache prayer times API responses
3. Rate limiting on commands
4. Optimize database queries

### Monitoring
1. Set up error logging
2. Monitor API usage
3. Track user engagement
4. Watch scheduled task execution

## Maintenance

### Adding Quiz Questions
Edit `QUIZ_QUESTIONS` list in `App.py`:
```python
QUIZ_QUESTIONS.append({
    'question': 'New question?',
    'options': ['A', 'B', 'C', 'D'],
    'correct': 2,  # Index of correct answer
    'explanation': 'Explanation here'
})
```

### Adding Azkar
Edit `AZKAR_DATA` dictionary in `App.py`:
```python
AZKAR_DATA['new_category'] = [
    "First azkar",
    "Second azkar",
    # ...
]
```

### Adding Islamic Events
Edit `ISLAMIC_EVENTS` dictionary:
```python
ISLAMIC_EVENTS['event_name'] = {
    'hijri_month': 9,
    'hijri_day': 1,
    'message': 'Event message'
}
```

## Support

For issues and questions:
1. Check IMPLEMENTATION_NOTES.md
2. Review README.md
3. Open GitHub issue
4. Contact @AlRASD1_BOT

## License

Open source - free to use and modify.

---

**May Allah accept this work and make it beneficial for Muslims worldwide** 🤲
