"""
Credential Management System - v2.0 Simplified
Loads device-specific credentials from credentials_store.csv
Supports multi-device fleet deployment with zero hardcoded credentials

v2.0 Changes:
- Removed ThingSpeak, Google Sheets support
- Removed enable flags (always upload to Telegram + Drive)
- Removed ML-related settings (confidence_threshold, max_flow_rate)
- Simplified to essential credentials only
"""

import os
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
        telegram_token = credentials['telegram_bot_token']
    """
    # Step 1: Read device_id from config_WM.py
    if not os.path.exists(config_file):
        raise FileNotFoundError(
            f"{config_file} not found.\n"
            f"Create this file with: device_id = \"YOUR-DEVICE-ID\"\n"
            f"Example: echo 'device_id = \"Node-1\"' > config_WM.py"
        )
    
    config_vars = {}
    try:
        with open(config_file, 'r') as f:
            exec(f.read(), config_vars)
    except Exception as e:
        raise CredentialError(f"Failed to read {config_file}: {str(e)}")
    
    device_id = config_vars.get('device_id')
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
        device_id,node_name,telegram_bot_token,telegram_chat_id,gdrive_folder_id,notes
        Node-1,Node-1,BOT_TOKEN,CHAT_ID,FOLDER_ID,Optional notes
    
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
                    # Extract credentials
                    credentials = {
                        'device_id': str(row['device_id']).strip(),
                        'node_name': str(row['node_name']).strip(),
                        'telegram_bot_token': str(row['telegram_bot_token']).strip(),
                        'telegram_chat_id': str(row['telegram_chat_id']).strip(),
                        'gdrive_folder_id': str(row['gdrive_folder_id']).strip(),
                        'notes': str(row.get('notes', '')).strip()
                    }
                    
                    # Validate required fields
                    _validate_credentials(credentials)
                    
                    logger.info(f"✓ Credentials loaded for {device_id} ({credentials['node_name']})")
                    logger.info(f"  Telegram Chat ID: {credentials['telegram_chat_id']}")
                    logger.info(f"  Drive Folder ID: {credentials['gdrive_folder_id'][:20]}...")
                    
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
            f"Required columns: device_id, node_name, telegram_bot_token, "
            f"telegram_chat_id, gdrive_folder_id"
        )


def _validate_credentials(credentials):
    """
    Validate that all required credentials are present and non-empty.
    
    Args:
        credentials: Credential dictionary
        
    Raises:
        CredentialMissingError: If required fields are missing or empty
    """
    required_fields = {
        'telegram_bot_token': 'Telegram Bot Token',
        'telegram_chat_id': 'Telegram Chat ID',
        'gdrive_folder_id': 'Google Drive Folder ID'
    }
    
    missing = []
    for field, display_name in required_fields.items():
        value = credentials.get(field, '').strip()
        if not value or value == 'nan' or value == 'None':
            missing.append(display_name)
    
    if missing:
        raise CredentialMissingError(
            f"Required credentials missing for {credentials['device_id']}: "
            f"{', '.join(missing)}\n"
            f"Update credentials_store.csv with valid values."
        )
