"""
Camera Capture Module - PiCamera with GPIO LED Control
Standalone function for image capture with strict timing
"""

import time
import logging
import numpy as np
from picamera import PiCamera
import RPi.GPIO as GPIO
import cv2
from io import BytesIO


# GPIO Configuration
LED_PIN = 23
GPIO_INITIALIZED = False


def _init_gpio():
    """Initialize GPIO if not already initialized."""
    global GPIO_INITIALIZED
    if not GPIO_INITIALIZED:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(LED_PIN, GPIO.OUT)
        GPIO.output(LED_PIN, GPIO.LOW)
        GPIO_INITIALIZED = True


def capture_image():
    """
    Capture high-resolution image with strict timing sequence.
    
    Timing Sequence:
    1. LED ON
    2. Wait 0.5s (warmup)
    3. Camera ON
    4. Wait 3s (focus adjustment)
    5. Capture image
    6. Close camera
    7. Wait 3s (post-capture)
    8. LED OFF
    
    Returns:
        numpy.ndarray: Captured image in BGR format, or None if capture failed
    
    Compatible with all PiCamera versions (v1.x, v2.x)
    Uses BytesIO stream capture for universal compatibility
    """
    # Import config here to avoid circular imports
    try:
        import config
        RESOLUTION = config.CAMERA_RESOLUTION
        WARMUP_DELAY = config.WARMUP_DELAY
        FOCUS_DELAY = config.FOCUS_DELAY
        POST_CAPTURE_DELAY = config.POST_CAPTURE_DELAY
        JPEG_QUALITY = config.JPEG_QUALITY
        CAMERA_ROTATION = config.CAMERA_ROTATION
    except Exception:
        # Fallback defaults
        RESOLUTION = (1640, 1232)
        CAMERA_ROTATION = 180
        WARMUP_DELAY = 0.5
        FOCUS_DELAY = 3.0
        POST_CAPTURE_DELAY = 3.0
        JPEG_QUALITY = 95
        WARMUP_DELAY = 0.5
        FOCUS_DELAY = 3.0
        POST_CAPTURE_DELAY = 3.0
        JPEG_QUALITY = 95
    
    _init_gpio()
    
    image = None
    camera = None
    
    try:
        # STEP 1: LED ON
        GPIO.output(LED_PIN, GPIO.HIGH)
        
        # STEP 2: Wait for warmup
        time.sleep(WARMUP_DELAY)
        
        # STEP 3: Camera ON
        camera = PiCamera()
        camera.resolution = RESOLUTION
        camera.rotation = CAMERA_ROTATION
        
        # STEP 4: Wait for focus adjustment
        time.sleep(FOCUS_DELAY)
        
        # STEP 5: Capture image to BytesIO stream
        stream = BytesIO()
        camera.capture(stream, format='jpeg', quality=JPEG_QUALITY)
        
        # STEP 6: Close camera immediately after capture
        camera.close()
        camera = None
        
        # Convert stream to numpy array
        stream.seek(0)
        image_data = stream.read()
        
        # Validate image size (should be > 100KB for 1640x1232)
        if len(image_data) < 100000:
            raise ValueError(f"Image too small: {len(image_data)} bytes - possible capture failure")
        
        file_bytes = np.frombuffer(image_data, dtype=np.uint8)
        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if image is None:
            raise Exception("Failed to decode image from stream")
        
        # Validate decoded image
        if image.size == 0:
            raise Exception("Decoded image is empty")
        
        # STEP 7: Keep LED ON for post-capture delay
        time.sleep(POST_CAPTURE_DELAY)
        
        logging.debug(f"✓ Image captured: {image.shape[1]}x{image.shape[0]} px, {len(image_data)} bytes")
        
    except Exception as e:
        logging.error(f"❌ Capture failed: {str(e)}")
        image = None
    
    finally:
        # STEP 8: LED OFF and cleanup
        if camera:
            try:
                camera.close()
            except Exception:
                pass
        GPIO.output(LED_PIN, GPIO.LOW)
    
    return image


def cleanup_gpio():
    """Clean up GPIO resources (call on program exit)."""
    global GPIO_INITIALIZED
    try:
        GPIO.cleanup()
        GPIO_INITIALIZED = False
        logging.info("✓ GPIO cleaned up")
    except Exception:
        pass
