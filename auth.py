from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import LoginManager, login_user, logout_user, current_user
from authlib.integrations.flask_client import OAuth
from models import db, User, AppSetting
from sqlalchemy.exc import OperationalError
from audit_ledger import append_ledger_entry

auth_bp = Blueprint('auth', __name__)
login_manager = LoginManager()
oauth = OAuth()


def init_auth(app):
    """Initialize authentication system."""
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    oauth.init_app(app)
    _register_oauth_providers(app)


def _register_oauth_providers(app):
    google_id = app.config.get('GOOGLE_OAUTH_CLIENT_ID')
    google_secret = app.config.get('GOOGLE_OAUTH_CLIENT_SECRET')
    if google_id and google_secret:
        oauth.register(
            name='google',
            client_id=google_id,
            client_secret=google_secret,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )

    microsoft_id = app.config.get('MICROSOFT_OAUTH_CLIENT_ID')
    microsoft_secret = app.config.get('MICROSOFT_OAUTH_CLIENT_SECRET')
    tenant = app.config.get('MICROSOFT_OAUTH_TENANT_ID', 'common')
    if microsoft_id and microsoft_secret:
        oauth.register(
            name='microsoft',
            client_id=microsoft_id,
            client_secret=microsoft_secret,
            server_metadata_url=f'https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )


def _get_setting_value(key, default=''):
    try:
        setting = AppSetting.query.get(key)
    except OperationalError:
        return default
    if not setting or setting.value is None:
        return default
    return setting.value


def _sso_enabled(provider):
    key = f'sso_{provider}_enabled'
    return _get_setting_value(key, 'false') == 'true'


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login."""
    return User.query.get(int(user_id))


def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('You need administrator privileges to access this page.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def roles_required(*roles):
    """Decorator to require one of the specified roles."""
    roles_set = set(roles)

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles_set:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function

    return decorator


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and handler."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember', False)

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if user.role in {'student', 'teacher'}:
                flash('Your account does not have access to this system.', 'danger')
                return redirect(url_for('auth.login'))
            login_user(user, remember=remember)
            append_ledger_entry(
                event_type='user_login',
                entity_type='user',
                entity_id=user.id,
                actor_id=user.id,
                payload={
                    'email': user.email,
                    'ip': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent', ''),
                }
            )
            next_page = request.args.get('next')
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(next_page if next_page else url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')

    google_enabled = _sso_enabled('google') and bool(current_app.config.get('GOOGLE_OAUTH_CLIENT_ID'))
    microsoft_enabled = _sso_enabled('microsoft') and bool(current_app.config.get('MICROSOFT_OAUTH_CLIENT_ID'))
    return render_template('login.html', sso_google_enabled=google_enabled, sso_microsoft_enabled=microsoft_enabled)


@auth_bp.route('/logout')
def logout():
    """Logout handler."""
    if current_user.is_authenticated:
        append_ledger_entry(
            event_type='user_logout',
            entity_type='user',
            entity_id=current_user.id,
            actor_id=current_user.id,
            payload={
                'email': current_user.email,
                'ip': request.remote_addr,
                'user_agent': request.headers.get('User-Agent', ''),
            }
        )
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/oauth/<provider>')
def oauth_login(provider):
    provider = provider.lower()
    if provider not in {'google', 'microsoft'}:
        flash('Unsupported SSO provider.', 'danger')
        return redirect(url_for('auth.login'))
    if not _sso_enabled(provider):
        flash('SSO provider is disabled.', 'warning')
        return redirect(url_for('auth.login'))

    client = oauth.create_client(provider)
    if not client:
        flash('SSO provider is not configured.', 'warning')
        return redirect(url_for('auth.login'))

    if provider == 'google':
        redirect_uri = current_app.config.get('GOOGLE_OAUTH_REDIRECT_URI') or url_for('auth.oauth_callback', provider=provider, _external=True)
    else:
        redirect_uri = current_app.config.get('MICROSOFT_OAUTH_REDIRECT_URI') or url_for('auth.oauth_callback', provider=provider, _external=True)
    return client.authorize_redirect(redirect_uri)


@auth_bp.route('/oauth/callback/<provider>')
def oauth_callback(provider):
    provider = provider.lower()
    if provider not in {'google', 'microsoft'}:
        flash('Unsupported SSO provider.', 'danger')
        return redirect(url_for('auth.login'))
    if not _sso_enabled(provider):
        flash('SSO provider is disabled.', 'warning')
        return redirect(url_for('auth.login'))

    client = oauth.create_client(provider)
    if not client:
        flash('SSO provider is not configured.', 'warning')
        return redirect(url_for('auth.login'))

    try:
        token = client.authorize_access_token()
    except Exception as exc:
        flash(f'SSO login failed: {str(exc)}', 'danger')
        return redirect(url_for('auth.login'))

    userinfo = {}
    try:
        userinfo = client.get('userinfo').json()
    except Exception:
        pass
    if not userinfo:
        try:
            userinfo = client.parse_id_token(token) or {}
        except Exception:
            userinfo = {}

    email = (userinfo.get('email') or userinfo.get('preferred_username') or userinfo.get('upn') or '').strip()
    if not email:
        flash('SSO login failed: email not provided.', 'danger')
        return redirect(url_for('auth.login'))

    user = User.query.filter(db.func.lower(User.email) == email.lower()).first()
    if not user:
        flash('SSO login failed: user not found.', 'danger')
        return redirect(url_for('auth.login'))
    if user.role in {'student', 'teacher'}:
        flash('Your account does not have access to this system.', 'danger')
        return redirect(url_for('auth.login'))

    login_user(user)
    append_ledger_entry(
        event_type='user_login',
        entity_type='user',
        entity_id=user.id,
        actor_id=user.id,
        payload={
            'email': user.email,
            'ip': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', ''),
            'provider': provider,
        }
    )
    flash(f'Welcome back, {user.name}!', 'success')
    return redirect(url_for('dashboard'))
