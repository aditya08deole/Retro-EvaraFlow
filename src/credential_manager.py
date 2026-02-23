"""
Dynamic Credential Management System
Loads device-specific credentials from credentials_store.xlsx based on device_id
Supports multi-device fleet deployment with zero hardcoded credentials
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


class CredentialManager:
    """
    Manages dynamic credential loading from Excel-based credential store.
    
    Each device reads its unique device_id and extracts only its credentials
    from the central credentials_store.xlsx file.
    """
    
    def __init__(self, device_id, credential_store_path='credentials_store.xlsx'):
        """
        Initialize credential manager
        
        Args:
            device_id: Unique device identifier (e.g., "PH-03")
            credential_store_path: Path to Excel credential file
        """
        self.device_id = device_id
        self.credential_store_path = credential_store_path
        self.credentials = None
        
    def load_credentials(self):
        """
        Load credentials for this device from Excel store
        
        Returns:
            dict: Credential dictionary with all device settings
            
        Raises:
            DeviceNotFoundError: If device_id not found in store
            CredentialMissingError: If required fields are empty
            FileNotFoundError: If credential store doesn't exist
        """
        # Try CSV fallback if Excel not available
        if not os.path.exists(self.credential_store_path):
            csv_path = self.credential_store_path.replace('.xlsx', '.csv')
            if os.path.exists(csv_path):
                logger.warning(f"Excel not found, using CSV: {csv_path}")
                return self._load_from_csv(csv_path)
            raise FileNotFoundError(f"Credential store not found: {self.credential_store_path}")
        
        try:
            import pandas as pd
        except ImportError:
            logger.warning("pandas not available, falling back to CSV")
            csv_path = self.credential_store_path.replace('.xlsx', '.csv')
            return self._load_from_csv(csv_path)
        
        try:
            # Load Excel file
            df = pd.read_excel(self.credential_store_path, sheet_name=0)
            
            # Find device row
            device_row = df[df['device_id'] == self.device_id]
            
            if device_row.empty:
                available_devices = df['device_id'].tolist()
                raise DeviceNotFoundError(
                    f"Device '{self.device_id}' not found in credential store. "
                    f"Available devices: {available_devices}"
                )
            
            # Extract credentials
            row = device_row.iloc[0]
            
            self.credentials = {
                'device_id': str(row['device_id']),
                'node_name': str(row['node_name']),
                'thingspeak_api_key': str(row['thingspeak_api_key']),
                'telegram_bot_token': str(row['telegram_bot_token']),
                'telegram_chat_id': str(row['telegram_chat_id']),
                'gdrive_folder_id': str(row.get('gdrive_folder_id', '')),
                'gsheets_deployment_id': str(row.get('gsheets_deployment_id', '')),
                'enable_thingspeak': bool(int(row['enable_thingspeak'])),
                'enable_telegram': bool(int(row['enable_telegram'])),
                'enable_gdrive': bool(int(row['enable_gdrive'])),
                'enable_gsheets': bool(int(row.get('enable_gsheets', 0))),
                'capture_interval': int(row.get('capture_interval', 300)),
                'confidence_threshold': float(row.get('confidence_threshold', 0.6)),
                'max_flow_rate': float(row.get('max_flow_rate', 100.0)),
                'active': bool(int(row.get('active', 1)))
            }
            
            # Validate required credentials
            self._validate_credentials()
            
            logger.info(f"✓ Loaded credentials for {self.device_id} ({self.credentials['node_name']})")
            logger.info(f"  ThingSpeak: {'ON' if self.credentials['enable_thingspeak'] else 'OFF'}")
            logger.info(f"  Telegram: {'ON' if self.credentials['enable_telegram'] else 'OFF'}")
            logger.info(f"  Google Drive: {'ON' if self.credentials['enable_gdrive'] else 'OFF'}")
            
            return self.credentials
            
        except Exception as e:
            if isinstance(e, CredentialError):
                raise
            raise CredentialError(f"Failed to load credentials: {str(e)}")
    
    def _load_from_csv(self, csv_path):
        """Fallback: Load credentials from CSV file"""
        import csv
        
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV credential store not found: {csv_path}")
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['device_id'] == self.device_id:
                    self.credentials = {
                        'device_id': str(row['device_id']),
                        'node_name': str(row['node_name']),
                        'thingspeak_api_key': str(row['thingspeak_api_key']),
                        'telegram_bot_token': str(row['telegram_bot_token']),
                        'telegram_chat_id': str(row['telegram_chat_id']),
                        'gdrive_folder_id': str(row.get('gdrive_folder_id', '')),
                        'gsheets_deployment_id': str(row.get('gsheets_deployment_id', '')),
                        'enable_thingspeak': bool(int(row['enable_thingspeak'])),
                        'enable_telegram': bool(int(row['enable_telegram'])),
                        'enable_gdrive': bool(int(row['enable_gdrive'])),
                        'enable_gsheets': bool(int(row.get('enable_gsheets', 0))),
                        'capture_interval': int(row.get('capture_interval', 300)),
                        'confidence_threshold': float(row.get('confidence_threshold', 0.6)),
                        'max_flow_rate': float(row.get('max_flow_rate', 100.0)),
                        'active': bool(int(row.get('active', 1)))
                    }
                    
                    self._validate_credentials()
                    logger.info(f"✓ Loaded credentials from CSV for {self.device_id}")
                    return self.credentials
        
        raise DeviceNotFoundError(f"Device '{self.device_id}' not found in CSV store")
    
    def _validate_credentials(self):
        """Validate that required credentials are present"""
        required_fields = []
        
        if self.credentials['enable_thingspeak']:
            if not self.credentials['thingspeak_api_key'] or self.credentials['thingspeak_api_key'] == 'nan':
                required_fields.append('thingspeak_api_key')
        
        if self.credentials['enable_telegram']:
            if not self.credentials['telegram_bot_token'] or self.credentials['telegram_bot_token'] == 'nan':
                required_fields.append('telegram_bot_token')
            if not self.credentials['telegram_chat_id'] or self.credentials['telegram_chat_id'] == 'nan':
                required_fields.append('telegram_chat_id')
        
        if required_fields:
            raise CredentialMissingError(
                f"Required credentials missing for {self.device_id}: {', '.join(required_fields)}"
            )
    
    # Convenience accessor methods
    def get_thingspeak_key(self):
        """Get ThingSpeak API key"""
        return self.credentials['thingspeak_api_key'] if self.credentials else None
    
    def get_telegram_token(self):
        """Get Telegram bot token"""
        return self.credentials['telegram_bot_token'] if self.credentials else None
    
    def get_telegram_chat_id(self):
        """Get Telegram chat ID"""
        return self.credentials['telegram_chat_id'] if self.credentials else None
    
    def get_gdrive_folder_id(self):
        """Get Google Drive folder ID"""
        return self.credentials['gdrive_folder_id'] if self.credentials else None
    
    def is_thingspeak_enabled(self):
        """Check if ThingSpeak upload is enabled"""
        return self.credentials['enable_thingspeak'] if self.credentials else False
    
    def is_telegram_enabled(self):
        """Check if Telegram upload is enabled"""
        return self.credentials['enable_telegram'] if self.credentials else False
    
    def is_gdrive_enabled(self):
        """Check if Google Drive upload is enabled"""
        return self.credentials['enable_gdrive'] if self.credentials else False
    
    def is_device_active(self):
        """Check if device is marked as active"""
        return self.credentials['active'] if self.credentials else False
    
    def get_capture_interval(self):
        """Get capture interval in seconds"""
        return self.credentials['capture_interval'] if self.credentials else 300
    
    def get_confidence_threshold(self):
        """Get digit classification confidence threshold"""
        return self.credentials['confidence_threshold'] if self.credentials else 0.6
    
    def mask_sensitive_data(self, credential_dict):
        """Return credential dict with sensitive values masked for logging"""
        masked = credential_dict.copy()
        
        if 'thingspeak_api_key' in masked and masked['thingspeak_api_key']:
            masked['thingspeak_api_key'] = masked['thingspeak_api_key'][:8] + '***'
        
        if 'telegram_bot_token' in masked and masked['telegram_bot_token']:
            masked['telegram_bot_token'] = masked['telegram_bot_token'][:15] + '***'
        
        return masked


def quick_load(device_id, credential_store='credentials_store.xlsx'):
    """
    Quick helper to load credentials in one call
    
    Usage:
        credentials = quick_load("PH-03")
    """
    manager = CredentialManager(device_id, credential_store)
    return manager.load_credentials()


# Backward compatibility: Support config_WM.py style loading
def load_from_config_wm(config_file='config_WM.py', credential_store='credentials_store.xlsx'):
    """
    Load credentials using device_id from config_WM.py file
    
    This maintains compatibility with existing deployment workflow.
    
    Usage:
        credentials = load_from_config_wm()
    """
    if not os.path.exists(config_file):
        raise FileNotFoundError(
            f"{config_file} not found. Create this file with: device_id = \"YOUR-DEVICE-ID\""
        )
    
    # Read device_id from config_WM.py
    config_vars = {}
    with open(config_file, 'r') as f:
        exec(f.read(), config_vars)
    
    device_id = config_vars.get('device_id')
    if not device_id:
        raise ValueError(f"device_id not defined in {config_file}")
    
    logger.info(f"Loading credentials for device: {device_id}")
    return quick_load(device_id, credential_store)
