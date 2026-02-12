from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from models import db, User
from auth import admin_required, roles_required
import csv
import io
import re
from audit_ledger import append_ledger_entry
import secrets

users_bp = Blueprint('users', __name__, url_prefix='/users')


@users_bp.route('/')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def list_users():
    """View all users."""
    page = request.args.get('page', 1, type=int)
    per_page = 25

    # Get filter parameters
    role_filter = request.args.get('role', 'all')  # all, admin, staff, teacher, student, helpdesk
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
                User.email.ilike(search_filter),
                User.asset_tag.ilike(search_filter)
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


@users_bp.route('/search')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def search_users():
    """Search users for checkout autocomplete."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    search_filter = f'%{query}%'
    results = User.query.filter(
        db.or_(
            User.name.ilike(search_filter),
            User.email.ilike(search_filter),
            User.asset_tag.ilike(search_filter)
        )
    ).order_by(User.name).limit(10).all()

    return jsonify([{
        'id': user.id,
        'name': user.name,
        'email': user.email,
        'asset_tag': user.asset_tag or ''
    } for user in results])


@users_bp.route('/<int:user_id>')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
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
@roles_required('admin', 'helpdesk')
def create():
    """Create a new user."""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            role = request.form.get('role', 'teacher')
            username = request.form.get('username', '').strip() or None
            asset_tag = request.form.get('asset_tag', '').strip() or None
            grade_level = request.form.get('grade_level', '').strip() or None
            password = request.form.get('password', '').strip()
            profile_picture_url = request.form.get('profile_picture_url', '').strip() or None
            default_theme = request.form.get('default_theme', 'light').strip()

            # Validation
            if not name or not email:
                flash('Name and email are required.', 'danger')
                return redirect(url_for('users.create'))

            # Check if email already exists
            if User.query.filter_by(email=email).first():
                flash(f'User with email {email} already exists.', 'danger')
                return redirect(url_for('users.create'))
            if username and User.query.filter_by(username=username).first():
                flash(f'Username {username} is already taken.', 'danger')
                return redirect(url_for('users.create'))

            # Create new user
            new_user = User(
                name=name,
                email=email,
                role=role,
                username=username,
                asset_tag=asset_tag,
                grade_level=grade_level,
                profile_picture_url=profile_picture_url,
                default_theme=default_theme if default_theme in {'light', 'dark'} else 'light'
            )
            if not password:
                password = secrets.token_urlsafe(24)
            new_user.set_password(password)

            db.session.add(new_user)
            db.session.flush()
            append_ledger_entry(
                event_type='user_created',
                entity_type='user',
                entity_id=new_user.id,
                actor_id=current_user.id,
                payload={
                    'name': new_user.name,
                    'email': new_user.email,
                    'role': new_user.role,
                }
            )
            db.session.commit()

            flash(f'User {name} created successfully!', 'success')
            return redirect(url_for('users.detail', user_id=new_user.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')

    prefill = {
        'name': request.args.get('name', '').strip(),
        'email': request.args.get('email', '').strip(),
        'role': request.args.get('role', 'teacher').strip(),
        'username': request.args.get('username', '').strip(),
        'asset_tag': request.args.get('asset_tag', '').strip(),
        'grade_level': request.args.get('grade_level', '').strip(),
        'profile_picture_url': request.args.get('profile_picture_url', '').strip(),
        'default_theme': request.args.get('default_theme', 'light').strip(),
    }
    return render_template('users/form.html', user=None, prefill=prefill)


@users_bp.route('/import', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'helpdesk')
def import_users():
    """Import users from CSV."""
    if request.method == 'POST':
        upload = request.files.get('file')
        if not upload or upload.filename == '':
            flash('Please choose a CSV file to import.', 'warning')
            return redirect(url_for('users.import_users'))

        try:
            content = upload.stream.read().decode('utf-8-sig')
        except Exception:
            flash('Unable to read file. Please upload a valid UTF-8 CSV.', 'danger')
            return redirect(url_for('users.import_users'))

        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            flash('CSV is missing header row.', 'danger')
            return redirect(url_for('users.import_users'))

        def normalize_header(value):
            return re.sub(r'[^a-z0-9_]', '', value.strip().lower().replace(' ', '_'))

        header_map = {normalize_header(h): h for h in reader.fieldnames}

        def get_value(row, key):
            original = header_map.get(key)
            return row.get(original, '').strip() if original else ''

        allowed_roles = {'admin', 'helpdesk', 'staff', 'teacher', 'student'}
        created = 0
        skipped = 0
        errors = []

        for idx, row in enumerate(reader, start=2):
            email = get_value(row, 'email')
            name = get_value(row, 'name')
            role = get_value(row, 'role') or 'staff'

            if not email or not name or not role:
                errors.append(f'Row {idx}: name, email, and role are required.')
                continue
            if role not in allowed_roles:
                errors.append(f'Row {idx}: invalid role "{role}".')
                continue

            if User.query.filter_by(email=email).first():
                skipped += 1
                continue

            new_user = User(
                name=name,
                email=email,
                role=role
            )
            new_user.set_password(secrets.token_urlsafe(24))
            db.session.add(new_user)
            created += 1

        if created:
            db.session.commit()
            append_ledger_entry(
                event_type='users_imported',
                entity_type='user',
                entity_id=None,
                actor_id=current_user.id,
                payload={
                    'created': created,
                    'skipped': skipped,
                }
            )
            db.session.commit()

        if errors:
            flash('Import completed with errors. See details below.', 'warning')
            return render_template(
                'users/import.html',
                created=created,
                skipped=skipped,
                errors=errors[:20]
            )

        flash(f'Import complete: {created} created, {skipped} skipped.', 'success')
        return redirect(url_for('users.list_users'))

    return render_template('users/import.html')


@users_bp.route('/template.csv')
@login_required
@roles_required('admin', 'helpdesk')
def users_template():
    """Download CSV template for users."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['email', 'name', 'role'])
    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='users_template.csv'
    )


@users_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(user_id):
    """Edit user details."""
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        try:
            before = {
                'name': user.name,
                'email': user.email,
                'role': user.role,
                'asset_tag': user.asset_tag,
                'grade_level': user.grade_level,
            }
            user.name = request.form.get('name', '').strip()
            user.email = request.form.get('email', '').strip()
            user.role = request.form.get('role', 'teacher')
            user.username = request.form.get('username', '').strip() or None
            user.asset_tag = request.form.get('asset_tag', '').strip() or None
            user.grade_level = request.form.get('grade_level', '').strip() or None
            user.profile_picture_url = request.form.get('profile_picture_url', '').strip() or None
            default_theme = request.form.get('default_theme', 'light').strip()
            user.default_theme = default_theme if default_theme in {'light', 'dark'} else 'light'

            # Update password if provided
            new_password = request.form.get('password', '').strip()
            if new_password:
                user.set_password(new_password)

            after = {
                'name': user.name,
                'email': user.email,
                'role': user.role,
                'username': user.username,
                'asset_tag': user.asset_tag,
                'grade_level': user.grade_level,
            }
            changes = {
                key: {'from': before[key], 'to': after[key]}
                for key in before
                if before[key] != after[key]
            }
            if new_password:
                changes['password'] = {'from': '***', 'to': '***'}

            append_ledger_entry(
                event_type='user_updated',
                entity_type='user',
                entity_id=user.id,
                actor_id=current_user.id,
                payload={
                    'name': user.name,
                    'email': user.email,
                    'changes': changes,
                }
            )
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

        append_ledger_entry(
            event_type='user_deleted',
            entity_type='user',
            entity_id=user.id,
            actor_id=current_user.id,
            payload={
                'name': user.name,
                'email': user.email,
                'role': user.role,
            }
        )
        db.session.delete(user)
        db.session.commit()

        flash(f'User {user.name} deleted successfully.', 'success')
        return redirect(url_for('users.list_users'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
        return redirect(url_for('users.detail', user_id=user_id))


@users_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'helpdesk')
def profile():
    """Edit current user's profile."""
    user = current_user
    if request.method == 'POST':
        try:
            user.name = request.form.get('name', '').strip()
            user.email = request.form.get('email', '').strip()
            user.username = request.form.get('username', '').strip() or None
            user.profile_picture_url = request.form.get('profile_picture_url', '').strip() or None
            default_theme = request.form.get('default_theme', 'light').strip()
            user.default_theme = default_theme if default_theme in {'light', 'dark'} else 'light'

            new_password = request.form.get('password', '').strip()
            if new_password:
                user.set_password(new_password)

            db.session.commit()
            flash('Profile updated.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to update profile: {str(e)}', 'danger')
        return redirect(url_for('users.profile'))

    return render_template('users/profile.html', user=user)
