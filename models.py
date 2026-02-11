from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User model for authentication and tracking."""

    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='staff')  # admin, staff, teacher
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    checkouts = db.relationship('Checkout', backref='user', lazy='dynamic')

    def set_password(self, password):
        """Hash and set password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if password matches hash."""
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """Check if user is admin."""
        return self.role == 'admin'

    def __repr__(self):
        return f'<User {self.email}>'


class Asset(db.Model):
    """Asset model for tracking inventory items."""

    __tablename__ = 'assets'

    id = db.Column(db.Integer, primary_key=True)
    asset_tag = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)
    serial_number = db.Column(db.String(100))
    status = db.Column(db.String(20), nullable=False, default='available', index=True)
    # Status: available, checked_out, maintenance, retired

    location = db.Column(db.String(100))
    purchase_date = db.Column(db.Date)
    purchase_cost = db.Column(db.Float)
    condition = db.Column(db.String(20), default='good')  # good, fair, needs_repair
    notes = db.Column(db.Text)

    # Google Sheets sync tracking
    google_sheets_row_id = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    checkouts = db.relationship('Checkout', backref='asset', lazy='dynamic',
                               order_by='Checkout.checkout_date.desc()')

    @property
    def current_checkout(self):
        """Get current active checkout if any."""
        return self.checkouts.filter_by(checked_in_date=None).first()

    @property
    def is_available(self):
        """Check if asset is available for checkout."""
        return self.status == 'available'

    def __repr__(self):
        return f'<Asset {self.asset_tag}: {self.name}>'


# Asset categories and types
ASSET_CATEGORIES = [
    'Technology',
    'IT Infrastructure',
    'Accessories',
    'Other'
]

ASSET_TYPES = [
    'Laptop',
    'Tablet',
    'Charger',
    'Projector',
    'Printer',
    'Smart Board',
    'Server',
    'VM',
    'Docker Container',
    'Other'
]

ASSET_STATUSES = [
    'available',
    'checked_out',
    'deployed',
    'maintenance',
    'retired'
]

ASSET_CONDITIONS = [
    'good',
    'fair',
    'needs_repair'
]


class Checkout(db.Model):
    """Checkout model for tracking asset loans."""

    __tablename__ = 'checkouts'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False, index=True)

    # Checkout info
    checked_out_to = db.Column(db.String(100), nullable=False)  # Name of person receiving
    checked_out_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    checkout_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expected_return_date = db.Column(db.Date)

    # Checkin info
    checked_in_date = db.Column(db.DateTime)
    checkin_condition = db.Column(db.String(20))
    checkin_notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_active(self):
        """Check if checkout is still active."""
        return self.checked_in_date is None

    @property
    def is_overdue(self):
        """Check if checkout is overdue."""
        if self.is_active and self.expected_return_date:
            return datetime.utcnow().date() > self.expected_return_date
        return False

    def __repr__(self):
        return f'<Checkout {self.id}: Asset {self.asset_id} to {self.checked_out_to}>'


class SyncLog(db.Model):
    """Sync log for tracking Google Sheets synchronization."""

    __tablename__ = 'sync_logs'

    id = db.Column(db.Integer, primary_key=True)
    sync_type = db.Column(db.String(50), nullable=False)  # sheets_to_db, db_to_sheets, bidirectional
    status = db.Column(db.String(20), nullable=False)  # success, failure, partial
    message = db.Column(db.Text)
    records_processed = db.Column(db.Integer, default=0)
    errors_count = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<SyncLog {self.id}: {self.sync_type} - {self.status}>'
