import requests
import cv2
import os
import time
from datetime import datetime
from io import BytesIO

class CloudUploader:
    def __init__(self, thingspeak_api_key, telegram_bot_token, 
                 telegram_chat_id, gdrive_credentials_path, node_name="WaterMeter"):
        self.thingspeak_api_key = thingspeak_api_key
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.gdrive_credentials_path = gdrive_credentials_path
        self.node_name = node_name
        self.gdrive_service = None
        
        self._init_gdrive()
    
    def _init_gdrive(self):
        if not os.path.exists(self.gdrive_credentials_path):
            return
        
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
            
            credentials = Credentials.from_service_account_file(
                self.gdrive_credentials_path,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )
            self.gdrive_service = build('drive', 'v3', credentials=credentials)
        except Exception:
            self.gdrive_service = None
    
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
    
    def upload_gdrive(self, image, folder_id=None):
        if not self.gdrive_service:
            return False
        
        try:
            from googleapiclient.http import MediaIoBaseUpload
            
            timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            filename = f"{timestamp}.jpg"
            
            _, buffer = cv2.imencode('.jpg', image)
            file_stream = BytesIO(buffer.tobytes())
            
            file_metadata = {'name': filename}
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            media = MediaIoBaseUpload(file_stream, mimetype='image/jpeg', resumable=True)
            
            self.gdrive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            return True
        except Exception:
            return False
