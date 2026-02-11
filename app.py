from flask import Flask, render_template, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from config import Config
from models import db, Asset, Checkout, User, RepairTicket
from auth import auth_bp, init_auth, roles_required
from assets import assets_bp
from checkouts import checkouts_bp
from settings import settings_bp
from users import users_bp
from reports import reports_bp
from docs import docs_bp
from scheduler import init_scheduler
from datetime import datetime, timedelta
import os

# Create Flask app
app = Flask(__name__)
app.config.from_object(Config)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Initialize extensions
db.init_app(app)
init_auth(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(assets_bp)
app.register_blueprint(checkouts_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(users_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(docs_bp)

# Initialize scheduler (commented out by default - uncomment when Google Sheets is configured)
init_scheduler(app)


@app.route('/')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def index():
    """Redirect to dashboard."""
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def dashboard():
    """Main dashboard view."""
    # Get summary statistics
    total_assets = Asset.query.filter(Asset.status != 'retired').count()
    available_assets = Asset.query.filter_by(status='available').count()
    checked_out_assets = Asset.query.filter_by(status='checked_out').count()
    deployed_assets = Asset.query.filter_by(status='deployed').count()
    maintenance_assets = Asset.query.filter_by(status='maintenance').count()
    open_repairs = RepairTicket.query.filter(RepairTicket.status != 'closed').count()

    # Recent checkouts (last 10)
    recent_checkouts = Checkout.query.order_by(Checkout.checkout_date.desc()).limit(10).all()

    # Overdue items
    overdue_checkouts = Checkout.query.filter(
        Checkout.checked_in_date.is_(None),
        Checkout.expected_return_date < datetime.utcnow().date()
    ).all()

    # Recent check-ins (last 10)
    recent_checkins = Checkout.query.filter(
        Checkout.checked_in_date.isnot(None)
    ).order_by(Checkout.checked_in_date.desc()).limit(10).all()

    return render_template('dashboard.html',
                         total_assets=total_assets,
                         available_assets=available_assets,
                         checked_out_assets=checked_out_assets,
                         deployed_assets=deployed_assets,
                         maintenance_assets=maintenance_assets,
                         open_repairs=open_repairs,
                         recent_checkouts=recent_checkouts,
                         recent_checkins=recent_checkins,
                         overdue_checkouts=overdue_checkouts)


@app.route('/search')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def search():
    """Global search across all asset fields."""
    query = request.args.get('q', '').strip()

    if not query or len(query) < 2:
        return jsonify([])

    # Build search filter
    search_filter = f'%{query}%'

    # Search across multiple fields
    results = Asset.query.filter(
        db.or_(
            Asset.asset_tag.ilike(search_filter),
            Asset.name.ilike(search_filter),
            Asset.serial_number.ilike(search_filter),
            Asset.location.ilike(search_filter),
            Asset.type.ilike(search_filter),
            Asset.category.ilike(search_filter),
            Asset.status.ilike(search_filter),
            Asset.condition.ilike(search_filter),
            Asset.notes.ilike(search_filter)
        )
    ).limit(20).all()

    # Format results
    search_results = []
    for asset in results:
        result = {
            'id': asset.id,
            'asset_tag': asset.asset_tag,
            'name': asset.name,
            'type': asset.type,
            'category': asset.category,
            'location': asset.location or '',
            'status': asset.status,
            'condition': asset.condition,
            'serial_number': asset.serial_number or '',
        }

        # Add current checkout info if checked out
        if asset.current_checkout:
            result['checked_out_to'] = asset.current_checkout.checked_out_to
            result['checkout_date'] = asset.current_checkout.checkout_date.strftime('%Y-%m-%d')
            if asset.current_checkout.expected_return_date:
                result['expected_return'] = asset.current_checkout.expected_return_date.strftime('%Y-%m-%d')

        search_results.append(result)

    return jsonify(search_results)


@app.errorhandler(404)
def not_found_error(error):
    """404 error handler."""
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """500 error handler."""
    db.session.rollback()
    return render_template('500.html'), 500


def init_db():
    """Initialize database with tables and sample data."""
    with app.app_context():
        # Create all tables
        db.create_all()

        # Check if admin user exists
        admin = User.query.filter_by(email='admin@school.edu').first()
        if not admin:
            # Create default admin user
            admin = User(
                email='admin@school.edu',
                name='Admin User',
                role='admin'
            )
            admin.set_password('admin123')
            db.session.add(admin)

            # Create sample staff user
            staff = User(
                email='staff@school.edu',
                name='Staff User',
                role='staff'
            )
            staff.set_password('staff123')
            db.session.add(staff)

            # Create sample assets
            sample_assets = [
                Asset(
                    asset_tag='LT001',
                    name='Dell Latitude 5420',
                    category='Technology',
                    type='Laptop',
                    serial_number='DL5420-001',
                    status='available',
                    location='Room 101',
                    condition='good',
                    notes='Standard teacher laptop'
                ),
                Asset(
                    asset_tag='TB001',
                    name='iPad Air 5th Gen',
                    category='Technology',
                    type='Tablet',
                    serial_number='IPAD-AIR-001',
                    status='available',
                    location='Room 102',
                    condition='good'
                ),
                Asset(
                    asset_tag='PR001',
                    name='Epson PowerLite Projector',
                    category='IT Infrastructure',
                    type='Projector',
                    serial_number='EPSON-PL-001',
                    status='available',
                    location='Room 103',
                    condition='good'
                ),
                Asset(
                    asset_tag='SB001',
                    name='SMART Board Interactive Display',
                    category='IT Infrastructure',
                    type='Smart Board',
                    serial_number='SMART-001',
                    status='available',
                    location='Room 104',
                    condition='good'
                ),
                Asset(
                    asset_tag='SRV001',
                    name='Dell PowerEdge R740',
                    category='IT Infrastructure',
                    type='Server',
                    serial_number='PE-R740-001',
                    status='maintenance',
                    location='Server Room',
                    condition='fair',
                    notes='Scheduled maintenance - disk replacement'
                )
            ]

            for asset in sample_assets:
                db.session.add(asset)

            db.session.commit()
            print('Database initialized with sample data!')
            print('Admin login: admin@school.edu / admin123')
            print('Staff login: staff@school.edu / staff123')


if __name__ == '__main__':
    # Initialize database if it doesn't exist
    if not os.path.exists('database.db'):
        init_db()

    app.run(debug=True, host='0.0.0.0', port=5000)
