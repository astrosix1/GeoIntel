#!/bin/bash

# GeoIntel Backend Startup Script for macOS/Linux

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║        GeoIntel Backend API Server                  ║"
echo "║     Real-Time Geopolitical Intelligence             ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Please install Python 3.8+"
    exit 1
fi

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment"
        exit 1
    fi
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo ""
echo "Installing dependencies (this may take a minute)..."
pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies"
    echo "Try running manually: pip install -r requirements.txt"
    exit 1
fi

# Check if database exists, initialize if not
if [ ! -f "geointel.db" ]; then
    echo ""
    echo "Initializing database..."
    python3 models.py
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to initialize database"
        exit 1
    fi
fi

# Start the Flask server
echo ""
echo "════════════════════════════════════════════════════════"
echo "Backend starting on http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop the server"
echo "════════════════════════════════════════════════════════"
echo ""

python3 app.py

# Show error if app crashes
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Backend crashed"
    echo "Check the error messages above"
    exit 1
fi
