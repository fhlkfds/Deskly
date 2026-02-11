#!/bin/bash

# K-12 School Inventory System - Quick Start Script

echo "=== K-12 School Inventory System ==="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and configure your settings!"
fi

# Run the application
echo ""
echo "Starting application..."
echo "Access the application at: http://localhost:5000"
echo "Default login: admin@school.edu / admin123"
echo ""
python app.py
