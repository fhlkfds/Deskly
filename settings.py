from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required
from auth import admin_required
from models import db, SyncLog
from sync import GoogleSheetsSync
from config import Config

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/sync')
@login_required
@admin_required
def sync_settings():
    """Google Sheets sync settings page."""
    # Get recent sync logs
    recent_logs = SyncLog.query.order_by(SyncLog.timestamp.desc()).limit(20).all()

    return render_template('settings/sync.html',
                         recent_logs=recent_logs,
                         spreadsheet_id=Config.GOOGLE_SHEETS_SPREADSHEET_ID,
                         sync_interval=Config.SYNC_INTERVAL_MINUTES)


@settings_bp.route('/sync/test', methods=['POST'])
@login_required
@admin_required
def test_connection():
    """Test Google Sheets connection."""
    try:
        sync = GoogleSheetsSync()
        result = sync.test_connection()

        if result['success']:
            return jsonify({'success': True, 'message': result['message']})
        else:
            return jsonify({'success': False, 'error': result['error']}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/sync/manual', methods=['POST'])
@login_required
@admin_required
def manual_sync():
    """Trigger manual sync."""
    try:
        sync_type = request.form.get('sync_type', 'bidirectional')
        sync = GoogleSheetsSync()

        if sync_type == 'sheets_to_db':
            result = sync.sheets_to_database()
        elif sync_type == 'db_to_sheets':
            result = sync.database_to_sheets()
        else:
            result = sync.sync_bidirectional()

        if result.get('success') or (isinstance(result, dict) and 'sheets_to_db' in result):
            flash('Sync completed successfully!', 'success')
        else:
            flash(f"Sync completed with errors: {result.get('error', 'Unknown error')}", 'warning')

        return redirect(url_for('settings.sync_settings'))

    except Exception as e:
        flash(f'Sync failed: {str(e)}', 'danger')
        return redirect(url_for('settings.sync_settings'))
