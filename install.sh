#!/bin/bash
# Retro-EvaraFlow Installation Script - Smart Package Management
# Automatically installs only missing packages to prevent version conflicts

echo "=========================================="
echo "  Retro-EvaraFlow Installation v1.0"
echo "=========================================="
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

echo ""
echo "[3/6] Checking required Python packages..."

# List of required packages with minimum versions
declare -A PACKAGES=(
    ["cv2"]="opencv-python>=4.5.0"
    ["numpy"]="numpy>=1.21.0"
    ["pandas"]="pandas>=1.3.0"
    ["openpyxl"]="openpyxl>=3.0.9"
    ["sklearn"]="scikit-learn>=1.0.0"
    ["joblib"]="joblib>=1.1.0"
    ["requests"]="requests>=2.26.0"
    ["telegram"]="python-telegram-bot>=13.14"
)

MISSING_PACKAGES=()

for import_name in "${!PACKAGES[@]}"; do
    pip_package="${PACKAGES[$import_name]}"
    
    if check_python_package "$import_name"; then
        version=$(check_package_version "$import_name")
        echo "✓ $import_name already installed: $version"
    else
        echo "✗ $import_name not found - will install"
        MISSING_PACKAGES+=("$pip_package")
    fi
done

# Install missing packages
if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo ""
    echo "Installing ${#MISSING_PACKAGES[@]} missing packages..."
    for package in "${MISSING_PACKAGES[@]}"; do
        echo "  Installing $package..."
        sudo pip3 install --upgrade "$package"
    done
    echo "✓ All missing packages installed"
else
    echo ""
    echo "✓ All required packages already installed!"
fi

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
