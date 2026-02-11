from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Asset, ASSET_CATEGORIES, ASSET_TYPES, ASSET_STATUSES, ASSET_CONDITIONS
from datetime import datetime

assets_bp = Blueprint('assets', __name__, url_prefix='/assets')


@assets_bp.route('/')
@login_required
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
def detail(asset_id):
    """View asset details and history."""
    asset = Asset.query.get_or_404(asset_id)
    checkouts = asset.checkouts.all()

    return render_template('assets/detail.html', asset=asset, checkouts=checkouts)


@assets_bp.route('/new', methods=['GET', 'POST'])
@login_required
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
