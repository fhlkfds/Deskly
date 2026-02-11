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
    role = db.Column(db.String(20), nullable=False, default='staff')  # admin, staff, teacher, student, helpdesk
    asset_tag = db.Column(db.String(50), index=True)
    grade_level = db.Column(db.String(20))
    repeat_breakage_flag = db.Column(db.Boolean, nullable=False, default=False, index=True)
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
    repeat_breakage_flag = db.Column(db.Boolean, nullable=False, default=False, index=True)
    notes = db.Column(db.Text)

    # Google Sheets sync tracking
    google_sheets_row_id = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    checkouts = db.relationship('Checkout', backref='asset', lazy='dynamic',
                               order_by='Checkout.checkout_date.desc()')
    repairs = db.relationship('RepairTicket', backref='asset', lazy='dynamic',
                              order_by='RepairTicket.updated_at.desc()')

    @property
    def current_checkout(self):
        """Get current active checkout if any."""
        return self.checkouts.filter_by(checked_in_date=None).first()

    @property
    def is_available(self):
        """Check if asset is available for checkout."""
        return self.status == 'available'

    @property
    def current_repair(self):
        """Get current active repair ticket if any."""
        return self.repairs.filter(RepairTicket.status != 'closed').first()

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


REPAIR_STATUSES = [
    'triage',
    'in_repair',
    'waiting_parts',
    'ready',
    'closed'
]

REPAIR_STATUS_LABELS = {
    'triage': 'In Triage',
    'in_repair': 'In Repair',
    'waiting_parts': 'Waiting Parts',
    'ready': 'Ready',
    'closed': 'Closed'
}


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


class RepairTicket(db.Model):
    """Repair ticket for tracking maintenance lifecycle."""

    __tablename__ = 'repair_tickets'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='triage', index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<RepairTicket {self.id}: Asset {self.asset_id} - {self.status}>'


class DamageIncident(db.Model):
    """Damage incident records used for repeat-breakage detection."""

    __tablename__ = 'damage_incidents'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    checkout_id = db.Column(db.Integer, db.ForeignKey('checkouts.id'), index=True)
    checked_out_to = db.Column(db.String(100), nullable=False)
    source = db.Column(db.String(50), nullable=False)  # checkin, fast_checkin, loaner_swap, repair_workflow
    notes = db.Column(db.Text)
    incident_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    asset = db.relationship('Asset', backref=db.backref('damage_incidents', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('damage_incidents', lazy='dynamic'))
    checkout = db.relationship('Checkout', backref=db.backref('damage_incidents', lazy='dynamic'))

    def __repr__(self):
        return f'<DamageIncident {self.id}: Asset {self.asset_id}>'


class EscalationCase(db.Model):
    """Escalation workflow for repeat breakage incidents."""

    __tablename__ = 'escalation_cases'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(20), nullable=False, index=True)  # asset, user
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    status = db.Column(db.String(30), nullable=False, default='open', index=True)  # open, admin_review, parent_contact, resolved
    reason = db.Column(db.String(200), nullable=False)
    evidence = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    asset = db.relationship('Asset', foreign_keys=[asset_id], backref=db.backref('escalation_cases', lazy='dynamic'))
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('escalation_cases', lazy='dynamic'))
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<EscalationCase {self.id}: {self.entity_type}>'


class AuditSnapshotSchedule(db.Model):
    """Schedule settings for automated audit-ready snapshots."""

    __tablename__ = 'audit_snapshot_schedules'

    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False, index=True)
    recipient_email = db.Column(db.String(120))
    frequency = db.Column(db.String(20), nullable=False, default='daily')  # daily, weekly
    hour_utc = db.Column(db.Integer, nullable=False, default=1)
    minute_utc = db.Column(db.Integer, nullable=False, default=0)
    weekday_utc = db.Column(db.Integer, nullable=False, default=0)  # 0=Monday
    last_run_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<AuditSnapshotSchedule enabled={self.enabled} freq={self.frequency}>'


class AuditSnapshotLog(db.Model):
    """Execution log for manual/scheduled audit snapshots."""

    __tablename__ = 'audit_snapshot_logs'

    id = db.Column(db.Integer, primary_key=True)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    trigger_type = db.Column(db.String(20), nullable=False)  # manual, scheduled
    delivery_method = db.Column(db.String(20), nullable=False)  # download, email
    recipient_email = db.Column(db.String(120))
    zip_filename = db.Column(db.String(200), nullable=False)
    manifest_sha256 = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='success')  # success, failed
    message = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)

    creator = db.relationship('User')

    def __repr__(self):
        return f'<AuditSnapshotLog {self.id} {self.generated_at} {self.status}>'


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
