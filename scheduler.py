from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask import Blueprint
from sync import GoogleSheetsSync
from config import Config
import logging

scheduler_bp = Blueprint('scheduler', __name__)
scheduler = BackgroundScheduler()

# Set up logging
logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.INFO)


def sync_job():
    """Background job to sync with Google Sheets."""
    try:
        from app import app
        with app.app_context():
            sync = GoogleSheetsSync()
            result = sync.sync_bidirectional()
            print(f'Scheduled sync completed: {result}')
    except Exception as e:
        print(f'Scheduled sync error: {str(e)}')


def init_scheduler(app):
    """Initialize the background scheduler."""
    if not scheduler.running:
        # Add sync job
        scheduler.add_job(
            func=sync_job,
            trigger=IntervalTrigger(minutes=Config.SYNC_INTERVAL_MINUTES),
            id='google_sheets_sync',
            name='Sync with Google Sheets',
            replace_existing=True
        )

        scheduler.start()
        print(f'Scheduler started - syncing every {Config.SYNC_INTERVAL_MINUTES} minutes')

        # Shut down scheduler when app stops
        import atexit
        atexit.register(lambda: scheduler.shutdown())
