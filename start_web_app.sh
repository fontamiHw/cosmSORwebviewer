#!/bin/bash
# Startup script for SOR File Parser Web Application

echo "🔧 SOR File Parser Web Application Startup"
echo "==========================================="

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.7 or higher."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Try to install dependencies with --user flag (safer option)
echo "📦 Running virtual Environment"
uv sync
source .venv/bin/activate

# Check if dumpSOR.py exists in current directory
if [ ! -f "dumpSOR.py" ]; then
    echo "⚠️  Warning: dumpSOR.py not found in current directory"
    echo "   Make sure dumpSOR.py is in the main otdr directory"
fi

echo ""
echo "🚀 Starting SOR File Parser Web Application..."
echo ""
echo "📱 Web Interface: http://localhost:8800"
echo "📖 API Docs: http://localhost:8800/docs"
echo "🛑 Press Ctrl+C to stop the server"
echo ""

# Start the web application using the virtual environment
python sor_web_app.py
