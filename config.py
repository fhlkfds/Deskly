import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration."""

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///database.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Google Sheets
    GOOGLE_SHEETS_CREDENTIALS_FILE = os.getenv('GOOGLE_SHEETS_CREDENTIALS_FILE', 'credentials.json')
    GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv('GOOGLE_SHEETS_SPREADSHEET_ID', '')
    GOOGLE_ADMIN_CREDENTIALS_FILE = os.getenv('GOOGLE_ADMIN_CREDENTIALS_FILE', 'credentials.json')
    GOOGLE_ADMIN_DELEGATED_ADMIN_EMAIL = os.getenv('GOOGLE_ADMIN_DELEGATED_ADMIN_EMAIL', '')
    GOOGLE_ADMIN_CUSTOMER_ID = os.getenv('GOOGLE_ADMIN_CUSTOMER_ID', 'my_customer')
    GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')
    GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')
    GOOGLE_OAUTH_REDIRECT_URI = os.getenv('GOOGLE_OAUTH_REDIRECT_URI', '')
    MICROSOFT_OAUTH_CLIENT_ID = os.getenv('MICROSOFT_OAUTH_CLIENT_ID', '')
    MICROSOFT_OAUTH_CLIENT_SECRET = os.getenv('MICROSOFT_OAUTH_CLIENT_SECRET', '')
    MICROSOFT_OAUTH_TENANT_ID = os.getenv('MICROSOFT_OAUTH_TENANT_ID', 'common')
    MICROSOFT_OAUTH_REDIRECT_URI = os.getenv('MICROSOFT_OAUTH_REDIRECT_URI', '')
    DOCS_DRIVE_CREDENTIALS_FILE = os.getenv('DOCS_DRIVE_CREDENTIALS_FILE', '')
    DOCS_DRIVE_FOLDER_ID = os.getenv('DOCS_DRIVE_FOLDER_ID', '')
    GMAIL_CREDENTIALS_FILE = os.getenv('GMAIL_CREDENTIALS_FILE', '')
    GMAIL_DELEGATED_USER = os.getenv('GMAIL_DELEGATED_USER', '')
    GMAIL_IMPORT_QUERY = os.getenv('GMAIL_IMPORT_QUERY', 'is:unread')
    GMAIL_IMPORT_MAX_RESULTS = int(os.getenv('GMAIL_IMPORT_MAX_RESULTS', 25))
    TICKET_GMAIL_IMPORT_INTERVAL_MINUTES = int(os.getenv('TICKET_GMAIL_IMPORT_INTERVAL_MINUTES', 5))

    # Sync settings
    SYNC_INTERVAL_MINUTES = int(os.getenv('SYNC_INTERVAL_MINUTES', 5))
    GOOGLE_ADMIN_SYNC_SCHEDULER_INTERVAL_MINUTES = int(os.getenv('GOOGLE_ADMIN_SYNC_SCHEDULER_INTERVAL_MINUTES', 5))

    # Pagination
    ITEMS_PER_PAGE = 25

    # Email (for report delivery)
    SMTP_HOST = os.getenv('SMTP_HOST', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
    REPORTS_FROM_EMAIL = os.getenv('REPORTS_FROM_EMAIL', SMTP_USERNAME or 'noreply@school.edu')

    # Audit snapshot scheduler
    SNAPSHOT_SCHEDULER_INTERVAL_MINUTES = int(os.getenv('SNAPSHOT_SCHEDULER_INTERVAL_MINUTES', 5))
