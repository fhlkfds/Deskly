from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from auth import roles_required
from models import db, Asset, RepairTicket, Checkout, ASSET_CATEGORIES, ASSET_TYPES, ASSET_STATUSES, ASSET_CONDITIONS, REPAIR_STATUSES, REPAIR_STATUS_LABELS
from datetime import datetime
from breakage import record_damage_incident
import csv
import io
import re

assets_bp = Blueprint('assets', __name__, url_prefix='/assets')


@assets_bp.route('/')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def list_assets():
    """List all assets with filtering and pagination."""
    page = request.args.get('page', 1, type=int)
    per_page = 25

    # Get filter parameters
    category = request.args.get('category', '')
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    asset_type = request.args.get('type', '')

    # Build query
    query = Asset.query

    if category:
        query = query.filter_by(category=category)
    if status:
        query = query.filter_by(status=status)
    if asset_type:
        query = query.filter_by(type=asset_type)
    if search:
        search_filter = f'%{search}%'
        query = query.filter(
            db.or_(
                Asset.asset_tag.ilike(search_filter),
                Asset.name.ilike(search_filter),
                Asset.serial_number.ilike(search_filter)
            )
        )

    # Order by asset tag
    query = query.order_by(Asset.asset_tag)

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    assets = pagination.items

    return render_template('assets/list.html',
                         assets=assets,
                         pagination=pagination,
                         categories=ASSET_CATEGORIES,
                         statuses=ASSET_STATUSES,
                         types=ASSET_TYPES,
                         current_category=category,
                         current_status=status,
                         current_type=asset_type,
                         current_search=search)


@assets_bp.route('/<int:asset_id>')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def detail(asset_id):
    """View asset details and history."""
    asset = Asset.query.get_or_404(asset_id)
    checkouts = asset.checkouts.all()

    return render_template('assets/detail.html',
                         asset=asset,
                         checkouts=checkouts)


@assets_bp.route('/new', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def create():
    """Create new asset."""
    if request.method == 'POST':
        try:
            asset = Asset(
                asset_tag=request.form['asset_tag'],
                name=request.form['name'],
                category=request.form['category'],
                type=request.form['type'],
                serial_number=request.form.get('serial_number', ''),
                status=request.form.get('status', 'available'),
                location=request.form.get('location', ''),
                condition=request.form.get('condition', 'good'),
                notes=request.form.get('notes', '')
            )

            # Handle optional fields
            if request.form.get('purchase_date'):
                asset.purchase_date = datetime.strptime(request.form['purchase_date'], '%Y-%m-%d').date()
            if request.form.get('purchase_cost'):
                asset.purchase_cost = float(request.form['purchase_cost'])

            db.session.add(asset)
            db.session.commit()

            flash(f'Asset {asset.asset_tag} created successfully!', 'success')
            return redirect(url_for('assets.detail', asset_id=asset.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating asset: {str(e)}', 'danger')

    return render_template('assets/form.html',
                         asset=None,
                         categories=ASSET_CATEGORIES,
                         types=ASSET_TYPES,
                         statuses=ASSET_STATUSES,
                         conditions=ASSET_CONDITIONS)


@assets_bp.route('/<int:asset_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def edit(asset_id):
    """Edit existing asset."""
    asset = Asset.query.get_or_404(asset_id)

    if request.method == 'POST':
        try:
            asset.asset_tag = request.form['asset_tag']
            asset.name = request.form['name']
            asset.category = request.form['category']
            asset.type = request.form['type']
            asset.serial_number = request.form.get('serial_number', '')
            asset.status = request.form.get('status', 'available')
            asset.location = request.form.get('location', '')
            asset.condition = request.form.get('condition', 'good')
            asset.notes = request.form.get('notes', '')

            # Handle optional fields
            if request.form.get('purchase_date'):
                asset.purchase_date = datetime.strptime(request.form['purchase_date'], '%Y-%m-%d').date()
            else:
                asset.purchase_date = None

            if request.form.get('purchase_cost'):
                asset.purchase_cost = float(request.form['purchase_cost'])
            else:
                asset.purchase_cost = None

            asset.updated_at = datetime.utcnow()

            db.session.commit()
            flash(f'Asset {asset.asset_tag} updated successfully!', 'success')
            return redirect(url_for('assets.detail', asset_id=asset.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating asset: {str(e)}', 'danger')

    return render_template('assets/form.html',
                         asset=asset,
                         categories=ASSET_CATEGORIES,
                         types=ASSET_TYPES,
                         statuses=ASSET_STATUSES,
                         conditions=ASSET_CONDITIONS)


@assets_bp.route('/<int:asset_id>/delete', methods=['POST'])
@login_required
@roles_required('admin')
def delete(asset_id):
    """Soft delete asset (mark as retired)."""
    asset = Asset.query.get_or_404(asset_id)

    try:
        # Soft delete - mark as retired
        asset.status = 'retired'
        asset.updated_at = datetime.utcnow()
        db.session.commit()

        flash(f'Asset {asset.asset_tag} has been retired.', 'info')
        return redirect(url_for('assets.list_assets'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error retiring asset: {str(e)}', 'danger')
        return redirect(url_for('assets.detail', asset_id=asset.id))


@assets_bp.route('/repair', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'helpdesk')
def repair_assets():
    """Repair workflow: check in broken asset and check out replacement."""
    if request.method == 'POST':
        broken_asset_id = request.form.get('broken_asset_id')
        replacement_asset_id = request.form.get('replacement_asset_id')
        status = request.form.get('status', 'triage').strip()
        notes = request.form.get('notes', '').strip()

        if status not in REPAIR_STATUSES:
            flash('Invalid repair status selected.', 'danger')
            return redirect(url_for('assets.repair_assets'))

        try:
            broken_asset = Asset.query.get_or_404(broken_asset_id)
            replacement_asset = Asset.query.get_or_404(replacement_asset_id)

            active_checkout = broken_asset.current_checkout
            if not active_checkout:
                flash('Broken asset is not currently checked out.', 'danger')
                return redirect(url_for('assets.repair_assets'))

            if replacement_asset.status != 'available':
                flash('Replacement asset is not available.', 'danger')
                return redirect(url_for('assets.repair_assets'))

            # Check in broken asset
            active_checkout.checked_in_date = datetime.utcnow()
            active_checkout.checkin_condition = 'needs_repair'
            active_checkout.checkin_notes = f"REPAIR ASSET - {notes}" if notes else "REPAIR ASSET"

            broken_asset.status = 'maintenance'
            broken_asset.condition = 'needs_repair'
            broken_asset.updated_at = datetime.utcnow()
            record_damage_incident(
                asset_id=broken_asset.id,
                checked_out_to=active_checkout.checked_out_to,
                source='repair_workflow',
                notes=notes,
                checkout_id=active_checkout.id
            )

            # Create or update repair ticket
            repair = broken_asset.current_repair
            if repair:
                repair.status = status
                repair.notes = notes or repair.notes
            else:
                db.session.add(RepairTicket(
                    asset_id=broken_asset.id,
                    status=status,
                    notes=notes
                ))

            # Check out replacement to same person
            loaner_checkout = Checkout(
                asset_id=replacement_asset.id,
                checked_out_to=active_checkout.checked_out_to,
                checked_out_by=current_user.id,
                checkout_date=datetime.utcnow()
            )
            if active_checkout.expected_return_date:
                loaner_checkout.expected_return_date = active_checkout.expected_return_date

            replacement_asset.status = 'checked_out'
            replacement_asset.updated_at = datetime.utcnow()

            db.session.add(loaner_checkout)
            db.session.commit()

            flash('Repair workflow completed: broken asset checked in and replacement checked out.', 'success')
            return redirect(url_for('assets.detail', asset_id=replacement_asset.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error processing repair workflow: {str(e)}', 'danger')
            return redirect(url_for('assets.repair_assets'))

    checked_out_query = Asset.query.filter(
        Asset.status.in_(['checked_out', 'deployed'])
    ).join(Checkout, Checkout.asset_id == Asset.id).filter(Checkout.checked_in_date.is_(None))

    checked_out_assets = checked_out_query.order_by(Asset.asset_tag).all()
    available_assets = Asset.query.filter_by(status='available').order_by(Asset.type, Asset.asset_tag).all()
    open_repairs = RepairTicket.query.filter(RepairTicket.status != 'closed').order_by(RepairTicket.updated_at.desc()).all()

    return render_template('assets/repair.html',
                         checked_out_assets=checked_out_assets,
                         available_assets=available_assets,
                         repair_statuses=REPAIR_STATUSES,
                         repair_labels=REPAIR_STATUS_LABELS,
                         open_repairs=open_repairs)


@assets_bp.route('/import', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def import_assets():
    """Import assets from CSV."""
    if request.method == 'POST':
        upload = request.files.get('file')
        if not upload or upload.filename == '':
            flash('Please choose a CSV file to import.', 'warning')
            return redirect(url_for('assets.import_assets'))

        try:
            content = upload.stream.read().decode('utf-8-sig')
        except Exception:
            flash('Unable to read file. Please upload a valid UTF-8 CSV.', 'danger')
            return redirect(url_for('assets.import_assets'))

        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            flash('CSV is missing header row.', 'danger')
            return redirect(url_for('assets.import_assets'))

        def normalize_header(value):
            return re.sub(r'[^a-z0-9_]', '', value.strip().lower().replace(' ', '_'))

        header_map = {normalize_header(h): h for h in reader.fieldnames}

        def get_value(row, key):
            original = header_map.get(key)
            return row.get(original, '').strip() if original else ''

        created = 0
        skipped = 0
        errors = []

        for idx, row in enumerate(reader, start=2):
            asset_tag = get_value(row, 'asset_tag')
            name = get_value(row, 'name')
            category = get_value(row, 'category')
            asset_type = get_value(row, 'type')
            serial_number = get_value(row, 'serial_number') or None
            status = get_value(row, 'status') or 'available'
            location = get_value(row, 'location') or None
            condition = get_value(row, 'condition') or 'good'
            notes = get_value(row, 'notes') or None
            purchase_date_raw = get_value(row, 'purchase_date')
            purchase_cost_raw = get_value(row, 'purchase_cost')

            if not asset_tag or not name or not category or not asset_type:
                errors.append(f'Row {idx}: asset_tag, name, category, and type are required.')
                continue
            if category not in ASSET_CATEGORIES:
                errors.append(f'Row {idx}: invalid category \"{category}\".')
                continue
            if asset_type not in ASSET_TYPES:
                errors.append(f'Row {idx}: invalid type \"{asset_type}\".')
                continue
            if status not in ASSET_STATUSES:
                errors.append(f'Row {idx}: invalid status \"{status}\".')
                continue
            if condition not in ASSET_CONDITIONS:
                errors.append(f'Row {idx}: invalid condition \"{condition}\".')
                continue

            if Asset.query.filter_by(asset_tag=asset_tag).first():
                skipped += 1
                continue

            asset = Asset(
                asset_tag=asset_tag,
                name=name,
                category=category,
                type=asset_type,
                serial_number=serial_number,
                status=status,
                location=location,
                condition=condition,
                notes=notes
            )

            if purchase_date_raw:
                try:
                    asset.purchase_date = datetime.strptime(purchase_date_raw, '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f'Row {idx}: invalid purchase_date \"{purchase_date_raw}\". Use YYYY-MM-DD.')
                    continue

            if purchase_cost_raw:
                try:
                    asset.purchase_cost = float(purchase_cost_raw)
                except ValueError:
                    errors.append(f'Row {idx}: invalid purchase_cost \"{purchase_cost_raw}\".')
                    continue

            db.session.add(asset)
            created += 1

        if created:
            db.session.commit()

        if errors:
            flash('Import completed with errors. See details below.', 'warning')
            return render_template(
                'assets/import.html',
                created=created,
                skipped=skipped,
                errors=errors[:20]
            )

        flash(f'Import complete: {created} created, {skipped} skipped.', 'success')
        return redirect(url_for('assets.list_assets'))

    return render_template('assets/import.html')


@assets_bp.route('/template.csv')
@login_required
@roles_required('admin')
def assets_template():
    """Download CSV template for assets."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'asset_tag',
        'name',
        'category',
        'type',
        'serial_number',
        'status',
        'location',
        'purchase_date',
        'purchase_cost',
        'condition',
        'notes'
    ])
    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='assets_template.csv'
    )
