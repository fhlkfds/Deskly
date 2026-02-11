import os
import gspread
from google.oauth2.service_account import Credentials
from models import db, Asset, SyncLog
from datetime import datetime
from config import Config


class GoogleSheetsSync:
    """Handle synchronization between database and Google Sheets."""

    def __init__(self):
        self.credentials_file = Config.GOOGLE_SHEETS_CREDENTIALS_FILE
        self.spreadsheet_id = Config.GOOGLE_SHEETS_SPREADSHEET_ID
        self.client = None
        self.worksheet = None

    def connect(self):
        """Connect to Google Sheets API."""
        try:
            if not os.path.exists(self.credentials_file):
                raise FileNotFoundError(f'Credentials file not found: {self.credentials_file}')

            if not self.spreadsheet_id:
                raise ValueError('Google Sheets spreadsheet ID not configured')

            # Set up credentials
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_file(self.credentials_file, scopes=scopes)

            # Connect to Google Sheets
            self.client = gspread.authorize(creds)
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            self.worksheet = spreadsheet.sheet1  # Use first sheet

            return True

        except Exception as e:
            raise Exception(f'Failed to connect to Google Sheets: {str(e)}')

    def sheets_to_database(self):
        """Sync from Google Sheets to database."""
        if not self.worksheet:
            self.connect()

        records_processed = 0
        errors_count = 0
        errors = []

        try:
            # Get all records from sheet
            rows = self.worksheet.get_all_records()

            for idx, row in enumerate(rows, start=2):  # Start at 2 (after header)
                try:
                    asset_tag = row.get('asset_tag', '').strip()
                    if not asset_tag:
                        continue

                    # Find existing asset or create new
                    asset = Asset.query.filter_by(asset_tag=asset_tag).first()
                    is_new = asset is None

                    if is_new:
                        asset = Asset(asset_tag=asset_tag)
                        asset.google_sheets_row_id = idx

                    # Update asset fields
                    asset.name = row.get('name', '')
                    asset.category = row.get('category', 'Other')
                    asset.type = row.get('type', 'Other')
                    asset.serial_number = row.get('serial_number', '')
                    asset.status = row.get('status', 'available')
                    asset.location = row.get('location', '')
                    asset.condition = row.get('condition', 'good')
                    asset.notes = row.get('notes', '')

                    # Handle dates and costs
                    if row.get('purchase_date'):
                        try:
                            asset.purchase_date = datetime.strptime(
                                row['purchase_date'], '%Y-%m-%d'
                            ).date()
                        except:
                            pass

                    if row.get('purchase_cost'):
                        try:
                            asset.purchase_cost = float(row['purchase_cost'])
                        except:
                            pass

                    asset.updated_at = datetime.utcnow()

                    if is_new:
                        db.session.add(asset)

                    records_processed += 1

                except Exception as e:
                    errors_count += 1
                    errors.append(f'Row {idx}: {str(e)}')

            db.session.commit()

            # Log sync
            log = SyncLog(
                sync_type='sheets_to_db',
                status='success' if errors_count == 0 else 'partial',
                message='\n'.join(errors) if errors else 'Sync completed successfully',
                records_processed=records_processed,
                errors_count=errors_count
            )
            db.session.add(log)
            db.session.commit()

            return {
                'success': True,
                'records_processed': records_processed,
                'errors_count': errors_count,
                'errors': errors
            }

        except Exception as e:
            db.session.rollback()
            log = SyncLog(
                sync_type='sheets_to_db',
                status='failure',
                message=str(e),
                records_processed=records_processed,
                errors_count=errors_count + 1
            )
            db.session.add(log)
            db.session.commit()

            return {
                'success': False,
                'error': str(e),
                'records_processed': records_processed,
                'errors_count': errors_count + 1
            }

    def database_to_sheets(self):
        """Sync from database to Google Sheets."""
        if not self.worksheet:
            self.connect()

        records_processed = 0
        errors_count = 0
        errors = []

        try:
            # Clear existing content (except header)
            self.worksheet.clear()

            # Set up header
            headers = [
                'asset_tag', 'name', 'category', 'type', 'serial_number',
                'status', 'location', 'purchase_date', 'purchase_cost',
                'condition', 'notes', 'updated_at'
            ]
            self.worksheet.append_row(headers)

            # Format header row
            self.worksheet.format('A1:L1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}
            })

            # Get all assets (except retired)
            assets = Asset.query.filter(Asset.status != 'retired').order_by(Asset.asset_tag).all()

            # Prepare data rows
            rows = []
            for asset in assets:
                row = [
                    asset.asset_tag,
                    asset.name,
                    asset.category,
                    asset.type,
                    asset.serial_number or '',
                    asset.status,
                    asset.location or '',
                    asset.purchase_date.strftime('%Y-%m-%d') if asset.purchase_date else '',
                    str(asset.purchase_cost) if asset.purchase_cost else '',
                    asset.condition,
                    asset.notes or '',
                    asset.updated_at.strftime('%Y-%m-%d %H:%M:%S') if asset.updated_at else ''
                ]
                rows.append(row)
                records_processed += 1

            # Append all rows at once (more efficient)
            if rows:
                self.worksheet.append_rows(rows)

            # Apply conditional formatting based on status
            # This would require more complex formatting rules
            # For now, we'll just note the row numbers for each status

            # Log sync
            log = SyncLog(
                sync_type='db_to_sheets',
                status='success',
                message='Sync completed successfully',
                records_processed=records_processed,
                errors_count=0
            )
            db.session.add(log)
            db.session.commit()

            return {
                'success': True,
                'records_processed': records_processed,
                'errors_count': 0
            }

        except Exception as e:
            db.session.rollback()
            log = SyncLog(
                sync_type='db_to_sheets',
                status='failure',
                message=str(e),
                records_processed=records_processed,
                errors_count=1
            )
            db.session.add(log)
            db.session.commit()

            return {
                'success': False,
                'error': str(e),
                'records_processed': records_processed,
                'errors_count': 1
            }

    def sync_bidirectional(self):
        """Perform bidirectional sync."""
        results = {
            'sheets_to_db': None,
            'db_to_sheets': None
        }

        try:
            self.connect()

            # First, sync from sheets to database
            results['sheets_to_db'] = self.sheets_to_database()

            # Then, sync from database to sheets
            results['db_to_sheets'] = self.database_to_sheets()

            # Log overall sync
            overall_success = (
                results['sheets_to_db']['success'] and
                results['db_to_sheets']['success']
            )

            log = SyncLog(
                sync_type='bidirectional',
                status='success' if overall_success else 'partial',
                message=f"Sheets→DB: {results['sheets_to_db']['records_processed']} records, "
                       f"DB→Sheets: {results['db_to_sheets']['records_processed']} records",
                records_processed=(
                    results['sheets_to_db']['records_processed'] +
                    results['db_to_sheets']['records_processed']
                ),
                errors_count=(
                    results['sheets_to_db']['errors_count'] +
                    results['db_to_sheets']['errors_count']
                )
            )
            db.session.add(log)
            db.session.commit()

            return results

        except Exception as e:
            log = SyncLog(
                sync_type='bidirectional',
                status='failure',
                message=str(e),
                records_processed=0,
                errors_count=1
            )
            db.session.add(log)
            db.session.commit()

            return {
                'success': False,
                'error': str(e)
            }

    def test_connection(self):
        """Test connection to Google Sheets."""
        try:
            self.connect()
            return {
                'success': True,
                'message': f'Successfully connected to spreadsheet'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
