from datetime import datetime, timedelta

from models import db, User, DamageIncident

REPEAT_BREAKAGE_WINDOW_DAYS = 180
REPEAT_BREAKAGE_THRESHOLD = 3


def _find_user_for_checked_out_to(checked_out_to):
    if not checked_out_to:
        return None

    # Try email exact match first, then name exact match.
    by_email = User.query.filter(db.func.lower(User.email) == checked_out_to.lower()).first()
    if by_email:
        return by_email
    return User.query.filter(db.func.lower(User.name) == checked_out_to.lower()).first()


def _is_flagged(count):
    return count >= REPEAT_BREAKAGE_THRESHOLD


def refresh_repeat_breakage_flags(asset_id=None, user_id=None):
    window_start = datetime.utcnow() - timedelta(days=REPEAT_BREAKAGE_WINDOW_DAYS)

    if asset_id:
        from models import Asset
        asset = Asset.query.get(asset_id)
        if asset:
            asset_incidents = DamageIncident.query.filter(
                DamageIncident.asset_id == asset.id,
                DamageIncident.incident_date >= window_start
            ).count()
            asset.repeat_breakage_flag = _is_flagged(asset_incidents)

    if user_id:
        user = User.query.get(user_id)
        if user:
            user_incidents = DamageIncident.query.filter(
                DamageIncident.user_id == user.id,
                DamageIncident.incident_date >= window_start
            ).count()
            user.repeat_breakage_flag = _is_flagged(user_incidents)


def record_damage_incident(asset_id, checked_out_to, source, notes='', checkout_id=None):
    user = _find_user_for_checked_out_to(checked_out_to)
    incident = DamageIncident(
        asset_id=asset_id,
        user_id=user.id if user else None,
        checkout_id=checkout_id,
        checked_out_to=checked_out_to or 'Unknown',
        source=source,
        notes=notes or None,
    )
    db.session.add(incident)

    refresh_repeat_breakage_flags(asset_id=asset_id, user_id=user.id if user else None)
    return incident
