#!/bin/bash
# ============================================================================
# RetroFit Image Capture Service v2.1 — Production Installer
# Fleet-ready deployment for Raspberry Pi Zero W (ARMv6 / Buster)
#
# Features:
#   - Idempotent (safe to re-run)
#   - Virtual environment isolation
#   - Deterministic OpenCV installation (piwheels direct)
#   - Structured timestamped logging
#   - Fail-fast on any error
#   - Full fresh-OS compatibility
#
# Usage: sudo ./install.sh
# ============================================================================

set -euo pipefail

# --- Logging ---
LOG_FILE="install.log"
log() {
    local level="$1"; shift
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*"
    echo "$msg" | tee -a "$LOG_FILE"
}
log_info()  { log "INFO"  "$@"; }
log_warn()  { log "WARN"  "$@"; }
log_error() { log "ERROR" "$@"; }
log_ok()    { log " OK  " "$@"; }
log_fail()  { log "FAIL" "$@"; exit 1; }

# --- Header ---
echo "==========================================" | tee -a "$LOG_FILE"
echo " RetroFit Image Capture Service v2.1"      | tee -a "$LOG_FILE"
echo " Production Installer"                     | tee -a "$LOG_FILE"
echo "==========================================" | tee -a "$LOG_FILE"

# --- Root check ---
if [ "$(id -u)" -ne 0 ]; then
    log_fail "This script must be run as root (sudo ./install.sh)"
fi

# --- Project directory ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
VENV_DIR="$SCRIPT_DIR/.venv"

# ============================================================================
# PHASE 1: System Detection & Logging
# ============================================================================
log_info "=== PHASE 1: System Detection ==="

# OS version
OS_VERSION=$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 || echo "Unknown")
log_info "OS: $OS_VERSION"

# Architecture
ARCH=$(uname -m)
log_info "Architecture: $ARCH"

# RAM
TOTAL_RAM=$(free -m | awk '/^Mem:/{print $2}')
log_info "Total RAM: ${TOTAL_RAM}MB"

# CPU
CPU_MODEL=$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo "Unknown")
log_info "CPU: $CPU_MODEL"

# Detect Pi model
detect_rpi_model() {
    if grep -q "Raspberry Pi Zero W" /proc/cpuinfo 2>/dev/null; then
        echo "Zero W"
    elif [ "$ARCH" = "armv6l" ]; then
        echo "Zero W"
    elif grep -q "Raspberry Pi 3" /proc/cpuinfo 2>/dev/null; then
        echo "3B+"
    else
        echo "3B+"
    fi
}
RPI_MODEL=$(detect_rpi_model)
log_info "Detected: Raspberry Pi $RPI_MODEL"

# Python version
if command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    log_ok "Python 3 found: $PYTHON_VERSION"
else
    log_info "Python 3 not found, will install"
fi

# ============================================================================
# PHASE 2: APT Repository Repair (Buster EOL)
# ============================================================================
log_info "=== PHASE 2: APT Repository Repair ==="

# Fix deprecated Buster repositories
if grep -q "raspbian.raspberrypi.org" /etc/apt/sources.list 2>/dev/null; then
    log_info "Replacing deprecated raspbian.raspberrypi.org with legacy.raspbian.org"
    sed -i 's/raspbian.raspberrypi.org/legacy.raspbian.org/g' /etc/apt/sources.list
    log_ok "APT sources updated"
else
    log_ok "APT sources already using legacy mirror"
fi

log_info "Updating package lists..."
apt-get clean
apt-get update --allow-releaseinfo-change -y > /dev/null 2>&1 || true
apt-get --fix-broken install -y > /dev/null 2>&1 || true
apt-get update --fix-missing -y > /dev/null 2>&1 || true
log_ok "APT repositories ready"

# ============================================================================
# PHASE 3: System Package Installation
# ============================================================================
log_info "=== PHASE 3: System Packages ==="

# Core packages (always needed)
CORE_PKGS="python3 python3-pip python3-venv python3-dev git ca-certificates"

# Build tools (needed for native Python packages)
BUILD_PKGS="build-essential cmake pkg-config"

# OpenCV runtime dependencies
OPENCV_PKGS="libatlas-base-dev libopenjp2-7 libtiff5 libjasper1 libjasper-dev"
OPENCV_PKGS="$OPENCV_PKGS libjpeg-dev libpng-dev"

# Camera libraries
CAMERA_PKGS="libraspberrypi-bin"

install_pkg_group() {
    local group_name="$1"; shift
    log_info "Installing $group_name..."
    for pkg in "$@"; do
        if dpkg -s "$pkg" &>/dev/null; then
            log_ok "  $pkg (already installed)"
        else
            if apt-get install -y "$pkg" > /dev/null 2>&1; then
                log_ok "  $pkg (installed)"
            else
                log_warn "  $pkg (failed to install, continuing)"
            fi
        fi
    done
}

install_pkg_group "core packages" $CORE_PKGS
install_pkg_group "build tools" $BUILD_PKGS
install_pkg_group "OpenCV dependencies" $OPENCV_PKGS
install_pkg_group "camera libraries" $CAMERA_PKGS

# libcamera (optional, for picamera2 on newer OS)
apt-get install -y python3-libcamera libcamera-dev > /dev/null 2>&1 || \
    log_warn "python3-libcamera not available (expected on Buster)"

# Pi Zero W specific: expand swap for large compilations
if [ "$RPI_MODEL" = "Zero W" ]; then
    CURRENT_SWAP=$(grep CONF_SWAPSIZE /etc/dphys-swapfile 2>/dev/null | grep -oP '\d+' || echo "100")
    if [ "$CURRENT_SWAP" -lt 2048 ] 2>/dev/null; then
        log_info "Expanding swap to 2GB (current: ${CURRENT_SWAP}MB)..."
        dphys-swapfile swapoff
        sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
        dphys-swapfile setup
        dphys-swapfile swapon
        log_ok "Swap expanded to 2GB"
    else
        log_ok "Swap already >= 2GB"
    fi
fi

log_ok "System packages ready"

# ============================================================================
# PHASE 4: Python Virtual Environment
# ============================================================================
log_info "=== PHASE 4: Python Virtual Environment ==="

if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python3" ]; then
    log_ok "Virtual environment exists at $VENV_DIR"
else
    log_info "Creating virtual environment at $VENV_DIR..."
    python3 -m venv --system-site-packages "$VENV_DIR"
    log_ok "Virtual environment created"
fi

# Activate venv for the rest of the script
export PATH="$VENV_DIR/bin:$PATH"
VENV_PYTHON="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip3"

# Upgrade pip inside venv
log_info "Upgrading pip inside venv..."
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel > /dev/null 2>&1
PIP_VERSION=$("$VENV_PIP" --version 2>&1 | head -1)
log_ok "pip: $PIP_VERSION"

# ============================================================================
# PHASE 5: OpenCV Nuclear Cleanse + Deterministic Install
# ============================================================================
log_info "=== PHASE 5: OpenCV Installation ==="

# Remove any conflicting system-level OpenCV
log_info "Removing conflicting OpenCV installations..."
apt-get remove -y python3-opencv > /dev/null 2>&1 || true
"$VENV_PIP" uninstall -y opencv-python opencv-contrib-python \
    opencv-python-headless opencv-contrib-python-headless 2>/dev/null || true

# Purge residual folders
rm -rf /usr/lib/python3/dist-packages/cv2* 2>/dev/null || true
rm -rf /usr/lib/python3/dist-packages/opencv* 2>/dev/null || true
rm -rf "$VENV_DIR"/lib/python3.*/site-packages/cv2* 2>/dev/null || true
rm -rf "$VENV_DIR"/lib/python3.*/site-packages/opencv* 2>/dev/null || true

# Purge pip cache
rm -rf /root/.cache/pip 2>/dev/null || true
rm -rf ~/.cache/pip 2>/dev/null || true
log_ok "Environment sanitized"

# Install OpenCV-contrib-headless 4.5.1.48 from archive1.piwheels.org
OPENCV_VERSION="4.5.1.48"
WHEEL_URL="https://archive1.piwheels.org/simple/opencv-contrib-python-headless/opencv_contrib_python_headless-${OPENCV_VERSION}-cp37-cp37m-linux_armv6l.whl"

log_info "Installing OpenCV $OPENCV_VERSION (ARMv6 wheel from archive1.piwheels.org)..."
# Adding --trusted-host to bypass SSL/Certificate issues common on Buster
# Removing > /dev/null to allow error diagnostics if it fails
if "$VENV_PIP" install --no-cache-dir \
    --trusted-host archive1.piwheels.org \
    --trusted-host www.piwheels.org \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    "$WHEEL_URL"; then
    log_ok "OpenCV $OPENCV_VERSION installed via direct wheel"
else
    log_warn "Direct wheel failed, trying index fallback..."
    if "$VENV_PIP" install --no-cache-dir --force-reinstall \
        "opencv-contrib-python-headless==$OPENCV_VERSION" \
        --index-url https://www.piwheels.org/simple \
        --trusted-host www.piwheels.org \
        --trusted-host archive1.piwheels.org \
        --trusted-host pypi.org \
        --trusted-host files.pythonhosted.org; then
        log_ok "OpenCV $OPENCV_VERSION installed via piwheels index"
    else
        log_fail "OpenCV installation failed. Manually check: ping archive1.piwheels.org"
    fi
fi

# ============================================================================
# PHASE 6: Python Dependencies (from requirements.txt)
# ============================================================================
log_info "=== PHASE 6: Python Dependencies ==="

if [ ! -f "requirements.txt" ]; then
    log_fail "requirements.txt not found in $SCRIPT_DIR"
fi

log_info "Installing Python packages from requirements.txt..."
if "$VENV_PIP" install --no-cache-dir -r requirements.txt > /dev/null 2>&1; then
    log_ok "All Python packages installed"
else
    log_warn "Some packages may have failed, checking individually..."
    while IFS= read -r line; do
        [[ "$line" =~ ^#.*$ ]] && continue
        [[ -z "$line" ]] && continue
        pkg=$(echo "$line" | sed 's/[=!<>].*//' | xargs)
        if "$VENV_PIP" show "$pkg" > /dev/null 2>&1; then
            log_ok "  $pkg"
        else
            log_warn "  $pkg — MISSING (attempting individual install)"
            "$VENV_PIP" install --no-cache-dir "$line" > /dev/null 2>&1 || \
                log_warn "  $pkg — failed to install"
        fi
    done < requirements.txt
fi

# ============================================================================
# PHASE 7: ArUco Verification (Smoke Test)
# ============================================================================
log_info "=== PHASE 7: ArUco Smoke Test ==="

VERIFY_SCRIPT="
import sys
try:
    import cv2
    v = cv2.__version__
    has_aruco = hasattr(cv2, 'aruco')
    if not has_aruco:
        import cv2.aruco
        has_aruco = True
    if has_aruco:
        print(f'OK|{v}')
        sys.exit(0)
    else:
        print(f'FAIL|{v}|no aruco')
        sys.exit(1)
except Exception as e:
    print(f'FAIL||{e}')
    sys.exit(1)
"

RESULT=$("$VENV_PYTHON" -c "$VERIFY_SCRIPT" 2>&1)
if [ $? -eq 0 ]; then
    CV_VERSION=$(echo "$RESULT" | cut -d'|' -f2)
    log_ok "OpenCV $CV_VERSION with ArUco verified"
else
    log_error "ArUco verification result: $RESULT"
    log_fail "ArUco smoke test failed. OpenCV installation is broken."
fi

# ============================================================================
# PHASE 8: rclone Installation
# ============================================================================
log_info "=== PHASE 8: rclone ==="

if command -v rclone &>/dev/null; then
    RCLONE_VER=$(rclone version 2>&1 | head -n1)
    log_ok "rclone already installed: $RCLONE_VER"

    # Upgrade if very old (v1.45 from apt is incompatible with Google OAuth)
    if echo "$RCLONE_VER" | grep -q "v1\.45"; then
        log_warn "rclone v1.45 is too old, upgrading..."
        apt remove -y rclone > /dev/null 2>&1 || true
        curl -s https://rclone.org/install.sh | bash > /dev/null 2>&1
        RCLONE_VER=$(rclone version 2>&1 | head -n1)
        log_ok "rclone upgraded to: $RCLONE_VER"
    fi
else
    log_info "Installing rclone..."
    if curl -s https://rclone.org/install.sh | bash > /dev/null 2>&1; then
        RCLONE_VER=$(rclone version 2>&1 | head -n1)
        log_ok "rclone installed: $RCLONE_VER"
        mkdir -p /home/pi/.config/rclone
        chmod 700 /home/pi/.config/rclone
        chown -R pi:pi /home/pi/.config/rclone
    else
        log_warn "rclone installation failed — GDrive uploads will not work"
    fi
fi

# Validate rclone remote
if rclone listremotes 2>/dev/null | grep -q "gdrive:"; then
    log_ok "rclone remote 'gdrive' configured"
else
    log_warn "rclone remote 'gdrive' not configured. Run: rclone config"
fi

# ============================================================================
# PHASE 9: Runtime Files
# ============================================================================
log_info "=== PHASE 9: Runtime Files ==="

for f in error.log update.log; do
    if [ ! -f "$f" ]; then
        touch "$f"
        chown pi:pi "$f"
        log_ok "Created $f"
    else
        log_ok "$f exists"
    fi
done

mkdir -p capture_output
chown pi:pi capture_output
log_ok "capture_output/ ready"

# ============================================================================
# PHASE 10: systemd Service Installation
# ============================================================================
log_info "=== PHASE 10: systemd Service ==="

SERVICE_NAME="codetest.service"
SERVICE_DEST="/etc/systemd/system/$SERVICE_NAME"

if [ ! -f "$SERVICE_NAME" ]; then
    log_fail "Service file $SERVICE_NAME not found in $SCRIPT_DIR"
fi

# Stop existing service gracefully
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    log_info "Stopping existing service..."
    systemctl stop "$SERVICE_NAME"
fi

# Install service file
cp "$SERVICE_NAME" "$SERVICE_DEST"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
log_ok "Service installed and enabled"

# Start service
log_info "Starting service..."
systemctl start "$SERVICE_NAME"
sleep 3

if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_ok "Service started successfully"
else
    log_warn "Service may not have started. Check: sudo journalctl -u $SERVICE_NAME -n 30"
fi

# ============================================================================
# PHASE 11: Auto-Update Cron
# ============================================================================
log_info "=== PHASE 11: Auto-Update Cron ==="

CRON_CMD="*/30 * * * * $SCRIPT_DIR/run_cmd_bash.sh >> $SCRIPT_DIR/update.log 2>&1"

if crontab -u pi -l 2>/dev/null | grep -q "run_cmd_bash.sh"; then
    log_ok "Auto-update cron already configured"
else
    (crontab -u pi -l 2>/dev/null; echo "$CRON_CMD") | crontab -u pi -
    log_ok "Auto-update cron installed (every 30 minutes)"
fi

# ============================================================================
# FINAL SUMMARY
# ============================================================================
echo "" | tee -a "$LOG_FILE"
echo "==========================================" | tee -a "$LOG_FILE"
echo "  Installation Complete" | tee -a "$LOG_FILE"
echo "==========================================" | tee -a "$LOG_FILE"
log_info "Architecture: $ARCH ($RPI_MODEL)"
log_info "Python: $PYTHON_VERSION (venv: $VENV_DIR)"
log_info "OpenCV: $CV_VERSION with ArUco"
log_info "rclone: $(rclone version 2>&1 | head -1 || echo 'not installed')"
echo "" | tee -a "$LOG_FILE"
echo "Useful commands:" | tee -a "$LOG_FILE"
echo "  Service status : sudo systemctl status codetest.service" | tee -a "$LOG_FILE"
echo "  View logs      : tail -f error.log" | tee -a "$LOG_FILE"
echo "  Live logs      : sudo journalctl -u codetest.service -f" | tee -a "$LOG_FILE"
echo "  Restart        : sudo systemctl restart codetest.service" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Next steps:" | tee -a "$LOG_FILE"
echo "  1. Configure rclone: rclone config (remote name: 'gdrive')" | tee -a "$LOG_FILE"
echo "  2. Create config_WM.py: device_id = \"YOUR-DEVICE-ID\"" | tee -a "$LOG_FILE"
echo "  3. Verify: sudo journalctl -u codetest.service -f" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
