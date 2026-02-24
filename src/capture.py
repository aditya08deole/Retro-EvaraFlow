import time
import numpy as np
from picamera import PiCamera
import RPi.GPIO as GPIO
import cv2
from io import BytesIO

class CameraCapture:
    def __init__(self, relay_pin=23, resolution=(1640, 1232), warmup_delay=3, focus_delay=2):
        self.relay_pin = relay_pin
        self.resolution = resolution
        self.warmup_delay = warmup_delay
        self.focus_delay = focus_delay
        
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.relay_pin, GPIO.OUT)
        GPIO.output(self.relay_pin, GPIO.LOW)
    
    def capture_image(self):
        """
        Capture image using BytesIO stream (compatible with all PiCamera versions)
        More reliable than direct numpy array on Pi Zero W and PiCamera v2.1
        """
        image = None
        camera = None
        
        try:
            # Power on relay
            GPIO.output(self.relay_pin, GPIO.HIGH)
            time.sleep(self.warmup_delay)
            
            # Initialize camera
            camera = PiCamera()
            camera.resolution = self.resolution
            camera.start_preview()
            time.sleep(self.focus_delay)
            
            # Capture to BytesIO stream (more compatible than numpy array)
            stream = BytesIO()
            camera.capture(stream, format='jpeg', quality=95)
            
            # Convert stream to numpy array
            stream.seek(0)
            file_bytes = np.asarray(bytearray(stream.read()), dtype=np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            
            if image is None:
                raise Exception("Failed to decode image from stream")
            
        except Exception as e:
            raise Exception(f"Capture failed: {str(e)}")
        
        finally:
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
