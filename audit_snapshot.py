import csv
import hashlib
import io
import json
import os
import smtplib
import zipfile
from datetime import datetime, timezone
from email.message import EmailMessage

from flask import current_app

from models import (
    db,
    Asset,
    Checkout,
    User,
    RepairTicket,
    AuditSnapshotLog,
    AuditSnapshotSchedule,
    AppSetting,
)


def _to_text(value):
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        return value.strftime('%Y-%m-%d')
    return str(value)


def _csv_bytes(columns, rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_to_text(v) for v in row])
    return out.getvalue().encode('utf-8')


def _sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


AUDIT_LOG_COLUMNS = [
    'timestamp_utc',
    'snapshot_filename',
    'zip_sha256',
    'manifest_sha256',
    'drive_zip_file_id',
    'drive_manifest_csv_file_id',
    'drive_manifest_pdf_file_id',
    'local_zip_path',
    'local_manifest_csv_path',
    'local_manifest_pdf_path',
    'prev_hash',
    'row_hash',
]


def _get_setting(key, default=''):
    setting = AppSetting.query.get(key)
    if not setting:
        return default
    return setting.value if setting.value is not None else default


def _setting_enabled(key):
    return _get_setting(key, 'false') == 'true'


def _build_manifest_rows(manifest):
    rows = []
    for name, meta in sorted(manifest.get('files', {}).items()):
        rows.append([name, meta.get('sha256', ''), meta.get('size_bytes', '')])
    return rows


def _build_manifest_csv_bytes(manifest):
    return _csv_bytes(['file', 'sha256', 'size_bytes'], _build_manifest_rows(manifest))


def _build_manifest_pdf_bytes(manifest):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError('PDF export requires reportlab. Install dependencies and retry.') from exc

    rows = _build_manifest_rows(manifest)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(40, y, 'Audit Snapshot Manifest')
    y -= 20
    pdf.setFont('Helvetica', 8)
    pdf.drawString(40, y, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    y -= 20

    pdf.setFont('Helvetica-Bold', 8)
    pdf.drawString(40, y, 'file | sha256 | size_bytes')
    y -= 14
    pdf.setFont('Helvetica', 8)

    for row in rows:
        if y < 40:
            pdf.showPage()
            y = height - 40
            pdf.setFont('Helvetica', 8)
        line = ' | '.join(str(col) for col in row)
        pdf.drawString(40, y, line[:150])
        y -= 12

    pdf.save()
    buffer.seek(0)
    return buffer.read()


def _compute_row_hash(prev_hash, fields):
    parts = [prev_hash or ''] + [str(field or '') for field in fields]
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()


def _write_audit_log_local(local_path, row_values):
    if not local_path:
        return None
    os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
    prev_hash = ''
    if os.path.exists(local_path):
        with open(local_path, 'r', encoding='utf-8', newline='') as handle:
            reader = csv.reader(handle)
            last_row = None
            for row in reader:
                if row and row[0] != AUDIT_LOG_COLUMNS[0]:
                    last_row = row
            if last_row and len(last_row) >= len(AUDIT_LOG_COLUMNS):
                prev_hash = last_row[-1]

    row_with_hash = list(row_values)
    row_hash = _compute_row_hash(prev_hash, row_with_hash)
    row_with_hash.extend([prev_hash, row_hash])

    write_header = not os.path.exists(local_path)
    with open(local_path, 'a', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        if write_header:
            writer.writerow(AUDIT_LOG_COLUMNS)
        writer.writerow(row_with_hash)
    return row_hash


def _write_audit_log_sheet(sheet_id, tab_name, credentials_file, row_values):
    if not sheet_id or not credentials_file:
        return None
    try:
        import gspread
    except Exception as exc:
        raise RuntimeError('gspread is not installed. Run pip install -r requirements.txt') from exc

    gc = gspread.service_account(filename=credentials_file)
    spreadsheet = gc.open_by_key(sheet_id)
    try:
        worksheet = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(AUDIT_LOG_COLUMNS))

    rows = worksheet.get_all_values()
    prev_hash = ''
    if len(rows) > 1:
        last_row = rows[-1]
        if len(last_row) >= len(AUDIT_LOG_COLUMNS):
            prev_hash = last_row[-1]

    row_with_hash = list(row_values)
    row_hash = _compute_row_hash(prev_hash, row_with_hash)
    row_with_hash.extend([prev_hash, row_hash])

    if not rows:
        worksheet.append_row(AUDIT_LOG_COLUMNS, value_input_option='RAW')
    worksheet.append_row(row_with_hash, value_input_option='RAW')
    return row_hash


def _upload_to_drive(service, filename, mime_type, file_bytes, folder_id=None):
    try:
        from googleapiclient.http import MediaIoBaseUpload
    except Exception as exc:
        raise RuntimeError('google-api-python-client is not installed. Run pip install -r requirements.txt') from exc

    metadata = {'name': filename}
    if folder_id:
        metadata['parents'] = [folder_id]
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=False)
    created = service.files().create(body=metadata, media_body=media, fields='id').execute()
    return created.get('id')


def _get_drive_service(credentials_file):
    if not credentials_file:
        return None
    if not os.path.exists(credentials_file):
        raise FileNotFoundError(f'Drive credentials file not found: {credentials_file}')
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
    except Exception as exc:
        raise RuntimeError('google-api-python-client is not installed. Run pip install -r requirements.txt') from exc

    creds = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=['https://www.googleapis.com/auth/drive.file'],
    )
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def handle_snapshot_artifacts(zip_bytes, manifest_sha, manifest, filename):
    results = {
        'zip_sha256': _sha256_hex(zip_bytes),
        'drive_zip_file_id': None,
        'drive_manifest_csv_file_id': None,
        'drive_manifest_pdf_file_id': None,
        'local_zip_path': None,
        'local_manifest_csv_path': None,
        'local_manifest_pdf_path': None,
        'audit_log_sheet_row_hash': None,
        'audit_log_local_row_hash': None,
        'errors': [],
    }

    manifest_csv = _build_manifest_csv_bytes(manifest)
    try:
        manifest_pdf = _build_manifest_pdf_bytes(manifest)
    except Exception as exc:
        manifest_pdf = None
        results['errors'].append(str(exc))

    if _setting_enabled('audit_local_output_enabled'):
        output_dir = _get_setting('audit_local_output_dir', 'audit_snapshots').strip()
        if not output_dir:
            output_dir = 'audit_snapshots'
        os.makedirs(output_dir, exist_ok=True)
        zip_path = os.path.join(output_dir, filename)
        manifest_csv_path = os.path.join(output_dir, filename.replace('.zip', '_manifest.csv'))
        manifest_pdf_path = os.path.join(output_dir, filename.replace('.zip', '_manifest.pdf'))
        try:
            with open(zip_path, 'wb') as handle:
                handle.write(zip_bytes)
            with open(manifest_csv_path, 'wb') as handle:
                handle.write(manifest_csv)
            if manifest_pdf:
                with open(manifest_pdf_path, 'wb') as handle:
                    handle.write(manifest_pdf)
            results['local_zip_path'] = zip_path
            results['local_manifest_csv_path'] = manifest_csv_path
            results['local_manifest_pdf_path'] = manifest_pdf_path if manifest_pdf else None
        except Exception as exc:
            results['errors'].append(f'Local output failed: {str(exc)}')

    if _setting_enabled('audit_drive_enabled'):
        credentials_file = _get_setting('audit_drive_credentials_file', '').strip()
        folder_id = _get_setting('audit_drive_folder_id', '').strip() or None
        try:
            service = _get_drive_service(credentials_file)
            if service:
                results['drive_zip_file_id'] = _upload_to_drive(
                    service, filename, 'application/zip', zip_bytes, folder_id
                )
                results['drive_manifest_csv_file_id'] = _upload_to_drive(
                    service, filename.replace('.zip', '_manifest.csv'), 'text/csv', manifest_csv, folder_id
                )
                if manifest_pdf:
                    results['drive_manifest_pdf_file_id'] = _upload_to_drive(
                        service, filename.replace('.zip', '_manifest.pdf'), 'application/pdf', manifest_pdf, folder_id
                    )
        except Exception as exc:
            results['errors'].append(f'Drive upload failed: {str(exc)}')

    row_values = [
        datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        filename,
        results['zip_sha256'],
        manifest_sha,
        results['drive_zip_file_id'] or '',
        results['drive_manifest_csv_file_id'] or '',
        results['drive_manifest_pdf_file_id'] or '',
        results['local_zip_path'] or '',
        results['local_manifest_csv_path'] or '',
        results['local_manifest_pdf_path'] or '',
    ]

    if _setting_enabled('audit_log_sheet_enabled'):
        sheet_id = _get_setting('audit_log_sheet_id', '').strip()
        tab_name = _get_setting('audit_log_sheet_tab', 'AuditLog').strip() or 'AuditLog'
        credentials_file = _get_setting('audit_log_sheet_credentials_file', '').strip()
        try:
            results['audit_log_sheet_row_hash'] = _write_audit_log_sheet(
                sheet_id, tab_name, credentials_file, row_values
            )
        except Exception as exc:
            results['errors'].append(f'Google Sheet log failed: {str(exc)}')

    if _setting_enabled('audit_log_local_enabled'):
        local_path = _get_setting('audit_log_local_path', 'audit_logs/audit_log.csv').strip()
        try:
            results['audit_log_local_row_hash'] = _write_audit_log_local(local_path, row_values)
        except Exception as exc:
            results['errors'].append(f'Local log failed: {str(exc)}')

    return results

def _build_snapshot_files():
    assignment_rows = db.session.query(
        Checkout.id,
        Asset.asset_tag,
        Asset.name,
        Checkout.checked_out_to,
        User.name,
        Checkout.checkout_date,
        Checkout.expected_return_date,
        Asset.status
    ).join(Asset, Checkout.asset_id == Asset.id).join(User, Checkout.checked_out_by == User.id).filter(
        Checkout.checked_in_date.is_(None)
    ).order_by(Checkout.checkout_date.desc()).all()

    assignments_csv = _csv_bytes(
        ['checkout_id', 'asset_tag', 'asset_name', 'checked_out_to', 'checked_out_by', 'checkout_date', 'expected_return_date', 'asset_status'],
        assignment_rows
    )

    asset_rows = db.session.query(
        Asset.id,
        Asset.asset_tag,
        Asset.name,
        Asset.category,
        Asset.type,
        Asset.serial_number,
        Asset.status,
        Asset.location,
        Asset.purchase_date,
        Asset.purchase_cost,
        Asset.condition,
        Asset.repeat_breakage_flag,
        Asset.created_at,
        Asset.updated_at,
    ).order_by(Asset.asset_tag).all()
    assets_csv = _csv_bytes(
        ['id', 'asset_tag', 'name', 'category', 'type', 'serial_number', 'status', 'location', 'purchase_date', 'purchase_cost', 'condition', 'repeat_breakage_flag', 'created_at', 'updated_at'],
        asset_rows
    )

    repair_rows = db.session.query(
        RepairTicket.id,
        Asset.asset_tag,
        RepairTicket.status,
        RepairTicket.notes,
        RepairTicket.created_at,
        RepairTicket.updated_at
    ).join(Asset, RepairTicket.asset_id == Asset.id).order_by(RepairTicket.updated_at.desc()).all()
    repairs_csv = _csv_bytes(
        ['repair_id', 'asset_tag', 'status', 'notes', 'created_at', 'updated_at'],
        repair_rows
    )

    event_rows = db.session.query(
        Checkout.id,
        Asset.asset_tag,
        Checkout.checked_out_to,
        User.name,
        Checkout.checkout_date,
        Checkout.checked_in_date,
        Checkout.checkin_condition,
        Checkout.checkin_notes
    ).join(Asset, Checkout.asset_id == Asset.id).join(User, Checkout.checked_out_by == User.id).order_by(Checkout.checkout_date.desc()).all()
    events_csv = _csv_bytes(
        ['checkout_id', 'asset_tag', 'checked_out_to', 'checked_out_by', 'checkout_date', 'checked_in_date', 'checkin_condition', 'checkin_notes'],
        event_rows
    )

    user_rows = db.session.query(
        User.id,
        User.email,
        User.name,
        User.role,
        User.asset_tag,
        User.grade_level,
        User.repeat_breakage_flag,
        User.created_at
    ).order_by(User.name).all()
    users_csv = _csv_bytes(
        ['id', 'email', 'name', 'role', 'asset_tag', 'grade_level', 'repeat_breakage_flag', 'created_at'],
        user_rows
    )

    generated_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    readme = (
        "Audit-Ready Snapshot\n"
        "Generated UTC: " + generated_at + "\n\n"
        "Files:\n"
        "- manifest.json: file metadata and hashes\n"
        "- manifest.sha256: sha256 hash of manifest.json\n"
        "- current_assignments.csv: active assignments\n"
        "- assets.csv: asset records\n"
        "- repairs.csv: repair records\n"
        "- assignment_events.csv: checkout/checkin history\n"
        "- users.csv: user records\n\n"
        "Integrity:\n"
        "Recompute each file hash and compare to manifest.json.\n"
    ).encode('utf-8')

    return {
        'current_assignments.csv': assignments_csv,
        'assets.csv': assets_csv,
        'repairs.csv': repairs_csv,
        'assignment_events.csv': events_csv,
        'users.csv': users_csv,
        'README.txt': readme,
    }


def build_audit_snapshot_bundle():
    files = _build_snapshot_files()

    manifest = {
        'snapshot_generated_at_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'files': {},
    }
    for name, data in files.items():
        manifest['files'][name] = {
            'sha256': _sha256_hex(data),
            'size_bytes': len(data),
        }

    manifest_json_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode('utf-8')
    manifest_sha = _sha256_hex(manifest_json_bytes)
    manifest['manifest_sha256'] = manifest_sha
    manifest_sha_bytes = f"{manifest_sha}  manifest.json\n".encode('utf-8')

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('manifest.json', manifest_json_bytes)
        zf.writestr('manifest.sha256', manifest_sha_bytes)
        zf.writestr('current_assignments.csv', files['current_assignments.csv'])
        zf.writestr('assets.csv', files['assets.csv'])
        zf.writestr('repairs.csv', files['repairs.csv'])
        zf.writestr('assignment_events.csv', files['assignment_events.csv'])
        zf.writestr('users.csv', files['users.csv'])
        zf.writestr('README.txt', files['README.txt'])

    zip_buffer.seek(0)
    return zip_buffer.read(), manifest_sha, manifest


def send_snapshot_email(recipient_email, zip_bytes, filename):
    smtp_host = current_app.config.get('SMTP_HOST')
    smtp_port = current_app.config.get('SMTP_PORT')
    smtp_username = current_app.config.get('SMTP_USERNAME')
    smtp_password = current_app.config.get('SMTP_PASSWORD')
    smtp_use_tls = current_app.config.get('SMTP_USE_TLS')
    from_email = current_app.config.get('REPORTS_FROM_EMAIL')

    if not smtp_host:
        raise RuntimeError('SMTP is not configured. Set SMTP_HOST in .env.')

    msg = EmailMessage()
    msg['Subject'] = 'Audit-Ready Snapshot'
    msg['From'] = from_email
    msg['To'] = recipient_email
    msg.set_content('Attached is the requested audit-ready snapshot ZIP.')
    msg.add_attachment(zip_bytes, maintype='application', subtype='zip', filename=filename)

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        if smtp_use_tls:
            smtp.starttls()
        if smtp_username:
            smtp.login(smtp_username, smtp_password)
        smtp.send_message(msg)


def create_snapshot_log(trigger_type, delivery_method, filename, manifest_sha256, status='success', message='', recipient_email='', created_by=None):
    log = AuditSnapshotLog(
        trigger_type=trigger_type,
        delivery_method=delivery_method,
        recipient_email=recipient_email or None,
        zip_filename=filename,
        manifest_sha256=manifest_sha256,
        status=status,
        message=message or None,
        created_by=created_by,
    )
    db.session.add(log)
    db.session.flush()
    from audit_ledger import append_ledger_entry
    append_ledger_entry(
        event_type='audit_snapshot',
        entity_type='audit_snapshot_log',
        entity_id=log.id,
        actor_id=created_by,
        payload={
            'trigger_type': trigger_type,
            'delivery_method': delivery_method,
            'filename': filename,
            'manifest_sha256': manifest_sha256,
            'status': status,
        }
    )
    db.session.commit()
    return log


def get_or_create_snapshot_schedule():
    schedule = AuditSnapshotSchedule.query.first()
    if not schedule:
        schedule = AuditSnapshotSchedule(
            enabled=False,
            recipient_email='',
            frequency='daily',
            hour_utc=1,
            minute_utc=0,
            weekday_utc=0,
        )
        db.session.add(schedule)
        db.session.commit()
    return schedule


def run_scheduled_snapshot_if_due():
    schedule = AuditSnapshotSchedule.query.first()
    if not schedule or not schedule.enabled or not schedule.recipient_email:
        return False, 'No enabled audit snapshot schedule.'

    now = datetime.utcnow()
    scheduled_at = None

    if schedule.frequency == 'daily':
        scheduled_at = now.replace(hour=schedule.hour_utc, minute=schedule.minute_utc, second=0, microsecond=0)
    elif schedule.frequency == 'weekly':
        days_behind = (now.weekday() - schedule.weekday_utc) % 7
        target_date = now.date() if days_behind == 0 else (now.date().fromordinal(now.date().toordinal() - days_behind))
        scheduled_at = datetime(target_date.year, target_date.month, target_date.day, schedule.hour_utc, schedule.minute_utc)
    else:
        return False, 'Invalid schedule frequency.'

    if now < scheduled_at:
        return False, 'Scheduled time not reached yet.'

    if schedule.last_run_at and schedule.last_run_at >= scheduled_at:
        return False, 'Snapshot already generated for current schedule window.'

    timestamp = now.strftime('%Y%m%d_%H%M%S')
    filename = f'audit_snapshot_{timestamp}.zip'

    try:
        zip_bytes, manifest_sha, manifest = build_audit_snapshot_bundle()
        send_snapshot_email(schedule.recipient_email, zip_bytes, filename)
        artifacts = handle_snapshot_artifacts(zip_bytes, manifest_sha, manifest, filename)
        artifact_message = ''
        if artifacts.get('errors'):
            artifact_message = f" Storage warnings: {'; '.join(artifacts['errors'])}"
        schedule.last_run_at = now
        db.session.commit()
        create_snapshot_log(
            trigger_type='scheduled',
            delivery_method='email',
            filename=filename,
            manifest_sha256=manifest_sha,
            status='success',
            message=f'Scheduled snapshot emailed.{artifact_message}',
            recipient_email=schedule.recipient_email,
            created_by=None,
        )
        return True, 'Scheduled snapshot sent.'
    except Exception as exc:
        db.session.rollback()
        # Best effort log for failed job.
        try:
            create_snapshot_log(
                trigger_type='scheduled',
                delivery_method='email',
                filename=filename,
                manifest_sha256='0' * 64,
                status='failed',
                message=str(exc),
                recipient_email=schedule.recipient_email,
                created_by=None,
            )
        except Exception:
            pass
        return False, str(exc)
