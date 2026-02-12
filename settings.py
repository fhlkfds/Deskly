from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
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
    ASSET_CATEGORIES,
    ASSET_STATUSES,
    ASSET_CONDITIONS,
    ASSET_TYPES,
    AppSetting,
    AuditLedgerEntry,
    Ticket,
    Notification,
)
from sync import GoogleSheetsSync
from google_admin_sync import GoogleAdminUserSync, get_or_create_google_admin_sync_schedule
from config import Config
from datetime import datetime, timedelta
import os
import uuid
import random
import json
from audit_ledger import is_ledger_enabled, set_ledger_enabled, get_latest_entry
from sqlalchemy.exc import OperationalError
from werkzeug.utils import secure_filename

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


def _get_setting(key, default=''):
    setting = AppSetting.query.get(key)
    if not setting:
        return default
    return setting.value if setting.value is not None else default


def _set_setting(key, value):
    setting = AppSetting.query.get(key)
    if not setting:
        setting = AppSetting(key=key, value=value)
        db.session.add(setting)
    else:
        setting.value = value


def _get_list_setting(key, default_list):
    raw = _get_setting(key, '')
    if not raw:
        return list(default_list)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return list(default_list)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return list(default_list)


def _set_list_setting(key, values):
    cleaned = [value.strip() for value in values if value.strip()]
    _set_setting(key, json.dumps(cleaned))


def _list_to_text(values):
    return '\n'.join(values)


def _create_demo_data():
    created_users = 0
    created_assets = 0
    created_checkouts = 0
    created_doc_folders = 0
    created_documents = 0
    created_tickets = 0
    created_notifications = 0

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

    ticket_users = User.query.order_by(User.id.asc()).all()
    ticket_assignees = User.query.filter(User.role.in_(['admin', 'helpdesk', 'staff'])).all()
    if ticket_users:
        rng = random.Random(datetime.utcnow().timestamp())
        subjects = [
            'Laptop not charging',
            'Printer not working',
            'WiFi keeps dropping',
            'Reset my password',
            'Software install request',
            "Projector won't turn on",
            'Keyboard missing keys',
            'Need access to shared drive',
            'Email not syncing',
            'Device running slow',
            'VPN not connecting',
            'Monitor flickering',
            'Smart board calibration issue',
            'Laptop overheating',
            'Docking station not detected',
            'Microphone not working',
            'Camera blocked',
            'Update stuck',
            'Browser crashes',
            'Printer queue jammed',
            'Chromebook login failed',
            'Asset lost',
            'Asset found',
            'Battery swelling',
            'Replacement charger needed',
            'Storage full',
            'Network drive missing',
            'MFA reset',
            'SSO error',
            'App license request',
        ]
        categories = ['Hardware', 'Software', 'Network', 'Account', 'Access', 'Printer', 'Other']
        tag_pool = ['battery', 'broken', 'charging', 'email', 'login', 'network', 'printer', 'software', 'slow', 'wifi']
        priorities = ['low', 'normal', 'high']
        statuses = ['open', 'triage', 'closed']
        users_by_role = {}
        for user in ticket_users:
            users_by_role.setdefault(user.role or 'unknown', []).append(user)
        if users_by_role.get('teacher'):
            requester_roles = ['teacher']
        else:
            requester_roles = [role for role in DEMO_ROLES if role in users_by_role] or list(users_by_role.keys())
        assignee_cycle = ticket_assignees[:] if ticket_assignees else []
        rng.shuffle(assignee_cycle)

        for idx in range(1, 51):
            role = rng.choice(requester_roles) if requester_roles else None
            if role and users_by_role.get(role):
                user = rng.choice(users_by_role[role])
            else:
                user = rng.choice(ticket_users)
            if assignee_cycle:
                assignee = assignee_cycle[(idx - 1) % len(assignee_cycle)]
            else:
                assignee = None
            tags = rng.sample(tag_pool, k=rng.randint(1, 3))
            created_at = datetime.utcnow() - timedelta(hours=(idx * 3), minutes=rng.randint(0, 59))
            ticket = Ticket(
                subject=f'{rng.choice(subjects)} ({idx:02d})',
                requester_email=user.email,
                requester_name=user.name,
                status=rng.choice(statuses),
                priority=rng.choice(priorities),
                category=rng.choice(categories),
                tags=','.join(tags),
                source='demo',
                body_text='DEMO_DATA: Auto-generated ticket for testing.',
                created_at=created_at,
                updated_at=created_at,
                last_message_at=created_at,
                assigned_to_id=assignee.id if assignee else None,
            )
            db.session.add(ticket)
            db.session.flush()
            ticket.ticket_code = f'T-{ticket.id:04d}'
            created_tickets += 1

        db.session.commit()

    recipients = User.query.filter(User.role.in_(['admin', 'helpdesk'])).all()
    if recipients:
        open_ticket_ids = [t.id for t in Ticket.query.filter(Ticket.status == 'open').order_by(Ticket.updated_at.desc()).limit(10).all()]
        for user in recipients:
            for ticket_id in open_ticket_ids:
                db.session.add(Notification(
                    user_id=user.id,
                    ticket_id=ticket_id,
                    title='New open ticket',
                    message='Demo notification for an open ticket.',
                ))
                created_notifications += 1
        db.session.commit()

    return created_users, created_assets, created_checkouts, created_doc_folders, created_documents, created_tickets, created_notifications


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
    demo_tickets = Ticket.query.filter(Ticket.source == 'demo').all()
    demo_notifications = Notification.query.filter(Notification.message == 'Demo notification for an open ticket.').all()

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
    removed_tickets = 0
    removed_notifications = 0

    for asset in demo_assets:
        db.session.delete(asset)
        removed_assets += 1

    for user in demo_users:
        if _is_demo_user_email(user.email):
            db.session.delete(user)
            removed_users += 1

    for ticket in demo_tickets:
        db.session.delete(ticket)
        removed_tickets += 1

    for note in demo_notifications:
        db.session.delete(note)
        removed_notifications += 1

    db.session.commit()
    return removed_users, removed_assets, len(demo_doc_ids), removed_doc_folders, removed_tickets, removed_notifications


def _settings_context():
    try:
        google_admin_ou_mappings = GoogleAdminOuRoleMapping.query.order_by(GoogleAdminOuRoleMapping.ou_path.asc()).all()
        google_admin_device_model_mappings = GoogleAdminDeviceModelMapping.query.order_by(GoogleAdminDeviceModelMapping.device_model.asc()).all()
        google_admin_schedule = get_or_create_google_admin_sync_schedule()
        demo_assets, demo_users = _demo_counts()
        audit_ledger_latest = get_latest_entry()
        recent_logs = SyncLog.query.order_by(SyncLog.timestamp.desc()).limit(20).all()
        google_admin_logs = GoogleAdminSyncLog.query.order_by(GoogleAdminSyncLog.created_at.desc()).limit(20).all()
    except OperationalError:
        db.create_all()
        google_admin_ou_mappings = GoogleAdminOuRoleMapping.query.order_by(GoogleAdminOuRoleMapping.ou_path.asc()).all()
        google_admin_device_model_mappings = GoogleAdminDeviceModelMapping.query.order_by(GoogleAdminDeviceModelMapping.device_model.asc()).all()
        google_admin_schedule = get_or_create_google_admin_sync_schedule()
        demo_assets, demo_users = _demo_counts()
        audit_ledger_latest = get_latest_entry()
        recent_logs = SyncLog.query.order_by(SyncLog.timestamp.desc()).limit(20).all()
        google_admin_logs = GoogleAdminSyncLog.query.order_by(GoogleAdminSyncLog.created_at.desc()).limit(20).all()
    asset_types = _get_list_setting('asset_types', ASSET_TYPES)
    asset_categories = _get_list_setting('asset_categories', ASSET_CATEGORIES)
    asset_statuses = _get_list_setting('asset_statuses', ASSET_STATUSES)
    asset_conditions = _get_list_setting('asset_conditions', ASSET_CONDITIONS)
    asset_locations = _get_list_setting('asset_locations', [])
    ticket_visibility_roles = _get_list_setting('ticket_visibility_roles', ['admin', 'helpdesk', 'staff'])

    return {
        'config': current_app.config,
        'recent_logs': recent_logs,
        'google_admin_logs': google_admin_logs,
        'google_admin_ou_mappings': google_admin_ou_mappings,
        'google_admin_device_model_mappings': google_admin_device_model_mappings,
        'google_admin_schedule': google_admin_schedule,
        'spreadsheet_id': Config.GOOGLE_SHEETS_SPREADSHEET_ID,
        'google_admin_credentials_file': Config.GOOGLE_ADMIN_CREDENTIALS_FILE,
        'google_admin_delegated_admin_email': Config.GOOGLE_ADMIN_DELEGATED_ADMIN_EMAIL,
        'google_admin_customer_id': Config.GOOGLE_ADMIN_CUSTOMER_ID,
        'sync_interval': Config.SYNC_INTERVAL_MINUTES,
        'demo_data_enabled': (demo_assets > 0 or demo_users > 0),
        'demo_assets_count': demo_assets,
        'demo_users_count': demo_users,
        'audit_ledger_enabled': is_ledger_enabled(),
        'audit_ledger_latest': audit_ledger_latest,
        'audit_drive_enabled': _get_setting('audit_drive_enabled', 'false') == 'true',
        'audit_drive_credentials_file': _get_setting('audit_drive_credentials_file', ''),
        'audit_drive_folder_id': _get_setting('audit_drive_folder_id', ''),
        'audit_local_output_enabled': _get_setting('audit_local_output_enabled', 'false') == 'true',
        'audit_local_output_dir': _get_setting('audit_local_output_dir', 'audit_snapshots'),
        'audit_log_sheet_enabled': _get_setting('audit_log_sheet_enabled', 'false') == 'true',
        'audit_log_sheet_id': _get_setting('audit_log_sheet_id', ''),
        'audit_log_sheet_tab': _get_setting('audit_log_sheet_tab', 'AuditLog'),
        'audit_log_sheet_credentials_file': _get_setting('audit_log_sheet_credentials_file', ''),
        'audit_log_local_enabled': _get_setting('audit_log_local_enabled', 'false') == 'true',
        'audit_log_local_path': _get_setting('audit_log_local_path', 'audit_logs/audit_log.csv'),
        'docs_drive_enabled': _get_setting('docs_drive_enabled', 'false') == 'true',
        'docs_drive_credentials_file': Config.DOCS_DRIVE_CREDENTIALS_FILE,
        'docs_drive_folder_id': Config.DOCS_DRIVE_FOLDER_ID,
        'branding_app_name': _get_setting('branding_app_name', 'School Inventory'),
        'branding_favicon_url': _get_setting('branding_favicon_url', ''),
        'branding_app_icon_url': _get_setting('branding_app_icon_url', ''),
        'branding_primary_color': _get_setting('branding_primary_color', ''),
        'branding_secondary_color': _get_setting('branding_secondary_color', ''),
        'branding_accent_color': _get_setting('branding_accent_color', ''),
        'asset_tag_auto_increment': _get_setting('asset_tag_auto_increment', 'false') == 'true',
        'asset_tag_prefix': _get_setting('asset_tag_prefix', 'AST-'),
        'asset_tag_next_number': _get_setting('asset_tag_next_number', '1'),
        'asset_tag_padding': _get_setting('asset_tag_padding', '4'),
        'asset_types_text': _list_to_text(asset_types),
        'asset_categories_text': _list_to_text(asset_categories),
        'asset_statuses_text': _list_to_text(asset_statuses),
        'asset_conditions_text': _list_to_text(asset_conditions),
        'asset_locations_text': _list_to_text(asset_locations),
        'sso_google_enabled': _get_setting('sso_google_enabled', 'false') == 'true',
        'sso_microsoft_enabled': _get_setting('sso_microsoft_enabled', 'false') == 'true',
        'ticket_visibility_roles': ticket_visibility_roles,
        'ticketing_gmail_enabled': _get_setting('ticketing_gmail_enabled', 'false') == 'true',
    }


@settings_bp.route('/sync')
@login_required
@admin_required
def sync_settings():
    """Combined Google Sheets + Google Admin sync settings page."""
    context = _settings_context()
    return render_template('settings/sync.html', **context)


@settings_bp.route('/credentials')
@login_required
@admin_required
def credential_settings():
    """Credential management settings page."""
    context = _settings_context()
    return render_template('settings/credentials.html', **context)


@settings_bp.route('/misc')
@login_required
@admin_required
def misc_settings():
    """Misc settings (example data, audit ledger, and history)."""
    context = _settings_context()
    return render_template('settings/misc.html', **context)


def _format_security_event(entry, user_name):
    summary = entry.event_type.replace('_', ' ').title()
    payload = {}
    if entry.payload_json:
        try:
            payload = json.loads(entry.payload_json)
        except json.JSONDecodeError:
            payload = {}

    if entry.event_type == 'user_login':
        summary = f"Login: {payload.get('email', user_name or 'Unknown')}"
    elif entry.event_type == 'user_logout':
        summary = f"Logout: {payload.get('email', user_name or 'Unknown')}"
    elif entry.event_type == 'asset_checked_out':
        summary = f"Check-out: {payload.get('asset_tag', 'Asset')} to {payload.get('checked_out_to', '-')}"
    elif entry.event_type == 'asset_checked_in':
        summary = f"Check-in: {payload.get('asset_tag', 'Asset')} ({payload.get('condition', '-')})"
    elif entry.event_type == 'asset_deployed':
        summary = f"Deployed: {payload.get('asset_tag', 'Asset')} to {payload.get('checked_out_to', '-')}"
    elif entry.event_type == 'loaner_swap':
        summary = f"Loaner swap: {payload.get('broken_asset_tag', '-') } → {payload.get('loaner_asset_tag', '-')}"

    return {
        'timestamp': entry.created_at,
        'event_type': entry.event_type,
        'actor_name': user_name or 'System',
        'summary': summary,
        'payload': payload,
    }


def _format_log_event(entry, user_map):
    payload = {}
    if entry.payload_json:
        try:
            payload = json.loads(entry.payload_json)
        except json.JSONDecodeError:
            payload = {}
    actor_name = user_map.get(entry.actor_id, 'System') if entry.actor_id else 'System'
    return {
        'timestamp': entry.created_at,
        'event_type': entry.event_type,
        'actor_name': actor_name,
        'payload': payload,
    }


@settings_bp.route('/logs')
@login_required
@admin_required
def logs_settings():
    """Security events and audit logs."""
    try:
        events = AuditLedgerEntry.query.order_by(AuditLedgerEntry.created_at.desc()).limit(200).all()
    except OperationalError:
        db.create_all()
        events = AuditLedgerEntry.query.order_by(AuditLedgerEntry.created_at.desc()).limit(200).all()

    actor_ids = {e.actor_id for e in events if e.actor_id}
    users = User.query.filter(User.id.in_(actor_ids)).all() if actor_ids else []
    user_map = {u.id: u.name for u in users}

    security_types = {
        'user_login',
        'user_logout',
        'asset_checked_out',
        'asset_checked_in',
        'asset_deployed',
        'loaner_swap',
    }
    security_events = [
        _format_security_event(e, user_map.get(e.actor_id))
        for e in events
        if e.event_type in security_types
    ]
    ticket_event_types = {
        'ticket_updated',
        'ticket_comment',
        'ticket_visibility_updated',
    }
    ticket_events = [
        _format_log_event(e, user_map)
        for e in events
        if e.event_type in ticket_event_types
    ]
    asset_event_types = {
        'asset_checked_out',
        'asset_checked_in',
        'asset_deployed',
        'loaner_swap',
    }
    asset_events = [
        _format_log_event(e, user_map)
        for e in events
        if e.event_type in asset_event_types
    ]
    account_event_types = {
        'user_login',
        'user_logout',
    }
    account_events = [
        _format_log_event(e, user_map)
        for e in events
        if e.event_type in account_event_types
    ]
    doc_event_types = {
        'doc_created',
        'doc_updated',
        'doc_deleted',
    }
    doc_events = [
        _format_log_event(e, user_map)
        for e in events
        if e.event_type in doc_event_types
    ]
    app_events = [
        _format_log_event(e, user_map)
        for e in events
        if e.event_type not in security_types
    ]

    return render_template(
        'settings/logs.html',
        security_events=security_events,
        app_events=app_events,
        asset_events=asset_events,
        doc_events=doc_events,
        account_events=account_events,
        ticket_events=ticket_events,
        audit_ledger_enabled=is_ledger_enabled(),
    )


@settings_bp.route('/branding')
@login_required
@admin_required
def branding_settings():
    """Branding settings page."""
    context = _settings_context()
    return render_template('settings/branding.html', **context)


@settings_bp.route('/imports')
@login_required
@admin_required
def import_settings():
    """Import assets and users."""
    return render_template('settings/imports.html')


@settings_bp.route('/assets')
@login_required
@admin_required
def asset_settings():
    """Asset configuration settings."""
    context = _settings_context()
    return render_template('settings/assets.html', **context)


@settings_bp.route('/sso')
@login_required
@admin_required
def sso_settings():
    """SSO settings page."""
    context = _settings_context()
    return render_template('settings/sso.html', **context)


@settings_bp.route('/ticketing')
@login_required
@admin_required
def ticketing_settings():
    """Ticketing settings page."""
    context = _settings_context()
    return render_template('settings/ticketing.html', **context)


@settings_bp.route('/ticketing', methods=['POST'])
@login_required
@admin_required
def update_ticketing_settings():
    roles = request.form.getlist('ticket_visibility_roles')
    ticketing_gmail_enabled = request.form.get('ticketing_gmail_enabled') == 'on'

    if 'ticket_visibility_roles' in request.form:
        previous_roles = _get_list_setting('ticket_visibility_roles', ['admin', 'helpdesk', 'staff'])
        _set_list_setting('ticket_visibility_roles', roles)
        from audit_ledger import append_ledger_entry
        append_ledger_entry(
            event_type='ticket_visibility_updated',
            entity_type='ticketing_settings',
            entity_id=None,
            actor_id=current_user.id,
            payload={'from': previous_roles, 'to': roles},
        )
    _set_setting('ticketing_gmail_enabled', 'true' if ticketing_gmail_enabled else 'false')
    db.session.commit()
    flash('Ticketing settings saved.', 'success')
    return redirect(url_for('settings.ticketing_settings'))


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
            created_users, created_assets, created_checkouts, created_doc_folders, created_documents, created_tickets, created_notifications = _create_demo_data()
            flash(
                f'Example data enabled. Added {created_users} users, {created_assets} assets, {created_checkouts} demo checkouts, {created_doc_folders} doc folders, {created_documents} demo docs, {created_tickets} tickets, and {created_notifications} notifications.',
                'success'
            )
        else:
            removed_users, removed_assets, removed_docs, removed_doc_folders, removed_tickets, removed_notifications = _remove_demo_data()
            flash(
                f'Example data disabled. Removed {removed_users} users, {removed_assets} assets, {removed_doc_folders} doc folders, {removed_docs} demo docs, {removed_tickets} tickets, and {removed_notifications} notifications.',
                'success'
            )
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update example data: {str(e)}', 'danger')

    return redirect(url_for('settings.misc_settings'))


@settings_bp.route('/audit-ledger', methods=['POST'])
@login_required
@admin_required
def update_audit_ledger():
    """Enable or disable the append-only audit ledger."""
    enabled = request.form.get('audit_ledger_enabled') == 'on'
    try:
        set_ledger_enabled(enabled)
        db.session.commit()
        if enabled:
            flash('Audit ledger enabled. New events will be chained with hashes.', 'success')
        else:
            flash('Audit ledger disabled. New events will no longer be recorded.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update audit ledger setting: {str(e)}', 'danger')
    return redirect(url_for('settings.misc_settings'))


@settings_bp.route('/credential-management', methods=['POST'])
@login_required
@admin_required
def update_credential_management():
    """Update credential and storage settings for audit artifacts."""
    try:
        audit_drive_enabled = request.form.get('audit_drive_enabled') == 'on'
        audit_drive_credentials_file = request.form.get('audit_drive_credentials_file', '').strip()
        audit_drive_folder_id = request.form.get('audit_drive_folder_id', '').strip()
        audit_local_output_enabled = request.form.get('audit_local_output_enabled') == 'on'
        audit_local_output_dir = request.form.get('audit_local_output_dir', '').strip()
        audit_log_sheet_enabled = request.form.get('audit_log_sheet_enabled') == 'on'
        audit_log_sheet_id = request.form.get('audit_log_sheet_id', '').strip()
        audit_log_sheet_tab = request.form.get('audit_log_sheet_tab', '').strip() or 'AuditLog'
        audit_log_sheet_credentials_file = request.form.get('audit_log_sheet_credentials_file', '').strip()
        audit_log_local_enabled = request.form.get('audit_log_local_enabled') == 'on'
        audit_log_local_path = request.form.get('audit_log_local_path', '').strip()
        docs_drive_enabled = request.form.get('docs_drive_enabled') == 'on'

        _set_setting('audit_drive_enabled', 'true' if audit_drive_enabled else 'false')
        _set_setting('audit_drive_credentials_file', audit_drive_credentials_file)
        _set_setting('audit_drive_folder_id', audit_drive_folder_id)
        _set_setting('audit_local_output_enabled', 'true' if audit_local_output_enabled else 'false')
        _set_setting('audit_local_output_dir', audit_local_output_dir)
        _set_setting('audit_log_sheet_enabled', 'true' if audit_log_sheet_enabled else 'false')
        _set_setting('audit_log_sheet_id', audit_log_sheet_id)
        _set_setting('audit_log_sheet_tab', audit_log_sheet_tab)
        _set_setting('audit_log_sheet_credentials_file', audit_log_sheet_credentials_file)
        _set_setting('audit_log_local_enabled', 'true' if audit_log_local_enabled else 'false')
        _set_setting('audit_log_local_path', audit_log_local_path)
        _set_setting('docs_drive_enabled', 'true' if docs_drive_enabled else 'false')

        db.session.commit()
        flash('Credential management settings saved.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update credential management: {str(e)}', 'danger')
    return redirect(url_for('settings.credential_settings'))


@settings_bp.route('/branding', methods=['POST'])
@login_required
@admin_required
def update_branding():
    """Update branding settings."""
    def allowed_icon_filename(filename):
        allowed = {'.png', '.jpg', '.jpeg', '.svg', '.ico'}
        _, ext = os.path.splitext(filename.lower())
        return ext in allowed

    def save_branding_file(file_storage, prefix):
        if not file_storage or not file_storage.filename:
            return ''
        filename = secure_filename(file_storage.filename)
        if not filename or not allowed_icon_filename(filename):
            return ''
        ext = os.path.splitext(filename)[1].lower()
        unique_name = f'{prefix}_{uuid.uuid4().hex}{ext}'
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'branding')
        os.makedirs(upload_dir, exist_ok=True)
        destination = os.path.join(upload_dir, unique_name)
        file_storage.save(destination)
        return url_for('static', filename=f'uploads/branding/{unique_name}')

    def normalize_hex(value):
        value = (value or '').strip()
        if not value:
            return ''
        if not value.startswith('#'):
            value = f'#{value}'
        if len(value) != 7:
            return ''
        for char in value[1:]:
            if char not in '0123456789abcdefABCDEF':
                return ''
        return value

    try:
        app_name = request.form.get('branding_app_name', '').strip()
        favicon_url = request.form.get('branding_favicon_url', '').strip()
        app_icon_url = request.form.get('branding_app_icon_url', '').strip()
        favicon_upload = save_branding_file(request.files.get('branding_favicon_file'), 'favicon')
        app_icon_upload = save_branding_file(request.files.get('branding_app_icon_file'), 'app_icon')
        primary_color = normalize_hex(request.form.get('branding_primary_color'))
        secondary_color = normalize_hex(request.form.get('branding_secondary_color'))
        accent_color = normalize_hex(request.form.get('branding_accent_color'))

        _set_setting('branding_app_name', app_name or 'School Inventory')
        _set_setting('branding_favicon_url', favicon_upload or favicon_url)
        _set_setting('branding_app_icon_url', app_icon_upload or app_icon_url)
        _set_setting('branding_primary_color', primary_color)
        _set_setting('branding_secondary_color', secondary_color)
        _set_setting('branding_accent_color', accent_color)

        db.session.commit()
        flash('Branding settings saved.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update branding settings: {str(e)}', 'danger')
    return redirect(url_for('settings.branding_settings'))


@settings_bp.route('/assets', methods=['POST'])
@login_required
@admin_required
def update_asset_settings():
    """Update asset configuration lists and auto-increment settings."""
    try:
        auto_increment = request.form.get('asset_tag_auto_increment') == 'on'
        prefix = request.form.get('asset_tag_prefix', '').strip()
        next_number = request.form.get('asset_tag_next_number', '').strip()
        padding = request.form.get('asset_tag_padding', '').strip()

        asset_types = request.form.get('asset_types_text', '').splitlines()
        asset_categories = request.form.get('asset_categories_text', '').splitlines()
        asset_statuses = request.form.get('asset_statuses_text', '').splitlines()
        asset_conditions = request.form.get('asset_conditions_text', '').splitlines()
        asset_locations = request.form.get('asset_locations_text', '').splitlines()

        _set_setting('asset_tag_auto_increment', 'true' if auto_increment else 'false')
        _set_setting('asset_tag_prefix', prefix or 'AST-')
        _set_setting('asset_tag_next_number', next_number or '1')
        _set_setting('asset_tag_padding', padding or '4')
        _set_list_setting('asset_types', asset_types or ASSET_TYPES)
        _set_list_setting('asset_categories', asset_categories or ASSET_CATEGORIES)
        _set_list_setting('asset_statuses', asset_statuses or ASSET_STATUSES)
        _set_list_setting('asset_conditions', asset_conditions or ASSET_CONDITIONS)
        _set_list_setting('asset_locations', asset_locations)

        db.session.commit()
        flash('Asset settings saved.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update asset settings: {str(e)}', 'danger')
    return redirect(url_for('settings.asset_settings'))


@settings_bp.route('/sso', methods=['POST'])
@login_required
@admin_required
def update_sso_settings():
    """Update SSO provider toggles."""
    try:
        google_enabled = request.form.get('sso_google_enabled') == 'on'
        microsoft_enabled = request.form.get('sso_microsoft_enabled') == 'on'
        _set_setting('sso_google_enabled', 'true' if google_enabled else 'false')
        _set_setting('sso_microsoft_enabled', 'true' if microsoft_enabled else 'false')
        db.session.commit()
        flash('SSO settings saved.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update SSO settings: {str(e)}', 'danger')
    return redirect(url_for('settings.sso_settings'))


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
