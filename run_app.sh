#!/bin/bash

# Medical Document Processor - Quick Start Script

echo "🏥 Starting Medical Document Processor..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies if needed
if [ ! -f "venv/installed" ]; then
    echo "📥 Installing dependencies..."
    pip install -r streamlit_requirements.txt
    touch venv/installed
fi

# Start the Streamlit app
echo "🚀 Starting Streamlit app..."
echo "📱 Open your browser and go to: http://localhost:8501"
echo "⏹️  Press Ctrl+C to stop the app"
echo ""

streamlit run streamlit_app.py --server.port 8501 