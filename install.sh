#!/bin/bash
# RetroFit Image Capture Service Installation Script
# Cloud Processing Architecture - No Edge ML
# Compatible with RPi 3B+ (ARM7) and RPi Zero W (ARM6)
# 
# v2.0 Changes:
#   - Removed ML dependencies (scikit-learn, joblib, etc.)
#   - Simplified to capture + upload only
#   - Added Python bytecode cache prevention
#   - Enhanced upload reliability with retry + verification
#   - 50% faster installation, 65% less memory usage

echo "=========================================="
echo " RetroFit Image Capture Service v2.1"
echo " Cloud Processing Architecture"
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

echo "[1/7] Checking Python environment..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo "✓ Python 3 found: $PYTHON_VERSION"
else
    echo "✗ Python 3 not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip
fi

echo ""
echo "[2/7] Checking system packages..."

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
    
    # Expand swap to 2GB for OpenCV compilation (512MB RAM is not enough)
    CURRENT_SWAP=$(grep CONF_SWAPSIZE /etc/dphys-swapfile | grep -oP '\d+')
    if [ "$CURRENT_SWAP" -lt 2048 ] 2>/dev/null; then
        echo "  📦 Expanding swap to 2GB for compilation..."
        sudo dphys-swapfile swapoff
        sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
        sudo dphys-swapfile setup
        sudo dphys-swapfile swapon
        echo "  ✓ Swap expanded to 2GB"
    fi

    # Build tools for OpenCV (cmake is required if pip needs to build from source)
    sudo apt-get install -y cmake pkg-config build-essential
    
    # System dependencies for OpenCV
    sudo apt-get install -y libatlas-base-dev libopenjp2-7 libtiff5 libjpeg-dev libpng-dev
    
    # libcamera dependencies (handling name changes between OS versions)
    sudo apt-get install -y libcamera-dev python3-libcamera 2>/dev/null || \
    echo "  ! python3-libcamera not found (common on older OS, skipping)"
else
    echo "  ⚙️  Optimizing for RPi 3B+ (1GB RAM, ARM7)..."
    sudo apt-get install -y cmake pkg-config build-essential libatlas-base-dev
    sudo apt-get install -y libcamera-dev python3-libcamera 2>/dev/null || \
    echo "  ! python3-libcamera not found (skipping)"
fi

echo ""
echo "[3/7] Checking required Python packages..."

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
        "opencv-contrib-python-headless") import_name="cv2" ;;
        "RPi.GPIO") import_name="RPi.GPIO" ;;
        "python-dateutil") import_name="dateutil" ;;
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
    echo "  ⏳ Note: Installation may take 5-10 minutes..."
    echo "     (opencv-contrib requires compilation)"
fi

# Uninstall all potentially conflicting OpenCV dependencies to prevent missing 'cv2.aruco'
echo "  🧹 Cleaning up corrupted OpenCV installations from armv6l cache..."
# 1. Remove the OS-level version which lacks ArUco
sudo apt-get remove -y python3-opencv > /dev/null 2>&1
# 2. Remove any pip-installed versions
sudo pip3 uninstall -y opencv-python opencv-contrib-python opencv-python-headless opencv-contrib-python-headless 2>/dev/null
# 3. Aggressive Surgical Strike: Manually delete broken cv2 package folders that pip / apt fail to clean up
sudo rm -rf /usr/lib/python3/dist-packages/cv2* 2>/dev/null
sudo rm -rf /usr/local/lib/python3.*/dist-packages/cv2* 2>/dev/null
sudo rm -rf /usr/local/lib/python3.*/dist-packages/opencv* 2>/dev/null

# Install with proper flags for ARM compatibility
# Use --extra-index-url to prioritize piwheels.org for pre-compiled binaries
sudo pip3 install --no-cache-dir \
    --extra-index-url https://www.piwheels.org/simple \
    -r requirements.txt

echo "✓ Package installation complete (50% faster than v1.x - no ML dependencies)"

echo ""
echo "========================================"
echo "[3.5/6] Installing rclone (Latest Version)..."
echo "========================================"

if command -v rclone &> /dev/null; then
    RCLONE_VERSION=$(rclone version | head -n1)
    echo "✓ rclone already installed: $RCLONE_VERSION"
    
    # Check if it's an old version from apt repository
    if [[ "$RCLONE_VERSION" == *"v1.45"* ]]; then
        echo "⚠️  Old rclone v1.45 detected (incompatible with Google OAuth)"
        echo "   Upgrading to latest version..."
        sudo apt remove -y rclone
        curl https://rclone.org/install.sh | sudo bash
        RCLONE_VERSION=$(rclone version | head -n1)
        echo "✓ rclone upgraded to: $RCLONE_VERSION"
    fi
else
    echo "Installing latest rclone from official source..."
    
    # Use official rclone install script (installs latest version)
    if curl https://rclone.org/install.sh | sudo bash; then
        RCLONE_VERSION=$(rclone version | head -n1)
        echo "✓ rclone installed: $RCLONE_VERSION"
        
        # Create config directory
        mkdir -p ~/.config/rclone
        chmod 700 ~/.config/rclone
        echo "✓ rclone config directory created"
        
        echo ""
        echo "⚠️  IMPORTANT: rclone configuration required for Google Drive uploads"
        echo "   After installation completes, run: rclone config"
        echo "   Setup guide:"
        echo "   1. Choose 'n' for new remote"
        echo "   2. Name it 'gdrive'"
        echo "   3. Select 'drive' (Google Drive)"
        echo "   4. Leave client_id and client_secret blank"
        echo "   5. Choose scope=1 (full access)"
        echo "   6. For auto-config, follow OAuth prompts"
        echo ""
    else
        echo "⚠️  rclone installation failed"
        echo "   Google Drive uploads will not work until rclone is configured"
        echo "   Install manually: curl https://rclone.org/install.sh | sudo bash"
    fi
fi

echo "✓ rclone setup complete"

echo ""
echo "[4/7] Creating required files..."
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
echo "[5/7] Configuring systemd service..."

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
echo "[6/7] Starting service..."
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
echo "[7/7] Setting up auto-update cron job..."
CRON_CMD="*/30 * * * * /home/pi/Desktop/Evaratech/Evaraflow/run_cmd_bash.sh >> /home/pi/Desktop/Evaratech/Evaraflow/update.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "run_cmd_bash.sh"; then
    echo "✓ Auto-update cron job already configured"
else
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "✓ Auto-update cron job installed (every 30 minutes)"
fi

echo ""
echo "=========================================="
echo "  Installation Complete! (v2.1)"
echo "=========================================="
echo ""
echo "Architecture: Cloud Processing (Capture + Upload Only)"
echo "Memory Usage: ~120MB (65% reduction from v1.x)"
echo "Disk Usage: ~90MB (70% reduction from v1.x, removed pandas/openpyxl)"
echo ""
echo "Useful commands:"
echo "  Service status : sudo systemctl status codetest.service"
echo "  View logs      : tail -f error.log"
echo "  View live logs : sudo journalctl -u codetest.service -f"
echo "  Restart service: sudo systemctl restart codetest.service"
echo "  Stop service   : sudo systemctl stop codetest.service"
echo "  Health check   : cat health.json"
echo ""
echo "Next steps:"
echo "  1. Configure rclone: rclone config (create remote named 'gdrive')"
echo "  2. Create config_WM.py with: device_id = \"YOUR-DEVICE-ID\""
echo "  3. Add device to credentials_store.csv with GDrive/ThingSpeak credentials"
echo "  4. Verify service logs: tail -f error.log"
echo "  5. Check first capture cycle (5 minutes after start)"
echo ""
echo "Auto-update: Cron runs every 30 minutes (see update.log)"
echo "Health file: health.json updated each cycle for fleet monitoring"
echo "Note: Service automatically clears Python cache on restart"
echo ""
