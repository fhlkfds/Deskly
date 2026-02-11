# Getting Started - K-12 School Inventory System

Welcome! This guide will help you start using your new inventory system in just a few minutes.

## 🚀 First-Time Setup (5 minutes)

### Step 1: Install Dependencies

```bash
# Navigate to project directory
cd /home/liam/project/inventory

# Use the quick start script (recommended)
chmod +x run.sh
./run.sh
```

**OR** do it manually:

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env

# Start the application
python app.py
```

### Step 2: Access the Application

1. Open your web browser
2. Go to: **http://localhost:5000**
3. You should see the login page

### Step 3: Login

Use the default admin credentials:
- **Email**: `admin@school.edu`
- **Password**: `admin123`

⚠️ **IMPORTANT**: Change this password after first login!

## 📝 Your First Tasks

### 1. Add Your First Asset (2 minutes)

1. From the Dashboard, click **"Add Asset"**
2. Fill in the form:
   - **Asset Tag**: A unique identifier (e.g., "LT001")
   - **Name**: What is it? (e.g., "Dell Laptop")
   - **Category**: Select from dropdown
   - **Type**: Select asset type
   - **Location**: Where is it? (e.g., "Room 101")
3. Click **"Create Asset"**

That's it! Your first asset is now tracked.

### 2. Check Out an Asset (1 minute)

1. Click **"Check Out Asset"** on the dashboard
2. Select an available asset
3. Enter the person's name who's receiving it
4. Optionally set a return date
5. Click **"Check Out Asset"**

The asset is now marked as checked out!

### 3. Check In an Asset (1 minute)

1. Click **"Check In Asset"** on the dashboard
2. Select the checked-out asset
3. Record the condition (Good/Fair/Needs Repair)
4. Add any notes if needed
5. Click **"Check In Asset"**

The asset is back and available!

## 🎯 Common Workflows

### Adding Multiple Assets

1. Go to **Assets** > **Add Asset**
2. Fill in details for each asset
3. Use a consistent naming scheme for asset tags
   - Laptops: LT001, LT002, LT003...
   - Tablets: TB001, TB002, TB003...
   - Projectors: PR001, PR002, PR003...

### Searching for Assets

1. Go to **Assets**
2. Use the filter options:
   - **Search**: Enter asset tag, name, or serial number
   - **Category**: Filter by category
   - **Type**: Filter by type
   - **Status**: Show only available, checked out, etc.
3. Click **"Filter"**

### Viewing Asset History

1. Go to **Assets**
2. Click **"View"** on any asset
3. Scroll down to see complete checkout history
4. See who had it, when, and in what condition it was returned

### Finding Overdue Items

1. Go to **Dashboard**
2. Look for the red "Overdue Items" alert
3. Click on any overdue asset to see details
4. Contact the person who has it

## 👥 User Management

### Creating Additional Users

Currently, you have two users:
- Admin (admin@school.edu)
- Staff (staff@school.edu)

To add more users, you'll need to add them directly to the database or extend the system with a user management interface.

**Quick way** (for now):
1. Stop the application
2. Open Python shell:
   ```bash
   python
   >>> from app import app, db
   >>> from models import User
   >>> with app.app_context():
   ...     user = User(email='teacher@school.edu', name='Teacher Name', role='staff')
   ...     user.set_password('password123')
   ...     db.session.add(user)
   ...     db.session.commit()
   ```

### User Roles

- **Admin**: Full access to everything including settings
- **Staff**: Can manage assets and checkouts
- **Teacher**: Can manage assets and checkouts (same as staff currently)

## 📊 Understanding the Dashboard

### Summary Cards
- **Total Assets**: All active assets (excluding retired)
- **Available**: Ready to be checked out
- **Checked Out**: Currently with someone
- **Maintenance**: Needs repair or servicing

### Recent Activity
- **Recent Checkouts**: Last 10 checkout transactions
- **Recent Check-ins**: Last 10 return transactions

### Overdue Alert
- Shows when assets haven't been returned by expected date
- Highlighted in red for visibility

## 🔄 Google Sheets Integration (Optional)

If you want to sync with Google Sheets:

1. Follow the detailed setup in **README.md** (Section: Google Sheets Integration Setup)
2. You'll need:
   - Google Cloud account
   - Service account credentials
   - A Google Sheet
3. Once set up, your data syncs automatically every 5 minutes

**Benefits:**
- Share read-only view with others
- Easy reporting and analysis
- Backup of your data
- Collaborative editing

## 🛠️ Customization

### Changing Asset Types

Edit `models.py` around line 85:

```python
ASSET_TYPES = [
    'Laptop',
    'Tablet',
    'Your New Type',  # Add here
    # ...
]
```

### Changing Categories

Edit `models.py` around line 72:

```python
ASSET_CATEGORIES = [
    'Technology',
    'IT Infrastructure',
    'Your New Category',  # Add here
    # ...
]
```

Restart the application after changes.

## 📱 Mobile Access

The system is mobile-friendly! Access it from:
- iPhone/iPad (Safari)
- Android (Chrome)
- Any tablet or smartphone

Same URL: http://localhost:5000

## 💡 Tips & Best Practices

### Asset Tags
- Use a consistent format
- Include location or type in the tag (e.g., "RM101-LT001")
- Make them easy to type and remember

### Locations
- Use consistent naming (e.g., always "Room 101" not "Rm 101")
- Include building if multi-building school
- Use specific locations (e.g., "Library - Tech Cart")

### Checkout Notes
- Record damage or issues immediately
- Include specific details (e.g., "Screen has small crack in corner")
- Note missing accessories (chargers, cases, etc.)

### Expected Return Dates
- Set realistic dates
- Check dashboard regularly for overdue items
- Send reminders before due date

## 🆘 Troubleshooting

### Can't Login
- Check that you're using the correct email and password
- Default: admin@school.edu / admin123
- Try clearing browser cookies

### Assets Not Showing
- Check your filters - you might have filters applied
- Make sure assets aren't retired
- Try searching by asset tag

### Can't Check Out Asset
- Make sure asset status is "Available"
- Check that it's not in maintenance
- Verify it's not already checked out

### Application Won't Start
- Check that port 5000 isn't already in use
- Make sure virtual environment is activated
- Verify all dependencies installed: `pip install -r requirements.txt`

### Database Errors
- Stop the application
- Delete `database.db` file
- Restart - it will recreate with fresh data

## 📚 Additional Resources

- **README.md** - Complete documentation
- **SETUP.md** - Detailed setup instructions
- **TESTING_CHECKLIST.md** - Verify everything works
- **PROJECT_SUMMARY.md** - Technical overview

## ✅ Quick Checklist

After setup, verify these work:

- [ ] Can login
- [ ] Can see dashboard
- [ ] Can add an asset
- [ ] Can check out an asset
- [ ] Can check in an asset
- [ ] Can search for assets
- [ ] Can view asset details
- [ ] Can see checkout history

If all checked, you're ready to go! 🎉

## 🎓 Next Steps

1. **Add Your School's Assets**
   - Start with high-value items
   - Add details like serial numbers
   - Set proper locations

2. **Train Your Staff**
   - Show them how to checkout/checkin
   - Explain the workflow
   - Create user accounts for them

3. **Establish Policies**
   - Set checkout duration limits
   - Define who can check out what
   - Create return procedures

4. **Set Up Google Sheets** (optional)
   - Useful for reports
   - Share with administration
   - Backup your data

5. **Go Live!**
   - Start using it daily
   - Monitor overdue items
   - Keep asset information updated

## 💬 Support

Need help?
1. Check the FAQ in README.md
2. Review error messages in terminal
3. Check TESTING_CHECKLIST.md for verification steps
4. Review the documentation files

---

**You're all set! Happy inventorying! 📦✨**
