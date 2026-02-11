# K-12 School Inventory System

A comprehensive inventory management system for K-12 schools, built with Flask. Manage tech devices (laptops, tablets), IT infrastructure (projectors, printers, smart boards, servers, VMs, Docker containers), and more with easy checkout/checkin workflows and two-way Google Sheets synchronization.

## Features

- **Asset Management**: Track all school assets with detailed information
- **Easy Checkout/Checkin**: Streamlined workflows for lending and returning assets
- **Google Sheets Integration**: Two-way synchronization with Google Sheets
- **Dashboard**: Real-time overview of inventory status
- **User Authentication**: Role-based access control (admin/staff/teacher)
- **Checkout History**: Complete audit trail of all transactions
- **Responsive Design**: Works on desktop, tablet, and mobile devices

## Technology Stack

- **Backend**: Python 3.x with Flask
- **Database**: SQLite (easy upgrade to PostgreSQL)
- **Frontend**: Bootstrap 5, HTML5
- **Authentication**: Flask-Login
- **ORM**: SQLAlchemy
- **Google API**: gspread, google-auth

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Git

### Setup Instructions

1. **Clone the repository** (or download the project):
   ```bash
   cd /path/to/project
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and configure your settings:
   ```
   SECRET_KEY=your-secret-key-here-change-in-production
   DATABASE_URL=sqlite:///database.db
   GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
   GOOGLE_SHEETS_SPREADSHEET_ID=your-spreadsheet-id-here
   SYNC_INTERVAL_MINUTES=5
   ```

5. **Initialize the database**:
   The database will be automatically created when you first run the application.

6. **Run the application**:
   ```bash
   python app.py
   ```

7. **Access the application**:
   Open your browser and navigate to `http://localhost:5000`

## Default Login Credentials

After first run, use these credentials to log in:

- **Admin User**:
  - Email: `admin@school.edu`
  - Password: `admin123`

- **Staff User**:
  - Email: `staff@school.edu`
  - Password: `staff123`

**⚠️ IMPORTANT**: Change these passwords immediately after first login!

## Google Sheets Integration Setup

To enable two-way synchronization with Google Sheets:

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Google Sheets API**:
   - Go to "APIs & Services" > "Library"
   - Search for "Google Sheets API"
   - Click "Enable"

### 2. Create Service Account Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "Service Account"
3. Fill in the service account details
4. Click "Create and Continue"
5. Skip granting additional roles (click "Continue")
6. Click "Done"

### 3. Download Credentials

1. Click on the service account you just created
2. Go to the "Keys" tab
3. Click "Add Key" > "Create New Key"
4. Choose "JSON" format
5. Click "Create" - the credentials file will download
6. Rename the file to `credentials.json` and place it in the project root directory

### 4. Share Your Google Sheet

1. Create a new Google Sheet or use an existing one
2. Copy the spreadsheet ID from the URL:
   - URL format: `https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit`
3. Open the `credentials.json` file and copy the service account email (looks like: `name@project-id.iam.gserviceaccount.com`)
4. Share your Google Sheet with this email address (give it "Editor" permissions)

### 5. Configure the Application

1. Update your `.env` file with the spreadsheet ID:
   ```
   GOOGLE_SHEETS_SPREADSHEET_ID=your-spreadsheet-id-here
   ```

2. Uncomment the scheduler initialization in `app.py`:
   ```python
   # Initialize scheduler
   init_scheduler(app)
   ```

3. Restart the application

### 6. Test the Connection

1. Log in as an admin user
2. Go to Settings > Sync
3. Click "Test Connection" to verify the setup
4. Run a manual sync to test the integration

## Usage Guide

### Adding Assets

1. Click "Add Asset" from the Dashboard or Assets page
2. Fill in the asset details:
   - **Asset Tag** (required): Unique identifier
   - **Name** (required): Asset name/model
   - **Category**: Technology, IT Infrastructure, etc.
   - **Type**: Laptop, Tablet, Projector, etc.
   - **Serial Number**: Manufacturer serial number
   - **Location**: Where the asset is located
   - **Status**: Available, Checked Out, Maintenance, Retired
   - **Condition**: Good, Fair, Needs Repair
   - **Purchase Date & Cost**: Optional financial tracking
   - **Notes**: Additional information
3. Click "Create Asset"

### Checking Out Assets

1. Go to Checkouts > Check Out
2. Select an available asset from the dropdown
3. Enter the name of the person receiving the asset
4. Optionally set an expected return date
5. Click "Check Out Asset"

The asset status will automatically change to "Checked Out"

### Checking In Assets

1. Go to Checkouts > Check In
2. Select the checked-out asset
3. Record the asset condition (Good/Fair/Needs Repair)
4. Add any notes about damage or issues
5. Click "Check In Asset"

The asset status will automatically change back to "Available"

### Viewing Reports

- **Dashboard**: Overview of all assets and recent activity
- **Assets**: Browse, filter, and search all assets
- **Checkout History**: View all checkout/checkin transactions
- **Asset Detail**: See complete history for a specific asset

### Google Sheets Sync

The system automatically syncs with Google Sheets every 5 minutes (configurable).

**Manual Sync Options**:
- **Import from Sheets**: Update database from Google Sheets
- **Export to Sheets**: Write database to Google Sheets
- **Bidirectional Sync**: Both import and export

## Project Structure

```
inventory/
├── app.py                      # Main Flask application
├── config.py                   # Configuration settings
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (create from .env.example)
├── models.py                   # Database models
├── auth.py                     # Authentication
├── assets.py                   # Asset management routes
├── checkouts.py               # Checkout/checkin routes
├── settings.py                # Settings routes
├── sync.py                    # Google Sheets sync
├── scheduler.py               # Background scheduler
├── database.db                # SQLite database (auto-created)
├── static/
│   ├── css/
│   │   └── custom.css         # Custom styles
│   └── js/
├── templates/
│   ├── base.html              # Base template
│   ├── login.html             # Login page
│   ├── dashboard.html         # Dashboard
│   ├── 404.html               # Error pages
│   ├── 500.html
│   ├── assets/
│   │   ├── list.html          # Asset list
│   │   ├── detail.html        # Asset detail
│   │   └── form.html          # Asset form
│   ├── checkouts/
│   │   ├── checkout.html      # Checkout form
│   │   ├── checkin.html       # Checkin form
│   │   └── history.html       # History
│   └── settings/
│       └── sync.html          # Sync settings
└── README.md
```

## Database Schema

### Users
- Authentication and user management
- Roles: admin, staff, teacher

### Assets
- Complete asset information
- Status tracking: available, checked_out, maintenance, retired
- Condition tracking: good, fair, needs_repair

### Checkouts
- Checkout/checkin history
- Links assets to users
- Tracks expected return dates and overdue items

### SyncLog
- Google Sheets synchronization history
- Error tracking and debugging

## Security Considerations

- All passwords are hashed using werkzeug.security
- Environment variables for sensitive data
- Role-based access control
- CSRF protection (recommended: add Flask-WTF)
- Input validation on all forms

## Customization

### Adding New Asset Types

Edit `models.py` and add to the `ASSET_TYPES` list:

```python
ASSET_TYPES = [
    'Laptop',
    'Tablet',
    'Your New Type',
    # ...
]
```

### Changing Sync Interval

Edit `.env`:

```
SYNC_INTERVAL_MINUTES=10  # Sync every 10 minutes
```

### Upgrading to PostgreSQL

1. Install PostgreSQL and psycopg2:
   ```bash
   pip install psycopg2-binary
   ```

2. Update `.env`:
   ```
   DATABASE_URL=postgresql://username:password@localhost/dbname
   ```

3. Restart the application

## Troubleshooting

### Database Issues

- **"Database locked"**: SQLite limitation with concurrent access. Consider upgrading to PostgreSQL.
- **"Table doesn't exist"**: Delete `database.db` and restart the app to recreate tables.

### Google Sheets Sync Issues

- **"Credentials file not found"**: Ensure `credentials.json` is in the project root
- **"Permission denied"**: Verify the Google Sheet is shared with the service account email
- **"Invalid spreadsheet ID"**: Check the ID in your `.env` file matches the URL

### Login Issues

- **"Invalid email or password"**: Use default credentials or reset the database
- **Can't access admin features**: Verify your user role is set to "admin"

## Contributing

This is a custom school inventory system. For modifications:

1. Create a backup of your database before making changes
2. Test changes in a development environment first
3. Document any new features or changes

## License

This project is provided as-is for educational and school use.

## Support

For issues or questions:
- Check the troubleshooting section above
- Review the error logs in the terminal
- Verify your configuration in `.env`

## Acknowledgments

- Built with [Flask](https://flask.palletsprojects.com/)
- UI powered by [Bootstrap 5](https://getbootstrap.com/)
- Icons by [Bootstrap Icons](https://icons.getbootstrap.com/)
