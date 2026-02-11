import csv
import hashlib
import io
import json
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
    return zip_buffer.read(), manifest_sha


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
        zip_bytes, manifest_sha = build_audit_snapshot_bundle()
        send_snapshot_email(schedule.recipient_email, zip_bytes, filename)
        schedule.last_run_at = now
        db.session.commit()
        create_snapshot_log(
            trigger_type='scheduled',
            delivery_method='email',
            filename=filename,
            manifest_sha256=manifest_sha,
            status='success',
            message='Scheduled snapshot emailed.',
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
