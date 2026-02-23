import cv2
import numpy as np
from imutils.contours import sort_contours

class Preprocessor:
    def __init__(self, min_contour_area=1500, crop_width=540):
        self.min_contour_area = min_contour_area
        self.crop_width = crop_width
    
    def process(self, img_roi):
        if img_roi is None:
            return []
        
        img_meter = img_roi[:, :self.crop_width]
        
        img_gray = cv2.cvtColor(img_meter, cv2.COLOR_BGR2GRAY)
        img_gray = cv2.medianBlur(img_gray, 15)
        
        thresh = cv2.adaptiveThreshold(
            img_gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            33, 5
        )
        
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.dilate(thresh, kernel, iterations=5)
        thresh = cv2.erode(thresh, kernel, iterations=2)
        
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return []
        
        contours, _ = sort_contours(contours)
        contours = [c for c in contours if cv2.contourArea(c) >= self.min_contour_area]
        
        digit_rois = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            roi = img_meter[y:y+h, x:x+w]
            digit_rois.append(roi)
        
        return digit_rois
