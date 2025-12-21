#!/bin/bash
set -e

echo "🔧 Installing OCR Support for Document Tagging System"
echo "=================================================="

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
else
    echo "⚠️  Unsupported OS: $OSTYPE"
    exit 1
fi

echo "📦 Detected OS: $OS"

# Install Tesseract
echo ""
echo "1️⃣  Installing Tesseract OCR..."
if [ "$OS" == "macos" ]; then
    if ! command -v brew &> /dev/null; then
        echo "❌ Homebrew not found. Please install from https://brew.sh"
        exit 1
    fi
    brew install tesseract tesseract-lang poppler
elif [ "$OS" == "linux" ]; then
    sudo apt-get update
    sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin poppler-utils
fi

# Verify Tesseract
echo ""
echo "2️⃣  Verifying Tesseract installation..."
tesseract --version
echo ""
echo "Available languages:"
tesseract --list-langs

# Install Python dependencies
echo ""
echo "3️⃣  Installing Python OCR dependencies..."
cd backend
source venv/bin/activate
pip install pytesseract pdf2image Pillow

echo ""
echo "✅ OCR Support Installation Complete!"
echo ""
echo "📋 Next Steps:"
echo "1. Start backend: cd backend && source venv/bin/activate && uvicorn app.main:app --reload"
echo "2. Upload a scanned PDF to test OCR"
echo "3. Look for 📷 badge indicating scanned PDF detection"
echo ""
echo "📚 For more details, see OCR_SETUP.md"
