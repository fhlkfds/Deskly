# Testing Checklist

Use this checklist to verify all features are working correctly after deployment.

## ✅ Phase 1: Installation & Setup

- [ ] Virtual environment created successfully
- [ ] All dependencies installed without errors
- [ ] `.env` file created and configured
- [ ] Application starts without errors
- [ ] Can access http://localhost:5000

## ✅ Phase 2: Authentication

- [ ] Login page loads correctly
- [ ] Can login with admin credentials (admin@school.edu / admin123)
- [ ] Can login with staff credentials (staff@school.edu / staff123)
- [ ] Invalid credentials show error message
- [ ] "Remember me" checkbox works
- [ ] Logout works correctly
- [ ] Redirected to login when accessing protected pages while logged out

## ✅ Phase 3: Dashboard

- [ ] Dashboard displays after login
- [ ] Summary cards show correct counts:
  - Total Assets
  - Available Assets
  - Checked Out Assets
  - Maintenance Assets
- [ ] Recent checkouts section displays
- [ ] Recent check-ins section displays
- [ ] Overdue items alert shows (if any overdue)
- [ ] Quick action buttons work:
  - Check Out Asset
  - Check In Asset
  - Browse Assets

## ✅ Phase 4: Asset Management

### List Assets
- [ ] Assets list page loads
- [ ] All sample assets display
- [ ] Filter by category works
- [ ] Filter by status works
- [ ] Filter by type works
- [ ] Search by asset tag works
- [ ] Search by name works
- [ ] Search by serial number works
- [ ] Pagination works (if > 25 assets)
- [ ] Status badges display with correct colors
- [ ] Condition badges display correctly

### Create Asset
- [ ] "Add Asset" button works
- [ ] Create form loads
- [ ] All fields display correctly
- [ ] Required field validation works
- [ ] Can create asset with minimum required fields
- [ ] Can create asset with all fields
- [ ] Asset appears in list after creation
- [ ] Success message displays
- [ ] Error handling works (duplicate asset tag)

### Edit Asset
- [ ] Edit button works from list
- [ ] Edit form loads with existing data
- [ ] Can update all fields
- [ ] Changes save correctly
- [ ] Updated data displays in list
- [ ] Success message displays

### View Asset Detail
- [ ] Detail page loads
- [ ] All asset information displays
- [ ] Asset status badge shows correctly
- [ ] Condition badge shows correctly
- [ ] Checkout history displays (if any)
- [ ] Current checkout info shows (if checked out)
- [ ] Edit button works
- [ ] Back button works

### Delete Asset
- [ ] Retire button shows confirmation
- [ ] Can retire asset
- [ ] Retired asset marked as "retired" status
- [ ] Retired asset doesn't show in default list
- [ ] Success message displays

## ✅ Phase 5: Checkout Workflow

### Check Out Asset
- [ ] Checkout page loads
- [ ] Available assets dropdown populates
- [ ] Only available assets show in dropdown
- [ ] Can enter recipient name
- [ ] Can set expected return date (optional)
- [ ] Checkout succeeds
- [ ] Asset status changes to "checked_out"
- [ ] Checkout record created
- [ ] Success message displays
- [ ] Redirects to asset detail page
- [ ] Asset shows in "Checked Out" dashboard card

### Check In Asset
- [ ] Checkin page loads
- [ ] Checked out assets dropdown populates
- [ ] Only checked out assets show in dropdown
- [ ] Current checkout info displays when asset selected
- [ ] Can select condition (Good/Fair/Needs Repair)
- [ ] Can add checkin notes
- [ ] Checkin succeeds
- [ ] Asset status changes to "available"
- [ ] Checkout record updated with checkin date
- [ ] Asset condition updated
- [ ] Success message displays
- [ ] Redirects to asset detail page
- [ ] Asset shows in "Available" dashboard card

### Checkout History
- [ ] History page loads
- [ ] All checkouts display
- [ ] Filter by "All" works
- [ ] Filter by "Active" works
- [ ] Filter by "Completed" works
- [ ] Active checkouts highlighted
- [ ] Overdue items marked with badge
- [ ] Pagination works (if > 25 records)
- [ ] Can click asset tag to view details
- [ ] Checkin notes display (if any)

## ✅ Phase 6: Google Sheets Sync (Optional)

### Setup
- [ ] credentials.json file placed in project root
- [ ] Spreadsheet ID configured in .env
- [ ] Scheduler initialized in app.py
- [ ] Application restarts successfully

### Test Connection
- [ ] Can access Settings > Sync page
- [ ] "Test Connection" button works
- [ ] Connection test succeeds
- [ ] Success message displays

### Manual Sync - Export to Sheets
- [ ] "Export" button works
- [ ] Assets appear in Google Sheet
- [ ] All fields populated correctly
- [ ] Header row formatted
- [ ] Sync log shows success
- [ ] Records count correct

### Manual Sync - Import from Sheets
- [ ] Edit asset in Google Sheet
- [ ] Click "Import" button
- [ ] Changes appear in database
- [ ] Updated asset displays correctly
- [ ] Sync log shows success

### Bidirectional Sync
- [ ] "Run Full Sync" works
- [ ] Import completes
- [ ] Export completes
- [ ] Both sync logs show success
- [ ] No data loss occurs

### Conflict Resolution
- [ ] Edit asset in both places
- [ ] Run sync
- [ ] Latest change wins
- [ ] Conflict logged
- [ ] No errors occur

### Scheduled Sync
- [ ] Wait for sync interval to pass
- [ ] Automatic sync occurs
- [ ] Check sync logs for scheduled sync
- [ ] No errors in logs

## ✅ Phase 7: User Interface & UX

### Navigation
- [ ] All navbar links work
- [ ] Dropdowns work
- [ ] Logo links to dashboard
- [ ] User dropdown shows name
- [ ] Profile link works (if implemented)
- [ ] Logout link works

### Responsive Design
- [ ] Desktop view looks good (1920px)
- [ ] Tablet view looks good (768px)
- [ ] Mobile view looks good (375px)
- [ ] Tables scroll on mobile
- [ ] Buttons stack properly on mobile
- [ ] Forms work on mobile

### Flash Messages
- [ ] Success messages display (green)
- [ ] Error messages display (red)
- [ ] Warning messages display (yellow)
- [ ] Info messages display (blue)
- [ ] Messages can be dismissed
- [ ] Messages auto-dismiss after time

### Forms
- [ ] All form fields work
- [ ] Validation messages display
- [ ] Date pickers work
- [ ] Dropdowns populate
- [ ] Required fields marked with *
- [ ] Help text displays where needed

## ✅ Phase 8: Security & Permissions

### Authentication
- [ ] Cannot access protected pages without login
- [ ] Session persists after login
- [ ] Session clears after logout
- [ ] Passwords are hashed (check database)

### Authorization
- [ ] Admin can access Settings
- [ ] Staff cannot access Settings
- [ ] Admin can delete assets
- [ ] Staff can create/edit assets
- [ ] All users can checkout/checkin

### Input Validation
- [ ] SQL injection attempts fail
- [ ] XSS attempts sanitized
- [ ] Invalid dates rejected
- [ ] Negative costs rejected
- [ ] Empty required fields rejected

## ✅ Phase 9: Error Handling

### 404 Errors
- [ ] Invalid URL shows 404 page
- [ ] 404 page has link to dashboard
- [ ] 404 page styled correctly

### 500 Errors
- [ ] Database errors handled gracefully
- [ ] 500 page displays on server error
- [ ] Error logged to console
- [ ] Session rolled back on error

### Form Errors
- [ ] Duplicate asset tag shows error
- [ ] Invalid email shows error
- [ ] Missing required fields show error
- [ ] All errors user-friendly

## ✅ Phase 10: Data Integrity

### Database
- [ ] Assets created successfully
- [ ] Checkouts linked to assets
- [ ] Users linked to checkouts
- [ ] Sync logs created
- [ ] Timestamps accurate
- [ ] Foreign keys enforced

### Business Logic
- [ ] Cannot checkout unavailable asset
- [ ] Cannot checkin available asset
- [ ] Asset status updates on checkout
- [ ] Asset status updates on checkin
- [ ] Asset condition updates on checkin
- [ ] Overdue calculation correct

## Performance Tests

- [ ] Dashboard loads < 1 second
- [ ] Asset list loads < 1 second
- [ ] Search returns results < 500ms
- [ ] Forms submit < 500ms
- [ ] Sync completes < 5 seconds (for 100 assets)

## Browser Compatibility

- [ ] Works in Chrome
- [ ] Works in Firefox
- [ ] Works in Safari
- [ ] Works in Edge

## Documentation

- [ ] README.md accurate and complete
- [ ] SETUP.md clear and helpful
- [ ] Comments in code helpful
- [ ] .env.example has all variables

---

## Summary

**Total Tests**: ~150+
**Passed**: ___
**Failed**: ___
**Skipped**: ___

**Notes**:


**Date Tested**: ___________
**Tested By**: ___________
**Version**: 1.0.0
