#!/usr/bin/env python3
"""
Retro-EvaraFlow - Smart Water Meter Retrofit Service
Multi-device fleet deployment with dynamic credential management

Repository: https://github.com/aditya08deole/Retro-EvaraFlow.git
"""

import time
import gc
import os
import sys
from datetime import datetime, timedelta

from src.capture import CameraCapture
from src.roi_extractor import ROIExtractor
from src.preprocess import Preprocessor
from src.digit_classifier import DigitClassifier
from src.flow_validator import FlowValidator
from src.cloud_uploader import CloudUploader
from src.state_manager import StateManager
from src.credential_manager import load_from_config_wm, CredentialError

import config

class MeterReaderService:
    def __init__(self):
        # ========== DYNAMIC CREDENTIAL LOADING ==========
        # Load device-specific credentials from credentials_store.xlsx
        # based on device_id from config_WM.py
        try:
            print("Loading device credentials...")
            self.credentials = load_from_config_wm(
                config_file=config.CONFIG_WM_PATH,
                credential_store=config.CREDENTIAL_STORE_PATH
            )
            
            # Extract device identity and settings
            self.device_id = self.credentials['device_id']
            self.node_name = self.credentials['node_name']
            
            # Use per-device settings with system defaults as fallback
            confidence_threshold = self.credentials.get('confidence_threshold', config.CONFIDENCE_THRESHOLD)
            max_flow_rate = self.credentials.get('max_flow_rate', config.MAX_FLOW_RATE)
            capture_interval = self.credentials.get('capture_interval', config.CAPTURE_INTERVAL)
            
            print(f"✓ Credentials loaded for: {self.device_id} ({self.node_name})")
            print(f"  ThingSpeak: {'ENABLED' if self.credentials['enable_thingspeak'] else 'DISABLED'}")
            print(f"  Telegram: {'ENABLED' if self.credentials['enable_telegram'] else 'DISABLED'}")
            print(f"  Google Drive: {'ENABLED' if self.credentials['enable_gdrive'] else 'DISABLED'}")
            
        except CredentialError as e:
            print(f"❌ CREDENTIAL ERROR: {str(e)}")
            print("\nSetup Required:")
            print("1. Create config_WM.py: device_id = \"YOUR-DEVICE-ID\"")
            print("2. Ensure credentials_store.xlsx contains your device_id")
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"❌ FILE NOT FOUND: {str(e)}")
            sys.exit(1)
        
        # ========== INITIALIZE MODULES ==========
        self.capture = CameraCapture(relay_pin=config.RELAY_PIN,
                                     resolution=config.CAMERA_RESOLUTION,
                                     warmup_delay=config.WARMUP_DELAY,
                                     focus_delay=config.FOCUS_DELAY)
        
        self.roi_extractor = ROIExtractor(width=config.ROI_WIDTH,
                                          height=config.ROI_HEIGHT,
                                          zoom=config.ROI_ZOOM)
        
        self.preprocessor = Preprocessor(min_contour_area=config.MIN_CONTOUR_AREA,
                                         crop_width=config.CROP_WIDTH)
        
        self.classifier = DigitClassifier(model_path=config.MODEL_PATH,
                                          confidence_threshold=confidence_threshold)
        
        self.validator = FlowValidator(max_flow_rate=max_flow_rate,
                                       min_time_diff=config.MIN_TIME_DIFF)
        
        # Cloud uploader now uses dynamic credentials
        self.uploader = CloudUploader(
            thingspeak_api_key=self.credentials['thingspeak_api_key'],
            telegram_bot_token=self.credentials['telegram_bot_token'],
            telegram_chat_id=self.credentials['telegram_chat_id'],
            gdrive_credentials_path=config.GDRIVE_CREDENTIALS_PATH,
            node_name=self.node_name
        )
        
        self.state_manager = StateManager(state_file=config.STATE_FILE)
        
        self.interval = capture_interval
        self.max_retries = config.MAX_RETRIES
        
        # Store credential flags for conditional uploads
        self.enable_thingspeak = self.credentials['enable_thingspeak']
        self.enable_telegram = self.credentials['enable_telegram']
        self.enable_gdrive = self.credentials['enable_gdrive']
        self.gdrive_folder_id = self.credentials.get('gdrive_folder_id')
    
    def process_cycle(self):
        start_time = time.time()
        current_timestamp = int(time.time())
        
        image = None
        reading = None
        confidence = 0.0
        
        for attempt in range(self.max_retries + 1):
            try:
                image = self.capture.capture_image()
                
                if image is None:
                    continue
                
                roi = self.roi_extractor.extract_roi(image, 
                                                     fallback_points=config.FALLBACK_ROI_POINTS)
                
                if roi is None:
                    continue
                
                digit_rois = self.preprocessor.process(roi)
                
                if not digit_rois:
                    continue
                
                reading, confidence = self.classifier.classify_digits(digit_rois)
                
                if reading is not None:
                    break
                
            except Exception as e:
                self._log_error(f"Cycle attempt {attempt + 1} failed: {str(e)}")
                time.sleep(1)
        
        if reading is None:
            self._log_error("All attempts failed, skipping cycle")
            gc.collect()
            return
        
        last_reading = self.state_manager.get_last_reading()
        last_timestamp = self.state_manager.get_last_timestamp()
        
        validated_reading, flow_rate = self.validator.validate_and_correct(
            reading, last_reading, last_timestamp, current_timestamp
        )
        
        if validated_reading is None:
            self._log_error("Validation failed, skipping upload")
            gc.collect()
            return
        
        self.state_manager.save_state(
            reading=validated_reading,
            timestamp=current_timestamp,
            flow_rate=flow_rate
        )
        
        # Dynamic cloud uploads based on credential flags
        if self.enable_thingspeak:
            self.uploader.send_thingspeak(validated_reading, flow_rate)
        
        if self.enable_telegram:
            self.uploader.send_telegram(image, validated_reading, flow_rate)
        
        if self.enable_gdrive:
            self.uploader.upload_gdrive(image, folder_id=self.gdrive_folder_id)
        
        elapsed = time.time() - start_time
        
        gc.collect()
    
    def run(self):
        self._log_error(f"Service started - Device: {self.device_id} ({self.node_name})")
        
        try:
            while True:
                next_cycle = datetime.now() + timedelta(seconds=self.interval)
                
                self.process_cycle()
                
                now = datetime.now()
                if now < next_cycle:
                    sleep_duration = (next_cycle - now).total_seconds()
                    time.sleep(sleep_duration)
                
        except KeyboardInterrupt:
            self._log_error("Service stopped by user")
            self.capture.cleanup()
            sys.exit(0)
        except Exception as e:
            self._log_error(f"Fatal error: {str(e)}")
            self.capture.cleanup()
            sys.exit(1)
    
    def _log_error(self, message):
        try:
            with open(config.ERROR_LOG, 'a') as f:
                f.write(f"{datetime.now()} - {message}\n")
        except:
            pass

if __name__ == '__main__':
    service = MeterReaderService()
    service.run()
