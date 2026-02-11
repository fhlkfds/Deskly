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
