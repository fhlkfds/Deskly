# Changelog

All notable changes to the K-12 School Inventory System will be documented in this file.

## [1.3.0] - 2026-02-11

### Added
- **Fast Check-In Feature** 📥
  - Streamlined two-step check-in process (Scan Device → Add Notes)
  - Optimized for bulk device returns (end of school year)
  - Barcode scanner support for rapid check-ins
  - Session counter to track check-ins
  - Condition recording (Good, Fair, Needs Repair)
  - Notes field for damage reports or observations
  - Confirmation screen showing device and check-in details
  - Auto-loop back to start for next device
  - Keyboard-friendly navigation (Tab, Enter)

- **User Management System** 👥
  - Complete user CRUD operations (Create, Read, Update, Delete)
  - User list with search and role filtering
  - User detail page with activity history
  - User creation and editing forms
  - Role-based permissions display
  - Admin-only access controls
  - Checkout activity tracking per user
  - Cannot delete users with checkout history (data integrity)
  - User search by name or email

- **Fast Checkout Confirmation Screen** ✅
  - Shows complete student information after deployment
  - Displays student full name, email, and device details
  - Confirmation before proceeding to next checkout
  - Enhanced user feedback during bulk operations

### Changed
- Updated navigation menu to include "Users" link
- Added "Fast Check-In" to Checkouts dropdown menu
- Enhanced Fast Checkout workflow with confirmation step
- Improved session management for multi-step workflows

### Technical Changes
- Created `users.py` - User management blueprint
- Created `templates/users/list.html` - User list view
- Created `templates/users/detail.html` - User detail view with activity
- Created `templates/users/form.html` - User creation/editing form
- Created `templates/checkouts/fast_checkin.html` - Fast check-in UI
- Modified `checkouts.py` - Added fast_checkin route with session management
- Modified `checkouts.py` - Added confirmation screen logic to fast_checkout
- Modified `templates/checkouts/fast_checkout.html` - Added confirmation step
- Modified `app.py` - Registered users blueprint
- Modified `templates/base.html` - Updated navigation with Users and Fast Check-In

### Security
- Admin-only access to user management features
- Protection against self-deletion
- Validation for user email uniqueness
- Role-based permission enforcement

## [1.2.0] - 2026-02-11

### Added
- **Fast Checkout Feature** ⚡
  - Streamlined two-step checkout process (Student → Device)
  - Optimized for bulk device deployments (beginning of school year)
  - Automatic student/user creation if not found
  - Barcode scanner support for rapid deployment
  - Session counter to track deployments
  - Keyboard-friendly navigation (Tab, Enter)
  - "Deployed" status for long-term student assignments
  - 365-day default deployment duration
  - Exception handling (cancel, back, retry)
  - Real-time deployment feedback
  - Auto-loop back to start for next checkout

- **Deployed Status** 📱
  - New asset status specifically for student deployments
  - Distinguishes long-term (deployed) from temporary (checked_out)
  - Dashboard card showing deployed asset count
  - Included in search and filtering

- **User Management Enhancement** 👥
  - Quick student creation from fast checkout
  - Default password system (changeme123)
  - Email validation
  - Role assignment (teacher/student)

### Changed
- Updated dashboard summary cards to include "Deployed" count
- Reorganized dashboard cards (now 5 cards instead of 4)
- Enhanced navigation menu with Fast Checkout as priority item
- Added Fast Checkout button to dashboard Quick Actions (highlighted in warning color)
- Updated models.py with "deployed" in ASSET_STATUSES

### Technical Changes
- Modified `models.py` - Added 'deployed' to ASSET_STATUSES
- Modified `checkouts.py` - Added `/fast-checkout` route with session management
- Created `templates/checkouts/fast_checkout.html` - Fast checkout UI
- Updated `app.py` - Dashboard includes deployed count
- Updated `templates/base.html` - Navigation menu includes Fast Checkout
- Updated `templates/dashboard.html` - Added deployed card and Fast Checkout button

### Documentation
- Added `FAST_CHECKOUT_GUIDE.md` - Complete fast checkout documentation

## [1.1.0] - 2026-02-11

### Added
- **Dark Mode Toggle** 🌙
  - Toggle button in navbar with moon/sun icon
  - Automatic theme persistence using localStorage
  - Bootstrap 5 native dark mode support
  - Custom dark mode styles for all components
  - Smooth theme transitions
  - Works across all pages

- **Global Search on Dashboard** 🔍
  - Comprehensive search across all asset fields
  - Real-time search with instant results (300ms debounce)
  - Searches: asset tag, name, serial number, location, type, category, status, condition, notes, current owner
  - Smart highlighting of matching text
  - Color-coded status and condition badges
  - Up to 20 results displayed
  - Click any result to view asset details
  - Keyboard shortcuts (ESC to clear)
  - Mobile-friendly responsive design
  - Visual icons for location, serial number, and owner
  - Hover effects and smooth animations

### Changed
- Enhanced dashboard UI with prominent search box
- Improved navbar with dark mode toggle
- Updated CSS with dark mode and search result styles
- Better visual hierarchy on dashboard

### Technical Changes
- Added `/search` endpoint in `app.py` for global asset search
- Modified `templates/base.html` for dark mode functionality
- Updated `templates/dashboard.html` with search UI and JavaScript
- Enhanced `static/css/custom.css` with dark mode and search styles

## [1.0.0] - 2026-02-11

### Added
- Initial release of K-12 School Inventory System
- User authentication with Flask-Login
  - Admin, staff, and teacher roles
  - Password hashing with werkzeug
  - Login/logout functionality
  - Remember me option

- Asset Management
  - Create, read, update, delete (CRUD) operations
  - Asset categories: Technology, IT Infrastructure, Accessories, Other
  - Asset types: Laptop, Tablet, Charger, Projector, Printer, Smart Board, Server, VM, Docker Container
  - Asset statuses: Available, Checked Out, Maintenance, Retired
  - Asset conditions: Good, Fair, Needs Repair
  - Search and filter functionality
  - Pagination for large datasets
  - Detailed asset view with history

- Checkout/Checkin System
  - Easy checkout workflow
  - Simple checkin workflow with condition recording
  - Checkout history tracking
  - Overdue item detection
  - Expected return date tracking
  - Condition assessment on return

- Dashboard
  - Summary statistics (total, available, checked out, maintenance)
  - Recent checkout activity
  - Recent checkin activity
  - Overdue items alert
  - Quick action buttons

- Google Sheets Integration
  - Two-way synchronization
  - Manual sync triggers (import, export, bidirectional)
  - Automatic scheduled sync (configurable interval)
  - Test connection functionality
  - Sync history logging
  - Error tracking and reporting
  - Conflict resolution (latest timestamp wins)

- User Interface
  - Responsive Bootstrap 5 design
  - Mobile-friendly layout
  - Intuitive navigation
  - Flash messages for user feedback
  - Color-coded status badges
  - Icon integration with Bootstrap Icons
  - Custom CSS styling

- Database
  - SQLite database (with PostgreSQL upgrade path)
  - SQLAlchemy ORM
  - Proper relationships and foreign keys
  - Automatic timestamp tracking
  - Sample data initialization

- Security Features
  - Password hashing
  - Role-based access control
  - Login required decorators
  - Admin-only routes
  - Session management

- Documentation
  - Comprehensive README.md
  - Quick setup guide (SETUP.md)
  - Testing checklist
  - Code comments
  - Environment variable examples

- Developer Tools
  - Quick start script (run.sh)
  - Requirements.txt for dependencies
  - .gitignore for version control
  - .env.example template

### Technical Details
- **Backend**: Flask 3.0.0, Python 3.8+
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: Bootstrap 5, HTML5
- **Authentication**: Flask-Login 0.6.3
- **Scheduling**: APScheduler 3.10.4
- **Google API**: gspread 6.0.0, google-auth 2.26.2

### Database Schema
- Users table (id, email, name, role, password_hash, created_at)
- Assets table (id, asset_tag, name, category, type, serial_number, status, location, purchase_date, purchase_cost, condition, notes, google_sheets_row_id, created_at, updated_at)
- Checkouts table (id, asset_id, checked_out_to, checked_out_by, checkout_date, expected_return_date, checked_in_date, checkin_condition, checkin_notes, created_at)
- SyncLog table (id, sync_type, status, message, records_processed, errors_count, timestamp)

### Default Credentials
- Admin: admin@school.edu / admin123
- Staff: staff@school.edu / staff123

### Known Limitations
- SQLite may have issues with concurrent access (recommend PostgreSQL for production)
- Sync interval minimum is 1 minute
- Google Sheets sync requires manual setup
- No built-in backup functionality (manual backups recommended)

### Future Enhancements (Not in v1.0)
- Email notifications for overdue items
- Barcode/QR code scanning
- Asset depreciation tracking
- Maintenance scheduling
- Reports and analytics
- Export to PDF/CSV
- Mobile app
- Multi-school support
- Bulk import/export
- Asset photos/attachments
- Advanced user permissions
- Two-factor authentication

---

## Release Notes

### v1.0.0 - Production Ready

This is the first production-ready release of the K-12 School Inventory System. It includes all core features for managing school inventory with an intuitive web interface and optional Google Sheets integration.

**Recommended for**:
- K-12 schools
- IT departments
- Teacher resource management
- Equipment tracking

**Requirements**:
- Python 3.8 or higher
- Modern web browser
- Google Sheets API access (optional)

**Installation**: See SETUP.md

**Support**: See README.md

---

© 2026 K-12 School Inventory System
