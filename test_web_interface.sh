#!/bin/bash

echo "========================================================================"
echo "TESTING WEB INTERFACE"
echo "========================================================================"

# Test various pages
echo ""
echo "✓ TEST: Web Pages Rendering"

# Login page
if curl -s http://localhost:5000/login | grep -q "School Inventory System"; then
    echo "  ✓ Login page renders correctly"
else
    echo "  ✗ Login page failed"
fi

# Check that protected routes redirect to login
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/dashboard)
if [ "$STATUS" = "302" ]; then
    echo "  ✓ Protected routes redirect to login (HTTP 302)"
else
    echo "  ✗ Protected route security check failed (got HTTP $STATUS)"
fi

# Check assets page redirects
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/assets/)
if [ "$STATUS" = "302" ]; then
    echo "  ✓ Assets page protected (HTTP 302)"
else
    echo "  ✗ Assets page security check failed"
fi

# Check static files
if curl -s http://localhost:5000/static/css/custom.css | grep -q "Custom styles"; then
    echo "  ✓ CSS file accessible"
else
    echo "  ✗ CSS file not accessible"
fi

# Check error page
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/nonexistent-page)
if [ "$STATUS" = "404" ]; then
    echo "  ✓ 404 error handling works"
else
    echo "  ✗ 404 error handling issue"
fi

echo ""
echo "✓ TEST: Application Health"

# Check if server is responding
if curl -s http://localhost:5000/login > /dev/null; then
    echo "  ✓ Server is responding to requests"
else
    echo "  ✗ Server not responding"
fi

# Check application log for errors
if grep -qi "error\|exception\|traceback" app.log; then
    echo "  ⚠ Warning: Errors found in application log"
    echo ""
    echo "Recent errors:"
    grep -i "error\|exception" app.log | tail -5
else
    echo "  ✓ No errors in application log"
fi

echo ""
echo "========================================================================"
echo "WEB INTERFACE TESTS COMPLETE"
echo "========================================================================"

