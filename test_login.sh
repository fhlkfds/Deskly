#!/bin/bash

# Test login and dashboard access
COOKIE_FILE=/tmp/cookies.txt

echo "=== Testing Login ==="
# Login with admin credentials
LOGIN_RESPONSE=$(curl -s -c $COOKIE_FILE -X POST http://localhost:5000/login \
  -d "email=admin@school.edu" \
  -d "password=admin123" \
  -w "\nHTTP_CODE:%{http_code}" \
  -L)

if echo "$LOGIN_RESPONSE" | grep -q "HTTP_CODE:200"; then
    echo "✓ Login successful"
else
    echo "✗ Login failed"
    echo "$LOGIN_RESPONSE"
fi

echo ""
echo "=== Testing Dashboard Access ==="
# Access dashboard with session cookie
DASHBOARD=$(curl -s -b $COOKIE_FILE http://localhost:5000/dashboard)

if echo "$DASHBOARD" | grep -q "Dashboard"; then
    echo "✓ Dashboard accessible"
    
    # Check for key elements
    echo "$DASHBOARD" | grep -o "Total Assets" && echo "  ✓ Total Assets card found"
    echo "$DASHBOARD" | grep -o "Available" && echo "  ✓ Available card found"
    echo "$DASHBOARD" | grep -o "Checked Out" && echo "  ✓ Checked Out card found"
    echo "$DASHBOARD" | grep -o "Recent Checkouts" && echo "  ✓ Recent Checkouts section found"
else
    echo "✗ Dashboard not accessible"
fi

rm -f $COOKIE_FILE
