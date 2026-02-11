#!/bin/bash
rm -f instance/database.db

source venv/bin/activate


python -c "from app import app, init_db; init_db(); app.run(debug=False, host='0.0.0.0', port=5000)"
