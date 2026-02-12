import csv
import io
import smtplib
from datetime import datetime
from email.message import EmailMessage

from flask import Blueprint, render_template, request, flash, redirect, url_for, send_file, current_app
from flask_login import login_required, current_user

from auth import roles_required
from models import (
    db,
    Asset,
    Checkout,
    User,
    RepairTicket,
    DamageIncident,
    EscalationCase,
    AuditSnapshotLog,
    OverdueAuditSweep,
    OverdueAuditSweepItem,
    OverdueAuditSweepScanLog,
    GoogleAdminDeviceUserLog,
    REPAIR_STATUS_LABELS,
    Ticket,
)
from audit_snapshot import (
    build_audit_snapshot_bundle,
    send_snapshot_email,
    create_snapshot_log,
    get_or_create_snapshot_schedule,
    handle_snapshot_artifacts,
)

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


PREMADE_REPORTS = [
    ('asset_status_summary', 'Asset Status Summary'),
    ('checked_out_assets', 'Currently Checked Out Assets'),
    ('repair_pipeline', 'Repair Pipeline'),
    ('user_role_summary', 'User Role Summary'),
    ('ticketing_report', 'Ticketing Report'),
]
ESCALATION_STATUSES = [
    ('open', 'Open'),
    ('admin_review', 'Admin Review'),
    ('parent_contact', 'Parent Contact'),
    ('resolved', 'Resolved'),
]

ASSET_REPORT_FIELDS = [
    ('id', 'ID'),
    ('asset_tag', 'Asset Tag'),
    ('name', 'Name'),
    ('category', 'Category'),
    ('type', 'Type'),
    ('serial_number', 'Serial Number'),
    ('status', 'Status'),
    ('location', 'Location'),
    ('purchase_date', 'Purchase Date'),
    ('purchase_cost', 'Purchase Cost'),
    ('condition', 'Condition'),
    ('repeat_breakage_flag', 'Repeat Breakage Flag'),
    ('notes', 'Notes'),
    ('warranty_vendor', 'Warranty Vendor'),
    ('warranty_end_date', 'Warranty End Date'),
    ('warranty_notes', 'Warranty Notes'),
    ('software_name', 'Software Name'),
    ('license_key', 'License Key'),
    ('license_seats', 'License Seats'),
    ('license_expires_on', 'License Expires On'),
    ('license_assigned_to', 'License Assigned To'),
    ('accessory_type', 'Accessory Type'),
    ('accessory_compatibility', 'Accessory Compatibility'),
    ('accessory_notes', 'Accessory Notes'),
    ('toner_model', 'Consumable Name / Model'),
    ('toner_compatible_printer', 'Consumable Compatible Device'),
    ('toner_quantity', 'Consumable Quantity'),
    ('toner_reorder_threshold', 'Consumable Reorder Threshold'),
    ('google_sheets_row_id', 'Google Sheets Row ID'),
    ('created_at', 'Created At'),
    ('updated_at', 'Updated At'),
]
ASSET_FIELD_LABELS = dict(ASSET_REPORT_FIELDS)


def _parse_date_range(form_data):
    start_date_raw = form_data.get('start_date', '').strip()
    end_date_raw = form_data.get('end_date', '').strip()

    start_dt = None
    end_dt = None
    if start_date_raw:
        start_date = datetime.strptime(start_date_raw, '%Y-%m-%d').date()
        start_dt = datetime.combine(start_date, datetime.min.time())
    if end_date_raw:
        end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date()
        end_dt = datetime.combine(end_date, datetime.max.time())
    if start_dt and end_dt and start_dt > end_dt:
        raise ValueError('Start date cannot be later than end date.')

    return start_dt, end_dt


def _apply_datetime_range(query, column, start_dt, end_dt):
    if start_dt:
        query = query.filter(column >= start_dt)
    if end_dt:
        query = query.filter(column <= end_dt)
    return query


def _build_report(report_type, form_data):
    start_dt, end_dt = _parse_date_range(form_data)

    if report_type == 'asset_status_summary':
        rows = _apply_datetime_range(
            db.session.query(Asset.status, db.func.count(Asset.id)),
            Asset.created_at,
            start_dt,
            end_dt
        ).group_by(Asset.status).all()
        return {
            'title': 'Asset Status Summary',
            'columns': ['Status', 'Count'],
            'rows': [[status, count] for status, count in rows],
        }

    if report_type == 'checked_out_assets':
        rows = _apply_datetime_range(
            db.session.query(
            Asset.asset_tag,
            Asset.name,
            Checkout.checked_out_to,
            Checkout.checkout_date,
            Checkout.expected_return_date,
            Asset.status
        ).join(Checkout, Checkout.asset_id == Asset.id).filter(
            Checkout.checked_in_date.is_(None)
            ),
            Checkout.checkout_date,
            start_dt,
            end_dt
        ).order_by(Checkout.checkout_date.desc()).all()
        return {
            'title': 'Currently Checked Out Assets',
            'columns': ['Asset Tag', 'Asset Name', 'Checked Out To', 'Checkout Date', 'Expected Return', 'Asset Status'],
            'rows': [[
                r.asset_tag,
                r.name,
                r.checked_out_to,
                r.checkout_date.strftime('%Y-%m-%d %H:%M') if r.checkout_date else '',
                r.expected_return_date.strftime('%Y-%m-%d') if r.expected_return_date else '',
                r.status,
            ] for r in rows],
        }

    if report_type == 'repair_pipeline':
        rows = _apply_datetime_range(
            db.session.query(
            Asset.asset_tag,
            Asset.name,
            RepairTicket.status,
            RepairTicket.updated_at,
            RepairTicket.notes
        ).join(RepairTicket, RepairTicket.asset_id == Asset.id).filter(
            RepairTicket.status != 'closed'
            ),
            RepairTicket.updated_at,
            start_dt,
            end_dt
        ).order_by(RepairTicket.updated_at.desc()).all()
        return {
            'title': 'Repair Pipeline',
            'columns': ['Asset Tag', 'Asset Name', 'Repair Status', 'Last Updated', 'Notes'],
            'rows': [[
                r.asset_tag,
                r.name,
                REPAIR_STATUS_LABELS.get(r.status, r.status),
                r.updated_at.strftime('%Y-%m-%d %H:%M') if r.updated_at else '',
                r.notes or '',
            ] for r in rows],
        }

    if report_type == 'user_role_summary':
        rows = _apply_datetime_range(
            db.session.query(User.role, db.func.count(User.id)),
            User.created_at,
            start_dt,
            end_dt
        ).group_by(User.role).all()
        return {
            'title': 'User Role Summary',
            'columns': ['Role', 'Count'],
            'rows': [[role, count] for role, count in rows],
        }

    if report_type == 'ticketing_report':
        rows = _apply_datetime_range(
            Ticket.query,
            Ticket.created_at,
            start_dt,
            end_dt
        ).outerjoin(User, Ticket.assigned_to_id == User.id).order_by(Ticket.created_at.desc()).all()
        return {
            'title': 'Ticketing Report',
            'columns': [
                'Ticket Code',
                'Subject',
                'Requester',
                'Status',
                'Priority',
                'Category',
                'Assignee',
                'Created At',
                'Updated At',
            ],
            'rows': [[
                ticket.ticket_code or f'T-{ticket.id:04d}',
                ticket.subject,
                ticket.requester_email,
                ticket.status,
                ticket.priority,
                ticket.category or '',
                ticket.assignee.name if ticket.assignee else '',
                ticket.created_at.strftime('%Y-%m-%d %H:%M') if ticket.created_at else '',
                ticket.updated_at.strftime('%Y-%m-%d %H:%M') if ticket.updated_at else '',
            ] for ticket in rows],
        }

    if report_type == 'custom_asset_fields':
        start_date_raw = form_data.get('start_date', '').strip()
        end_date_raw = form_data.get('end_date', '').strip()
        date_field = form_data.get('date_field', 'created_at').strip()
        selected_fields = [f for f in form_data.getlist('fields') if f in ASSET_FIELD_LABELS]
        if not selected_fields:
            raise ValueError('Select at least one asset field for the custom report.')
        if date_field not in {'created_at', 'updated_at', 'purchase_date'}:
            raise ValueError('Invalid date field selected.')

        query = Asset.query

        if start_date_raw:
            start_date = datetime.strptime(start_date_raw, '%Y-%m-%d').date()
            if date_field == 'purchase_date':
                query = query.filter(Asset.purchase_date >= start_date)
            else:
                query = query.filter(getattr(Asset, date_field) >= datetime.combine(start_date, datetime.min.time()))
        if end_date_raw:
            end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date()
            if date_field == 'purchase_date':
                query = query.filter(Asset.purchase_date <= end_date)
            else:
                query = query.filter(getattr(Asset, date_field) <= datetime.combine(end_date, datetime.max.time()))

        assets = query.order_by(Asset.asset_tag).all()

        columns = [ASSET_FIELD_LABELS[field] for field in selected_fields]
        rows = []
        for asset in assets:
            row = []
            for field in selected_fields:
                value = getattr(asset, field)
                if isinstance(value, datetime):
                    value = value.strftime('%Y-%m-%d %H:%M')
                elif hasattr(value, 'strftime'):
                    value = value.strftime('%Y-%m-%d')
                row.append(value if value is not None else '')
            rows.append(row)

        return {
            'title': 'Custom Asset Fields Report',
            'columns': columns,
            'rows': rows,
        }

    raise ValueError('Unknown report type selected.')


def _build_csv_bytes(report_data):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(report_data['columns'])
    for row in report_data['rows']:
        writer.writerow(row)
    return output.getvalue().encode('utf-8')


def _build_pdf_bytes(report_data):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError('PDF export requires reportlab. Install dependencies and retry.') from exc

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(40, y, report_data['title'])
    y -= 20
    pdf.setFont('Helvetica', 8)
    pdf.drawString(40, y, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    y -= 20

    header_line = ' | '.join(report_data['columns'])
    pdf.setFont('Helvetica-Bold', 8)
    pdf.drawString(40, y, header_line[:150])
    y -= 14
    pdf.setFont('Helvetica', 8)

    for row in report_data['rows']:
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


def _send_report_email(to_email, filename, mime_type, file_bytes, report_title):
    smtp_host = current_app.config.get('SMTP_HOST')
    smtp_port = current_app.config.get('SMTP_PORT')
    smtp_username = current_app.config.get('SMTP_USERNAME')
    smtp_password = current_app.config.get('SMTP_PASSWORD')
    smtp_use_tls = current_app.config.get('SMTP_USE_TLS')
    from_email = current_app.config.get('REPORTS_FROM_EMAIL')

    if not smtp_host:
        raise RuntimeError('SMTP is not configured. Set SMTP_HOST in .env.')

    msg = EmailMessage()
    msg['Subject'] = f'Report: {report_title}'
    msg['From'] = from_email
    msg['To'] = to_email
    msg.set_content(f'Attached is your requested report: {report_title}')

    main_type, sub_type = mime_type.split('/', 1)
    msg.add_attachment(file_bytes, maintype=main_type, subtype=sub_type, filename=filename)

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        if smtp_use_tls:
            smtp.starttls()
        if smtp_username:
            smtp.login(smtp_username, smtp_password)
        smtp.send_message(msg)


def _build_escalation_evidence(entity_type, entity_id):
    if entity_type == 'asset':
        incidents = DamageIncident.query.filter_by(asset_id=entity_id).order_by(DamageIncident.incident_date.desc()).limit(10).all()
    else:
        incidents = DamageIncident.query.filter_by(user_id=entity_id).order_by(DamageIncident.incident_date.desc()).limit(10).all()

    lines = []
    for i in incidents:
        lines.append(
            f"{i.incident_date.strftime('%Y-%m-%d %H:%M')} | asset={i.asset.asset_tag} | to={i.checked_out_to} | source={i.source} | notes={i.notes or ''}"
        )
    return '\n'.join(lines) if lines else 'No incident evidence found.'


@reports_bp.route('/')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def index():
    return redirect(url_for('reports.audit'))


@reports_bp.route('/audit')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def audit():
    snapshot_logs = AuditSnapshotLog.query.order_by(AuditSnapshotLog.generated_at.desc()).limit(20).all()
    snapshot_schedule = get_or_create_snapshot_schedule()
    selected_sweep_id = request.args.get('sweep_id', type=int)
    if selected_sweep_id:
        selected_sweep = OverdueAuditSweep.query.get(selected_sweep_id)
    else:
        selected_sweep = OverdueAuditSweep.query.filter_by(status='open').order_by(OverdueAuditSweep.generated_at.desc()).first()
        if not selected_sweep:
            selected_sweep = OverdueAuditSweep.query.order_by(OverdueAuditSweep.generated_at.desc()).first()

    selected_sweep_items = []
    selected_sweep_logs = []
    pending_count = 0
    verified_count = 0
    if selected_sweep:
        selected_sweep_items = selected_sweep.items.order_by(
            OverdueAuditSweepItem.status.asc(),
            OverdueAuditSweepItem.expected_return_date.asc()
        ).all()
        selected_sweep_logs = selected_sweep.scan_logs.order_by(OverdueAuditSweepScanLog.scanned_at.desc()).limit(30).all()
        pending_count = selected_sweep.items.filter_by(status='pending').count()
        verified_count = selected_sweep.items.filter_by(status='verified').count()

    recent_sweeps = OverdueAuditSweep.query.order_by(OverdueAuditSweep.generated_at.desc()).limit(20).all()
    return render_template(
        'reports/audit.html',
        snapshot_logs=snapshot_logs,
        snapshot_schedule=snapshot_schedule,
        selected_sweep=selected_sweep,
        selected_sweep_items=selected_sweep_items,
        selected_sweep_logs=selected_sweep_logs,
        recent_sweeps=recent_sweeps,
        sweep_pending_count=pending_count,
        sweep_verified_count=verified_count,
    )


@reports_bp.route('/flagged')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def flagged():
    flagged_assets = Asset.query.filter_by(repeat_breakage_flag=True).order_by(Asset.asset_tag).all()
    flagged_users = User.query.filter_by(repeat_breakage_flag=True).order_by(User.name).all()
    escalation_cases = EscalationCase.query.order_by(EscalationCase.updated_at.desc()).limit(50).all()
    return render_template(
        'reports/flagged.html',
        flagged_assets=flagged_assets,
        flagged_users=flagged_users,
        escalation_cases=escalation_cases,
        escalation_statuses=ESCALATION_STATUSES,
    )


@reports_bp.route('/reports')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def report_center():
    device_user_logs = GoogleAdminDeviceUserLog.query.order_by(
        GoogleAdminDeviceUserLog.observed_at.desc()
    ).limit(50).all()
    open_by_assignee = db.session.query(
        User.name,
        db.func.count(Ticket.id)
    ).join(User, Ticket.assigned_to_id == User.id).filter(
        Ticket.status == 'open'
    ).group_by(User.name).order_by(db.func.count(Ticket.id).desc()).all()
    open_by_category = db.session.query(
        Ticket.category,
        db.func.count(Ticket.id)
    ).filter(
        Ticket.status == 'open'
    ).group_by(Ticket.category).order_by(db.func.count(Ticket.id).desc()).all()
    open_by_status = db.session.query(
        Ticket.status,
        db.func.count(Ticket.id)
    ).group_by(Ticket.status).order_by(db.func.count(Ticket.id).desc()).all()
    return render_template(
        'reports/reports.html',
        premade_reports=PREMADE_REPORTS,
        asset_report_fields=ASSET_REPORT_FIELDS,
        device_user_logs=device_user_logs,
        open_by_assignee=open_by_assignee,
        open_by_category=open_by_category,
        open_by_status=open_by_status,
    )


@reports_bp.route('/escalate', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk')
def escalate():
    entity_type = request.form.get('entity_type', '').strip()
    entity_id = request.form.get('entity_id', type=int)
    reason = request.form.get('reason', '').strip() or 'Repeat breakage threshold exceeded'

    if entity_type not in {'asset', 'user'} or not entity_id:
        flash('Invalid escalation request.', 'danger')
        return redirect(url_for('reports.flagged'))

    try:
        existing = EscalationCase.query.filter_by(
            entity_type=entity_type,
            asset_id=entity_id if entity_type == 'asset' else None,
            user_id=entity_id if entity_type == 'user' else None,
        ).filter(EscalationCase.status != 'resolved').first()
        if existing:
            flash('An open escalation already exists for this record.', 'warning')
            return redirect(url_for('reports.flagged'))

        evidence = _build_escalation_evidence(entity_type, entity_id)
        case = EscalationCase(
            entity_type=entity_type,
            asset_id=entity_id if entity_type == 'asset' else None,
            user_id=entity_id if entity_type == 'user' else None,
            status='open',
            reason=reason,
            evidence=evidence,
            created_by=current_user.id
        )
        db.session.add(case)
        db.session.commit()
        flash('Escalation case created with incident evidence.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Failed to create escalation: {str(exc)}', 'danger')

    return redirect(url_for('reports.flagged'))


@reports_bp.route('/escalation/<int:case_id>/status', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk')
def update_escalation_status(case_id):
    status = request.form.get('status', '').strip()
    valid_statuses = {k for k, _ in ESCALATION_STATUSES}
    if status not in valid_statuses:
        flash('Invalid escalation status.', 'danger')
        return redirect(url_for('reports.flagged'))

    case = EscalationCase.query.get_or_404(case_id)
    case.status = status
    db.session.commit()
    flash('Escalation status updated.', 'success')
    return redirect(url_for('reports.flagged'))


@reports_bp.route('/audit-snapshot/generate', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def generate_audit_snapshot():
    delivery_method = request.form.get('snapshot_delivery_method', 'download').strip().lower()
    email_to = request.form.get('snapshot_email_to', '').strip()
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f'audit_snapshot_{timestamp}.zip'

    try:
        zip_bytes, manifest_sha, manifest = build_audit_snapshot_bundle()
    except Exception as exc:
        flash(f'Failed to build audit snapshot: {str(exc)}', 'danger')
        return redirect(url_for('reports.audit'))

    artifacts = handle_snapshot_artifacts(zip_bytes, manifest_sha, manifest, filename)
    artifact_message = ''
    if artifacts.get('errors'):
        artifact_message = f" Storage warnings: {'; '.join(artifacts['errors'])}"

    if delivery_method == 'download':
        create_snapshot_log(
            trigger_type='manual',
            delivery_method='download',
            filename=filename,
            manifest_sha256=manifest_sha,
            status='success',
            message=f'Manual snapshot downloaded.{artifact_message}',
            recipient_email='',
            created_by=current_user.id
        )
        return send_file(
            io.BytesIO(zip_bytes),
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )

    if delivery_method == 'email':
        if not email_to:
            flash('Email address is required for snapshot email delivery.', 'danger')
            return redirect(url_for('reports.audit'))
        try:
            send_snapshot_email(email_to, zip_bytes, filename)
            create_snapshot_log(
                trigger_type='manual',
                delivery_method='email',
                filename=filename,
                manifest_sha256=manifest_sha,
                status='success',
                message=f'Manual snapshot emailed.{artifact_message}',
                recipient_email=email_to,
                created_by=current_user.id
            )
            flash(f'Audit snapshot emailed to {email_to}.', 'success')
        except Exception as exc:
            create_snapshot_log(
                trigger_type='manual',
                delivery_method='email',
                filename=filename,
                manifest_sha256=manifest_sha,
                status='failed',
                message=str(exc),
                recipient_email=email_to,
                created_by=current_user.id
            )
            flash(f'Email delivery failed: {str(exc)}', 'danger')
        return redirect(url_for('reports.audit'))

    flash('Invalid snapshot delivery method.', 'danger')
    return redirect(url_for('reports.audit'))


@reports_bp.route('/audit-snapshot/schedule', methods=['POST'])
@login_required
@roles_required('admin')
def update_audit_snapshot_schedule():
    enabled = request.form.get('snapshot_schedule_enabled') == 'on'
    recipient_email = request.form.get('snapshot_schedule_email', '').strip()
    frequency = request.form.get('snapshot_schedule_frequency', 'daily').strip()
    hour_utc = request.form.get('snapshot_schedule_hour_utc', type=int)
    minute_utc = request.form.get('snapshot_schedule_minute_utc', type=int)
    weekday_utc = request.form.get('snapshot_schedule_weekday_utc', type=int)

    if frequency not in {'daily', 'weekly'}:
        flash('Invalid snapshot schedule frequency.', 'danger')
        return redirect(url_for('reports.audit'))
    if hour_utc is None or minute_utc is None:
        flash('Hour and minute are required for snapshot schedule.', 'danger')
        return redirect(url_for('reports.audit'))
    if hour_utc < 0 or hour_utc > 23 or minute_utc < 0 or minute_utc > 59:
        flash('Snapshot schedule time is invalid.', 'danger')
        return redirect(url_for('reports.audit'))
    if frequency == 'weekly' and (weekday_utc is None or weekday_utc < 0 or weekday_utc > 6):
        flash('Snapshot schedule weekday is invalid.', 'danger')
        return redirect(url_for('reports.audit'))
    if enabled and not recipient_email:
        flash('Recipient email is required when snapshot schedule is enabled.', 'danger')
        return redirect(url_for('reports.audit'))

    schedule = get_or_create_snapshot_schedule()
    schedule.enabled = enabled
    schedule.recipient_email = recipient_email
    schedule.frequency = frequency
    schedule.hour_utc = hour_utc
    schedule.minute_utc = minute_utc
    schedule.weekday_utc = weekday_utc if weekday_utc is not None else 0
    db.session.commit()

    flash('Audit snapshot schedule saved.', 'success')
    return redirect(url_for('reports.audit'))


@reports_bp.route('/overdue-sweep/generate', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def generate_overdue_sweep():
    period_type = request.form.get('period_type', 'monthly').strip().lower()
    if period_type not in {'monthly', 'quarterly'}:
        flash('Invalid period type.', 'danger')
        return redirect(url_for('reports.audit'))

    now = datetime.utcnow()
    if period_type == 'monthly':
        period_label = now.strftime('%Y-%m')
    else:
        quarter = ((now.month - 1) // 3) + 1
        period_label = f'{now.year}-Q{quarter}'

    sweep = OverdueAuditSweep(
        period_type=period_type,
        period_label=period_label,
        status='open',
        generated_by=current_user.id
    )
    db.session.add(sweep)
    db.session.flush()

    overdue_rows = db.session.query(
        Checkout,
        Asset
    ).join(Asset, Checkout.asset_id == Asset.id).filter(
        Checkout.checked_in_date.is_(None),
        Checkout.expected_return_date.isnot(None),
        Checkout.expected_return_date < datetime.utcnow().date()
    ).order_by(Checkout.expected_return_date.asc()).all()

    for checkout, asset in overdue_rows:
        item = OverdueAuditSweepItem(
            sweep_id=sweep.id,
            asset_id=asset.id,
            checkout_id=checkout.id,
            asset_tag=asset.asset_tag,
            asset_name=asset.name,
            checked_out_to=checkout.checked_out_to,
            expected_return_date=checkout.expected_return_date,
            status='pending'
        )
        db.session.add(item)

    db.session.commit()
    flash(f'Overdue audit sweep created with {len(overdue_rows)} item(s).', 'success')
    return redirect(url_for('reports.audit', sweep_id=sweep.id))


@reports_bp.route('/overdue-sweep/<int:sweep_id>/scan', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def scan_overdue_sweep_item(sweep_id):
    scanned_input = request.form.get('scanned_input', '').strip()
    sweep = OverdueAuditSweep.query.get_or_404(sweep_id)
    if not scanned_input:
        flash('Enter an asset tag to scan.', 'warning')
        return redirect(url_for('reports.audit', sweep_id=sweep.id))

    item = sweep.items.filter(
        db.func.lower(OverdueAuditSweepItem.asset_tag) == scanned_input.lower(),
        OverdueAuditSweepItem.status == 'pending'
    ).first()

    if item:
        item.status = 'verified'
        item.scanned_at = datetime.utcnow()
        item.scanned_by = current_user.id
        log = OverdueAuditSweepScanLog(
            sweep_id=sweep.id,
            item_id=item.id,
            scanned_input=scanned_input,
            matched=True,
            message=f'Verified {item.asset_tag}.',
            scanned_by=current_user.id
        )
        db.session.add(log)

        remaining = sweep.items.filter_by(status='pending').count() - 1
        if remaining <= 0:
            sweep.status = 'completed'
            sweep.completed_at = datetime.utcnow()
        db.session.commit()
        flash(f'Asset {item.asset_tag} verified.', 'success')
    else:
        log = OverdueAuditSweepScanLog(
            sweep_id=sweep.id,
            item_id=None,
            scanned_input=scanned_input,
            matched=False,
            message='No pending overdue item matched this scan.',
            scanned_by=current_user.id
        )
        db.session.add(log)
        db.session.commit()
        flash('No pending overdue item matched that scan.', 'warning')

    return redirect(url_for('reports.audit', sweep_id=sweep.id))


@reports_bp.route('/overdue-sweep/<int:sweep_id>/list.csv')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def download_overdue_sweep_csv(sweep_id):
    sweep = OverdueAuditSweep.query.get_or_404(sweep_id)
    rows = sweep.items.order_by(OverdueAuditSweepItem.status.asc(), OverdueAuditSweepItem.asset_tag.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'sweep_id',
        'period_type',
        'period_label',
        'asset_tag',
        'asset_name',
        'checked_out_to',
        'expected_return_date',
        'status',
        'scanned_at',
        'scanned_by'
    ])
    for item in rows:
        writer.writerow([
            sweep.id,
            sweep.period_type,
            sweep.period_label,
            item.asset_tag,
            item.asset_name,
            item.checked_out_to,
            item.expected_return_date.strftime('%Y-%m-%d') if item.expected_return_date else '',
            item.status,
            item.scanned_at.strftime('%Y-%m-%d %H:%M:%S') if item.scanned_at else '',
            item.scanner.name if item.scanner else ''
        ])

    output.seek(0)
    filename = f'overdue_audit_sweep_{sweep.id}_{sweep.period_label}.csv'
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )


@reports_bp.route('/generate', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def generate():
    report_type = request.form.get('report_type', '').strip()
    output_format = request.form.get('output_format', 'csv').strip().lower()
    delivery_method = request.form.get('delivery_method', 'download').strip().lower()
    email_to = request.form.get('email_to', '').strip()

    try:
        report_data = _build_report(report_type, request.form)
    except Exception as exc:
        flash(f'Failed to build report: {str(exc)}', 'danger')
        return redirect(url_for('reports.report_center'))

    if output_format == 'csv':
        file_bytes = _build_csv_bytes(report_data)
        mime_type = 'text/csv'
        extension = 'csv'
    elif output_format == 'pdf':
        try:
            file_bytes = _build_pdf_bytes(report_data)
        except Exception as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('reports.report_center'))
        mime_type = 'application/pdf'
        extension = 'pdf'
    else:
        flash('Invalid output format.', 'danger')
        return redirect(url_for('reports.report_center'))

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"{report_type}_{timestamp}.{extension}"

    if delivery_method == 'download':
        return send_file(
            io.BytesIO(file_bytes),
            mimetype=mime_type,
            as_attachment=True,
            download_name=filename
        )

    if delivery_method == 'email':
        if not email_to:
            flash('Email address is required for email delivery.', 'danger')
            return redirect(url_for('reports.report_center'))
        try:
            _send_report_email(email_to, filename, mime_type, file_bytes, report_data['title'])
            flash(f'Report emailed to {email_to}.', 'success')
        except Exception as exc:
            flash(f'Email delivery failed: {str(exc)}', 'danger')
        return redirect(url_for('reports.report_center'))

    flash('Invalid delivery method.', 'danger')
    return redirect(url_for('reports.report_center'))
