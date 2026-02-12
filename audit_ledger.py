import hashlib
import json
from datetime import datetime

from models import db, AppSetting, AuditLedgerEntry
from sqlalchemy.exc import OperationalError

LEDGER_SETTING_KEY = 'audit_ledger_enabled'


def is_ledger_enabled():
    try:
        setting = AppSetting.query.get(LEDGER_SETTING_KEY)
    except OperationalError:
        return False
    if not setting:
        return False
    return setting.value == 'true'


def set_ledger_enabled(enabled):
    value = 'true' if enabled else 'false'
    try:
        setting = AppSetting.query.get(LEDGER_SETTING_KEY)
    except OperationalError:
        db.create_all()
        setting = AppSetting.query.get(LEDGER_SETTING_KEY)
    if not setting:
        setting = AppSetting(key=LEDGER_SETTING_KEY, value=value)
        db.session.add(setting)
    else:
        setting.value = value
    return setting


def get_latest_entry():
    try:
        return AuditLedgerEntry.query.order_by(AuditLedgerEntry.id.desc()).first()
    except OperationalError:
        return None


def _compute_entry_hash(prev_hash, created_at, event_type, entity_type, entity_id, actor_id, payload_json):
    safe_prev = prev_hash or ''
    safe_entity = '' if entity_id is None else str(entity_id)
    safe_actor = '' if actor_id is None else str(actor_id)
    raw = '|'.join([
        safe_prev,
        created_at.isoformat(),
        event_type or '',
        entity_type or '',
        safe_entity,
        safe_actor,
        payload_json or '',
    ])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def append_ledger_entry(event_type, entity_type='', entity_id=None, actor_id=None, payload=None, created_at=None):
    if not is_ledger_enabled():
        return None

    timestamp = created_at or datetime.utcnow()
    payload_json = ''
    if payload is not None:
        payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))

    try:
        prev_entry = AuditLedgerEntry.query.order_by(AuditLedgerEntry.id.desc()).first()
    except OperationalError:
        db.create_all()
        prev_entry = AuditLedgerEntry.query.order_by(AuditLedgerEntry.id.desc()).first()
    prev_hash = prev_entry.entry_hash if prev_entry else ''
    entry_hash = _compute_entry_hash(
        prev_hash,
        timestamp,
        event_type,
        entity_type,
        entity_id,
        actor_id,
        payload_json
    )

    entry = AuditLedgerEntry(
        created_at=timestamp,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        payload_json=payload_json or None,
        prev_hash=prev_hash or None,
        entry_hash=entry_hash
    )
    db.session.add(entry)
    return entry
