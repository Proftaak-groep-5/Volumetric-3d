#!/bin/bash

echo "Starting Multi-Camera 3D Recording Frontend..."
echo ""

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

# Start the development server
echo ""
echo "Starting React development server on http://localhost:3000"
echo ""
npm start

