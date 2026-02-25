#!/usr/bin/env python3
"""
RetroFit Image Capture Service v2.1
Cloud Processing Architecture - Capture, Upload to GDrive, Report to ThingSpeak

Pipeline per cycle:
  1. Capture image (PiCamera + GPIO LED)
  2. Extract ROI via ArUco markers
  3. Save image locally
  4. Upload to Google Drive (rclone)
  5. Report status to ThingSpeak:
       field1=1  →  ArUco ROI extracted, upload success
       field1=0  →  No ArUco detected, full image uploaded
       field1=2  →  Error (capture fail, upload fail, any error)

Repository: https://github.com/aditya08deole/Retro-EvaraFlow.git
"""

import os
import sys
import json
import time
import signal
import shutil
import logging
import traceback
import cv2
from datetime import datetime
from pathlib import Path
from collections import deque

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from capture import capture_image, cleanup_gpio
from roi_extractor import extract_roi
from rclone_uploader import RcloneUploader
from thingspeak_reporter import ThingSpeakReporter
from credential_manager import load_from_config_wm, CredentialError
import config

# Configure logging with both file and console output
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.ERROR_LOG),
        logging.StreamHandler(sys.stdout)
    ]
)

# Minimum free disk space in MB before skipping capture
MIN_FREE_DISK_MB = 50

# Maximum backlog size (failed uploads to retry)
MAX_BACKLOG_SIZE = 20

# Health watchdog file path
HEALTH_FILE = "health.json"


class ImageCaptureService:
    """Main service: capture image → upload to GDrive → report status to ThingSpeak."""
    
    def __init__(self):
        """Initialize service with credentials, GDrive uploader, and ThingSpeak reporter."""
        logging.info("=" * 70)
        logging.info("RetroFit Image Capture Service v2.1 - Starting")
        logging.info("Pipeline: Capture → GDrive Upload → ThingSpeak Status")
        logging.info("=" * 70)
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        
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
        
        # Initialize Google Drive uploader
        try:
            self.drive = RcloneUploader(
                remote_name=config.RCLONE_REMOTE_NAME,
                timeout=config.UPLOAD_TIMEOUT
            )
            self.gdrive_folder_id = self.credentials.get('gdrive_folder_id')
            logging.info(f"✓ Google Drive: Configured (Folder: {self.gdrive_folder_id})")
            
        except Exception as e:
            logging.error(f"❌ GDrive uploader initialization failed: {str(e)}")
            sys.exit(1)
        
        # Initialize ThingSpeak reporter
        try:
            ts_channel = self.credentials.get('thingspeak_channel_id', '')
            ts_api_key = self.credentials.get('thingspeak_write_api_key', '')
            
            if ts_channel and ts_api_key and ts_channel.lower() not in ('disabled', 'nan', 'none'):
                self.thingspeak = ThingSpeakReporter(
                    channel_id=ts_channel,
                    write_api_key=ts_api_key
                )
                logging.info(f"✓ ThingSpeak: Channel {ts_channel} configured")
            else:
                self.thingspeak = None
                logging.warning("⚠️  ThingSpeak: Not configured (no channel_id/api_key)")
            
        except Exception as e:
            logging.error(f"⚠️  ThingSpeak initialization failed: {str(e)}")
            self.thingspeak = None
        
        # Telegram status (disabled for now)
        if self.credentials.get('telegram_enabled', False):
            logging.info("✓ Telegram: Enabled (but not initialized in this version)")
        else:
            logging.info("ℹ️  Telegram: Disabled in credentials")
        
        # Create output directory for captured images
        self.output_dir = Path("capture_output")
        self.output_dir.mkdir(exist_ok=True)
        logging.info(f"✓ Output directory: {self.output_dir.absolute()}")
        
        # Upload backlog queue (for retrying failed GDrive uploads)
        self.upload_backlog = deque(maxlen=MAX_BACKLOG_SIZE)
        
        # Service configuration
        self.capture_interval = config.CAPTURE_INTERVAL_MINUTES * 60  # Convert to seconds
        
        logging.info(f"✓ Capture interval: {config.CAPTURE_INTERVAL_MINUTES} minutes")
        logging.info(f"✓ Camera resolution: {config.CAMERA_RESOLUTION[0]}x{config.CAMERA_RESOLUTION[1]}")
        logging.info(f"✓ JPEG quality: {config.JPEG_QUALITY}")
        logging.info(f"✓ Disk space check: {MIN_FREE_DISK_MB}MB minimum")
        logging.info(f"✓ Upload backlog: up to {MAX_BACKLOG_SIZE} items")
        logging.info("✓ Service initialized successfully")
        logging.info("=" * 70)
    
    def _handle_shutdown(self, signum, frame):
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        sig_name = signal.Signals(signum).name
        logging.info(f"\n🛑 Received {sig_name} — shutting down gracefully...")
        cleanup_gpio()
        self._write_health("stopped", f"Shutdown via {sig_name}")
        sys.exit(0)
    
    def _check_disk_space(self) -> bool:
        """Check if there's enough free disk space for capture."""
        try:
            usage = shutil.disk_usage('/')
            free_mb = usage.free / (1024 * 1024)
            
            if free_mb < MIN_FREE_DISK_MB:
                logging.error(
                    f"❌ Disk space critically low: {free_mb:.1f}MB free "
                    f"(minimum: {MIN_FREE_DISK_MB}MB) — skipping capture"
                )
                return False
            
            if free_mb < MIN_FREE_DISK_MB * 3:
                logging.warning(
                    f"⚠️  Disk space low: {free_mb:.1f}MB free — "
                    f"consider increasing cleanup frequency"
                )
            
            return True
        except Exception as e:
            logging.warning(f"⚠️  Disk space check failed: {e}")
            return True  # Continue if check fails
    
    def _write_health(self, status: str, message: str = ""):
        """Write health watchdog file for fleet monitoring."""
        try:
            health = {
                "device_id": getattr(self, 'device_id', 'unknown'),
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "message": message,
                "uptime_cycles": getattr(self, '_cycle_count', 0),
                "success_count": getattr(self, '_success_count', 0),
                "backlog_size": len(self.upload_backlog) if hasattr(self, 'upload_backlog') else 0
            }
            with open(HEALTH_FILE, 'w') as f:
                json.dump(health, f, indent=2)
        except Exception:
            pass  # Health file is best-effort
    
    def _send_thingspeak_status(self, status_code, file_size_kb=None, cycle_duration=None):
        """Send status code to ThingSpeak (if configured)."""
        if self.thingspeak is None:
            logging.debug("ThingSpeak not configured — skipping status report")
            return
        
        try:
            self.thingspeak.send_status(status_code, file_size_kb, cycle_duration)
        except Exception as e:
            logging.error(f"⚠️  ThingSpeak status report failed: {e}")
    
    def _retry_backlog(self):
        """Retry uploading files from the backlog queue."""
        if not self.upload_backlog:
            return
        
        logging.info(f"📋 Retrying {len(self.upload_backlog)} backlogged uploads...")
        
        retried = []
        while self.upload_backlog:
            item = self.upload_backlog.popleft()
            filepath = item['filepath']
            
            if not os.path.exists(filepath):
                logging.warning(f"⚠️  Backlog file missing: {filepath}")
                continue
            
            drive_ok = self.drive.upload_with_verification(filepath, self.gdrive_folder_id)
            
            if drive_ok:
                logging.info(f"✓ Backlog upload succeeded: {os.path.basename(filepath)}")
            else:
                retried.append(item)
        
        # Re-queue items that still failed
        for item in retried:
            item['retries'] = item.get('retries', 0) + 1
            if item['retries'] <= 2:
                self.upload_backlog.append(item)
            else:
                logging.error(f"❌ Permanently failed upload dropped: {item['filepath']}")
    
    def process_cycle(self) -> bool:
        """
        Execute one capture-upload cycle.
        
        Returns True if GDrive upload succeeded.
        
        ThingSpeak status codes:
          1 = ArUco ROI extracted + GDrive upload success
          0 = No ArUco, full image + GDrive upload success
          2 = Any error (capture fail, upload fail, etc.)
        """
        cycle_start = time.time()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        aruco_detected = False
        
        try:
            logging.info(f"\n{'─' * 70}")
            logging.info(f"CYCLE START: {timestamp}")
            logging.info(f"{'─' * 70}")
            
            # Pre-check: Disk space
            if not self._check_disk_space():
                cycle_duration = time.time() - cycle_start
                self._send_thingspeak_status(config.THINGSPEAK_STATUS_ERROR, cycle_duration=cycle_duration)
                return False
            
            # Step 1: Capture image
            logging.info("Step 1/4: Capturing image...")
            image = capture_image()
            
            if image is None:
                logging.error("❌ Image capture failed - skipping cycle")
                cycle_duration = time.time() - cycle_start
                self._send_thingspeak_status(config.THINGSPEAK_STATUS_ERROR, cycle_duration=cycle_duration)
                return False
            
            logging.info(f"✓ Image captured: {image.shape[1]}x{image.shape[0]} px, size: {image.nbytes / 1024:.1f} KB")
            
            # Step 2: Extract ROI using ArUco markers
            logging.info("Step 2/4: Extracting ROI...")
            roi = extract_roi(image)
            
            if roi is not None:
                upload_image = roi
                aruco_detected = True
                roi_status = f"{roi.shape[1]}x{roi.shape[0]} px (ArUco detected)"
                logging.info(f"✓ ROI extracted: {roi_status}")
            else:
                upload_image = image
                aruco_detected = False
                roi_status = "Using full image (ArUco not detected)"
                logging.warning(f"⚠️  {roi_status}")
            
            # Free original image from memory early (important on Zero W)
            del image
            
            # Step 3: Save image locally
            logging.info("Step 3/4: Saving image...")
            filename = f"{self.device_id}_{timestamp}.jpg"
            filepath = self.output_dir / filename
            
            cv2.imwrite(
                str(filepath), 
                upload_image, 
                [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY]
            )
            
            # Free upload image from memory (keep only file on disk)
            del upload_image
            
            file_size = filepath.stat().st_size / 1024  # KB
            logging.info(f"✓ Image saved: {filename} ({file_size:.1f} KB)")
            
            # Step 4: Upload to Google Drive (with retry and verification)
            logging.info("Step 4/4: Uploading to Google Drive...")
            drive_success = self.drive.upload_with_verification(
                str(filepath), 
                self.gdrive_folder_id
            )
            
            cycle_duration = time.time() - cycle_start
            
            if drive_success:
                logging.info("✓ Google Drive upload successful")
                
                # Send ThingSpeak status based on ArUco detection
                if aruco_detected:
                    # Status 1: ArUco ROI cropped + uploaded successfully
                    logging.info("📊 ThingSpeak: Sending status=1 (ArUco ROI success)")
                    self._send_thingspeak_status(
                        config.THINGSPEAK_STATUS_ARUCO_SUCCESS,
                        file_size_kb=round(file_size, 1),
                        cycle_duration=round(cycle_duration, 1)
                    )
                else:
                    # Status 0: No ArUco, full image uploaded
                    logging.info("📊 ThingSpeak: Sending status=0 (no ArUco, full image)")
                    self._send_thingspeak_status(
                        config.THINGSPEAK_STATUS_NO_ARUCO,
                        file_size_kb=round(file_size, 1),
                        cycle_duration=round(cycle_duration, 1)
                    )
                
                logging.info(f"{'─' * 70}")
                logging.info(f"✅ CYCLE COMPLETE - GDrive upload successful")
                logging.info(f"   ArUco: {'✓ detected' if aruco_detected else '✗ not detected'}")
                logging.info(f"⏱️  Duration: {cycle_duration:.1f}s")
                logging.info(f"{'─' * 70}\n")
                return True
            else:
                logging.error("❌ Google Drive upload failed after retries")
                
                # Status 2: Upload error
                logging.info("📊 ThingSpeak: Sending status=2 (upload error)")
                self._send_thingspeak_status(
                    config.THINGSPEAK_STATUS_ERROR,
                    cycle_duration=round(cycle_duration, 1)
                )
                
                # Queue for retry
                self.upload_backlog.append({
                    'filepath': str(filepath),
                    'aruco_detected': aruco_detected,
                    'retries': 0,
                    'timestamp': timestamp
                })
                logging.info(f"📋 Queued for retry ({len(self.upload_backlog)} in backlog)")
                
                logging.warning(f"{'─' * 70}")
                logging.warning(f"⚠️  CYCLE COMPLETE - GDrive upload FAILED")
                logging.warning(f"⏱️  Duration: {cycle_duration:.1f}s")
                logging.warning(f"{'─' * 70}\n")
                return False
        
        except Exception as e:
            logging.error(f"❌ CYCLE FAILED: {e}")
            logging.error(traceback.format_exc())
            
            # Status 2: Error
            cycle_duration = time.time() - cycle_start
            self._send_thingspeak_status(
                config.THINGSPEAK_STATUS_ERROR,
                cycle_duration=round(cycle_duration, 1)
            )
            return False
    
    def run(self):
        """Run service loop with automatic retry."""
        self._cycle_count = 0
        self._success_count = 0
        
        logging.info("🚀 Service loop starting...")
        logging.info(f"⏱️  Capture interval: {config.CAPTURE_INTERVAL_MINUTES} minutes\n")
        
        self._write_health("running", "Service loop started")
        
        while True:
            try:
                self._cycle_count += 1
                success_rate = (self._success_count / max(1, self._cycle_count - 1)) * 100 if self._cycle_count > 1 else 0
                
                logging.info(f"\n{'═' * 70}")
                logging.info(f"CYCLE #{self._cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                if self._cycle_count > 1:
                    logging.info(f"Success Rate: {self._success_count}/{self._cycle_count - 1} ({success_rate:.1f}%)")
                if self.upload_backlog:
                    logging.info(f"Upload Backlog: {len(self.upload_backlog)} pending")
                logging.info(f"{'═' * 70}")
                
                # Retry any backlogged uploads first
                self._retry_backlog()
                
                # Run capture cycle
                success = self.process_cycle()
                if success:
                    self._success_count += 1
                
                # Clean up old images (keep last 50)
                self._cleanup_old_images(keep_count=50)
                
                # Update health watchdog
                self._write_health(
                    "running",
                    f"Cycle #{self._cycle_count}: {'success' if success else 'failed'}"
                )
                
                # Wait for next cycle
                logging.info(f"⏳ Next cycle in {config.CAPTURE_INTERVAL_MINUTES} minutes...")
                time.sleep(self.capture_interval)
            
            except KeyboardInterrupt:
                logging.info("\n🛑 Service stopped by user")
                cleanup_gpio()
                self._write_health("stopped", "User interrupt")
                break
            except Exception as e:
                logging.error(f"❌ Service error: {e}")
                logging.error(traceback.format_exc())
                self._write_health("error", str(e))
                logging.info("⏳ Waiting 60 seconds before retry...")
                time.sleep(60)  # Wait 1 minute before retry
    
    def _cleanup_old_images(self, keep_count=50):
        """Remove old images, keeping only the most recent ones."""
        try:
            images = sorted(self.output_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
            
            # Don't delete images that are in the backlog
            backlog_files = {item['filepath'] for item in self.upload_backlog}
            
            if len(images) > keep_count:
                for old_image in images[keep_count:]:
                    if str(old_image) not in backlog_files:
                        old_image.unlink()
                        logging.debug(f"🗑️  Cleaned up old image: {old_image.name}")
        except Exception as e:
            logging.warning(f"⚠️  Cleanup failed: {e}")

if __name__ == "__main__":
    try:
        service = ImageCaptureService()
        service.run()
    except Exception as e:
        logging.error(f"❌ FATAL ERROR: {e}")
        logging.error(traceback.format_exc())
        cleanup_gpio()
        sys.exit(1)
