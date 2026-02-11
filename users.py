from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, User
from functools import wraps

users_bp = Blueprint('users', __name__, url_prefix='/users')


def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'admin':
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@users_bp.route('/')
@login_required
def list_users():
    """View all users."""
    page = request.args.get('page', 1, type=int)
    per_page = 25

    # Get filter parameters
    role_filter = request.args.get('role', 'all')  # all, admin, staff, teacher
    search_query = request.args.get('q', '')

    query = User.query

    # Apply role filter
    if role_filter != 'all':
        query = query.filter_by(role=role_filter)

    # Apply search filter
    if search_query:
        search_filter = f'%{search_query}%'
        query = query.filter(
            db.or_(
                User.name.ilike(search_filter),
                User.email.ilike(search_filter)
            )
        )

    # Order by name
    query = query.order_by(User.name)

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items

    return render_template('users/list.html',
                         users=users,
                         pagination=pagination,
                         role_filter=role_filter,
                         search_query=search_query)


@users_bp.route('/<int:user_id>')
@login_required
def detail(user_id):
    """View user details."""
    user = User.query.get_or_404(user_id)

    # Get user's checkout activity
    from models import Checkout
    checkouts_performed = Checkout.query.filter_by(checked_out_by=user_id).order_by(Checkout.checkout_date.desc()).limit(10).all()

    return render_template('users/detail.html',
                         user=user,
                         checkouts_performed=checkouts_performed)


@users_bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create():
    """Create a new user."""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            role = request.form.get('role', 'teacher')
            password = request.form.get('password', 'changeme123')

            # Validation
            if not name or not email:
                flash('Name and email are required.', 'danger')
                return redirect(url_for('users.create'))

            # Check if email already exists
            if User.query.filter_by(email=email).first():
                flash(f'User with email {email} already exists.', 'danger')
                return redirect(url_for('users.create'))

            # Create new user
            new_user = User(
                name=name,
                email=email,
                role=role
            )
            new_user.set_password(password)

            db.session.add(new_user)
            db.session.commit()

            flash(f'User {name} created successfully!', 'success')
            return redirect(url_for('users.detail', user_id=new_user.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')

    return render_template('users/form.html', user=None)


@users_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(user_id):
    """Edit user details."""
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        try:
            user.name = request.form.get('name', '').strip()
            user.email = request.form.get('email', '').strip()
            user.role = request.form.get('role', 'teacher')

            # Update password if provided
            new_password = request.form.get('password', '').strip()
            if new_password:
                user.set_password(new_password)

            db.session.commit()

            flash(f'User {user.name} updated successfully!', 'success')
            return redirect(url_for('users.detail', user_id=user.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'danger')

    return render_template('users/form.html', user=user)


@users_bp.route('/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(user_id):
    """Delete a user."""
    user = User.query.get_or_404(user_id)

    # Prevent deleting yourself
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('users.list_users'))

    try:
        # Check if user has checkout activity
        from models import Checkout
        checkout_count = Checkout.query.filter_by(checked_out_by=user_id).count()

        if checkout_count > 0:
            flash(f'Cannot delete user {user.name} - they have {checkout_count} checkout records. Consider deactivating instead.', 'warning')
            return redirect(url_for('users.detail', user_id=user_id))

        db.session.delete(user)
        db.session.commit()

        flash(f'User {user.name} deleted successfully.', 'success')
        return redirect(url_for('users.list_users'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
        return redirect(url_for('users.detail', user_id=user_id))
