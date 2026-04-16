#!/bin/bash

set -e

echo "Starting Multi-Camera 3D Recording Backend v2..."
echo ""

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "Starting FastAPI server on http://localhost:8000"
echo ""
python main.py
