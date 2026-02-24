import time
import numpy as np
from picamera import PiCamera
import RPi.GPIO as GPIO
import cv2
from io import BytesIO

class CameraCapture:
    def __init__(self, relay_pin=23, resolution=(1640, 1232), warmup_delay=0.5, focus_delay=3, post_capture_delay=3):
        """
        Initialize camera capture with LED control
        
        Args:
            relay_pin: GPIO pin for LED/relay control
            resolution: Camera resolution (width, height)
            warmup_delay: Initial delay after LED ON (seconds)
            focus_delay: Focus adjustment time after camera starts (seconds)
            post_capture_delay: Keep LED ON after capture (seconds)
        """
        self.relay_pin = relay_pin
        self.resolution = resolution
        self.warmup_delay = warmup_delay
        self.focus_delay = focus_delay
        self.post_capture_delay = post_capture_delay
        
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.relay_pin, GPIO.OUT)
        GPIO.output(self.relay_pin, GPIO.LOW)
    
    def capture_image(self):
        """
        Capture image with strict timing sequence:
        1. LED ON
        2. Camera ON
        3. Wait 3 seconds (focus adjustment)
        4. Capture image
        5. Keep LED ON for 3 seconds after capture
        6. LED OFF
        
        Compatible with all PiCamera versions (v1.x, v2.x)
        """
        image = None
        camera = None
        
        try:
            # STEP 1: LED ON
            GPIO.output(self.relay_pin, GPIO.HIGH)
            time.sleep(self.warmup_delay)  # Brief warmup
            
            # STEP 2: Camera ON
            camera = PiCamera()
            camera.resolution = self.resolution
            camera.start_preview()
            
            # STEP 3: Wait for focus adjustment (3 seconds)
            time.sleep(self.focus_delay)
            
            # STEP 4: Capture image to BytesIO stream
            stream = BytesIO()
            camera.capture(stream, format='jpeg', quality=95)
            
            # Close camera immediately after capture
            camera.close()
            camera = None
            
            # Convert stream to numpy array
            stream.seek(0)
            file_bytes = np.asarray(bytearray(stream.read()), dtype=np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            
            if image is None:
                raise Exception("Failed to decode image from stream")
            
            # STEP 5: Keep LED ON for 3 seconds after successful capture
            time.sleep(self.post_capture_delay)
            
        except Exception as e:
            raise Exception(f"Capture failed: {str(e)}")
        
        finally:
            # STEP 6: LED OFF and cleanup
            if camera:
                try:
                    camera.close()
                except:
                    pass
            GPIO.output(self.relay_pin, GPIO.LOW)
            
        return image
    
    def cleanup(self):
        try:
            GPIO.cleanup()
        except:
            pass
