# Loaner Swap Feature Guide

## Overview
The Loaner Swap feature allows you to quickly swap a broken/malfunctioning device with a loaner in a single operation. This streamlines the process of handling device issues while maintaining continuous service for users.

## What It Does

The loaner swap performs **two operations atomically**:

1. **Check In Broken Device**:
   - Marks the asset as "needs_repair" condition
   - Sets status to "maintenance"
   - Records issue notes with "LOANER SWAP" prefix
   - Completes the active checkout record

2. **Check Out Loaner Device**:
   - Checks out a replacement device to the **same person**
   - Carries over the **expected return date**
   - Creates new checkout record
   - Updates loaner status to "checked_out"

## How to Access

There are multiple ways to access the loaner swap feature:

1. **Navigation Menu**: Checkouts → Loaner Swap
2. **Dashboard**: Click the "Loaner Swap" button in Quick Actions
3. **Asset Detail Page**: When viewing a checked-out asset, click the "Loaner Swap" button
4. **Direct URL**: `/checkouts/loaner-swap`

## Using the Loaner Swap Interface

### Step 1: Select Broken Asset
- Choose the asset that needs to be swapped from the dropdown
- Only checked-out or deployed assets are shown
- You'll see who currently has the device

### Step 2: Select Loaner
- Choose an available loaner device
- Loaners are grouped by type for easy selection
- The system will warn if types don't match (but still allows the swap)

### Step 3: Add Issue Description (Optional)
- Describe what's wrong with the broken device
- This helps the repair team understand the issue

### Step 4: Review Swap Summary
- Verify the person and asset tags are correct
- Check that the expected return date makes sense

### Step 5: Perform Swap
- Click "Perform Loaner Swap" button
- Both operations happen in a single transaction
- If either fails, neither happens (atomic operation)

## Benefits

- **Time Savings**: One operation instead of two separate check-in/check-out processes
- **User Continuity**: Person keeps working with minimal downtime
- **Proper Tracking**: Broken device goes to maintenance with detailed notes
- **Data Integrity**: Return dates carry over automatically
- **Error Prevention**: Atomic transaction ensures data consistency

## Example Workflow

### Scenario
Student Jane has laptop LT-005 but the screen is cracked. She needs a loaner immediately.

### Traditional Process (2 steps)
1. Check in LT-005 (broken screen) → Set to maintenance
2. Check out LT-LOAN-001 to Jane → New checkout record

### With Loaner Swap (1 step)
1. Loaner Swap: LT-005 (broken) → LT-LOAN-001 (loaner)
   - Jane continues working
   - LT-005 automatically goes to maintenance
   - Return date carries over to LT-LOAN-001

## Technical Details

### Status Changes
- **Broken Asset**: `checked_out` → `maintenance`
- **Loaner Asset**: `available` → `checked_out`

### Condition Changes
- **Broken Asset**: Any condition → `needs_repair`
- **Loaner Asset**: Unchanged

### Notes
- Checkin notes are prefixed with "LOANER SWAP -"
- Original checkout info is preserved
- New checkout links to same person and expected return date

## Tips

1. **Match Types**: Try to swap like-for-like (laptop for laptop, tablet for tablet)
2. **Check Availability**: Ensure you have enough loaners of each type
3. **Document Issues**: Add detailed notes about what's broken
4. **Track Loaners**: Keep track of loaner usage patterns to optimize your pool
5. **Fast Process**: Use this during busy times (start of year, exam periods)

## Database Schema

### Checkout Records (Broken Device)
```
checked_in_date: Current timestamp
checkin_condition: 'needs_repair'
checkin_notes: 'LOANER SWAP - [your notes]'
```

### Checkout Records (Loaner)
```
checked_out_to: Same as broken device checkout
checked_out_by: Current user
checkout_date: Current timestamp
expected_return_date: Carried from broken device
```

## Testing

To test the feature:
```bash
./venv/bin/python test_loaner_swap.py
```

## Future Enhancements

Potential improvements:
- Automatic loaner selection based on type matching
- Email notification to user about the swap
- Loaner pool analytics and reporting
- Integration with repair ticketing system
- Batch swap for multiple devices
