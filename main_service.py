#!/usr/bin/env python3
"""
RetroFit Image Capture Service v2.0
Cloud Processing Architecture - Capture and Upload Only

Repository: https://github.com/aditya08deole/Retro-EvaraFlow.git
"""

import os
import sys
import time
import logging
import traceback
import cv2
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from capture import capture_image
from roi_extractor import extract_roi
from cloud_uploader import CloudUploader
from rclone_uploader import RcloneUploader
from credential_manager import load_from_config_wm, CredentialError
import config

# Configure logging with both file and console output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.ERROR_LOG),
        logging.StreamHandler(sys.stdout)
    ]
)

class ImageCaptureService:
    """Main service for image capture and upload - NO edge processing."""
    
    def __init__(self):
        """Initialize service with credentials and uploaders."""
        logging.info("=" * 70)
        logging.info("RetroFit Image Capture Service v2.0 - Starting")
        logging.info("Architecture: Cloud Processing (Capture + Upload Only)")
        logging.info("=" * 70)
        
        # Validate configuration
        try:
            config.validate_config()
            logging.info("✓ Configuration validated")
        except ValueError as e:
            logging.error(f"❌ CONFIG ERROR: {str(e)}")
            sys.exit(1)
        
        # Load device credentials
        try:
            logging.info("Loading device credentials...")
            self.credentials = load_from_config_wm(
                config_file=config.CONFIG_WM_PATH,
                credential_store=config.CREDENTIAL_STORE_PATH
            )
            
            self.device_id = self.credentials['device_id']
            self.node_name = self.credentials['node_name']
            
            logging.info(f"✓ Device ID: {self.device_id}")
            logging.info(f"✓ Node Name: {self.node_name}")
            
        except CredentialError as e:
            logging.error(f"❌ CREDENTIAL ERROR: {str(e)}")
            logging.error("\nSetup Required:")
            logging.error("1. Create config_WM.py: device_id = \"YOUR-DEVICE-ID\"")
            logging.error("2. Ensure credentials_store.csv contains your device_id")
            sys.exit(1)
        except Exception as e:
            logging.error(f"❌ Initialization error: {str(e)}")
            logging.error(traceback.format_exc())
            sys.exit(1)
        
        # Initialize uploaders (always upload to both services)
        try:
            self.telegram = CloudUploader(
                telegram_token=self.credentials['telegram_bot_token'],
                telegram_chat_id=self.credentials['telegram_chat_id'],
                node_name=self.node_name
            )
            logging.info(f"✓ Telegram: Configured (Chat ID: {self.credentials['telegram_chat_id']})")
            
            self.drive = RcloneUploader(
                remote_name=config.RCLONE_REMOTE_NAME,
                timeout=config.UPLOAD_TIMEOUT
            )
            self.gdrive_folder_id = self.credentials.get('gdrive_folder_id')
            logging.info(f"✓ Google Drive: Configured (Folder: {self.gdrive_folder_id})")
            
        except Exception as e:
            logging.error(f"❌ Uploader initialization failed: {str(e)}")
            sys.exit(1)
        
        # Create output directory for captured images
        self.output_dir = Path("capture_output")
        self.output_dir.mkdir(exist_ok=True)
        logging.info(f"✓ Output directory: {self.output_dir.absolute()}")
        
        # Service configuration
        self.capture_interval = config.CAPTURE_INTERVAL_MINUTES * 60  # Convert to seconds
        
        logging.info(f"✓ Capture interval: {config.CAPTURE_INTERVAL_MINUTES} minutes")
        logging.info(f"✓ Camera resolution: {config.CAMERA_RESOLUTION[0]}x{config.CAMERA_RESOLUTION[1]}")
        logging.info(f"✓ JPEG quality: {config.JPEG_QUALITY}")
        logging.info("✓ Service initialized successfully")
        logging.info("=" * 70)
    
    def process_cycle(self) -> bool:
        """Execute one capture-upload cycle. Returns True if successful."""
        cycle_start = time.time()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            logging.info(f"\n{'─' * 70}")
            logging.info(f"CYCLE START: {timestamp}")
            logging.info(f"{'─' * 70}")
            
            # Step 1: Capture image
            logging.info("Step 1/4: Capturing image...")
            image = capture_image()
            
            if image is None:
                logging.error("❌ Image capture failed - skipping cycle")
                return False
            
            logging.info(f"✓ Image captured: {image.shape[1]}x{image.shape[0]} px, size: {image.nbytes / 1024:.1f} KB")
            
            # Step 2: Extract ROI using ArUco markers
            logging.info("Step 2/4: Extracting ROI...")
            roi = extract_roi(image)
            
            if roi is not None:
                upload_image = roi
                roi_status = f"{roi.shape[1]}x{roi.shape[0]} px (ArUco detected)"
                logging.info(f"✓ ROI extracted: {roi_status}")
            else:
                upload_image = image
                roi_status = "Using full image (ArUco not detected)"
                logging.warning(f"⚠️  {roi_status}")
            
            # Step 3: Save image locally
            filename = f"{self.device_id}_{timestamp}.jpg"
            filepath = self.output_dir / filename
            
            cv2.imwrite(
                str(filepath), 
                upload_image, 
                [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY]
            )
            
            file_size = filepath.stat().st_size / 1024  # KB
            logging.info(f"✓ Image saved: {filename} ({file_size:.1f} KB)")
            
            # Step 4: Upload to Google Drive (with retry and verification)
            logging.info("Step 3/4: Uploading to Google Drive...")
            drive_success = self.drive.upload_with_verification(
                str(filepath), 
                self.gdrive_folder_id
            )
            
            if drive_success:
                logging.info("✓ Google Drive upload successful")
            else:
                logging.error("❌ Google Drive upload failed after retries")
            
            # Step 5: Upload to Telegram (with retry)
            logging.info("Step 4/4: Uploading to Telegram...")
            caption = (
                f"🔍 Device: {self.device_id}\n"
                f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📐 Image: {roi_status}\n"
                f"💾 Size: {file_size:.1f} KB"
            )
            
            telegram_success = self.telegram.upload_telegram_with_retry(
                str(filepath), 
                caption
            )
            
            if telegram_success:
                logging.info("✓ Telegram upload successful")
            else:
                logging.error("❌ Telegram upload failed after retries")
            
            # Report cycle results
            cycle_time = time.time() - cycle_start
            
            if drive_success and telegram_success:
                logging.info(f"{'─' * 70}")
                logging.info(f"✅ CYCLE COMPLETE - All uploads successful")
                logging.info(f"⏱️  Duration: {cycle_time:.1f}s")
                logging.info(f"{'─' * 70}\n")
                return True
            else:
                logging.warning(f"{'─' * 70}")
                logging.warning(f"⚠️  CYCLE COMPLETE - Some uploads failed")
                logging.warning(f"   Google Drive: {'✓' if drive_success else '✗'}")
                logging.warning(f"   Telegram: {'✓' if telegram_success else '✗'}")
                logging.warning(f"⏱️  Duration: {cycle_time:.1f}s")
                logging.warning(f"{'─' * 70}\n")
                return False
        
        except Exception as e:
            logging.error(f"❌ CYCLE FAILED: {e}")
            logging.error(traceback.format_exc())
            return False
    
    def run(self):
        """Run service loop with automatic retry."""
        cycle_count = 0
        success_count = 0
        
        logging.info("🚀 Service loop starting...")
        logging.info(f"⏱️  Capture interval: {config.CAPTURE_INTERVAL_MINUTES} minutes\n")
        
        while True:
            try:
                cycle_count += 1
                success_rate = (success_count / max(1, cycle_count - 1)) * 100 if cycle_count > 1 else 0
                
                logging.info(f"\n{'═' * 70}")
                logging.info(f"CYCLE #{cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                if cycle_count > 1:
                    logging.info(f"Success Rate: {success_count}/{cycle_count - 1} ({success_rate:.1f}%)")
                logging.info(f"{'═' * 70}")
                
                success = self.process_cycle()
                if success:
                    success_count += 1
                
                # Clean up old images (keep last 50)
                self._cleanup_old_images(keep_count=50)
                
                # Wait for next cycle
                logging.info(f"⏳ Next cycle in {config.CAPTURE_INTERVAL_MINUTES} minutes...")
                time.sleep(self.capture_interval)
            
            except KeyboardInterrupt:
                logging.info("\n🛑 Service stopped by user")
                break
            except Exception as e:
                logging.error(f"❌ Service error: {e}")
                logging.error(traceback.format_exc())
                logging.info("⏳ Waiting 60 seconds before retry...")
                time.sleep(60)  # Wait 1 minute before retry
    
    def _cleanup_old_images(self, keep_count=50):
        """Remove old images, keeping only the most recent ones."""
        try:
            images = sorted(self.output_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
            
            if len(images) > keep_count:
                for old_image in images[keep_count:]:
                    old_image.unlink()
                    logging.info(f"🗑️  Cleaned up old image: {old_image.name}")
        except Exception as e:
            logging.warning(f"⚠️  Cleanup failed: {e}")

if __name__ == "__main__":
    try:
        service = ImageCaptureService()
        service.run()
    except Exception as e:
        logging.error(f"❌ FATAL ERROR: {e}")
        logging.error(traceback.format_exc())
        sys.exit(1)
