from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required
from auth import admin_required
from models import db, SyncLog, Asset, User, Checkout, DamageIncident, EscalationCase, ASSET_TYPES
from sync import GoogleSheetsSync
from config import Config
from datetime import datetime, timedelta

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')
DEMO_ASSET_PREFIX = 'DEMO-'
DEMO_USER_PREFIX = 'demo-'
DEMO_USER_DOMAIN = '@example.local'
DEMO_USERS_PER_ROLE = 15
DEMO_ASSETS_PER_TYPE = 15
DEMO_ROLES = ['admin', 'helpdesk', 'staff', 'teacher', 'student']
DEMO_CHECKOUT_TYPES_COUNT = 5


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


def _create_demo_data():
    created_users = 0
    created_assets = 0
    created_checkouts = 0

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

    return created_users, created_assets, created_checkouts


def _remove_demo_data():
    demo_users = User.query.filter(User.email.like(f'{DEMO_USER_PREFIX}%{DEMO_USER_DOMAIN}')).all()
    demo_user_ids = [u.id for u in demo_users]
    demo_assets = Asset.query.filter(Asset.asset_tag.like(f'{DEMO_ASSET_PREFIX}%')).all()
    demo_asset_ids = [a.id for a in demo_assets]

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
    return removed_users, removed_assets


@settings_bp.route('/sync')
@login_required
@admin_required
def sync_settings():
    """Google Sheets sync settings page."""
    # Get recent sync logs
    recent_logs = SyncLog.query.order_by(SyncLog.timestamp.desc()).limit(20).all()
    demo_assets, demo_users = _demo_counts()

    return render_template('settings/sync.html',
                         recent_logs=recent_logs,
                         spreadsheet_id=Config.GOOGLE_SHEETS_SPREADSHEET_ID,
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
            created_users, created_assets, created_checkouts = _create_demo_data()
            flash(
                f'Example data enabled. Added {created_users} users, {created_assets} assets, and {created_checkouts} demo checkouts.',
                'success'
            )
        else:
            removed_users, removed_assets = _remove_demo_data()
            flash(
                f'Example data disabled. Removed {removed_users} users and {removed_assets} assets.',
                'success'
            )
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update example data: {str(e)}', 'danger')

    return redirect(url_for('settings.sync_settings'))
