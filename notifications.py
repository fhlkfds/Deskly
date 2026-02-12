from flask import Blueprint, redirect, render_template, url_for
from flask_login import login_required, current_user

from auth import roles_required
from models import db, Notification

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')


@notifications_bp.route('/')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def index():
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(200).all()
    return render_template('notifications/index.html', notifications=notifications)


@notifications_bp.route('/read/<int:notification_id>', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def mark_read(notification_id):
    notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
    notification.is_read = True
    db.session.commit()
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/read-all', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return redirect(url_for('notifications.index'))
