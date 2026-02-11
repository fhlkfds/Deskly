# New Features - Dark Mode & Global Search

**Version**: 1.1.0
**Date**: 2026-02-11
**Status**: ✅ Active

---

## Overview

Two major features have been added to enhance the user experience:

1. **Dark Mode Toggle** - Eye-friendly theme switching
2. **Global Search** - Comprehensive asset search across all fields

---

## Feature 1: Dark Mode 🌙

### Description
A dark theme option that provides a more comfortable viewing experience in low-light environments. The theme preference is automatically saved and persists across sessions.

### How It Works
- **Toggle Button**: Moon/sun icon in the top-right navbar
- **Automatic Persistence**: Uses browser localStorage to remember preference
- **Bootstrap 5 Native**: Leverages Bootstrap's built-in dark mode support
- **Custom Styling**: Additional custom styles for optimal appearance

### Visual Changes in Dark Mode
- Darker background colors (#212529)
- Lighter text for better contrast
- Adjusted card shadows
- Modified table hover effects
- Updated form elements
- Customized badges and buttons
- Dark footer

### Usage

1. **Activate Dark Mode**:
   - Click the moon icon (🌙) in the navbar
   - Icon changes to sun (☀️)
   - Page theme switches to dark

2. **Deactivate Dark Mode**:
   - Click the sun icon (☀️)
   - Icon changes back to moon (🌙)
   - Page theme switches to light

3. **Persistence**:
   - Your choice is saved automatically
   - Preference persists after logout
   - Works across all browser tabs

### Technical Details

**Files Modified**:
- `templates/base.html` - Added toggle button and JavaScript
- `static/css/custom.css` - Dark mode styles

**JavaScript**:
```javascript
// Theme is stored in localStorage
localStorage.setItem('theme', 'dark');
// Or
localStorage.setItem('theme', 'light');
```

**CSS**:
```css
[data-bs-theme="dark"] {
    /* Dark mode styles */
}
```

### Benefits
- ✅ Reduced eye strain in dark environments
- ✅ Professional appearance
- ✅ Battery saving on OLED/AMOLED screens
- ✅ Improved accessibility
- ✅ Modern UI/UX

---

## Feature 2: Global Search 🔍

### Description
A powerful, real-time search function on the dashboard that searches across ALL asset fields including asset tags, names, locations, serial numbers, types, categories, statuses, conditions, notes, and current checkout information.

### Searchable Fields

The search covers the following fields:

1. **Asset Tag** - Unique identifier (e.g., "LT001")
2. **Asset Name** - Full name (e.g., "Dell Latitude 5420")
3. **Serial Number** - Manufacturer serial number
4. **Location** - Physical location (e.g., "Room 101")
5. **Type** - Asset type (e.g., "Laptop", "Tablet")
6. **Category** - Asset category (e.g., "Technology")
7. **Status** - Current status (e.g., "available", "checked_out")
8. **Condition** - Physical condition (e.g., "good", "fair")
9. **Notes** - Any text in the notes field
10. **Current Owner** - Person who has it checked out

### How It Works

1. **Real-time Search**:
   - Type at least 2 characters
   - Results appear instantly (300ms debounce)
   - Up to 20 results shown

2. **Smart Highlighting**:
   - Matching text is highlighted in yellow
   - Makes it easy to see why a result matched

3. **Rich Results**:
   - Asset tag and name prominently displayed
   - Color-coded status badges
   - Color-coded condition indicators
   - Location and serial number when available
   - Current checkout information displayed

4. **Interactive**:
   - Click any result to view full asset details
   - Hover effects for better UX
   - Keyboard support (ESC to clear)

### Usage Examples

**Search by Asset Tag**:
```
Type: "LT001"
Result: LT001 - Dell Latitude 5420
```

**Search by Location**:
```
Type: "room 101"
Result: All assets in Room 101
```

**Search by Type**:
```
Type: "laptop"
Result: All laptop assets
```

**Search by Status**:
```
Type: "available"
Result: All available assets
```

**Search by Owner**:
```
Type: "John"
Result: Assets checked out to anyone named John
```

**Search by Condition**:
```
Type: "needs repair"
Result: Assets needing maintenance
```

### Visual Features

**Status Badges**:
- 🟢 Green - Available
- 🟡 Yellow - Checked Out
- 🔴 Red - Maintenance
- ⚫ Gray - Retired

**Condition Badges**:
- 🟢 Green - Good
- 🟡 Yellow - Fair
- 🔴 Red - Needs Repair

**Icons**:
- 📍 Location icon for physical location
- #️⃣ Hash icon for serial number
- 👤 Person icon for current owner
- ➡️ Arrow icon indicating clickable

### Keyboard Shortcuts

- **ESC** - Clear search and close results
- **Click outside** - Close results dropdown

### Technical Details

**Backend Endpoint**:
```
GET /search?q={query}
```

**Response Format**:
```json
[
  {
    "id": 1,
    "asset_tag": "LT001",
    "name": "Dell Latitude 5420",
    "type": "Laptop",
    "category": "Technology",
    "location": "Room 101",
    "status": "checked_out",
    "condition": "good",
    "serial_number": "DL5420-001",
    "checked_out_to": "John Teacher",
    "checkout_date": "2026-02-11",
    "expected_return": "2026-02-18"
  }
]
```

**Files Modified**:
- `app.py` - Added `/search` endpoint
- `templates/dashboard.html` - Search box UI and JavaScript
- `static/css/custom.css` - Search result styling

**Database Query**:
```python
Asset.query.filter(
    db.or_(
        Asset.asset_tag.ilike(search_filter),
        Asset.name.ilike(search_filter),
        Asset.serial_number.ilike(search_filter),
        Asset.location.ilike(search_filter),
        Asset.type.ilike(search_filter),
        Asset.category.ilike(search_filter),
        Asset.status.ilike(search_filter),
        Asset.condition.ilike(search_filter),
        Asset.notes.ilike(search_filter)
    )
).limit(20)
```

### Performance

- **Debounced Input**: 300ms delay prevents excessive API calls
- **Limited Results**: Maximum 20 results for fast rendering
- **Efficient Query**: Single database query with OR conditions
- **ILIKE Search**: Case-insensitive matching
- **Indexed Fields**: Asset_tag, status, category indexed for speed

### Benefits
- ✅ Find assets quickly without navigating
- ✅ Search by any field or combination
- ✅ Instant results as you type
- ✅ Visual highlighting of matches
- ✅ Complete asset information in results
- ✅ Mobile-friendly responsive design

---

## Testing Results

### Dark Mode Tests
✅ Toggle switches theme correctly
✅ Preference persists after refresh
✅ Works across all pages
✅ Icons update correctly
✅ All UI components styled properly

### Search Tests
✅ Search "laptop" - Found 2 results
✅ Search "room" - Found 5 results
✅ Search "LT001" - Found 1 result (exact match)
✅ Search "available" - Found 4 results (by status)
✅ Real-time updates working
✅ Highlighting functional
✅ Click-to-navigate working

---

## Browser Compatibility

Both features work on:
- ✅ Chrome/Chromium
- ✅ Firefox
- ✅ Safari
- ✅ Edge
- ✅ Mobile browsers

---

## Future Enhancements

Potential improvements for future versions:

### Dark Mode
- [ ] Auto-detect system theme preference
- [ ] Scheduled theme switching (day/night)
- [ ] Additional color themes (blue, green, etc.)

### Search
- [ ] Search filters (type, status, etc.)
- [ ] Sort options (newest, oldest, name)
- [ ] Export search results
- [ ] Save frequent searches
- [ ] Advanced search with operators (AND, OR, NOT)
- [ ] Search history

---

## Troubleshooting

### Dark Mode Not Saving
**Issue**: Theme resets on page refresh
**Solution**: Check browser localStorage is enabled
**Check**: Open browser console and run `localStorage.getItem('theme')`

### Search Not Working
**Issue**: No results appearing
**Solution**: Type at least 2 characters
**Check**: Open browser console for JavaScript errors

### Search Results Not Clickable
**Issue**: Clicking results doesn't navigate
**Solution**: Check JavaScript console for errors
**Fix**: Refresh the page

---

## API Documentation

### Search Endpoint

**URL**: `/search`
**Method**: `GET`
**Auth Required**: Yes (login required)

**Parameters**:
- `q` (string, required) - Search query (minimum 2 characters)

**Success Response**:
- **Code**: 200 OK
- **Content**: Array of asset objects

**Error Response**:
- **Code**: 302 Redirect (not authenticated)
- **Content**: Redirect to login

**Example Request**:
```bash
curl -X GET "http://localhost:5000/search?q=laptop" \
  -H "Cookie: session=your-session-cookie"
```

**Example Response**:
```json
[
  {
    "id": 1,
    "asset_tag": "LT001",
    "name": "Dell Latitude 5420",
    "type": "Laptop",
    "status": "available",
    "condition": "good"
  }
]
```

---

## Credits

- **Dark Mode**: Bootstrap 5 native dark mode
- **Icons**: Bootstrap Icons
- **Search**: Custom implementation with vanilla JavaScript
- **Styling**: Custom CSS with Bootstrap 5

---

## Version History

### v1.1.0 (2026-02-11)
- ✅ Added dark mode toggle
- ✅ Added global search functionality
- ✅ Enhanced dashboard UI
- ✅ Improved user experience

### v1.0.0 (2026-02-11)
- Initial release

---

## Support

For issues or questions:
1. Check this documentation
2. Review browser console for errors
3. Clear browser cache and cookies
4. Try in incognito/private mode

---

**Enjoy the new features!** 🎉
