"""
Credential Management System - v2.1
Loads device-specific credentials from credentials_store.csv
Supports multi-device fleet deployment with zero hardcoded credentials

v2.1 Changes:
- Added ThingSpeak credentials (channel_id, write_api_key)
- Added telegram_enabled flag (can disable Telegram per device)
- Telegram fields are optional when telegram_enabled=false
- Safe regex parsing (no exec())
"""

import os
import re
import logging

logger = logging.getLogger(__name__)


class CredentialError(Exception):
    """Base exception for credential-related errors"""
    pass


class DeviceNotFoundError(CredentialError):
    """Raised when device_id is not found in credential store"""
    pass


class CredentialMissingError(CredentialError):
    """Raised when required credential field is empty"""
    pass


def load_from_config_wm(config_file='config_WM.py', credential_store='credentials_store.csv'):
    """
    Load credentials using device_id from config_WM.py file.
    
    This maintains compatibility with existing deployment workflow.
    Each device has a config_WM.py file (not in git) that specifies its device_id,
    which is then used to look up credentials in the central credentials_store.csv.
    
    Args:
        config_file: Path to config_WM.py (device-specific, contains device_id)
        credential_store: Path to credentials_store.csv (contains all device credentials)
        
    Returns:
        dict: Credential dictionary with device settings
        
    Raises:
        FileNotFoundError: If config_WM.py or credentials_store.csv not found
        CredentialError: If device_id not found or credentials invalid
        
    Usage:
        credentials = load_from_config_wm()
        device_id = credentials['device_id']
        thingspeak_key = credentials['thingspeak_write_api_key']
    """
    # Step 1: Read device_id from config_WM.py
    if not os.path.exists(config_file):
        raise FileNotFoundError(
            f"{config_file} not found.\n"
            f"Create this file with: device_id = \"YOUR-DEVICE-ID\"\n"
            f"Example: echo 'device_id = \"Node-1\"' > config_WM.py"
        )
    
    # Read device_id safely using regex (no exec() for security)
    try:
        with open(config_file, 'r') as f:
            content = f.read()
        
        # Match: device_id = "value" or device_id = 'value'
        match = re.search(r'device_id\s*=\s*["\'](.+?)["\']', content)
        if match:
            device_id = match.group(1).strip()
        else:
            device_id = None
    except Exception as e:
        raise CredentialError(f"Failed to read {config_file}: {str(e)}")
    
    if not device_id:
        raise CredentialError(
            f"device_id not defined in {config_file}.\n"
            f"Add this line: device_id = \"YOUR-DEVICE-ID\""
        )
    
    logger.info(f"Device ID from {config_file}: {device_id}")
    
    # Step 2: Load credentials from CSV
    return load_credentials_from_csv(device_id, credential_store)


def load_credentials_from_csv(device_id, csv_path='credentials_store.csv'):
    """
    Load credentials for specific device from CSV file.
    
    CSV Format:
        device_id,node_name,telegram_bot_token,telegram_chat_id,telegram_enabled,
        gdrive_folder_id,thingspeak_channel_id,thingspeak_write_api_key,notes
    
    Args:
        device_id: Unique device identifier (e.g., "Node-1")
        csv_path: Path to CSV credential file
        
    Returns:
        dict: Credential dictionary with all required fields
        
    Raises:
        FileNotFoundError: If CSV file doesn't exist
        DeviceNotFoundError: If device_id not found in CSV
        CredentialMissingError: If required fields are empty
    """
    import csv
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Credential store not found: {csv_path}\n"
            f"Create this file with device credentials.\n"
            f"See credentials_store.csv.example for format."
        )
    
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['device_id'].strip() == device_id:
                    # Determine if Telegram is enabled
                    telegram_enabled_raw = str(row.get('telegram_enabled', 'true')).strip().lower()
                    telegram_enabled = telegram_enabled_raw in ('true', '1', 'yes', 'enabled')
                    
                    # Extract credentials
                    credentials = {
                        'device_id': str(row['device_id']).strip(),
                        'node_name': str(row['node_name']).strip(),
                        'telegram_bot_token': str(row.get('telegram_bot_token', '')).strip(),
                        'telegram_chat_id': str(row.get('telegram_chat_id', '')).strip(),
                        'telegram_enabled': telegram_enabled,
                        'gdrive_folder_id': str(row['gdrive_folder_id']).strip(),
                        'thingspeak_channel_id': str(row.get('thingspeak_channel_id', '')).strip(),
                        'thingspeak_write_api_key': str(row.get('thingspeak_write_api_key', '')).strip(),
                        'notes': str(row.get('notes', '')).strip()
                    }
                    
                    # Validate required fields
                    _validate_credentials(credentials)
                    
                    logger.info(f"✓ Credentials loaded for {device_id} ({credentials['node_name']})")
                    logger.info(f"  Drive Folder ID: {credentials['gdrive_folder_id'][:20]}...")
                    logger.info(f"  Telegram: {'enabled' if telegram_enabled else 'DISABLED'}")
                    
                    if credentials['thingspeak_channel_id']:
                        logger.info(f"  ThingSpeak: Channel {credentials['thingspeak_channel_id']}")
                    else:
                        logger.info(f"  ThingSpeak: not configured")
                    
                    return credentials
        
        # Device not found
        raise DeviceNotFoundError(
            f"Device '{device_id}' not found in {csv_path}.\n"
            f"Add device credentials to CSV file."
        )
    
    except csv.Error as e:
        raise CredentialError(f"Failed to parse CSV {csv_path}: {str(e)}")
    except KeyError as e:
        raise CredentialError(
            f"Missing required column in CSV: {str(e)}\n"
            f"Required columns: device_id, node_name, gdrive_folder_id\n"
            f"Optional columns: telegram_bot_token, telegram_chat_id, telegram_enabled, "
            f"thingspeak_channel_id, thingspeak_write_api_key, notes"
        )


def _validate_credentials(credentials):
    """
    Validate that all required credentials are present and non-empty.
    
    Args:
        credentials: Credential dictionary
        
    Raises:
        CredentialMissingError: If required fields are missing or empty
    """
    # Always required
    required_fields = {
        'gdrive_folder_id': 'Google Drive Folder ID'
    }
    
    # Telegram fields only required if telegram is enabled
    if credentials.get('telegram_enabled', False):
        required_fields['telegram_bot_token'] = 'Telegram Bot Token'
        required_fields['telegram_chat_id'] = 'Telegram Chat ID'
    
    # ThingSpeak: if channel_id is set, api_key is also required
    if _is_valid_value(credentials.get('thingspeak_channel_id', '')):
        required_fields['thingspeak_write_api_key'] = 'ThingSpeak Write API Key'
    
    missing = []
    for field, display_name in required_fields.items():
        value = credentials.get(field, '').strip()
        if not _is_valid_value(value):
            missing.append(display_name)
    
    if missing:
        raise CredentialMissingError(
            f"Required credentials missing for {credentials['device_id']}: "
            f"{', '.join(missing)}\n"
            f"Update credentials_store.csv with valid values."
        )


def _is_valid_value(value):
    """Check if a credential value is valid (not empty, nan, None, or DISABLED)."""
    if not value:
        return False
    return value.lower() not in ('nan', 'none', 'disabled', '')
