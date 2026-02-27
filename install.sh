#!/bin/bash
# ============================================================================
# RetroFit Image Capture Service v2.1 — Production Installer
# Fleet-ready deployment for Raspberry Pi Zero W (ARMv6 / Buster)
#
# Features:
#   - Idempotent (safe to re-run)
#   - Virtual environment isolation
#   - Deterministic OpenCV installation (piwheels direct + hardened)
#   - Structured timestamped logging
#   - Fail-fast on any error with deep diagnostics
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
log_fail()  { 
    log "FAIL" "$@"; 
    echo "==========================================" >> "$LOG_FILE"
    echo "  DIAGNOSTIC DUMP" >> "$LOG_FILE"
    echo "==========================================" >> "$LOG_FILE"
    if [ -d ".venv" ]; then
        echo "--> OpenSSL Version:" >> "$LOG_FILE"
        .venv/bin/python3 -c "import ssl; print(ssl.OPENSSL_VERSION)" >> "$LOG_FILE" 2>&1 || true
        echo -e "\n--> pip config list:" >> "$LOG_FILE"
        .venv/bin/pip config list >> "$LOG_FILE" 2>&1 || true
        echo -e "\n--> pip debug --verbose:" >> "$LOG_FILE"
        .venv/bin/python3 -m pip debug --verbose >> "$LOG_FILE" 2>&1 || true
    fi
    exit 1; 
}

# --- Header ---
echo "==========================================" | tee -a "$LOG_FILE"
echo " RetroFit Image Capture Service v2.1"      | tee -a "$LOG_FILE"
echo " Production Installer (Hardened)"          | tee -a "$LOG_FILE"
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
fi

log_info "Updating package lists..."
apt-get clean > /dev/null 2>&1
apt-get update --allow-releaseinfo-change -y > /dev/null 2>&1 || true
apt-get --fix-broken install -y > /dev/null 2>&1 || true
apt-get update --fix-missing -y > /dev/null 2>&1 || true
log_ok "APT repositories ready"

# ============================================================================
# PHASE 3: System Package Installation
# ============================================================================
log_info "=== PHASE 3: System Packages ==="

# Core packages
CORE_PKGS="python3 python3-pip python3-venv python3-dev git ca-certificates"

# Build tools
BUILD_PKGS="build-essential cmake pkg-config"

# OpenCV runtime dependencies
OPENCV_PKGS="libatlas-base-dev libopenjp2-7 libtiff5 libjasper1 libjasper-dev"
OPENCV_PKGS="$OPENCV_PKGS libjpeg-dev libpng-dev"

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

# Camera libraries (always install)
apt-get install -y libraspberrypi-bin > /dev/null 2>&1 || true

# Conditional libcamera warning suppression for Buster
if [[ "$OS_VERSION" == *"buster"* ]]; then
    log_ok "Buster detected: Skipping python3-libcamera (Legacy cam stack used)"
else
    apt-get install -y python3-libcamera libcamera-dev > /dev/null 2>&1 || true
fi

# Expand swap to 2GB for Zero W (needed for reliable pip installs on low RAM)
if [ "$RPI_MODEL" = "Zero W" ]; then
    CURRENT_SWAP=$(grep CONF_SWAPSIZE /etc/dphys-swapfile 2>/dev/null | grep -oP '\d+' || echo "100")
    if [ "$CURRENT_SWAP" -lt 2048 ] 2>/dev/null; then
        log_info "Expanding swap to 2GB..."
        dphys-swapfile swapoff > /dev/null 2>&1 || true
        sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
        dphys-swapfile setup > /dev/null 2>&1
        dphys-swapfile swapon > /dev/null 2>&1
        log_ok "Swap expanded"
    else
        log_ok "Swap already sufficient"
    fi
fi

log_ok "System packages ready"

# ============================================================================
# PHASE 4: Python Virtual Environment
# ============================================================================
log_info "=== PHASE 4: Python Virtual Environment ==="

if [ ! -d "$VENV_DIR" ]; then
    log_info "Creating virtual environment..."
    python3 -m venv --system-site-packages "$VENV_DIR"
fi

export PATH="$VENV_DIR/bin:$PATH"
VENV_PYTHON="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"

# Hardened pip version for Python 3.7
TARGET_PIP_VER="23.0.1"
export PIP_DISABLE_PIP_VERSION_CHECK=1
unset PIP_REQUIRE_HASHES || true
# Bypass global /etc/pip.conf to prevent piwheels index duplication and global config policies
export PIP_CONFIG_FILE=/dev/null 

log_info "Enforcing pip stable version $TARGET_PIP_VER..."
"$VENV_PYTHON" -m pip install --upgrade "pip==$TARGET_PIP_VER" setuptools==59.6.0 wheel==0.37.1 > /dev/null 2>&1 || true
log_ok "pip ready: $($VENV_PIP --version)"

# ============================================================================
# PHASE 5: Python Dependencies
# ============================================================================
log_info "=== PHASE 5: Python Dependencies ==="

log_info "Purging cache before dependency install..."
"$VENV_PIP" cache purge > /dev/null 2>&1 || true
rm -rf /tmp/pip-* 2>/dev/null || true

log_info "Installing numpy (strict)..."
"$VENV_PIP" install --no-cache-dir \
    --index-url https://www.piwheels.org/simple \
    --extra-index-url https://pypi.org/simple \
    --prefer-binary \
    numpy==1.19.5 > /dev/null 2>&1 || true

log_info "Installing requirements.txt..."
if "$VENV_PIP" install --no-cache-dir \
    --index-url https://www.piwheels.org/simple \
    --extra-index-url https://pypi.org/simple \
    --prefer-binary \
    -r requirements.txt; then
    
    # Final dependency integrity check
    if "$VENV_PYTHON" -c "import numpy; print(numpy.__version__)" >/dev/null 2>&1; then
        log_ok "Dependency installation and integrity validated"
    else
        log_fail "Numpy installed but failed python import checks."
    fi
else
    log_fail "Dependency installation failed"
fi

# ============================================================================
# PHASE 6: OpenCV Installation (Deterministic & Hardened)
# ============================================================================
log_info "=== PHASE 6: OpenCV Installation ==="

# Pre-flight Diagnostics
log_info "Dumping PIP Config & Requirements State..."
echo "--- requirements.txt contents ---" >> "$LOG_FILE"
cat requirements.txt >> "$LOG_FILE" 2>&1 || true
echo "--- pip config list ---" >> "$LOG_FILE"
"$VENV_PIP" config list >> "$LOG_FILE" 2>&1 || true
echo "--- PIP_REQUIRE_HASHES environment ---" >> "$LOG_FILE"
echo "${PIP_REQUIRE_HASHES:-Not Set}" >> "$LOG_FILE" 2>&1 || true

# Sanitary purge
log_info "Sanitizing environment..."
"$VENV_PIP" uninstall -y opencv-python opencv-contrib-python opencv-python-headless opencv-contrib-python-headless 2>/dev/null || true
"$VENV_PIP" cache purge > /dev/null 2>&1 || true
rm -rf /tmp/pip-* 2>/dev/null || true

OPENCV_VERSION="4.5.1.48"
LOCAL_WHEEL_NAME="opencv_contrib_python_headless-${OPENCV_VERSION}-cp37-cp37m-linux_armv6l.whl"

log_info "Installing OpenCV $OPENCV_VERSION (ARMv6) from LOCAL FILE..."

if [ ! -f "$LOCAL_WHEEL_NAME" ]; then
    log_fail "LOCAL WHEEL MISSING! You must manually download $LOCAL_WHEEL_NAME to your PC, place it in the Evaraflow folder on the SD card, and run this script again."
fi

# Strategy: Local offline install
if "$VENV_PIP" install "$LOCAL_WHEEL_NAME" --no-index --no-cache-dir; then
    log_ok "OpenCV $OPENCV_VERSION installed successfully from local file"
else
    log_fail "Failed to install the local wheel file. It may be corrupted."
fi

# Post-install primary validation (mandated by workflow)
log_info "Verifying OpenCV python bindings..."
if "$VENV_PYTHON" -c "import cv2; print(cv2.__version__)" >/tmp/opencv_import.log 2>&1 && \
   "$VENV_PYTHON" -c "import cv2; print(hasattr(cv2,'aruco'))" >>/tmp/opencv_import.log 2>&1; then
    log_ok "OpenCV integrity visually confirmed inside venv."
else
    log_error "OpenCV python import check failed. Details below:"
    cat /tmp/opencv_import.log | tee -a "$LOG_FILE"
    log_fail "OpenCV installed but failed python import checks. (Likely Numpy incompatibility)"
fi

# ============================================================================
# PHASE 7: ArUco Smoke Test
# ============================================================================
log_info "=== PHASE 7: ArUco Smoke Test ==="

SMOKE_TEST="
import sys, logging
try:
    import cv2
    import numpy as np
    v = cv2.__version__
    import cv2.aruco as aruco
    # Verify legacy API call
    d = aruco.Dictionary_get(aruco.DICT_4X4_50)
    print(f'OK|{v}')
    sys.exit(0)
except Exception as e:
    print(f'FAIL|{e}')
    sys.exit(1)
"

RESULT=$("$VENV_PYTHON" -c "$SMOKE_TEST" 2>&1 || echo "ERROR|$?")
if [[ "$RESULT" == OK* ]]; then
    log_ok "ArUco verified (OpenCV $(echo "$RESULT" | cut -d'|' -f2))"
else
    log_error "Smoke test failed: $RESULT"
    log_fail "OpenCV installed but ArUco functionality is missing."
fi

# ============================================================================
# FINAL PHASES (rclone, Service, Cron)
# ============================================================================
log_info "=== FINAL PHASES: System Integration ==="

# rclone (idempotent)
if ! command -v rclone &>/dev/null; then
    curl -s https://rclone.org/install.sh | bash > /dev/null 2>&1 || true
fi

# Service file
SERVICE_NAME="codetest.service"
if [ -f "$SERVICE_NAME" ]; then
    cp "$SERVICE_NAME" "/etc/systemd/system/$SERVICE_NAME"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME" > /dev/null 2>&1
    systemctl restart "$SERVICE_NAME"
    log_ok "Service deployed"
fi

# Cron
CRON_CMD="*/30 * * * * $SCRIPT_DIR/run_cmd_bash.sh >> $SCRIPT_DIR/update.log 2>&1"
(crontab -u pi -l 2>/dev/null | grep -v "run_cmd_bash.sh"; echo "$CRON_CMD") | crontab -u pi -
log_ok "Cron installed"

log_info "=== INSTALLATION COMPLETE ==="
log_info "Log saved to: $LOG_FILE"
echo "=========================================="
echo "  Success! Your system is ready."
echo "=========================================="
