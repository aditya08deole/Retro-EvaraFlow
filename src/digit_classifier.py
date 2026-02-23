import cv2
import numpy as np
from skimage.transform import resize
from skimage.feature import hog
import joblib
import gc

class DigitClassifier:
    def __init__(self, model_path='rf_rasp_classifier.sav', 
                 resized_width=45, resized_height=90,
                 confidence_threshold=0.6):
        self.model = joblib.load(model_path)
        self.resized_width = resized_width
        self.resized_height = resized_height
        self.confidence_threshold = confidence_threshold
    
    def extract_hog_features(self, img_roi):
        img = cv2.cvtColor(img_roi, cv2.COLOR_BGR2GRAY)
        img = resize(img, (self.resized_height, self.resized_width))
        
        flower = cv2.morphologyEx(img, cv2.MORPH_CLOSE, 
                                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        flower = cv2.morphologyEx(flower, cv2.MORPH_OPEN,
                                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
        img = cv2.erode(flower, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), 
                       iterations=3)
        
        features = hog(img, orientations=9, pixels_per_cell=(8, 8),
                      cells_per_block=(2, 2))
        
        return features
    
    def classify_digits(self, digit_rois):
        if not digit_rois:
            return None, 0.0
        
        result = ''
        confidences = []
        
        for roi in digit_rois:
            try:
                features = self.extract_hog_features(roi)
                digit = self.model.predict(features.reshape(1, -1))[0]
                
                proba = self.model.predict_proba(features.reshape(1, -1))
                confidence = np.max(proba)
                
                result += str(digit)
                confidences.append(confidence)
                
            except Exception:
                return None, 0.0
        
        if not result:
            return None, 0.0
        
        avg_confidence = np.mean(confidences)
        
        try:
            reading = int(result) / 10.0 if result else 0
        except:
            return None, 0.0
        
        gc.collect()
        
        if avg_confidence < self.confidence_threshold:
            return None, avg_confidence
        
        return reading, avg_confidence
