"""
System Configuration - Fleet-Wide Settings

NOTE: Device-specific credentials are now loaded from credentials_store.xlsx
      based on device_id from config_WM.py (following deployment workflow)

NO HARDCODED CREDENTIALS IN THIS FILE!
"""

# Hardware Settings (Fleet-wide defaults)
RELAY_PIN = 23
CAMERA_RESOLUTION = (1640, 1232)

# Camera timing (strictly enforced sequence)
WARMUP_DELAY = 0.5        # Initial delay after LED ON (seconds)
FOCUS_DELAY = 3           # Focus adjustment time (seconds) - LED stays ON
POST_CAPTURE_DELAY = 3    # Keep LED ON after capture (seconds)

# Model Configuration
MODEL_PATH = "rf_rasp_classifier.sav"
MIN_CONTOUR_AREA = 1500
CROP_WIDTH = 540
CONFIDENCE_THRESHOLD = 0.6  # Default, per-device override in credentials_store

# ROI Settings
ROI_WIDTH = 650
ROI_HEIGHT = 215
ROI_ZOOM = 60

# Fallback ROI coordinates (if ArUco markers fail)
FALLBACK_ROI_POINTS = [[144, 127], [1569, 103], [1582, 517], [152, 539]]

# Flow Validation (Fleet-wide defaults)
MAX_FLOW_RATE = 100.0
MIN_TIME_DIFF = 1

# Timing (Can be overridden per-device in credentials_store.xlsx)
CAPTURE_INTERVAL = 300

# Retry Configuration
MAX_RETRIES = 1

# Persistence
STATE_FILE = "meter_state.json"
ERROR_LOG = "error.log"

# Credential Store (Fleet deployment)
CREDENTIAL_STORE_PATH = "credentials_store.xlsx"
CONFIG_WM_PATH = "config_WM.py"  # Device identity file
