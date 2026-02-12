import base64
import json
import os
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for, abort
from flask_login import login_required, current_user

from auth import roles_required
from config import Config
from models import db, Ticket, TicketComment, TicketDocLink, User, AppSetting, Document, Notification
from audit_ledger import append_ledger_entry

tickets_bp = Blueprint('tickets', __name__, url_prefix='/tickets')

DEFAULT_TICKET_CATEGORIES = [
    'Hardware',
    'Software',
    'Network',
    'Account',
    'Access',
    'Printer',
    'Other',
]

DEFAULT_TICKET_TAGS = [
    'battery',
    'broken',
    'charging',
    'email',
    'login',
    'network',
    'printer',
    'software',
    'slow',
    'wifi',
]

TAG_KEYWORDS = {
    'battery': ['battery', 'power', 'drain'],
    'broken': ['broken', 'cracked', 'damaged'],
    'charging': ['charge', 'charger', 'charging'],
    'email': ['email', 'gmail', 'outlook'],
    'login': ['login', 'sign in', 'password', 'account'],
    'network': ['network', 'lan', 'ethernet'],
    'printer': ['printer', 'print', 'toner'],
    'software': ['software', 'app', 'application', 'install'],
    'slow': ['slow', 'lag', 'freeze'],
    'wifi': ['wifi', 'wireless'],
}


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


def _append_unique(values, new_values):
    for value in new_values:
        if not value:
            continue
        if not any(existing.lower() == value.lower() for existing in values):
            values.append(value)
    return values


def _allowed_ticket_roles():
    return _get_list_setting('ticket_visibility_roles', ['admin', 'helpdesk', 'staff'])


def _ensure_ticket_access():
    if current_user.is_authenticated and current_user.role in _allowed_ticket_roles():
        return None
    return abort(403)


def _notification_recipients(ticket, actor_id):
    recipients = set()
    for user in User.query.filter(User.role.in_(['admin', 'helpdesk'])).all():
        recipients.add(user.id)
    if ticket.assigned_to_id:
        assignee = User.query.get(ticket.assigned_to_id)
        if assignee and assignee.role in ['admin', 'helpdesk']:
            recipients.add(ticket.assigned_to_id)
    return recipients


def _create_ticket_notification_for_users(ticket, user_ids, title, message):
    for user_id in set(user_ids):
        if not user_id:
            continue
        db.session.add(Notification(
            user_id=user_id,
            ticket_id=ticket.id,
            title=title,
            message=message,
        ))


def _create_ticket_notification(ticket, actor_id, title, message):
    recipients = _notification_recipients(ticket, actor_id)
    _create_ticket_notification_for_users(ticket, recipients, title, message)


def _find_requester_user(ticket):
    if not ticket.requester_email:
        return None
    return User.query.filter(User.email.ilike(ticket.requester_email)).first()


def _extract_mentions(body):
    if not body:
        return []
    tokens = []
    for raw in body.replace('\n', ' ').split(' '):
        if raw.startswith('@') and len(raw) > 1:
            token = raw[1:].strip('.,:;!?()[]{}<>')
            if token:
                tokens.append(token)
    return tokens


def _resolve_mentions(tokens):
    if not tokens:
        return []
    users = []
    for token in tokens:
        if '@' in token:
            users.extend(User.query.filter(User.email.ilike(token)).all())
        else:
            users.extend(User.query.filter(User.name.ilike(token)).all())
    return list({user.id: user for user in users}.values())


def _ticketing_gmail_enabled():
    return _get_setting('ticketing_gmail_enabled', 'false') == 'true'


def _import_gmail_messages():
    service = _get_gmail_service()
    query = (Config.GMAIL_IMPORT_QUERY or 'is:unread').strip() or 'is:unread'
    max_results = Config.GMAIL_IMPORT_MAX_RESULTS or 25
    response = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
    messages = response.get('messages', [])
    created = 0

    for msg in messages:
        message_id = msg.get('id')
        if not message_id:
            continue
        if Ticket.query.filter_by(gmail_message_id=message_id).first():
            continue

        full = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        payload = full.get('payload', {})
        headers = payload.get('headers', [])
        subject = _extract_header(headers, 'Subject') or '(No subject)'
        from_header = _extract_header(headers, 'From')
        date_header = _extract_header(headers, 'Date')
        snippet = full.get('snippet', '')
        body_text = _get_message_body(payload) or snippet

        requester_email = from_header
        requester_name = ''
        if '<' in from_header and '>' in from_header:
            requester_name = from_header.split('<')[0].strip().strip('"')
            requester_email = from_header.split('<')[-1].split('>')[0].strip()

        last_message_at = datetime.utcnow()
        if date_header:
            try:
                last_message_at = datetime.strptime(date_header[:25], '%a, %d %b %Y %H:%M:%S')
            except Exception:
                last_message_at = datetime.utcnow()

        ticket = Ticket(
            subject=subject,
            requester_email=requester_email or 'unknown@example.com',
            requester_name=requester_name or None,
            status='open',
            priority='normal',
            category=None,
            tags=None,
            source='gmail',
            gmail_message_id=message_id,
            body_text=body_text,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_message_at=last_message_at,
        )
        auto_tags = _infer_tags(subject, body_text)
        if auto_tags:
            tag_options = _get_list_setting('ticket_tags', DEFAULT_TICKET_TAGS)
            _append_unique(tag_options, auto_tags)
            _set_list_setting('ticket_tags', tag_options)
            ticket.tags = ','.join(auto_tags)
        auto_category = _infer_category(auto_tags)
        if auto_category:
            category_options = _get_list_setting('ticket_categories', DEFAULT_TICKET_CATEGORIES)
            _append_unique(category_options, [auto_category])
            _set_list_setting('ticket_categories', category_options)
            ticket.category = auto_category
        db.session.add(ticket)
        db.session.flush()
        _assign_ticket_code(ticket)
        _create_ticket_notification(
            ticket,
            None,
            f'New ticket {ticket.ticket_code}',
            ticket.subject,
        )
        created += 1

    db.session.commit()
    return created


def run_ticket_gmail_import_if_enabled():
    if not _ticketing_gmail_enabled():
        return 0
    created = _import_gmail_messages()
    return created

def _get_gmail_service():
    credentials_file = (Config.GMAIL_CREDENTIALS_FILE or '').strip()
    delegated_user = (Config.GMAIL_DELEGATED_USER or '').strip()
    if not credentials_file:
        raise RuntimeError('GMAIL_CREDENTIALS_FILE is not set in .env.')
    if not os.path.exists(credentials_file):
        raise FileNotFoundError(f'Gmail credentials file not found: {credentials_file}')
    if not delegated_user:
        raise RuntimeError('GMAIL_DELEGATED_USER is not set in .env.')

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except Exception as exc:
        raise RuntimeError('google-api-python-client is not installed. Run pip install -r requirements.txt') from exc

    scopes = ['https://www.googleapis.com/auth/gmail.readonly']
    creds = service_account.Credentials.from_service_account_file(credentials_file, scopes=scopes)
    delegated_creds = creds.with_subject(delegated_user)
    return build('gmail', 'v1', credentials=delegated_creds, cache_discovery=False)


def _extract_header(headers, name):
    for header in headers or []:
        if header.get('name', '').lower() == name.lower():
            return header.get('value', '')
    return ''


def _decode_body(data):
    if not data:
        return ''
    try:
        return base64.urlsafe_b64decode(data.encode('utf-8')).decode('utf-8', errors='replace')
    except Exception:
        return ''


def _get_message_body(payload):
    if not payload:
        return ''
    body = payload.get('body', {}).get('data')
    if body:
        return _decode_body(body)

    parts = payload.get('parts', []) or []
    for part in parts:
        if part.get('mimeType') == 'text/plain':
            return _decode_body(part.get('body', {}).get('data'))
    for part in parts:
        if part.get('mimeType') == 'text/html':
            return _decode_body(part.get('body', {}).get('data'))
    return ''


def _assign_ticket_code(ticket):
    if ticket.ticket_code:
        return
    ticket.ticket_code = f'T-{ticket.id:04d}'


def _infer_tags(subject, body):
    haystack = f"{subject or ''} {body or ''}".lower()
    matches = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            matches.append(tag)
    return matches


def _infer_category(tags):
    if not tags:
        return ''
    if 'printer' in tags:
        return 'Printer'
    if 'network' in tags or 'wifi' in tags:
        return 'Network'
    if 'software' in tags:
        return 'Software'
    if 'login' in tags or 'email' in tags:
        return 'Account'
    if 'charging' in tags or 'battery' in tags or 'broken' in tags:
        return 'Hardware'
    return 'Other'

def _normalize_category(value):
    return value.strip().title()


def _normalize_tags(values):
    return [value.strip().lower() for value in values if value.strip()]


@tickets_bp.route('/')
@login_required
def index():
    _ensure_ticket_access()
    query_text = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    assignee_id = request.args.get('assignee_id', type=int)
    priority = request.args.get('priority', '').strip()
    category = request.args.get('category', '').strip()
    tag = request.args.get('tag', '').strip()
    query = Ticket.query
    if query_text:
        search_filter = f'%{query_text}%'
        id_match = Ticket.id == int(query_text) if query_text.isdigit() else False
        query = query.filter(
            db.or_(
                Ticket.subject.ilike(search_filter),
                Ticket.body_text.ilike(search_filter),
                Ticket.ticket_code.ilike(search_filter),
                Ticket.requester_email.ilike(search_filter),
                id_match,
            )
        )
    if status:
        query = query.filter_by(status=status)
    if assignee_id:
        query = query.filter_by(assigned_to_id=assignee_id)
    if priority:
        query = query.filter_by(priority=priority)
    if category:
        query = query.filter_by(category=category)
    if tag:
        query = query.filter(Ticket.tags.ilike(f'%{tag}%'))
    tickets = query.order_by(Ticket.updated_at.desc()).limit(200).all()
    category_options = _get_list_setting('ticket_categories', DEFAULT_TICKET_CATEGORIES)
    tag_options = _get_list_setting('ticket_tags', DEFAULT_TICKET_TAGS)
    return render_template(
        'tickets/index.html',
        tickets=tickets,
        query_text=query_text,
        status=status,
        assignee_id=assignee_id,
        priority=priority,
        category=category,
        tag=tag,
        assignees=User.query.filter(User.role.in_(['admin', 'helpdesk', 'staff'])).order_by(User.name).all(),
        category_options=category_options,
        tag_options=tag_options,
        priority_options=['low', 'normal', 'high'],
        status_options=['open', 'triage', 'closed'],
    )


@tickets_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    _ensure_ticket_access()
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        requester_email = request.form.get('requester_email', '').strip()
        requester_name = request.form.get('requester_name', '').strip()
        body_text = request.form.get('body_text', '').strip()
        priority = request.form.get('priority', 'normal').strip() or 'normal'
        category = request.form.get('category', '').strip()
        tags = request.form.get('tags', '').split(',')

        if not subject or not requester_email:
            flash('Subject and requester email are required.', 'warning')
            category_options = _get_list_setting('ticket_categories', DEFAULT_TICKET_CATEGORIES)
            tag_options = _get_list_setting('ticket_tags', DEFAULT_TICKET_TAGS)
            return render_template('tickets/create.html', category_options=category_options, tag_options=tag_options)

        category_options = _get_list_setting('ticket_categories', DEFAULT_TICKET_CATEGORIES)
        tag_options = _get_list_setting('ticket_tags', DEFAULT_TICKET_TAGS)
        normalized_category = _normalize_category(category) if category else ''
        normalized_tags = _normalize_tags(tags)
        if normalized_category:
            _append_unique(category_options, [normalized_category])
            _set_list_setting('ticket_categories', category_options)
        if normalized_tags:
            _append_unique(tag_options, normalized_tags)
            _set_list_setting('ticket_tags', tag_options)

        ticket = Ticket(
            subject=subject,
            requester_email=requester_email,
            requester_name=requester_name or None,
            body_text=body_text or None,
            priority=priority,
            category=normalized_category or None,
            tags=','.join(normalized_tags) if normalized_tags else None,
            source='manual',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_message_at=datetime.utcnow(),
        )
        db.session.add(ticket)
        db.session.flush()
        _assign_ticket_code(ticket)
        _create_ticket_notification(
            ticket,
            current_user.id,
            f'New ticket {ticket.ticket_code}',
            ticket.subject,
        )
        db.session.commit()
        flash('Ticket created.', 'success')
        return redirect(url_for('tickets.index'))

    category_options = _get_list_setting('ticket_categories', DEFAULT_TICKET_CATEGORIES)
    tag_options = _get_list_setting('ticket_tags', DEFAULT_TICKET_TAGS)
    return render_template('tickets/create.html', category_options=category_options, tag_options=tag_options)


@tickets_bp.route('/<int:ticket_id>')
@login_required
def detail(ticket_id):
    _ensure_ticket_access()
    ticket = Ticket.query.get_or_404(ticket_id)
    tag_list = [tag.strip() for tag in (ticket.tags or '').split(',') if tag.strip()]
    comments = TicketComment.query.filter_by(ticket_id=ticket.id).order_by(TicketComment.created_at.asc()).all()
    assignees = User.query.filter(User.role.in_(['admin', 'helpdesk', 'staff'])).order_by(User.name).all()
    linked_docs = TicketDocLink.query.filter_by(ticket_id=ticket.id).order_by(TicketDocLink.created_at.desc()).all()
    documents = Document.query.order_by(Document.title.asc()).limit(500).all()
    category_options = _get_list_setting('ticket_categories', DEFAULT_TICKET_CATEGORIES)
    tag_options = _get_list_setting('ticket_tags', DEFAULT_TICKET_TAGS)
    return render_template(
        'tickets/detail.html',
        ticket=ticket,
        tag_list=tag_list,
        comments=comments,
        assignees=assignees,
        linked_docs=linked_docs,
        documents=documents,
        category_options=category_options,
        tag_options=tag_options,
        priority_options=['low', 'normal', 'high'],
        status_options=['open', 'triage', 'closed'],
    )


@tickets_bp.route('/<int:ticket_id>/update', methods=['POST'])
@login_required
def update(ticket_id):
    _ensure_ticket_access()
    ticket = Ticket.query.get_or_404(ticket_id)
    previous_status = ticket.status
    previous_assignee = ticket.assigned_to_id
    previous_priority = ticket.priority
    previous_category = ticket.category
    previous_tags = ticket.tags
    ticket.status = request.form.get('status', ticket.status).strip() or ticket.status
    ticket.priority = request.form.get('priority', ticket.priority).strip() or ticket.priority
    category = request.form.get('category', '').strip()
    tags = request.form.get('tags', '').split(',')
    category_options = _get_list_setting('ticket_categories', DEFAULT_TICKET_CATEGORIES)
    tag_options = _get_list_setting('ticket_tags', DEFAULT_TICKET_TAGS)
    normalized_category = _normalize_category(category) if category else ''
    normalized_tags = _normalize_tags(tags)
    if normalized_category:
        _append_unique(category_options, [normalized_category])
        _set_list_setting('ticket_categories', category_options)
    if normalized_tags:
        _append_unique(tag_options, normalized_tags)
        _set_list_setting('ticket_tags', tag_options)
    ticket.category = normalized_category or None
    ticket.tags = ','.join(normalized_tags) if normalized_tags else None
    ticket.assigned_to_id = request.form.get('assigned_to_id', type=int) or None
    ticket.updated_at = datetime.utcnow()
    append_ledger_entry(
        event_type='ticket_updated',
        entity_type='ticket',
        entity_id=ticket.id,
        actor_id=current_user.id,
        payload={
            'status': {'from': previous_status, 'to': ticket.status},
            'assignee_id': {'from': previous_assignee, 'to': ticket.assigned_to_id},
            'priority': {'from': previous_priority, 'to': ticket.priority},
            'category': {'from': previous_category, 'to': ticket.category},
            'tags': {'from': previous_tags, 'to': ticket.tags},
        }
    )
    if previous_status != ticket.status and ticket.status == 'closed':
        _create_ticket_notification(
            ticket,
            current_user.id,
            f'Ticket closed {ticket.ticket_code}',
            ticket.subject,
        )
    if previous_status == 'closed' and ticket.status in ['open', 'triage']:
        _create_ticket_notification(
            ticket,
            current_user.id,
            f'Ticket reopened {ticket.ticket_code}',
            ticket.subject,
        )
    if previous_status != ticket.status:
        requester = _find_requester_user(ticket)
        if requester:
            _create_ticket_notification_for_users(
                ticket,
                [requester.id],
                f'Status updated {ticket.ticket_code}',
                f'Status is now {ticket.status}.',
            )
    if previous_assignee != ticket.assigned_to_id and ticket.assigned_to_id:
        _create_ticket_notification(
            ticket,
            current_user.id,
            f'Ticket assigned {ticket.ticket_code}',
            f'Assigned to {ticket.assignee.name if ticket.assignee else "user"}',
        )
    db.session.commit()
    flash('Ticket updated.', 'success')
    return redirect(url_for('tickets.detail', ticket_id=ticket.id))


@tickets_bp.route('/<int:ticket_id>/comment', methods=['POST'])
@login_required
def add_comment(ticket_id):
    _ensure_ticket_access()
    ticket = Ticket.query.get_or_404(ticket_id)
    body = request.form.get('body', '').strip()
    is_internal = request.form.get('is_internal') == 'on'
    if not body:
        flash('Comment cannot be empty.', 'warning')
        return redirect(url_for('tickets.detail', ticket_id=ticket.id))
    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=current_user.id,
        body=body,
        is_internal=is_internal,
    )
    ticket.last_message_at = datetime.utcnow()
    ticket.updated_at = datetime.utcnow()
    db.session.add(comment)
    append_ledger_entry(
        event_type='ticket_comment',
        entity_type='ticket',
        entity_id=ticket.id,
        actor_id=current_user.id,
        payload={
            'comment_id': comment.id,
            'is_internal': comment.is_internal,
        }
    )
    _create_ticket_notification(
        ticket,
        current_user.id,
        f'New comment on {ticket.ticket_code}',
        comment.body[:200],
    )
    if not is_internal:
        requester = _find_requester_user(ticket)
        if requester:
            _create_ticket_notification_for_users(
                ticket,
                [requester.id],
                f'Public reply on {ticket.ticket_code}',
                comment.body[:200],
            )
    mentioned = _resolve_mentions(_extract_mentions(body))
    if mentioned:
        _create_ticket_notification_for_users(
            ticket,
            [user.id for user in mentioned],
            f'Mentioned on {ticket.ticket_code}',
            comment.body[:200],
        )
    db.session.commit()
    flash('Comment added.', 'success')
    return redirect(url_for('tickets.detail', ticket_id=ticket.id))


@tickets_bp.route('/<int:ticket_id>/link-doc', methods=['POST'])
@login_required
def link_doc(ticket_id):
    _ensure_ticket_access()
    ticket = Ticket.query.get_or_404(ticket_id)
    document_id = request.form.get('document_id', type=int)
    if not document_id:
        flash('Select a document to link.', 'warning')
        return redirect(url_for('tickets.detail', ticket_id=ticket.id))
    if TicketDocLink.query.filter_by(ticket_id=ticket.id, document_id=document_id).first():
        flash('This document is already linked.', 'info')
        return redirect(url_for('tickets.detail', ticket_id=ticket.id))
    link = TicketDocLink(
        ticket_id=ticket.id,
        document_id=document_id,
        linked_by_id=current_user.id,
    )
    db.session.add(link)
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Document linked to ticket.', 'success')
    return redirect(url_for('tickets.detail', ticket_id=ticket.id))


@tickets_bp.route('/<int:ticket_id>/unlink-doc', methods=['POST'])
@login_required
def unlink_doc(ticket_id):
    _ensure_ticket_access()
    ticket = Ticket.query.get_or_404(ticket_id)
    link_id = request.form.get('link_id', type=int)
    link = TicketDocLink.query.filter_by(id=link_id, ticket_id=ticket.id).first()
    if not link:
        flash('Link not found.', 'warning')
        return redirect(url_for('tickets.detail', ticket_id=ticket.id))
    db.session.delete(link)
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Document link removed.', 'success')
    return redirect(url_for('tickets.detail', ticket_id=ticket.id))


@tickets_bp.route('/import/gmail', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk')
def import_gmail():
    try:
        created = _import_gmail_messages()
        flash(f'Imported {created} ticket(s) from Gmail.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Gmail import failed: {str(exc)}', 'danger')

    return redirect(url_for('tickets.index'))
