#!/bin/bash

# ListingBoost - Startup Script

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Starting ListingBoost..."
echo ""

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Check dependencies
echo "📋 Checking dependencies..."
pip install -q flask flask-cors python-dotenv anthropic pillow opencv-python numpy

# Create uploads folder if it doesn't exist
mkdir -p uploads

echo ""
echo "✅ Environment ready!"
echo ""
echo "🌐 Starting Flask server on http://localhost:5000"
echo ""
echo "Available endpoints:"
echo "  POST /api/improve-description  - Improve Airbnb descriptions"
echo "  POST /api/generate-titles      - Generate title suggestions"
echo "  POST /api/enhance-images       - Enhance listing photos"
echo "  GET  /health                   - Health check"
echo "  GET  /                         - Web interface"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start Flask app
python app.py
