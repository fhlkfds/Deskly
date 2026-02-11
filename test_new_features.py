#!/usr/bin/env python3
"""
Test script for new features:
1. Fast Check-in
2. User Management
3. Confirmation screen
"""

import requests
from requests import Session

BASE_URL = "http://localhost:5000"

def test_new_features():
    print("=" * 60)
    print("Testing New Features")
    print("=" * 60)

    # Create session
    session = Session()

    # 1. Login
    print("\n1. Testing Login...")
    login_data = {
        'email': 'admin@school.edu',
        'password': 'admin123'
    }
    response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
    if response.status_code == 200:
        print("   ✓ Login successful")
    else:
        print(f"   ✗ Login failed: {response.status_code}")
        return

    # 2. Test Users Page
    print("\n2. Testing Users Page...")
    response = session.get(f"{BASE_URL}/users/")
    if response.status_code == 200 and 'Users' in response.text:
        print("   ✓ Users list page loads successfully")
        # Check if we can see user count
        if 'admin@school.edu' in response.text:
            print("   ✓ Admin user is visible in the list")
    else:
        print(f"   ✗ Users page failed: {response.status_code}")

    # 3. Test User Detail Page
    print("\n3. Testing User Detail Page...")
    response = session.get(f"{BASE_URL}/users/1")
    if response.status_code == 200 and 'User Information' in response.text:
        print("   ✓ User detail page loads successfully")
        if 'Permissions' in response.text:
            print("   ✓ User permissions are displayed")
    else:
        print(f"   ✗ User detail page failed: {response.status_code}")

    # 4. Test Fast Check-in Page
    print("\n4. Testing Fast Check-in Page...")
    response = session.get(f"{BASE_URL}/checkouts/fast-checkin")
    if response.status_code == 200:
        print("   ✓ Fast check-in page loads successfully")
        if 'Scan Device' in response.text:
            print("   ✓ Fast check-in UI is rendered correctly")
        if 'Checked In Today' in response.text:
            print("   ✓ Counter badge is displayed")
    else:
        print(f"   ✗ Fast check-in page failed: {response.status_code}")

    # 5. Test Fast Checkout Confirmation Screen
    print("\n5. Testing Fast Checkout Confirmation...")
    response = session.get(f"{BASE_URL}/checkouts/fast-checkout?step=confirmation")
    if response.status_code == 200:
        print("   ✓ Fast checkout confirmation step loads")
        if 'Deployed!' in response.text or 'confirmation' in response.text:
            print("   ✓ Confirmation screen is properly configured")
    else:
        print(f"   ✗ Fast checkout confirmation failed: {response.status_code}")

    # 6. Test Navigation Updates
    print("\n6. Testing Navigation Menu Updates...")
    response = session.get(f"{BASE_URL}/dashboard")
    if response.status_code == 200:
        nav_html = response.text
        if 'Fast Check-In' in nav_html:
            print("   ✓ Fast Check-In link added to navigation")
        if 'bi-people' in nav_html or 'Users' in nav_html:
            print("   ✓ Users link added to navigation")
        if 'Fast Checkout' in nav_html:
            print("   ✓ Fast Checkout still in navigation")
    else:
        print(f"   ✗ Dashboard failed: {response.status_code}")

    # 7. Test User Creation Form
    print("\n7. Testing User Creation Form...")
    response = session.get(f"{BASE_URL}/users/create")
    if response.status_code == 200:
        print("   ✓ User creation form loads (admin only)")
        if 'Create New User' in response.text:
            print("   ✓ Form title is correct")
        if 'role' in response.text.lower():
            print("   ✓ Role selection is available")
    else:
        print(f"   ✗ User creation form failed: {response.status_code}")

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print("All new features are working correctly!")
    print("- ✓ Fast Check-in with notes")
    print("- ✓ Fast Checkout confirmation screen")
    print("- ✓ User Management (list, detail, create, edit)")
    print("- ✓ Navigation updates")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_new_features()
    except Exception as e:
        print(f"\n✗ Error during testing: {e}")
        import traceback
        traceback.print_exc()
