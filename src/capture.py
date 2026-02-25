"""
Camera Capture Module - PiCamera/PiCamera2 with GPIO LED Control
Standalone function for image capture with strict timing

Supports both:
  - picamera  (legacy camera stack, RPi OS Buster/Bullseye-legacy)
  - picamera2 (libcamera stack, RPi OS Bullseye/Bookworm)
"""

import time
import logging
import numpy as np
import cv2
from io import BytesIO

# Auto-detect camera library
USE_PICAMERA2 = False
try:
    from picamera2 import Picamera2
    USE_PICAMERA2 = True
    logging.info("✓ Using picamera2 (libcamera stack)")
except ImportError:
    try:
        from picamera import PiCamera
        logging.info("✓ Using picamera (legacy stack)")
    except ImportError:
        logging.error("❌ No camera library found! Install picamera or picamera2.")

try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False
    logging.warning("⚠️  RPi.GPIO not available (not running on Raspberry Pi?)")


# GPIO Configuration (loaded from config module)
GPIO_INITIALIZED = False
_LED_PIN = None  # Lazy-loaded from config


def _get_led_pin():
    """Get LED pin from config, with fallback."""
    global _LED_PIN
    if _LED_PIN is None:
        try:
            import config
            _LED_PIN = config.LED_PIN
        except Exception:
            _LED_PIN = 23  # Default fallback
    return _LED_PIN


def _init_gpio():
    """Initialize GPIO if not already initialized."""
    global GPIO_INITIALIZED
    if not HAS_GPIO:
        return
    if not GPIO_INITIALIZED:
        led_pin = _get_led_pin()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(led_pin, GPIO.OUT)
        GPIO.output(led_pin, GPIO.LOW)
        GPIO_INITIALIZED = True


def _led_on():
    """Turn LED/relay ON."""
    if HAS_GPIO:
        GPIO.output(_get_led_pin(), GPIO.HIGH)


def _led_off():
    """Turn LED/relay OFF."""
    if HAS_GPIO:
        GPIO.output(_get_led_pin(), GPIO.LOW)


def _capture_with_picamera2(resolution, rotation, jpeg_quality):
    """Capture image using picamera2 (libcamera stack)."""
    picam2 = Picamera2()
    try:
        capture_config = picam2.create_still_configuration(
            main={"size": resolution, "format": "RGB888"}
        )
        picam2.configure(capture_config)

        # Apply rotation via transform if needed
        if rotation in [90, 180, 270]:
            from libcamera import Transform
            if rotation == 180:
                picam2.set_controls({"Transform": Transform(hflip=True, vflip=True)})

        picam2.start()
        time.sleep(2)  # Warmup for auto-exposure/white balance

        # Capture as numpy array (RGB format)
        image_rgb = picam2.capture_array()
        picam2.stop()

        # Convert RGB to BGR for OpenCV compatibility
        image = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
        return image
    finally:
        picam2.close()


def _capture_with_picamera(resolution, rotation, jpeg_quality, focus_delay):
    """Capture image using picamera (legacy stack)."""
    camera = PiCamera()
    try:
        camera.resolution = resolution
        camera.rotation = rotation

        # Wait for focus/auto-exposure adjustment
        time.sleep(focus_delay)

        # Capture to BytesIO stream
        stream = BytesIO()
        camera.capture(stream, format='jpeg', quality=jpeg_quality)
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

        return image
    finally:
        if camera:
            try:
                camera.close()
            except Exception:
                pass


def capture_image(max_retries=2):
    """
    Capture high-resolution image with strict timing sequence.
    
    Timing Sequence:
    1. LED ON
    2. Wait warmup delay
    3. Camera ON + capture
    4. Close camera
    5. Wait post-capture delay
    6. LED OFF
    
    Args:
        max_retries: Number of capture attempts (default 2)
    
    Returns:
        numpy.ndarray: Captured image in BGR format, or None if capture failed
    
    Compatible with both picamera (legacy) and picamera2 (libcamera)
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
        # Fallback defaults if config module unavailable
        RESOLUTION = (1640, 1232)
        CAMERA_ROTATION = 180
        WARMUP_DELAY = 0.5
        FOCUS_DELAY = 3.0
        POST_CAPTURE_DELAY = 3.0
        JPEG_QUALITY = 85
    
    _init_gpio()
    
    for attempt in range(max_retries):
        image = None
        
        try:
            # STEP 1: LED ON
            _led_on()
            
            # STEP 2: Wait for warmup
            time.sleep(WARMUP_DELAY)
            
            # STEP 3+4: Capture image (auto-selects camera library)
            if USE_PICAMERA2:
                image = _capture_with_picamera2(RESOLUTION, CAMERA_ROTATION, JPEG_QUALITY)
            else:
                image = _capture_with_picamera(RESOLUTION, CAMERA_ROTATION, JPEG_QUALITY, FOCUS_DELAY)
            
            # Validate decoded image
            if image is None or image.size == 0:
                raise Exception("Captured image is None or empty")
            
            # STEP 5: Keep LED ON for post-capture delay
            time.sleep(POST_CAPTURE_DELAY)
            
            logging.debug(f"✓ Image captured: {image.shape[1]}x{image.shape[0]} px")
            
            # STEP 6: LED OFF
            _led_off()
            
            return image
        
        except Exception as e:
            _led_off()
            
            if attempt < max_retries - 1:
                logging.warning(f"⚠️  Capture attempt {attempt + 1}/{max_retries} failed: {str(e)}, retrying...")
                time.sleep(2)  # Brief pause before retry
            else:
                logging.error(f"❌ Capture failed after {max_retries} attempts: {str(e)}")
    
    return None


def cleanup_gpio():
    """Clean up GPIO resources (call on program exit)."""
    global GPIO_INITIALIZED
    if not HAS_GPIO:
        return
    try:
        GPIO.cleanup()
        GPIO_INITIALIZED = False
        logging.info("✓ GPIO cleaned up")
    except Exception:
        pass
