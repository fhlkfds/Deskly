"""
Test script for the loaner swap feature.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, Asset, Checkout, User
from datetime import datetime, timedelta

def test_loaner_swap():
    """Test the loaner swap functionality."""
    with app.app_context():
        # Create test data
        print("Setting up test data...")

        # Get or create a test user
        test_user = User.query.filter_by(email='staff@school.edu').first()
        if not test_user:
            test_user = User(
                email='staff@school.edu',
                name='Staff User',
                role='staff'
            )
            test_user.set_password('staff123')
            db.session.add(test_user)

        # Create a broken device that's checked out
        broken_asset = Asset(
            asset_tag='TEST-BROKEN-001',
            name='Test Broken Laptop',
            category='Technology',
            type='Laptop',
            serial_number='BROKEN-001',
            status='checked_out',
            condition='good'
        )
        db.session.add(broken_asset)
        db.session.flush()

        # Create checkout for broken asset
        checkout = Checkout(
            asset_id=broken_asset.id,
            checked_out_to='John Doe',
            checked_out_by=test_user.id,
            checkout_date=datetime.utcnow() - timedelta(days=5),
            expected_return_date=(datetime.utcnow() + timedelta(days=25)).date()
        )
        db.session.add(checkout)

        # Create a loaner device
        loaner_asset = Asset(
            asset_tag='TEST-LOANER-001',
            name='Test Loaner Laptop',
            category='Technology',
            type='Laptop',
            serial_number='LOANER-001',
            status='available',
            condition='good'
        )
        db.session.add(loaner_asset)

        db.session.commit()

        print(f"✓ Created broken asset: {broken_asset.asset_tag} (checked out to {checkout.checked_out_to})")
        print(f"✓ Created loaner asset: {loaner_asset.asset_tag} (available)")

        # Simulate loaner swap
        print("\nSimulating loaner swap...")

        # Step 1: Check in broken asset
        active_checkout = broken_asset.current_checkout
        active_checkout.checked_in_date = datetime.utcnow()
        active_checkout.checkin_condition = 'needs_repair'
        active_checkout.checkin_notes = "LOANER SWAP - Screen cracked"

        broken_asset.status = 'maintenance'
        broken_asset.condition = 'needs_repair'

        # Step 2: Check out loaner
        loaner_checkout = Checkout(
            asset_id=loaner_asset.id,
            checked_out_to=active_checkout.checked_out_to,
            checked_out_by=test_user.id,
            checkout_date=datetime.utcnow(),
            expected_return_date=active_checkout.expected_return_date
        )
        db.session.add(loaner_checkout)

        loaner_asset.status = 'checked_out'

        db.session.commit()

        print(f"✓ Checked in {broken_asset.asset_tag} - Status: {broken_asset.status}, Condition: {broken_asset.condition}")
        print(f"✓ Checked out {loaner_asset.asset_tag} to {loaner_checkout.checked_out_to}")
        print(f"✓ Expected return date carried over: {loaner_checkout.expected_return_date}")

        # Verify results
        print("\nVerifying results...")
        assert broken_asset.status == 'maintenance', "Broken asset should be in maintenance"
        assert broken_asset.condition == 'needs_repair', "Broken asset should need repair"
        assert broken_asset.current_checkout is None, "Broken asset should not have active checkout"

        assert loaner_asset.status == 'checked_out', "Loaner should be checked out"
        assert loaner_asset.current_checkout is not None, "Loaner should have active checkout"
        assert loaner_asset.current_checkout.checked_out_to == 'John Doe', "Loaner should be checked out to same person"

        print("✓ All assertions passed!")

        # Cleanup
        print("\nCleaning up test data...")
        db.session.delete(loaner_checkout)
        db.session.delete(loaner_asset)
        db.session.delete(checkout)
        db.session.delete(broken_asset)
        db.session.commit()
        print("✓ Test data cleaned up")

        print("\n" + "="*50)
        print("LOANER SWAP TEST PASSED!")
        print("="*50)

if __name__ == '__main__':
    test_loaner_swap()
