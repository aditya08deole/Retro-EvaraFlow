"""
Cloud Uploader - Telegram Bot Upload with Retry Logic
Supports image uploads with automatic retry on failure
"""

import requests
import time
import logging
from pathlib import Path

class CloudUploader:
    """Upload images to Telegram with retry logic and verification."""
    
    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 5, 10]  # seconds - exponential backoff
    TIMEOUT = 30  # seconds
    
    def __init__(self, telegram_token, telegram_chat_id, node_name="WaterMeter"):
        """
        Initialize uploader with Telegram credentials.
        
        Args:
            telegram_token: Telegram bot token
            telegram_chat_id: Telegram chat ID to send messages
            node_name: Device/node name for captions
        """
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.node_name = node_name
        
        if not telegram_token or not telegram_chat_id:
            raise ValueError("Telegram token and chat ID are required")
    
    def upload_telegram_with_retry(self, image_path: str, caption: str) -> bool:
        """
        Upload image to Telegram with automatic retry on failure.
        
        Args:
            image_path: Path to image file to upload
            caption: Caption text to include with image
            
        Returns:
            True if upload successful, False otherwise
        """
        if not Path(image_path).exists():
            logging.error(f"❌ Image file not found: {image_path}")
            return False
        
        for attempt in range(self.MAX_RETRIES):
            try:
                success = self._upload_telegram_single(image_path, caption)
                
                if success:
                    logging.info(f"✓ Telegram upload successful (attempt {attempt + 1}/{self.MAX_RETRIES})")
                    return True
                
                # Log failure and retry
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logging.warning(
                        f"⚠️  Telegram upload failed (attempt {attempt + 1}/{self.MAX_RETRIES}), "
                        f"retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    logging.error(f"❌ Telegram upload failed (attempt {attempt + 1}/{self.MAX_RETRIES})")
            
            except Exception as e:
                logging.error(f"❌ Telegram upload error (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}")
                
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logging.info(f"   Retrying in {delay}s...")
                    time.sleep(delay)
        
        logging.error(f"❌ Telegram upload failed after {self.MAX_RETRIES} attempts")
        return False
    
    def _upload_telegram_single(self, image_path: str, caption: str) -> bool:
        """
        Single attempt to upload image to Telegram.
        
        Args:
            image_path: Path to image file
            caption: Caption text
            
        Returns:
            True if successful, False otherwise
        """
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendPhoto"
        
        try:
            with open(image_path, 'rb') as image_file:
                files = {'photo': image_file}
                data = {
                    'chat_id': self.telegram_chat_id, 
                    'caption': caption[:1024]  # Telegram caption limit
                }
                
                response = requests.post(
                    url, 
                    files=files, 
                    data=data, 
                    timeout=self.TIMEOUT
                )
                
                if response.status_code == 200:
                    return True
                else:
                    logging.warning(f"⚠️  Telegram API returned status {response.status_code}")
                    try:
                        error_msg = response.json().get('description', 'Unknown error')
                        logging.warning(f"   Error: {error_msg}")
                    except Exception:
                        pass
                    return False
        
        except requests.Timeout:
            logging.error(f"❌ Telegram upload timeout after {self.TIMEOUT}s")
            return False
        except requests.ConnectionError:
            logging.error("❌ Telegram upload connection error (network issue)")
            return False
        except Exception as e:
            logging.error(f"❌ Telegram upload exception: {type(e).__name__}: {e}")
            return False
