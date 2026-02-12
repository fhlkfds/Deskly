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
    username = db.Column(db.String(60), unique=True, index=True)
    role = db.Column(db.String(20), nullable=False, default='staff')  # admin, staff, teacher, student, helpdesk
    asset_tag = db.Column(db.String(50), index=True)
    grade_level = db.Column(db.String(20))
    repeat_breakage_flag = db.Column(db.Boolean, nullable=False, default=False, index=True)
    profile_picture_url = db.Column(db.Text)
    default_theme = db.Column(db.String(10), default='light')
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
    warranty_vendor = db.Column(db.String(120))
    warranty_end_date = db.Column(db.Date)
    warranty_notes = db.Column(db.Text)

    software_name = db.Column(db.String(200))
    license_key = db.Column(db.String(200))
    license_seats = db.Column(db.Integer)
    license_expires_on = db.Column(db.Date)
    license_assigned_to = db.Column(db.String(200))

    accessory_type = db.Column(db.String(120))
    accessory_compatibility = db.Column(db.String(200))
    accessory_notes = db.Column(db.Text)

    toner_model = db.Column(db.String(200))
    toner_compatible_printer = db.Column(db.String(200))
    toner_quantity = db.Column(db.Integer)
    toner_reorder_threshold = db.Column(db.Integer)

    # Google Sheets sync tracking
    google_sheets_row_id = db.Column(db.Integer)
    google_admin_device_ou_path = db.Column(db.String(255), index=True)
    google_admin_device_model = db.Column(db.String(120), index=True)
    device_group = db.Column(db.String(20), index=True)  # admin, helpdesk, staff, teacher, student
    google_admin_last_user_email = db.Column(db.String(120), index=True)
    google_admin_last_user_seen_at = db.Column(db.DateTime)
    google_admin_recent_users_json = db.Column(db.Text)
    google_admin_last_sync_at = db.Column(db.DateTime)

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

    @staticmethod
    def _normalized_value(value):
        return (value or '').strip().lower()

    @property
    def normalized_category(self):
        return self._normalized_value(self.category)

    @property
    def normalized_type(self):
        return self._normalized_value(self.type)

    @property
    def is_consumable(self):
        category = self.normalized_category
        asset_type = self.normalized_type
        return (
            category in {'consumable', 'consumables'}
            or asset_type in {'consumable', 'consumables', 'toner'}
        )

    @property
    def is_license(self):
        if self.is_consumable:
            return False
        category = self.normalized_category
        asset_type = self.normalized_type
        has_license_fields = any([
            bool(self.license_key),
            bool(self.license_assigned_to),
            bool(self.license_expires_on),
            self.license_seats is not None,
        ])
        return category in {'license', 'licenses'} or 'license' in asset_type or has_license_fields

    @property
    def is_accessory(self):
        if self.is_consumable or self.is_license:
            return False
        category = self.normalized_category
        return category in {'accessory', 'accessories'} or bool(self.accessory_type)

    @property
    def checkout_bucket(self):
        if self.is_consumable:
            return 'consumables'
        if self.is_license:
            return 'licenses'
        if self.is_accessory:
            return 'accessories'
        return 'assets'

    def __repr__(self):
        return f'<Asset {self.asset_tag}: {self.name}>'


# Asset categories and types
ASSET_CATEGORIES = [
    'Technology',
    'IT Infrastructure',
    'Accessories',
    'Licenses',
    'Consumables',
    'Other'
]

ASSET_TYPES = [
    'Laptop',
    'Tablet',
    'Charger',
    'Keyboard',
    'Mouse',
    'Headphones',
    'Consumable',
    'Software License',
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


class DocFolder(db.Model):
    """Folder for organizing documentation pages."""

    __tablename__ = 'doc_folders'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<DocFolder {self.name}>'


class Document(db.Model):
    """Markdown documentation page."""

    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    folder_id = db.Column(db.Integer, db.ForeignKey('doc_folders.id'), index=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    content_md = db.Column(db.Text, nullable=False, default='')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    folder = db.relationship('DocFolder', backref=db.backref('documents', lazy='dynamic'))
    creator = db.relationship('User', foreign_keys=[created_by])
    updater = db.relationship('User', foreign_keys=[updated_by])

    def __repr__(self):
        return f'<Document {self.id} {self.title}>'


class DocumentFile(db.Model):
    """Uploaded file for documentation pages."""

    __tablename__ = 'document_files'

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), index=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    relative_path = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(120))
    size_bytes = db.Column(db.Integer)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    document = db.relationship('Document', backref=db.backref('files', lazy='dynamic'))
    uploader = db.relationship('User')

    def __repr__(self):
        return f'<DocumentFile {self.id} {self.original_name}>'


class Ticket(db.Model):
    """Basic IT support ticket."""

    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    ticket_code = db.Column(db.String(20), unique=True, index=True)
    subject = db.Column(db.String(200), nullable=False, index=True)
    requester_email = db.Column(db.String(120), nullable=False, index=True)
    requester_name = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False, default='open', index=True)
    priority = db.Column(db.String(20), nullable=False, default='normal', index=True)
    category = db.Column(db.String(50), index=True)
    tags = db.Column(db.String(200))
    source = db.Column(db.String(20), nullable=False, default='gmail', index=True)
    gmail_message_id = db.Column(db.String(120), unique=True, index=True)
    body_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_message_at = db.Column(db.DateTime)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)

    assignee = db.relationship('User')

    def __repr__(self):
        return f'<Ticket {self.id} {self.subject}>'


class TicketComment(db.Model):
    """Ticket comments and internal notes."""

    __tablename__ = 'ticket_comments'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    ticket = db.relationship('Ticket', backref=db.backref('comments', lazy='dynamic'))
    author = db.relationship('User')

    def __repr__(self):
        return f'<TicketComment {self.id} ticket={self.ticket_id} internal={self.is_internal}>'


class TicketDocLink(db.Model):
    """Link a ticket to a documentation article."""

    __tablename__ = 'ticket_doc_links'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False, index=True)
    linked_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    ticket = db.relationship('Ticket', backref=db.backref('doc_links', lazy='dynamic'))
    document = db.relationship('Document')
    linked_by = db.relationship('User')

    def __repr__(self):
        return f'<TicketDocLink {self.id} ticket={self.ticket_id} doc={self.document_id}>'


class Notification(db.Model):
    """In-app notification for users."""

    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), index=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User')
    ticket = db.relationship('Ticket')

    def __repr__(self):
        return f'<Notification {self.id} user={self.user_id} read={self.is_read}>'


class OverdueAuditSweep(db.Model):
    """Monthly/quarterly overdue audit sweep run."""

    __tablename__ = 'overdue_audit_sweeps'

    id = db.Column(db.Integer, primary_key=True)
    period_type = db.Column(db.String(20), nullable=False, index=True)  # monthly, quarterly
    period_label = db.Column(db.String(40), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='open', index=True)  # open, completed
    generated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = db.Column(db.DateTime)
    generated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    generator = db.relationship('User')

    def __repr__(self):
        return f'<OverdueAuditSweep {self.id} {self.period_label}>'


class OverdueAuditSweepItem(db.Model):
    """An overdue checkout item captured in a sweep."""

    __tablename__ = 'overdue_audit_sweep_items'

    id = db.Column(db.Integer, primary_key=True)
    sweep_id = db.Column(db.Integer, db.ForeignKey('overdue_audit_sweeps.id'), nullable=False, index=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False, index=True)
    checkout_id = db.Column(db.Integer, db.ForeignKey('checkouts.id'), nullable=False, index=True)
    asset_tag = db.Column(db.String(50), nullable=False, index=True)
    asset_name = db.Column(db.String(200), nullable=False)
    checked_out_to = db.Column(db.String(100), nullable=False)
    expected_return_date = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)  # pending, verified
    scanned_at = db.Column(db.DateTime)
    scanned_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)

    sweep = db.relationship('OverdueAuditSweep', backref=db.backref('items', lazy='dynamic'))
    asset = db.relationship('Asset')
    checkout = db.relationship('Checkout')
    scanner = db.relationship('User')

    def __repr__(self):
        return f'<OverdueAuditSweepItem {self.id} {self.asset_tag} {self.status}>'


class OverdueAuditSweepScanLog(db.Model):
    """Scan attempt log for overdue audit sweep."""

    __tablename__ = 'overdue_audit_sweep_scan_logs'

    id = db.Column(db.Integer, primary_key=True)
    sweep_id = db.Column(db.Integer, db.ForeignKey('overdue_audit_sweeps.id'), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey('overdue_audit_sweep_items.id'), index=True)
    scanned_input = db.Column(db.String(100), nullable=False)
    matched = db.Column(db.Boolean, nullable=False, default=False, index=True)
    message = db.Column(db.Text)
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    scanned_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    sweep = db.relationship('OverdueAuditSweep', backref=db.backref('scan_logs', lazy='dynamic'))
    item = db.relationship('OverdueAuditSweepItem')
    scanner = db.relationship('User')

    def __repr__(self):
        return f'<OverdueAuditSweepScanLog {self.id} sweep={self.sweep_id} matched={self.matched}>'


class GoogleAdminRoleMapping(db.Model):
    """Maps Google Admin group email to local user role."""

    __tablename__ = 'google_admin_role_mappings'

    id = db.Column(db.Integer, primary_key=True)
    group_email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    role = db.Column(db.String(20), nullable=False, index=True)  # admin, helpdesk, staff, teacher, student
    enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<GoogleAdminRoleMapping {self.group_email} -> {self.role}>'


class GoogleAdminOuRoleMapping(db.Model):
    """Maps Google Admin OU path to local user role."""

    __tablename__ = 'google_admin_ou_role_mappings'

    id = db.Column(db.Integer, primary_key=True)
    ou_path = db.Column(db.String(255), nullable=False, unique=True, index=True)  # e.g. /Students/Grade-9
    role = db.Column(db.String(20), nullable=False, index=True)  # admin, helpdesk, staff, teacher, student
    enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<GoogleAdminOuRoleMapping {self.ou_path} -> {self.role}>'


class GoogleAdminSyncSchedule(db.Model):
    """Schedule for Google Admin user sync."""

    __tablename__ = 'google_admin_sync_schedules'

    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False, index=True)
    days_of_week = db.Column(db.String(30), nullable=False, default='')  # comma list: 0..6, Monday=0
    sync_device_ou = db.Column(db.Boolean, nullable=False, default=False)
    hour_utc = db.Column(db.Integer, nullable=False, default=1)
    minute_utc = db.Column(db.Integer, nullable=False, default=0)
    last_run_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<GoogleAdminSyncSchedule enabled={self.enabled} days={self.days_of_week}>'


class GoogleAdminSyncLog(db.Model):
    """Execution log for Google Admin sync."""

    __tablename__ = 'google_admin_sync_logs'

    id = db.Column(db.Integer, primary_key=True)
    trigger_type = db.Column(db.String(20), nullable=False)  # manual, scheduled
    status = db.Column(db.String(20), nullable=False, default='success')  # success, partial, failed
    users_processed = db.Column(db.Integer, nullable=False, default=0)
    users_created = db.Column(db.Integer, nullable=False, default=0)
    users_updated = db.Column(db.Integer, nullable=False, default=0)
    users_skipped = db.Column(db.Integer, nullable=False, default=0)
    devices_processed = db.Column(db.Integer, nullable=False, default=0)
    devices_updated = db.Column(db.Integer, nullable=False, default=0)
    devices_skipped = db.Column(db.Integer, nullable=False, default=0)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f'<GoogleAdminSyncLog {self.id} {self.status}>'


class GoogleAdminDeviceUserLog(db.Model):
    """Log of ChromeOS device users observed via Google Admin."""

    __tablename__ = 'google_admin_device_user_logs'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False, index=True)
    user_email = db.Column(db.String(120), index=True)
    observed_at = db.Column(db.DateTime, nullable=False, index=True)
    device_serial = db.Column(db.String(100))
    device_asset_tag = db.Column(db.String(100))
    recent_users_json = db.Column(db.Text)
    last_sync_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    asset = db.relationship('Asset', backref=db.backref('google_admin_user_logs', lazy='dynamic'))

    def __repr__(self):
        return f'<GoogleAdminDeviceUserLog {self.id} {self.user_email}>'


class GoogleAdminDeviceModelMapping(db.Model):
    """Maps Google Admin device model to local device group."""

    __tablename__ = 'google_admin_device_model_mappings'

    id = db.Column(db.Integer, primary_key=True)
    device_model = db.Column(db.String(120), nullable=False, unique=True, index=True)
    device_group = db.Column(db.String(20), nullable=False, index=True)  # admin, helpdesk, staff, teacher, student
    enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<GoogleAdminDeviceModelMapping {self.device_model} -> {self.device_group}>'


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


class AppSetting(db.Model):
    """Key/value application settings."""

    __tablename__ = 'app_settings'

    key = db.Column(db.String(120), primary_key=True)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<AppSetting {self.key}>'


class AuditLedgerEntry(db.Model):
    """Append-only audit ledger entry with hash chaining."""

    __tablename__ = 'audit_ledger_entries'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(80), nullable=False, index=True)
    entity_id = db.Column(db.Integer, index=True)
    actor_id = db.Column(db.Integer, index=True)
    payload_json = db.Column(db.Text)
    prev_hash = db.Column(db.String(64), index=True)
    entry_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)

    def __repr__(self):
        return f'<AuditLedgerEntry {self.id} {self.event_type}>'
