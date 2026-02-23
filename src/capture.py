import time
import numpy as np
from picamera import PiCamera
import RPi.GPIO as GPIO
import cv2

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
        image = None
        camera = None
        
        try:
            GPIO.output(self.relay_pin, GPIO.HIGH)
            time.sleep(self.warmup_delay)
            
            camera = PiCamera()
            camera.resolution = self.resolution
            camera.start_preview()
            time.sleep(self.focus_delay)
            
            output = np.empty((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)
            camera.capture(output, 'rgb')
            image = cv2.cvtColor(output, cv2.COLOR_RGB2BGR)
            
        except Exception as e:
            raise Exception(f"Capture failed: {str(e)}")
        
        finally:
            if camera:
                camera.close()
            GPIO.output(self.relay_pin, GPIO.LOW)
            
        return image
    
    def cleanup(self):
        try:
            GPIO.cleanup()
        except:
            pass
