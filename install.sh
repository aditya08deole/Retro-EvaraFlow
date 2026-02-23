#!/bin/bash
# Retro-EvaraFlow Installation Script - Smart Package Management
# Compatible with RPi 3B+ (ARM7) and RPi Zero W (ARM6)

echo "=========================================="
echo "  Retro-EvaraFlow Installation v1.1"
echo "=========================================="
echo ""

# Detect Raspberry Pi model
detect_rpi_model() {
    if grep -q "Raspberry Pi Zero W" /proc/cpuinfo; then
        echo "Zero W"
    elif grep -q "Raspberry Pi 3 Model B Plus" /proc/cpuinfo; then
        echo "3B+"
    else
        # Default - check for ARM version
        if [ "$(uname -m)" = "armv6l" ]; then
            echo "Zero W"
        else
            echo "3B+"
        fi
    fi
}

RPI_MODEL=$(detect_rpi_model)
echo "📟 Detected: Raspberry Pi $RPI_MODEL"
echo ""

# Function to check if Python package is installed
check_python_package() {
    python3 -c "import $1" 2>/dev/null
    return $?
}

# Function to check package version
check_package_version() {
    python3 -c "import $1; print($1.__version__)" 2>/dev/null
}

echo "[1/6] Checking Python environment..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo "✓ Python 3 found: $PYTHON_VERSION"
else
    echo "✗ Python 3 not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip
fi

echo ""
echo "[2/6] Checking system packages..."

# Check and install pip if needed
if ! command -v pip3 &> /dev/null; then
    echo "  Installing pip3..."
    sudo apt-get install -y python3-pip
else
    echo "✓ pip3 already installed"
fi

# Install system dependencies based on model
echo ""
echo "  Installing system dependencies..."
if [ "$RPI_MODEL" = "Zero W" ]; then
    echo "  ⚙️  Optimizing for RPi Zero W (512MB RAM, ARM6)..."
    sudo apt-get install -y python3-dev libatlas-base-dev libopenjp2-7 libtiff5
else
    echo "  ⚙️  Optimizing for RPi 3B+ (1GB RAM, ARM7)..."
    sudo apt-get install -y python3-dev libatlas-base-dev
fi

echo ""
echo "[3/6] Checking required Python packages..."

# Use requirements.txt for installation
if [ ! -f "requirements.txt" ]; then
    echo "⚠️  requirements.txt not found!"
    exit 1
fi

echo "  Checking installed packages vs requirements..."

# Parse requirements.txt and check each package
while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    
    # Extract package name (before == or >= or !=)
    package_name=$(echo "$line" | sed 's/[=!<>].*//' | xargs)
    
    # Map pip package names to import names
    case "$package_name" in
        "opencv-python-headless") import_name="cv2" ;;
        "scikit-learn") import_name="sklearn" ;;
        "scikit-image") import_name="skimage" ;;
        "python-telegram-bot") import_name="telegram" ;;
        "google-api-python-client") import_name="googleapiclient" ;;
        "google-auth") import_name="google.auth" ;;
        "RPi.GPIO") import_name="RPi.GPIO" ;;
        *) import_name="$package_name" ;;
    esac
    
    if check_python_package "$import_name"; then
        version=$(check_package_version "$import_name" 2>/dev/null || echo "unknown")
        echo "  ✓ $package_name ($version)"
    else
        echo "  ✗ $package_name - missing"
    fi
done < requirements.txt

echo ""
echo "  Installing/updating packages from requirements.txt..."

if [ "$RPI_MODEL" = "Zero W" ]; then
    echo "  ⏳ Note: Installation on Zero W may take 15-30 minutes..."
    echo "     (scikit-learn requires compilation)"
fi

# Install with proper flags for ARM compatibility
sudo pip3 install --no-cache-dir -r requirements.txt

echo "✓ Package installation complete"

echo ""
echo "[4/6] Creating required files..."
if [ ! -f "error.log" ]; then
    touch error.log
    echo "✓ Created error.log"
else
    echo "✓ error.log already exists"
fi

if [ ! -f "update.log" ]; then
    touch update.log
    echo "✓ Created update.log"
else
    echo "✓ update.log already exists"
fi

echo ""
echo "[5/6] Configuring systemd service..."

# Check if service already exists
if systemctl list-unit-files | grep -q "codetest.service"; then
    echo "⚠ Service already exists. Updating..."
    sudo systemctl stop codetest.service 2>/dev/null
fi

# Copy service file
sudo cp codetest.service /etc/systemd/system/
echo "✓ Service file copied"

# Reload systemd
sudo systemctl daemon-reload
echo "✓ Systemd reloaded"

# Enable service
sudo systemctl enable codetest.service
echo "✓ Service enabled for auto-start"

echo ""
echo "[6/6] Starting service..."
sudo systemctl start codetest.service

# Wait a moment for service to initialize
sleep 2

# Check status
SERVICE_STATUS=$(systemctl is-active codetest.service)
if [ "$SERVICE_STATUS" = "active" ]; then
    echo "✓ Service started successfully"
else
    echo "⚠ Service status: $SERVICE_STATUS"
    echo "  Check logs: sudo journalctl -u codetest.service -n 50"
fi

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Useful commands:"
echo "  Check status : sudo systemctl status codetest.service"
echo "  View logs    : sudo journalctl -u codetest.service -f"
echo "  Restart      : sudo systemctl restart codetest.service"
echo "  Stop         : sudo systemctl stop codetest.service"
echo ""
echo "Next steps:"
echo "  1. Configure device ID in config_WM.py"
echo "  2. Set initial reading in Variable.txt and var2.txt"
echo "  3. Add device credentials to credentials_store.xlsx"
echo "  4. Setup cron job for auto-updates"
echo ""
