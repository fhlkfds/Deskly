from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from auth import roles_required
from models import db, Asset, Checkout, User, RepairTicket, Notification
from datetime import datetime, timedelta
import re
from breakage import record_damage_incident
from audit_ledger import append_ledger_entry

checkouts_bp = Blueprint('checkouts', __name__, url_prefix='/checkouts')

CHECKOUT_MODE_ORDER = ['assets', 'consumables', 'licenses', 'accessories']
CHECKOUT_MODE_META = {
    'assets': {
        'title': 'Check Out Asset',
        'button_label': 'Check Out Asset',
        'description': 'Standard returnable device and infrastructure checkout.',
        'show_expected_return': True,
        'requires_existing_user': False,
    },
    'consumables': {
        'title': 'Issue Consumable',
        'button_label': 'Issue Consumable',
        'description': 'Consumables are issued to people and do not get checked back in.',
        'show_expected_return': False,
        'requires_existing_user': True,
    },
    'licenses': {
        'title': 'Assign License',
        'button_label': 'Assign License',
        'description': 'Assign software licenses directly to a known user.',
        'show_expected_return': False,
        'requires_existing_user': True,
    },
    'accessories': {
        'title': 'Check Out Accessory',
        'button_label': 'Check Out Accessory',
        'description': 'Track accessories like mice, keyboards, and headsets.',
        'show_expected_return': True,
        'requires_existing_user': False,
    },
}


def _normalize_checkout_mode(mode):
    if mode in CHECKOUT_MODE_META:
        return mode
    return 'assets'


def _match_user_by_identifier(identifier):
    value = (identifier or '').strip()
    if not value:
        return None
    if '@' in value:
        return User.query.filter(db.func.lower(User.email) == value.lower()).first()
    if re.match(r'^[A-Za-z0-9-]{3,}$', value):
        by_tag = User.query.filter(db.func.lower(User.asset_tag) == value.lower()).first()
        if by_tag:
            return by_tag
    return User.query.filter(db.func.lower(User.name) == value.lower()).first()


def _assets_for_checkout_mode(assets, mode):
    if mode == 'assets':
        return [asset for asset in assets if asset.checkout_bucket == 'assets']
    return [asset for asset in assets if asset.checkout_bucket == mode]


def _redirect_checkout_mode(mode):
    return redirect(url_for('checkouts.checkout', mode=mode))


def _checkout_notification_title(mode):
    if mode == 'consumables':
        return 'Consumable issued'
    if mode == 'licenses':
        return 'License assigned'
    if mode == 'accessories':
        return 'Accessory checked out'
    return 'Asset checked out'


def _create_checkout_notifications(asset, mode, checked_out_to, actor_user, recipient_user=None):
    title = _checkout_notification_title(mode)
    actor_message = f'{asset.asset_tag} ({asset.name}) was checked out to {checked_out_to}.'
    recipient_ids = {actor_user.id}
    if recipient_user:
        recipient_ids.add(recipient_user.id)

    for user_id in recipient_ids:
        if user_id == actor_user.id:
            message = actor_message
        else:
            message = f'{asset.asset_tag} ({asset.name}) was checked out to you by {actor_user.name}.'
        db.session.add(Notification(
            user_id=user_id,
            title=title,
            message=message,
        ))


@checkouts_bp.route('/')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def history():
    """View checkout history."""
    page = request.args.get('page', 1, type=int)
    per_page = 25

    # Get filter parameters
    status_filter = request.args.get('status', 'all')  # all, active, completed

    query = Checkout.query

    if status_filter == 'active':
        query = query.filter(Checkout.checked_in_date.is_(None))
    elif status_filter == 'completed':
        query = query.filter(Checkout.checked_in_date.isnot(None))

    # Order by checkout date descending
    query = query.order_by(Checkout.checkout_date.desc())

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    checkouts = pagination.items

    return render_template('checkouts/history.html',
                         checkouts=checkouts,
                         pagination=pagination,
                         status_filter=status_filter)


@checkouts_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'helpdesk')
def checkout():
    """Checkout an asset."""
    mode = _normalize_checkout_mode(request.args.get('mode', 'assets'))

    requested_asset_id = request.args.get('asset_id', type=int)
    if requested_asset_id and mode == 'assets':
        requested_asset = Asset.query.get(requested_asset_id)
        if requested_asset and requested_asset.checkout_bucket in CHECKOUT_MODE_META:
            mode = requested_asset.checkout_bucket

    if request.method == 'POST':
        mode = _normalize_checkout_mode(request.form.get('checkout_mode', mode))
        mode_meta = CHECKOUT_MODE_META[mode]
        try:
            asset_id = request.form.get('asset_id')
            asset = Asset.query.get_or_404(asset_id)

            if mode == 'assets' and asset.checkout_bucket != 'assets':
                flash('Use the correct checkout workflow for this asset type.', 'danger')
                return _redirect_checkout_mode(asset.checkout_bucket)
            if mode != 'assets' and asset.checkout_bucket != mode:
                flash('Selected asset does not belong to this checkout workflow.', 'danger')
                return _redirect_checkout_mode(mode)

            # Check if asset is available
            if asset.status != 'available':
                flash(f'Asset {asset.asset_tag} is not available for checkout.', 'danger')
                return _redirect_checkout_mode(mode)

            checked_out_to = request.form.get('checked_out_to', '').strip()
            if not checked_out_to:
                flash('Please enter who the asset is checked out to.', 'danger')
                return _redirect_checkout_mode(mode)

            matched_user = _match_user_by_identifier(checked_out_to)
            if '@' in checked_out_to:
                if not matched_user:
                    flash('No user found with that email. Create the user or enter a name instead.', 'warning')
                    return _redirect_checkout_mode(mode)
            else:
                is_tag_like = re.match(r'^[A-Za-z0-9-]{3,}$', checked_out_to) is not None
                if is_tag_like:
                    if not matched_user:
                        flash('No user found with that asset tag. Create the user or enter a name instead.', 'warning')
                        return _redirect_checkout_mode(mode)
                elif mode_meta['requires_existing_user'] and not matched_user:
                    flash('Select an existing user by email, asset tag, or exact name for this checkout type.', 'danger')
                    return _redirect_checkout_mode(mode)

            if mode_meta['requires_existing_user'] and not matched_user:
                flash('This checkout type requires assignment to an existing user.', 'danger')
                return _redirect_checkout_mode(mode)

            if matched_user:
                checked_out_to = matched_user.name

            # Create checkout record
            checkout_record = Checkout(
                asset_id=asset.id,
                checked_out_to=checked_out_to,
                checked_out_by=current_user.id,
                checkout_date=datetime.utcnow()
            )

            # Set expected return date if provided
            if mode_meta['show_expected_return'] and request.form.get('expected_return_date'):
                checkout_record.expected_return_date = datetime.strptime(
                    request.form['expected_return_date'], '%Y-%m-%d'
                ).date()

            # Update asset status
            if mode == 'consumables':
                checkout_record.checked_in_date = checkout_record.checkout_date
                checkout_record.checkin_condition = 'consumed'
                checkout_record.checkin_notes = 'Consumable issued (non-returnable).'
                asset.status = 'retired'
            else:
                asset.status = 'checked_out'
            asset.updated_at = datetime.utcnow()
            if mode == 'licenses' and matched_user:
                asset.license_assigned_to = matched_user.email or matched_user.name

            db.session.add(checkout_record)
            db.session.flush()
            append_ledger_entry(
                event_type='asset_checked_out',
                entity_type='checkout',
                entity_id=checkout_record.id,
                actor_id=current_user.id,
                payload={
                    'asset_id': asset.id,
                    'asset_tag': asset.asset_tag,
                    'checked_out_to': checkout_record.checked_out_to,
                    'expected_return_date': checkout_record.expected_return_date.isoformat() if checkout_record.expected_return_date else None,
                    'checkout_mode': mode,
                    'non_returnable': mode == 'consumables',
                }
            )
            _create_checkout_notifications(
                asset=asset,
                mode=mode,
                checked_out_to=checkout_record.checked_out_to,
                actor_user=current_user,
                recipient_user=matched_user,
            )
            db.session.commit()

            if mode == 'consumables':
                flash(
                    f'Consumable {asset.asset_tag} issued to {checkout_record.checked_out_to}. '
                    'This item is non-returnable and has been marked as retired.',
                    'success'
                )
            elif mode == 'licenses':
                flash(f'License {asset.asset_tag} assigned to {checkout_record.checked_out_to}.', 'success')
            elif mode == 'accessories':
                flash(f'Accessory {asset.asset_tag} checked out to {checkout_record.checked_out_to}.', 'success')
            else:
                flash(f'Asset {asset.asset_tag} checked out to {checkout_record.checked_out_to}!', 'success')
            return redirect(url_for('checkouts.checkout', mode=mode))

        except Exception as e:
            db.session.rollback()
            flash(f'Error checking out asset: {str(e)}', 'danger')

    # Get available assets for checkout
    available_assets = Asset.query.filter_by(status='available').order_by(Asset.type, Asset.asset_tag).all()
    filtered_assets = _assets_for_checkout_mode(available_assets, mode)
    mode_meta = CHECKOUT_MODE_META[mode]
    mode_options = [(key, CHECKOUT_MODE_META[key]) for key in CHECKOUT_MODE_ORDER]

    return render_template(
        'checkouts/checkout.html',
        assets=filtered_assets,
        checkout_mode=mode,
        checkout_mode_meta=mode_meta,
        checkout_mode_options=mode_options,
    )


@checkouts_bp.route('/checkin', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'helpdesk')
def checkin():
    """Check in an asset."""
    if request.method == 'POST':
        try:
            asset_id = request.form.get('asset_id')
            asset = Asset.query.get_or_404(asset_id)

            if asset.is_consumable:
                flash('Consumables are non-returnable and cannot be checked in.', 'warning')
                return redirect(url_for('checkouts.checkin'))

            # Get active checkout
            active_checkout = asset.current_checkout

            if not active_checkout:
                flash(f'Asset {asset.asset_tag} is not currently checked out.', 'danger')
                return redirect(url_for('checkouts.checkin'))

            # Update checkout record
            active_checkout.checked_in_date = datetime.utcnow()
            active_checkout.checkin_condition = request.form.get('checkin_condition', 'good')
            active_checkout.checkin_notes = request.form.get('checkin_notes', '')

            # Update asset status and condition
            asset.status = 'available'
            asset.condition = active_checkout.checkin_condition
            asset.updated_at = datetime.utcnow()
            if asset.is_license:
                asset.license_assigned_to = None

            if active_checkout.checkin_condition == 'needs_repair':
                if not asset.current_repair:
                    db.session.add(RepairTicket(
                        asset_id=asset.id,
                        status='triage',
                        notes='Auto-created from check-in (needs repair).'
                    ))
                record_damage_incident(
                    asset_id=asset.id,
                    checked_out_to=active_checkout.checked_out_to,
                    source='checkin',
                    notes=active_checkout.checkin_notes,
                    checkout_id=active_checkout.id
                    )

            append_ledger_entry(
                event_type='asset_checked_in',
                entity_type='checkout',
                entity_id=active_checkout.id,
                actor_id=current_user.id,
                payload={
                    'asset_id': asset.id,
                    'asset_tag': asset.asset_tag,
                    'checked_out_to': active_checkout.checked_out_to,
                    'condition': active_checkout.checkin_condition,
                    'notes': active_checkout.checkin_notes,
                }
            )
            db.session.commit()

            flash(f'Asset {asset.asset_tag} checked in successfully!', 'success')
            return redirect(url_for('assets.detail', asset_id=asset.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error checking in asset: {str(e)}', 'danger')

    # Get checked out assets
    checked_out_assets = Asset.query.filter_by(status='checked_out').order_by(Asset.asset_tag).all()
    checked_out_assets = [asset for asset in checked_out_assets if not asset.is_consumable]

    return render_template('checkouts/checkin.html', assets=checked_out_assets)


@checkouts_bp.route('/search')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def search():
    """Search for assets (AJAX endpoint)."""
    query = request.args.get('q', '')
    status_filter = request.args.get('status', '')

    if not query:
        return jsonify([])

    search_filter = f'%{query}%'
    asset_query = Asset.query.filter(
        db.or_(
            Asset.asset_tag.ilike(search_filter),
            Asset.name.ilike(search_filter),
            Asset.serial_number.ilike(search_filter)
        )
    )

    if status_filter:
        asset_query = asset_query.filter_by(status=status_filter)

    assets = asset_query.limit(10).all()

    results = [{
        'id': asset.id,
        'asset_tag': asset.asset_tag,
        'name': asset.name,
        'status': asset.status,
        'location': asset.location or ''
    } for asset in assets]

    return jsonify(results)


@checkouts_bp.route('/fast-checkout', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'helpdesk')
def fast_checkout():
    """Fast checkout for bulk deployments (e.g., beginning of year)."""
    # Initialize session counter if not exists
    if 'fast_checkout_count' not in session:
        session['fast_checkout_count'] = 0

    if request.method == 'POST':
        action = request.form.get('action')

        # Reset counter
        if action == 'reset':
            session['fast_checkout_count'] = 0
            flash('Checkout counter reset.', 'info')
            return redirect(url_for('checkouts.fast_checkout'))

        # Handle student/user search or creation
        if action == 'find_student':
            student_identifier = request.form.get('student_identifier', '').strip()

            if not student_identifier:
                flash('Please enter a student ID, email, or name.', 'warning')
                return redirect(url_for('checkouts.fast_checkout'))

            # Search for student by email, name, or treat as student ID
            search_filter = f'%{student_identifier}%'
            student = User.query.filter(
                db.or_(
                    User.email.ilike(search_filter),
                    User.name.ilike(search_filter),
                    User.email == student_identifier
                )
            ).first()

            if student:
                # Store student info in session
                session['fast_checkout_student'] = {
                    'id': student.id,
                    'name': student.name,
                    'email': student.email
                }
                return redirect(url_for('checkouts.fast_checkout', step='asset'))
            else:
                # Student not found, show create option
                return redirect(url_for('checkouts.fast_checkout', step='create_student', identifier=student_identifier))

        # Create new student
        elif action == 'create_student':
            try:
                student_name = request.form.get('student_name', '').strip()
                student_email = request.form.get('student_email', '').strip()
                student_asset_tag = request.form.get('student_asset_tag', '').strip() or None
                student_grade_level = request.form.get('student_grade_level', '').strip() or None

                if not student_name or not student_email:
                    flash('Name and email are required.', 'danger')
                    return redirect(url_for('checkouts.fast_checkout', step='create_student'))

                # Create new user (student)
                new_student = User(
                    name=student_name,
                    email=student_email,
                    role='student',
                    asset_tag=student_asset_tag,
                    grade_level=student_grade_level
                )
                new_student.set_password('changeme123')  # Default password
                db.session.add(new_student)
                db.session.flush()
                append_ledger_entry(
                    event_type='user_created',
                    entity_type='user',
                    entity_id=new_student.id,
                    actor_id=current_user.id,
                    payload={
                        'name': new_student.name,
                        'email': new_student.email,
                        'role': new_student.role,
                        'source': 'fast_checkout',
                    }
                )
                db.session.commit()

                # Store student info in session
                session['fast_checkout_student'] = {
                    'id': new_student.id,
                    'name': new_student.name,
                    'email': new_student.email
                }

                flash(f'Student {student_name} created successfully!', 'success')
                return redirect(url_for('checkouts.fast_checkout', step='asset'))

            except Exception as e:
                db.session.rollback()
                flash(f'Error creating student: {str(e)}', 'danger')
                return redirect(url_for('checkouts.fast_checkout', step='create_student'))

        # Handle asset checkout
        elif action == 'checkout_asset':
            asset_identifier = request.form.get('asset_identifier', '').strip()

            if not asset_identifier:
                flash('Please enter an asset tag or serial number.', 'warning')
                return redirect(url_for('checkouts.fast_checkout', step='asset'))

            # Get student from session
            student_info = session.get('fast_checkout_student')
            if not student_info:
                flash('Student information lost. Please start over.', 'danger')
                return redirect(url_for('checkouts.fast_checkout'))

            # Search for asset by tag or serial number
            asset = Asset.query.filter(
                db.or_(
                    Asset.asset_tag == asset_identifier,
                    Asset.serial_number == asset_identifier
                )
            ).first()

            if not asset:
                flash(f'Asset not found: {asset_identifier}', 'danger')
                return redirect(url_for('checkouts.fast_checkout', step='asset'))

            # Check if asset is available
            if asset.status not in ['available', 'maintenance']:
                flash(f'Asset {asset.asset_tag} is already {asset.status}.', 'warning')
                return redirect(url_for('checkouts.fast_checkout', step='asset'))
            if asset.checkout_bucket != 'assets':
                flash('Fast checkout is for returnable device assets only.', 'warning')
                return redirect(url_for('checkouts.fast_checkout', step='asset'))

            try:
                # Create checkout record
                checkout_record = Checkout(
                    asset_id=asset.id,
                    checked_out_to=student_info['name'],
                    checked_out_by=current_user.id,
                    checkout_date=datetime.utcnow(),
                    expected_return_date=(datetime.utcnow() + timedelta(days=365)).date()  # 1 year deployment
                )

                # Update asset status to deployed
                asset.status = 'deployed'
                asset.updated_at = datetime.utcnow()

                db.session.add(checkout_record)
                db.session.flush()
                append_ledger_entry(
                    event_type='asset_deployed',
                    entity_type='checkout',
                    entity_id=checkout_record.id,
                    actor_id=current_user.id,
                    payload={
                        'asset_id': asset.id,
                        'asset_tag': asset.asset_tag,
                        'checked_out_to': checkout_record.checked_out_to,
                        'expected_return_date': checkout_record.expected_return_date.isoformat() if checkout_record.expected_return_date else None,
                    }
                )
                db.session.commit()

                # Increment counter
                session['fast_checkout_count'] = session.get('fast_checkout_count', 0) + 1

                # Store deployment info for confirmation screen
                session['last_deployment'] = {
                    'student_name': student_info['name'],
                    'student_email': student_info['email'],
                    'asset_tag': asset.asset_tag,
                    'asset_name': asset.name
                }

                flash(f'✓ {asset.asset_tag} deployed to {student_info["name"]}', 'success')

                # Clear student from session for next checkout
                session.pop('fast_checkout_student', None)

                return redirect(url_for('checkouts.fast_checkout', step='confirmation'))

            except Exception as e:
                db.session.rollback()
                flash(f'Error deploying asset: {str(e)}', 'danger')
                return redirect(url_for('checkouts.fast_checkout', step='asset'))

    # GET request - determine which step to show
    step = request.args.get('step', 'student')
    student_info = session.get('fast_checkout_student')
    identifier = request.args.get('identifier', '')
    last_deployment = session.get('last_deployment')

    return render_template('checkouts/fast_checkout.html',
                         step=step,
                         student_info=student_info,
                         identifier=identifier,
                         last_deployment=last_deployment,
                         checkout_count=session.get('fast_checkout_count', 0))


@checkouts_bp.route('/fast-checkin', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'helpdesk')
def fast_checkin():
    """Fast check-in for bulk returns."""
    # Initialize session counter if not exists
    if 'fast_checkin_count' not in session:
        session['fast_checkin_count'] = 0

    if request.method == 'POST':
        action = request.form.get('action')

        # Reset counter
        if action == 'reset':
            session['fast_checkin_count'] = 0
            flash('Check-in counter reset.', 'info')
            return redirect(url_for('checkouts.fast_checkin'))

        # Handle asset check-in
        elif action == 'checkin_asset':
            asset_identifier = request.form.get('asset_identifier', '').strip()

            if not asset_identifier:
                flash('Please enter an asset tag or serial number.', 'warning')
                return redirect(url_for('checkouts.fast_checkin'))

            # Search for asset by tag or serial number
            asset = Asset.query.filter(
                db.or_(
                    Asset.asset_tag == asset_identifier,
                    Asset.serial_number == asset_identifier
                )
            ).first()

            if not asset:
                flash(f'Asset not found: {asset_identifier}', 'danger')
                return redirect(url_for('checkouts.fast_checkin'))
            if asset.is_consumable:
                flash('Consumables are non-returnable and cannot be checked in.', 'warning')
                return redirect(url_for('checkouts.fast_checkin'))

            # Get active checkout
            active_checkout = asset.current_checkout

            if not active_checkout:
                flash(f'Asset {asset.asset_tag} is not currently checked out.', 'warning')
                return redirect(url_for('checkouts.fast_checkin'))

            # Store asset info in session for notes
            session['fast_checkin_asset'] = {
                'id': asset.id,
                'asset_tag': asset.asset_tag,
                'name': asset.name,
                'checked_out_to': active_checkout.checked_out_to
            }

            return redirect(url_for('checkouts.fast_checkin', step='notes'))

        # Complete check-in with notes
        elif action == 'complete_checkin':
            asset_info = session.get('fast_checkin_asset')
            if not asset_info:
                flash('Asset information lost. Please start over.', 'danger')
                return redirect(url_for('checkouts.fast_checkin'))

            asset = Asset.query.get(asset_info['id'])
            if not asset:
                flash('Asset not found.', 'danger')
                return redirect(url_for('checkouts.fast_checkin'))
            if asset.is_consumable:
                flash('Consumables are non-returnable and cannot be checked in.', 'warning')
                return redirect(url_for('checkouts.fast_checkin'))

            active_checkout = asset.current_checkout
            if not active_checkout:
                flash('No active checkout found.', 'warning')
                return redirect(url_for('checkouts.fast_checkin'))

            try:
                # Get form data
                condition = request.form.get('condition', 'good')
                notes = request.form.get('notes', '').strip()

                # Update checkout record
                active_checkout.checked_in_date = datetime.utcnow()
                active_checkout.checkin_condition = condition
                active_checkout.checkin_notes = notes

                # Update asset status and condition
                asset.status = 'available'
                asset.condition = condition
                asset.updated_at = datetime.utcnow()
                if asset.is_license:
                    asset.license_assigned_to = None

                if condition == 'needs_repair':
                    if not asset.current_repair:
                        db.session.add(RepairTicket(
                            asset_id=asset.id,
                            status='triage',
                            notes='Auto-created from fast check-in (needs repair).'
                        ))
                    record_damage_incident(
                        asset_id=asset.id,
                        checked_out_to=active_checkout.checked_out_to,
                        source='fast_checkin',
                        notes=notes,
                        checkout_id=active_checkout.id
                    )

                append_ledger_entry(
                    event_type='asset_checked_in',
                    entity_type='checkout',
                    entity_id=active_checkout.id,
                    actor_id=current_user.id,
                    payload={
                        'asset_id': asset.id,
                        'asset_tag': asset.asset_tag,
                        'checked_out_to': active_checkout.checked_out_to,
                        'condition': condition,
                        'notes': notes,
                        'source': 'fast_checkin',
                    }
                )
                db.session.commit()

                # Increment counter
                session['fast_checkin_count'] = session.get('fast_checkin_count', 0) + 1

                # Store check-in info for confirmation
                session['last_checkin'] = {
                    'asset_tag': asset.asset_tag,
                    'asset_name': asset.name,
                    'student_name': active_checkout.checked_out_to,
                    'condition': condition,
                    'notes': notes
                }

                flash(f'✓ {asset.asset_tag} checked in from {active_checkout.checked_out_to}', 'success')

                # Clear asset from session
                session.pop('fast_checkin_asset', None)

                return redirect(url_for('checkouts.fast_checkin', step='checkin_confirmation'))

            except Exception as e:
                db.session.rollback()
                flash(f'Error checking in asset: {str(e)}', 'danger')
                return redirect(url_for('checkouts.fast_checkin', step='notes'))

    # GET request - determine which step to show
    step = request.args.get('step', 'scan')
    asset_info = session.get('fast_checkin_asset')
    last_checkin = session.get('last_checkin')

    return render_template('checkouts/fast_checkin.html',
                         step=step,
                         asset_info=asset_info,
                         last_checkin=last_checkin,
                         checkin_count=session.get('fast_checkin_count', 0))


@checkouts_bp.route('/loaner-swap', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'helpdesk')
def loaner_swap():
    """Swap a broken item with a loaner (check in broken, check out loaner)."""
    if request.method == 'POST':
        try:
            # Get broken asset
            broken_asset_id = request.form.get('broken_asset_id')
            broken_asset = Asset.query.get_or_404(broken_asset_id)

            # Get loaner asset
            loaner_asset_id = request.form.get('loaner_asset_id')
            loaner_asset = Asset.query.get_or_404(loaner_asset_id)

            # Validate broken asset is checked out
            active_checkout = broken_asset.current_checkout
            if not active_checkout:
                flash(f'Asset {broken_asset.asset_tag} is not currently checked out.', 'danger')
                return redirect(url_for('checkouts.loaner_swap'))
            if broken_asset.checkout_bucket != 'assets':
                flash('Loaner swap is only available for returnable device assets.', 'danger')
                return redirect(url_for('checkouts.loaner_swap'))

            # Validate loaner is available
            if loaner_asset.status != 'available':
                flash(f'Loaner {loaner_asset.asset_tag} is not available.', 'danger')
                return redirect(url_for('checkouts.loaner_swap'))
            if loaner_asset.checkout_bucket != 'assets':
                flash('Selected loaner is not a returnable device asset.', 'danger')
                return redirect(url_for('checkouts.loaner_swap'))

            # Get form data
            checkin_notes = request.form.get('checkin_notes', '').strip()

            # Step 1: Check in the broken asset
            active_checkout.checked_in_date = datetime.utcnow()
            active_checkout.checkin_condition = 'needs_repair'
            active_checkout.checkin_notes = f"LOANER SWAP - {checkin_notes}" if checkin_notes else "LOANER SWAP"

            # Set broken asset to maintenance status
            broken_asset.status = 'maintenance'
            broken_asset.condition = 'needs_repair'
            broken_asset.updated_at = datetime.utcnow()
            if not broken_asset.current_repair:
                db.session.add(RepairTicket(
                    asset_id=broken_asset.id,
                    status='triage',
                    notes='Auto-created from loaner swap (needs repair).'
                ))
            record_damage_incident(
                asset_id=broken_asset.id,
                checked_out_to=active_checkout.checked_out_to,
                source='loaner_swap',
                notes=checkin_notes,
                checkout_id=active_checkout.id
            )

            # Step 2: Check out the loaner to the same person
            loaner_checkout = Checkout(
                asset_id=loaner_asset.id,
                checked_out_to=active_checkout.checked_out_to,
                checked_out_by=current_user.id,
                checkout_date=datetime.utcnow()
            )

            # Set expected return date if original had one
            if active_checkout.expected_return_date:
                loaner_checkout.expected_return_date = active_checkout.expected_return_date

            # Update loaner asset status
            loaner_asset.status = 'checked_out'
            loaner_asset.updated_at = datetime.utcnow()

            db.session.add(loaner_checkout)
            db.session.flush()
            append_ledger_entry(
                event_type='loaner_swap',
                entity_type='checkout',
                entity_id=loaner_checkout.id,
                actor_id=current_user.id,
                payload={
                    'broken_asset_id': broken_asset.id,
                    'broken_asset_tag': broken_asset.asset_tag,
                    'loaner_asset_id': loaner_asset.id,
                    'loaner_asset_tag': loaner_asset.asset_tag,
                    'checked_out_to': active_checkout.checked_out_to,
                }
            )
            db.session.commit()

            flash(f'✓ Swap completed! {broken_asset.asset_tag} (broken) checked in → {loaner_asset.asset_tag} (loaner) checked out to {active_checkout.checked_out_to}', 'success')
            return redirect(url_for('assets.detail', asset_id=loaner_asset.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error performing loaner swap: {str(e)}', 'danger')
            return redirect(url_for('checkouts.loaner_swap'))

    # GET request - show swap form
    # Get all checked out assets
    checked_out_assets = Asset.query.filter(
        Asset.status.in_(['checked_out', 'deployed'])
    ).order_by(Asset.asset_tag).all()
    checked_out_assets = [asset for asset in checked_out_assets if asset.checkout_bucket == 'assets']

    # Get all available assets (potential loaners)
    available_assets = Asset.query.filter_by(status='available').order_by(Asset.type, Asset.asset_tag).all()
    available_assets = [asset for asset in available_assets if asset.checkout_bucket == 'assets']

    return render_template('checkouts/loaner_swap.html',
                         checked_out_assets=checked_out_assets,
                         available_assets=available_assets)
