import requests
import cv2
import os
import time
from datetime import datetime

class CloudUploader:
    def __init__(self, thingspeak_api_key, telegram_bot_token, 
                 telegram_chat_id, node_name="WaterMeter"):
        self.thingspeak_api_key = thingspeak_api_key
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.node_name = node_name
    
    def get_epoch_time(self):
        return int(time.time())
    
    def send_thingspeak(self, reading, flow_rate):
        url = "https://api.thingspeak.com/update"
        params = {
            "api_key": self.thingspeak_api_key,
            "field1": reading,
            "field2": flow_rate
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            return response.status_code == 200
        except Exception:
            return False
    
    def send_telegram(self, image, reading, flow_rate):
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendPhoto"
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        caption = f"{self.node_name}\nTime: {timestamp}\nReading: {reading} L\nFlow Rate: {flow_rate} L/min"
        
        try:
            _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            files = {'photo': ('meter.jpg', buffer.tobytes(), 'image/jpeg')}
            data = {'chat_id': self.telegram_chat_id, 'caption': caption}
            
            response = requests.post(url, files=files, data=data, timeout=15)
            return response.status_code == 200
        except Exception:
            return False
    
    # Google Drive upload now handled by RcloneUploader in main_service.py
    # This method kept for reference but not used
