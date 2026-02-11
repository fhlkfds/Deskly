import os
from datetime import datetime

from google.oauth2 import service_account

from models import (
    db,
    User,
    Asset,
    GoogleAdminOuRoleMapping,
    GoogleAdminDeviceModelMapping,
    GoogleAdminSyncSchedule,
    GoogleAdminSyncLog,
)
from config import Config


class GoogleAdminUserSync:
    """Sync Google Admin users and map groups to local roles."""

    SCOPES = [
        'https://www.googleapis.com/auth/admin.directory.user.readonly',
        'https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly',
    ]

    VALID_ROLES = {'admin', 'helpdesk', 'staff', 'teacher', 'student'}

    def __init__(self):
        self.credentials_file = Config.GOOGLE_ADMIN_CREDENTIALS_FILE
        self.delegated_admin_email = Config.GOOGLE_ADMIN_DELEGATED_ADMIN_EMAIL
        self.customer_id = Config.GOOGLE_ADMIN_CUSTOMER_ID
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service

        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(f'Google Admin credentials file not found: {self.credentials_file}')
        if not self.delegated_admin_email:
            raise ValueError('GOOGLE_ADMIN_DELEGATED_ADMIN_EMAIL is not configured')
        try:
            from googleapiclient.discovery import build
        except Exception as exc:
            raise RuntimeError('google-api-python-client is not installed. Run pip install -r requirements.txt') from exc

        creds = service_account.Credentials.from_service_account_file(
            self.credentials_file,
            scopes=self.SCOPES
        )
        delegated = creds.with_subject(self.delegated_admin_email)
        self._service = build('admin', 'directory_v1', credentials=delegated, cache_discovery=False)
        return self._service

    def test_connection(self):
        service = self._get_service()
        result = service.users().list(
            customer=self.customer_id or 'my_customer',
            maxResults=1,
            orderBy='email'
        ).execute()
        users_count = len(result.get('users', []))
        return {'success': True, 'message': f'Connected to Google Admin. Sample users fetched: {users_count}'}

    def _list_all_users(self):
        service = self._get_service()
        users = []
        page_token = None
        while True:
            response = service.users().list(
                customer=self.customer_id or 'my_customer',
                maxResults=500,
                orderBy='email',
                pageToken=page_token
            ).execute()
            users.extend(response.get('users', []))
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return users

    @staticmethod
    def _normalize_ou_path(value):
        path = (value or '').strip()
        if not path:
            return '/'
        if not path.startswith('/'):
            path = '/' + path
        return path.rstrip('/') or '/'

    @classmethod
    def _resolve_role_by_ou(cls, user_ou_path, mappings):
        normalized_user_ou = cls._normalize_ou_path(user_ou_path).lower()
        matched = []
        for mapped_path, role in mappings:
            mapped_path_norm = cls._normalize_ou_path(mapped_path).lower()
            if normalized_user_ou == mapped_path_norm or normalized_user_ou.startswith(mapped_path_norm + '/'):
                matched.append((mapped_path_norm, role))
        if not matched:
            return None
        matched.sort(key=lambda item: len(item[0]), reverse=True)
        return matched[0][1]

    def run_sync(self, trigger_type='manual'):
        mappings = GoogleAdminOuRoleMapping.query.filter_by(enabled=True).all()
        mapping_pairs = [(m.ou_path, m.role) for m in mappings if m.role in self.VALID_ROLES]
        if not mapping_pairs:
            raise ValueError('No enabled Google Admin OU-to-role mappings configured.')

        users_processed = 0
        users_created = 0
        users_updated = 0
        users_skipped = 0
        devices_processed = 0
        devices_updated = 0
        devices_skipped = 0
        errors = []

        for g_user in self._list_all_users():
            try:
                email = (g_user.get('primaryEmail') or '').strip().lower()
                if not email:
                    continue

                users_processed += 1
                user_ou_path = g_user.get('orgUnitPath', '/')
                resolved_role = self._resolve_role_by_ou(user_ou_path, mapping_pairs)
                if not resolved_role:
                    users_skipped += 1
                    continue

                local_user = User.query.filter(db.func.lower(User.email) == email).first()
                full_name = (g_user.get('name', {}) or {}).get('fullName') or email.split('@')[0]
                if local_user:
                    changed = False
                    if local_user.name != full_name:
                        local_user.name = full_name
                        changed = True
                    if local_user.role != resolved_role:
                        local_user.role = resolved_role
                        changed = True
                    if changed:
                        users_updated += 1
                else:
                    local_user = User(
                        email=email,
                        name=full_name,
                        role=resolved_role
                    )
                    local_user.set_password('changeme123')
                    db.session.add(local_user)
                    users_created += 1
            except Exception as exc:
                errors.append(f'{g_user.get("primaryEmail", "unknown")}: {str(exc)}')

        db.session.commit()

        status = 'success'
        if errors:
            status = 'partial' if users_processed > 0 else 'failed'

        message = (
            f'Processed={users_processed}, Created={users_created}, Updated={users_updated}, '
            f'Skipped={users_skipped}, Errors={len(errors)}'
        )
        if errors:
            message += ' | ' + '; '.join(errors[:10])

        log = GoogleAdminSyncLog(
            trigger_type=trigger_type,
            status=status,
            users_processed=users_processed,
            users_created=users_created,
            users_updated=users_updated,
            users_skipped=users_skipped,
            devices_processed=devices_processed,
            devices_updated=devices_updated,
            devices_skipped=devices_skipped,
            message=message
        )
        db.session.add(log)
        db.session.commit()

        return {
            'success': status in {'success', 'partial'},
            'status': status,
            'users_processed': users_processed,
            'users_created': users_created,
            'users_updated': users_updated,
            'users_skipped': users_skipped,
            'devices_processed': devices_processed,
            'devices_updated': devices_updated,
            'devices_skipped': devices_skipped,
            'errors': errors,
            'message': message,
        }

    def _list_chromeos_devices(self):
        service = self._get_service()
        devices = []
        page_token = None
        while True:
            response = service.chromeosdevices().list(
                customerId=self.customer_id or 'my_customer',
                maxResults=200,
                projection='FULL',
                pageToken=page_token
            ).execute()
            devices.extend(response.get('chromeosdevices', []))
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return devices

    def sync_device_ous(self, trigger_type='manual'):
        devices_processed = 0
        devices_updated = 0
        devices_skipped = 0
        errors = []
        model_mappings = {
            m.device_model.lower(): m.device_group
            for m in GoogleAdminDeviceModelMapping.query.filter_by(enabled=True).all()
            if m.device_group in self.VALID_ROLES
        }

        for device in self._list_chromeos_devices():
            try:
                serial = (device.get('serialNumber') or '').strip()
                ou_path = (device.get('orgUnitPath') or '').strip()
                model = (device.get('model') or '').strip()
                annotated_asset_id = (device.get('annotatedAssetId') or '').strip()

                devices_processed += 1

                asset = None
                if serial:
                    asset = Asset.query.filter(db.func.lower(Asset.serial_number) == serial.lower()).first()
                if not asset and annotated_asset_id:
                    asset = Asset.query.filter(db.func.lower(Asset.asset_tag) == annotated_asset_id.lower()).first()
                if not asset:
                    devices_skipped += 1
                    continue

                changed = False
                if (asset.google_admin_device_ou_path or '') != ou_path:
                    asset.google_admin_device_ou_path = ou_path or None
                    changed = True
                if (asset.google_admin_device_model or '') != model:
                    asset.google_admin_device_model = model or None
                    changed = True

                mapped_group = model_mappings.get(model.lower()) if model else None
                if mapped_group and (asset.device_group or '') != mapped_group:
                    asset.device_group = mapped_group
                    changed = True

                if changed:
                    devices_updated += 1
                else:
                    devices_skipped += 1
            except Exception as exc:
                errors.append(f'{device.get("serialNumber", "unknown")}: {str(exc)}')

        db.session.commit()

        status = 'success'
        if errors:
            status = 'partial' if devices_processed > 0 else 'failed'

        message = (
            f'Device OU sync: Processed={devices_processed}, Updated={devices_updated}, '
            f'Skipped={devices_skipped}, Errors={len(errors)}'
        )
        if errors:
            message += ' | ' + '; '.join(errors[:10])

        log = GoogleAdminSyncLog(
            trigger_type=trigger_type,
            status=status,
            users_processed=0,
            users_created=0,
            users_updated=0,
            users_skipped=0,
            devices_processed=devices_processed,
            devices_updated=devices_updated,
            devices_skipped=devices_skipped,
            message=message
        )
        db.session.add(log)
        db.session.commit()

        return {
            'success': status in {'success', 'partial'},
            'status': status,
            'devices_processed': devices_processed,
            'devices_updated': devices_updated,
            'devices_skipped': devices_skipped,
            'errors': errors,
            'message': message
        }


def get_or_create_google_admin_sync_schedule():
    schedule = GoogleAdminSyncSchedule.query.first()
    if not schedule:
        schedule = GoogleAdminSyncSchedule(
            enabled=False,
            days_of_week='',
            hour_utc=1,
            minute_utc=0,
        )
        db.session.add(schedule)
        db.session.commit()
    return schedule


def run_google_admin_sync_if_due():
    schedule = GoogleAdminSyncSchedule.query.first()
    if not schedule or not schedule.enabled:
        return False, 'Google Admin sync schedule disabled.'

    days = {int(x) for x in schedule.days_of_week.split(',') if x.strip().isdigit()}
    if not days:
        return False, 'No sync days configured.'

    now = datetime.utcnow()
    if now.weekday() not in days:
        return False, 'Today is not a configured sync day.'

    scheduled_at = now.replace(hour=schedule.hour_utc, minute=schedule.minute_utc, second=0, microsecond=0)
    if now < scheduled_at:
        return False, 'Scheduled time not reached yet.'

    if schedule.last_run_at and schedule.last_run_at >= scheduled_at:
        return False, 'Sync already run for this schedule window.'

    syncer = GoogleAdminUserSync()
    result = syncer.run_sync(trigger_type='scheduled')
    if schedule.sync_device_ou:
        device_result = syncer.sync_device_ous(trigger_type='scheduled')
        result['message'] = f"{result.get('message', '')} | {device_result.get('message', '')}".strip(' |')
    schedule.last_run_at = datetime.utcnow()
    db.session.commit()
    return True, result.get('message', 'Scheduled sync completed.')
