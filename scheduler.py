from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask import Blueprint
from sync import GoogleSheetsSync
from config import Config
import logging
import os

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


def audit_snapshot_schedule_job():
    """Background job to evaluate and run scheduled audit snapshot email."""
    try:
        from app import app
        from audit_snapshot import run_scheduled_snapshot_if_due
        with app.app_context():
            success, message = run_scheduled_snapshot_if_due()
            if success:
                print(f'Scheduled audit snapshot: {message}')
    except Exception as e:
        print(f'Scheduled audit snapshot error: {str(e)}')


def init_scheduler(app):
    """Initialize the background scheduler."""
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return

    if not scheduler.running:
        # Add sync job only when a spreadsheet ID is configured.
        if Config.GOOGLE_SHEETS_SPREADSHEET_ID:
            scheduler.add_job(
                func=sync_job,
                trigger=IntervalTrigger(minutes=Config.SYNC_INTERVAL_MINUTES),
                id='google_sheets_sync',
                name='Sync with Google Sheets',
                replace_existing=True
            )

        # Add audit snapshot schedule evaluator.
        scheduler.add_job(
            func=audit_snapshot_schedule_job,
            trigger=IntervalTrigger(minutes=Config.SNAPSHOT_SCHEDULER_INTERVAL_MINUTES),
            id='audit_snapshot_schedule',
            name='Scheduled Audit Snapshot',
            replace_existing=True
        )

        scheduler.start()
        print('Scheduler started')

        # Shut down scheduler when app stops
        import atexit
        atexit.register(lambda: scheduler.shutdown())
