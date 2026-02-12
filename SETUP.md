# Quick Setup Guide

This guide will help you get the K-12 School Inventory System up and running in minutes.

## Quick Start (Recommended)

### Option 1: Using the Quick Start Script

```bash
chmod +x run.sh
./run.sh
```

The script will:
1. Create a virtual environment
2. Install all dependencies
3. Create a `.env` file from template
4. Start the application

### Option 2: Manual Setup

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create environment file
cp .env.example .env

# 4. Run the application
python app.py
```

### Option 3: Docker Deployment

```bash
# 1. Create environment file
cp .env.example .env

# 2. Build and run
docker compose up -d --build

# 3. Open app
# http://localhost:5000
```

Stop the stack:

```bash
docker compose down
```

## First Steps

1. **Access the application**:
   - Open browser to: http://localhost:5000

2. **Login with default credentials**:
   - Email: `admin@school.edu`
   - Password: `admin123`

3. **Change the default password** (Important!)

4. **Start adding assets**:
   - Click "Add Asset" on the dashboard
   - Fill in asset details
   - Save

## Google Sheets Integration (Optional)

If you want to sync with Google Sheets, follow these steps:

### 1. Create Google Cloud Project

1. Go to https://console.cloud.google.com/
2. Create new project
3. Enable Google Sheets API

### 2. Create Service Account

1. Go to "APIs & Services" > "Credentials"
2. Create service account
3. Download JSON credentials
4. Save as `credentials.json` in project root

### 3. Configure Spreadsheet

1. Create a Google Sheet
2. Copy the spreadsheet ID from URL
3. Share sheet with service account email (found in credentials.json)
4. Update `.env`:
   ```
   GOOGLE_SHEETS_SPREADSHEET_ID=your-spreadsheet-id-here
   ```

### 4. Enable Sync

1. Uncomment in `app.py`:
   ```python
   init_scheduler(app)
   ```
2. Restart application
3. Test connection in Settings > Sync

## Directory Structure

```
inventory/
├── Dockerfile          # Container build
├── docker-compose.yml  # Container runtime
├── docker-entrypoint.sh
├── app.py              # Main application
├── models.py           # Database models
├── auth.py            # Authentication
├── assets.py          # Asset management
├── checkouts.py       # Checkout/checkin
├── settings.py        # Settings
├── sync.py            # Google Sheets sync
├── scheduler.py       # Background tasks
├── config.py          # Configuration
├── templates/         # HTML templates
├── static/           # CSS, JS, images
└── database.db       # SQLite database (auto-created)
```

## Common Issues

### Port Already in Use

If port 5000 is already in use, edit `app.py` and change:
```python
app.run(debug=True, host='0.0.0.0', port=5001)  # Change to 5001
```

### Permission Denied on run.sh

Make the script executable:
```bash
chmod +x run.sh
```

### Import Errors

Make sure virtual environment is activated:
```bash
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### Database Locked

SQLite limitation with concurrent users. For production:
1. Install PostgreSQL
2. Update DATABASE_URL in .env
3. Restart application

## Next Steps

1. ✅ Add your school's assets
2. ✅ Create additional user accounts
3. ✅ Set up Google Sheets sync (optional)
4. ✅ Configure automatic backups
5. ✅ Customize asset types and categories

## Production Deployment

For production use:

1. **Change SECRET_KEY** in `.env` to a strong random string
2. **Set DEBUG=False** in `app.py`
3. **Use PostgreSQL** instead of SQLite
4. **Set up HTTPS** with SSL certificate
5. **Use a production WSGI server** (gunicorn, uwsgi)
6. **Set up regular database backups**

Example production run with gunicorn:
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Support

- Check README.md for detailed documentation
- Review error logs in terminal
- Verify .env configuration

---

**Ready to go!** Access your inventory system at http://localhost:5000
