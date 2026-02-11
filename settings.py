from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required
from auth import admin_required
from models import (
    db,
    SyncLog,
    GoogleAdminOuRoleMapping,
    GoogleAdminDeviceModelMapping,
    GoogleAdminSyncSchedule,
    GoogleAdminSyncLog,
    Asset,
    User,
    Checkout,
    DamageIncident,
    EscalationCase,
    DocFolder,
    Document,
    DocumentFile,
    ASSET_TYPES,
)
from sync import GoogleSheetsSync
from google_admin_sync import GoogleAdminUserSync, get_or_create_google_admin_sync_schedule
from config import Config
from datetime import datetime, timedelta
import random

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')
DEMO_ASSET_PREFIX = 'DEMO-'
DEMO_USER_PREFIX = 'demo-'
DEMO_USER_DOMAIN = '@example.local'
DEMO_USERS_PER_ROLE = 15
DEMO_ASSETS_PER_TYPE = 15
DEMO_ROLES = ['admin', 'helpdesk', 'staff', 'teacher', 'student']
DEMO_CHECKOUT_TYPES_COUNT = 5
DEMO_DOC_FOLDER_COUNT = 5
DEMO_DOC_SUBFOLDER_COUNT = 5
DEMO_DOCS_PER_SUBFOLDER = 5
DEMO_DOC_FOLDER_PREFIX = 'Demo Folder '
DEMO_DOC_SUBFOLDER_PREFIX = 'Subfolder '
DEMO_DOC_TITLE_PREFIX = 'Demo Doc '
DEMO_DOC_MARKER = '<!-- DEMO_DOCUMENTATION_DATA -->'


def _is_demo_user_email(email):
    return email.startswith(DEMO_USER_PREFIX) and email.endswith(DEMO_USER_DOMAIN)


def _demo_counts():
    demo_assets = Asset.query.filter(Asset.asset_tag.like(f'{DEMO_ASSET_PREFIX}%')).count()
    demo_users = User.query.filter(User.email.like(f'{DEMO_USER_PREFIX}%{DEMO_USER_DOMAIN}')).count()
    return demo_assets, demo_users


def _asset_category_for_type(asset_type):
    if asset_type in ['Laptop', 'Tablet', 'Projector', 'Smart Board']:
        return 'Technology'
    if asset_type in ['Server', 'VM', 'Docker Container', 'Printer']:
        return 'IT Infrastructure'
    if asset_type == 'Charger':
        return 'Accessories'
    return 'Other'


def _random_markdown(seed_num):
    rng = random.Random(seed_num)
    topics = [
        'device onboarding',
        'network access',
        'help desk intake',
        'loaner process',
        'repair triage',
        'inventory audit',
        'student assignment',
        'check-in workflow',
        'security baseline',
        'asset retirement'
    ]
    verbs = ['review', 'verify', 'record', 'approve', 'sync', 'document', 'confirm', 'track']
    nouns = ['ticket', 'asset', 'policy', 'form', 'checklist', 'request', 'incident', 'history']

    lines = [
        DEMO_DOC_MARKER,
        f"# {rng.choice(topics).title()} Procedure",
        "",
        "## Purpose",
        f"This document describes how to {rng.choice(verbs)} each {rng.choice(nouns)} in the workflow.",
        "",
        "## Steps",
        f"1. {rng.choice(verbs).title()} the {rng.choice(nouns)} details.",
        f"2. {rng.choice(verbs).title()} ownership and timestamps.",
        f"3. {rng.choice(verbs).title()} completion in the system.",
        "",
        "## Notes",
        f"- Keep records for {rng.randint(30, 365)} days.",
        f"- Escalate unresolved items after {rng.randint(2, 10)} business days.",
        "",
        "## References",
        "- [Internal Policy](https://example.local/policy)",
    ]
    return "\n".join(lines)


def _create_demo_data():
    created_users = 0
    created_assets = 0
    created_checkouts = 0
    created_doc_folders = 0
    created_documents = 0

    for role in DEMO_ROLES:
        for idx in range(1, DEMO_USERS_PER_ROLE + 1):
            email = f'{DEMO_USER_PREFIX}{role}-{idx:02d}{DEMO_USER_DOMAIN}'
            if User.query.filter_by(email=email).first():
                continue

            user = User(
                email=email,
                name=f'Demo {role.title()} {idx:02d}',
                role=role,
                asset_tag=f'DEMO-USER-{role[:3].upper()}-{idx:02d}',
                grade_level='N/A'
            )
            user.set_password('demo1234')
            db.session.add(user)
            created_users += 1

    for type_idx, asset_type in enumerate(ASSET_TYPES, start=1):
        for idx in range(1, DEMO_ASSETS_PER_TYPE + 1):
            asset_tag = f'{DEMO_ASSET_PREFIX}{type_idx:02d}-{idx:03d}'
            if Asset.query.filter_by(asset_tag=asset_tag).first():
                continue

            asset = Asset(
                asset_tag=asset_tag,
                name=f'Demo {asset_type} {idx:03d}',
                category=_asset_category_for_type(asset_type),
                type=asset_type,
                serial_number=f'DM-{type_idx:02d}-{idx:04d}',
                status='available',
                location='Demo Lab',
                condition='good',
                notes='DEMO_DATA'
            )
            db.session.add(asset)
            created_assets += 1

    db.session.commit()

    recipient_users = User.query.filter(
        User.email.like(f'{DEMO_USER_PREFIX}student-%{DEMO_USER_DOMAIN}')
    ).order_by(User.email).limit(DEMO_CHECKOUT_TYPES_COUNT).all()
    if len(recipient_users) < DEMO_CHECKOUT_TYPES_COUNT:
        recipient_users = User.query.filter(
            User.email.like(f'{DEMO_USER_PREFIX}%{DEMO_USER_DOMAIN}')
        ).order_by(User.email).limit(DEMO_CHECKOUT_TYPES_COUNT).all()

    checkout_operator = User.query.filter_by(
        email=f'{DEMO_USER_PREFIX}helpdesk-01{DEMO_USER_DOMAIN}'
    ).first() or User.query.filter_by(
        email=f'{DEMO_USER_PREFIX}admin-01{DEMO_USER_DOMAIN}'
    ).first()

    if recipient_users and checkout_operator:
        for idx, asset_type in enumerate(ASSET_TYPES[:DEMO_CHECKOUT_TYPES_COUNT]):
            asset = Asset.query.filter(
                Asset.asset_tag.like(f'{DEMO_ASSET_PREFIX}%'),
                Asset.type == asset_type,
                Asset.status == 'available'
            ).order_by(Asset.asset_tag).first()
            if not asset:
                continue

            recipient = recipient_users[idx % len(recipient_users)]
            checkout = Checkout(
                asset_id=asset.id,
                checked_out_to=recipient.name,
                checked_out_by=checkout_operator.id,
                checkout_date=datetime.utcnow(),
                expected_return_date=(datetime.utcnow() + timedelta(days=30)).date()
            )
            asset.status = 'checked_out'
            asset.updated_at = datetime.utcnow()
            db.session.add(checkout)
            created_checkouts += 1

        db.session.commit()

    doc_owner = User.query.filter_by(email='admin@school.edu').first() or checkout_operator
    if doc_owner:
        seed_base = int(datetime.utcnow().timestamp())
        for f_idx in range(1, DEMO_DOC_FOLDER_COUNT + 1):
            folder_name = f'{DEMO_DOC_FOLDER_PREFIX}{f_idx}'
            folder = DocFolder.query.filter_by(name=folder_name).first()
            if not folder:
                folder = DocFolder(name=folder_name)
                db.session.add(folder)
                db.session.flush()
                created_doc_folders += 1

            for s_idx in range(1, DEMO_DOC_SUBFOLDER_COUNT + 1):
                subfolder_name = f'{folder_name} / {DEMO_DOC_SUBFOLDER_PREFIX}{s_idx}'
                subfolder = DocFolder.query.filter_by(name=subfolder_name).first()
                if not subfolder:
                    subfolder = DocFolder(name=subfolder_name)
                    db.session.add(subfolder)
                    db.session.flush()
                    created_doc_folders += 1

                for d_idx in range(1, DEMO_DOCS_PER_SUBFOLDER + 1):
                    title = f'{DEMO_DOC_TITLE_PREFIX}F{f_idx}-S{s_idx}-D{d_idx}'
                    exists = Document.query.filter_by(title=title, folder_id=subfolder.id).first()
                    if exists:
                        continue

                    doc = Document(
                        folder_id=subfolder.id,
                        title=title,
                        content_md=_random_markdown(seed_base + (f_idx * 100 + s_idx * 10 + d_idx)),
                        created_by=doc_owner.id,
                        updated_by=doc_owner.id,
                    )
                    db.session.add(doc)
                    created_documents += 1

        db.session.commit()

    return created_users, created_assets, created_checkouts, created_doc_folders, created_documents


def _remove_demo_data():
    demo_users = User.query.filter(User.email.like(f'{DEMO_USER_PREFIX}%{DEMO_USER_DOMAIN}')).all()
    demo_user_ids = [u.id for u in demo_users]
    demo_assets = Asset.query.filter(Asset.asset_tag.like(f'{DEMO_ASSET_PREFIX}%')).all()
    demo_asset_ids = [a.id for a in demo_assets]
    demo_docs = Document.query.filter(
        Document.title.like(f'{DEMO_DOC_TITLE_PREFIX}%'),
        Document.content_md.ilike(f'%{DEMO_DOC_MARKER}%')
    ).all()
    demo_doc_ids = [d.id for d in demo_docs]
    demo_folders = DocFolder.query.filter(DocFolder.name.like(f'{DEMO_DOC_FOLDER_PREFIX}%')).all()

    if demo_asset_ids or demo_user_ids:
        incident_conditions = []
        escalation_conditions = []
        if demo_asset_ids:
            incident_conditions.append(DamageIncident.asset_id.in_(demo_asset_ids))
            escalation_conditions.append(EscalationCase.asset_id.in_(demo_asset_ids))
        if demo_user_ids:
            incident_conditions.append(DamageIncident.user_id.in_(demo_user_ids))
            escalation_conditions.append(EscalationCase.user_id.in_(demo_user_ids))
            escalation_conditions.append(EscalationCase.created_by.in_(demo_user_ids))

        if incident_conditions:
            DamageIncident.query.filter(db.or_(*incident_conditions)).delete(synchronize_session=False)
        if escalation_conditions:
            EscalationCase.query.filter(db.or_(*escalation_conditions)).delete(synchronize_session=False)

        checkout_query = Checkout.query
        if demo_asset_ids and demo_user_ids:
            checkout_query = checkout_query.filter(
                db.or_(
                    Checkout.asset_id.in_(demo_asset_ids),
                    Checkout.checked_out_by.in_(demo_user_ids)
                )
            )
        elif demo_asset_ids:
            checkout_query = checkout_query.filter(Checkout.asset_id.in_(demo_asset_ids))
        else:
            checkout_query = checkout_query.filter(Checkout.checked_out_by.in_(demo_user_ids))
        checkout_query.delete(synchronize_session=False)

    if demo_doc_ids:
        DocumentFile.query.filter(DocumentFile.document_id.in_(demo_doc_ids)).delete(synchronize_session=False)
        Document.query.filter(Document.id.in_(demo_doc_ids)).delete(synchronize_session=False)

    removed_doc_folders = 0
    for folder in demo_folders:
        db.session.delete(folder)
        removed_doc_folders += 1

    removed_assets = 0
    removed_users = 0

    for asset in demo_assets:
        db.session.delete(asset)
        removed_assets += 1

    for user in demo_users:
        if _is_demo_user_email(user.email):
            db.session.delete(user)
            removed_users += 1

    db.session.commit()
    return removed_users, removed_assets, len(demo_doc_ids), removed_doc_folders


@settings_bp.route('/sync')
@login_required
@admin_required
def sync_settings():
    """Google Sheets sync settings page."""
    # Get recent sync logs
    recent_logs = SyncLog.query.order_by(SyncLog.timestamp.desc()).limit(20).all()
    google_admin_logs = GoogleAdminSyncLog.query.order_by(GoogleAdminSyncLog.created_at.desc()).limit(20).all()
    google_admin_ou_mappings = GoogleAdminOuRoleMapping.query.order_by(GoogleAdminOuRoleMapping.ou_path.asc()).all()
    google_admin_device_model_mappings = GoogleAdminDeviceModelMapping.query.order_by(GoogleAdminDeviceModelMapping.device_model.asc()).all()
    google_admin_schedule = get_or_create_google_admin_sync_schedule()
    demo_assets, demo_users = _demo_counts()

    return render_template('settings/sync.html',
                         recent_logs=recent_logs,
                         google_admin_logs=google_admin_logs,
                         google_admin_ou_mappings=google_admin_ou_mappings,
                         google_admin_device_model_mappings=google_admin_device_model_mappings,
                         google_admin_schedule=google_admin_schedule,
                         spreadsheet_id=Config.GOOGLE_SHEETS_SPREADSHEET_ID,
                         google_admin_credentials_file=Config.GOOGLE_ADMIN_CREDENTIALS_FILE,
                         google_admin_delegated_admin_email=Config.GOOGLE_ADMIN_DELEGATED_ADMIN_EMAIL,
                         google_admin_customer_id=Config.GOOGLE_ADMIN_CUSTOMER_ID,
                         sync_interval=Config.SYNC_INTERVAL_MINUTES,
                         demo_data_enabled=(demo_assets > 0 or demo_users > 0),
                         demo_assets_count=demo_assets,
                         demo_users_count=demo_users)


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


@settings_bp.route('/example-data', methods=['POST'])
@login_required
@admin_required
def toggle_example_data():
    """Enable or disable demo data."""
    enabled = request.form.get('example_data_enabled') == 'on'

    try:
        if enabled:
            created_users, created_assets, created_checkouts, created_doc_folders, created_documents = _create_demo_data()
            flash(
                f'Example data enabled. Added {created_users} users, {created_assets} assets, {created_checkouts} demo checkouts, {created_doc_folders} doc folders, and {created_documents} demo docs.',
                'success'
            )
        else:
            removed_users, removed_assets, removed_docs, removed_doc_folders = _remove_demo_data()
            flash(
                f'Example data disabled. Removed {removed_users} users, {removed_assets} assets, {removed_doc_folders} doc folders, and {removed_docs} demo docs.',
                'success'
            )
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update example data: {str(e)}', 'danger')

    return redirect(url_for('settings.sync_settings'))


@settings_bp.route('/google-admin/test', methods=['POST'])
@login_required
@admin_required
def test_google_admin_connection():
    """Test Google Admin API connection."""
    try:
        syncer = GoogleAdminUserSync()
        result = syncer.test_connection()
        if result.get('success'):
            return jsonify({'success': True, 'message': result.get('message', 'Connected')})
        return jsonify({'success': False, 'error': result.get('error', 'Unknown error')}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/google-admin/sync', methods=['POST'])
@login_required
@admin_required
def manual_google_admin_sync():
    """Run Google Admin user sync manually."""
    try:
        sync_device_ou = request.form.get('sync_device_ou') == 'on'
        syncer = GoogleAdminUserSync()
        result = syncer.run_sync(trigger_type='manual')
        device_result = None
        if sync_device_ou:
            device_result = syncer.sync_device_ous(trigger_type='manual')
        if result.get('success'):
            msg = f"Google Admin user sync complete. {result.get('message', '')}"
            if device_result:
                msg += f" | {device_result.get('message', '')}"
            flash(msg, 'success')
        else:
            flash(f"Google Admin sync failed. {result.get('message', '')}", 'danger')
    except Exception as e:
        flash(f'Google Admin sync failed: {str(e)}', 'danger')
    return redirect(url_for('settings.sync_settings'))


@settings_bp.route('/google-admin/ou-mappings/add', methods=['POST'])
@login_required
@admin_required
def add_google_admin_ou_mapping():
    """Add or update Google OU to local role mapping."""
    ou_path = request.form.get('ou_path', '').strip()
    role = request.form.get('role', '').strip().lower()
    enabled = request.form.get('enabled') == 'on'

    valid_roles = {'admin', 'helpdesk', 'staff', 'teacher', 'student'}
    if not ou_path:
        flash('Google OU path is required.', 'danger')
        return redirect(url_for('settings.sync_settings'))
    if not ou_path.startswith('/'):
        ou_path = '/' + ou_path
    ou_path = ou_path.rstrip('/') or '/'
    if role not in valid_roles:
        flash('Invalid role for Google OU mapping.', 'danger')
        return redirect(url_for('settings.sync_settings'))

    mapping = GoogleAdminOuRoleMapping.query.filter_by(ou_path=ou_path).first()
    if not mapping:
        mapping = GoogleAdminOuRoleMapping(ou_path=ou_path, role=role, enabled=enabled)
        db.session.add(mapping)
    else:
        mapping.role = role
        mapping.enabled = enabled
    db.session.commit()
    flash('Google OU mapping saved.', 'success')
    return redirect(url_for('settings.sync_settings'))


@settings_bp.route('/google-admin/ou-mappings/<int:mapping_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_google_admin_ou_mapping(mapping_id):
    """Delete Google OU to role mapping."""
    mapping = GoogleAdminOuRoleMapping.query.get_or_404(mapping_id)
    db.session.delete(mapping)
    db.session.commit()
    flash('Google OU mapping deleted.', 'success')
    return redirect(url_for('settings.sync_settings'))


@settings_bp.route('/google-admin/device-model-mappings/add', methods=['POST'])
@login_required
@admin_required
def add_google_admin_device_model_mapping():
    """Add or update Google device model to local device group mapping."""
    device_model = request.form.get('device_model', '').strip()
    device_group = request.form.get('device_group', '').strip().lower()
    enabled = request.form.get('enabled') == 'on'

    valid_groups = {'admin', 'helpdesk', 'staff', 'teacher', 'student'}
    if not device_model:
        flash('Google device model is required.', 'danger')
        return redirect(url_for('settings.sync_settings'))
    if device_group not in valid_groups:
        flash('Invalid device group for model mapping.', 'danger')
        return redirect(url_for('settings.sync_settings'))

    mapping = GoogleAdminDeviceModelMapping.query.filter(
        db.func.lower(GoogleAdminDeviceModelMapping.device_model) == device_model.lower()
    ).first()
    if not mapping:
        mapping = GoogleAdminDeviceModelMapping(
            device_model=device_model,
            device_group=device_group,
            enabled=enabled
        )
        db.session.add(mapping)
    else:
        mapping.device_group = device_group
        mapping.enabled = enabled
    db.session.commit()
    flash('Google device model mapping saved.', 'success')
    return redirect(url_for('settings.sync_settings'))


@settings_bp.route('/google-admin/device-model-mappings/<int:mapping_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_google_admin_device_model_mapping(mapping_id):
    """Delete Google device model mapping."""
    mapping = GoogleAdminDeviceModelMapping.query.get_or_404(mapping_id)
    db.session.delete(mapping)
    db.session.commit()
    flash('Google device model mapping deleted.', 'success')
    return redirect(url_for('settings.sync_settings'))


@settings_bp.route('/google-admin/schedule', methods=['POST'])
@login_required
@admin_required
def save_google_admin_schedule():
    """Save Google Admin sync schedule."""
    enabled = request.form.get('ga_schedule_enabled') == 'on'
    sync_device_ou = request.form.get('ga_sync_device_ou') == 'on'
    selected_days = request.form.getlist('ga_days')
    hour_utc = request.form.get('ga_hour_utc', type=int)
    minute_utc = request.form.get('ga_minute_utc', type=int)

    valid_days = {'0', '1', '2', '3', '4', '5', '6'}
    if hour_utc is None or minute_utc is None:
        flash('Sync time is required.', 'danger')
        return redirect(url_for('settings.sync_settings'))
    if hour_utc < 0 or hour_utc > 23 or minute_utc < 0 or minute_utc > 59:
        flash('Sync time is invalid.', 'danger')
        return redirect(url_for('settings.sync_settings'))
    if enabled:
        if not selected_days:
            flash('Select at least one day for scheduled Google Admin sync.', 'danger')
            return redirect(url_for('settings.sync_settings'))
        if any(day not in valid_days for day in selected_days):
            flash('Invalid day selection for schedule.', 'danger')
            return redirect(url_for('settings.sync_settings'))

    schedule = get_or_create_google_admin_sync_schedule()
    schedule.enabled = enabled
    schedule.days_of_week = ','.join(sorted(set(selected_days), key=lambda x: int(x)))
    schedule.sync_device_ou = sync_device_ou
    schedule.hour_utc = hour_utc
    schedule.minute_utc = minute_utc
    db.session.commit()
    flash('Google Admin sync schedule saved.', 'success')
    return redirect(url_for('settings.sync_settings'))
