#!/bin/bash
set -e

rm -f instance/database.db

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

pip install -q -r requirements.txt

python -c "from app import app, init_db; init_db(); app.run(debug=False, host='0.0.0.0', port=5000)"
