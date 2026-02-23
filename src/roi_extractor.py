import cv2
import numpy as np

class ROIExtractor:
    def __init__(self, width=650, height=215, zoom=60):
        self.width = width
        self.height = height
        self.zoom = zoom
        
        self.pts_dst = np.float32([
            [-zoom, -zoom],
            [width + zoom, -zoom],
            [width + zoom, height + zoom],
            [-zoom, height + zoom]
        ])
        
        self.marker_map = {"TL": 1, "TR": 3, "BR": 0, "BL": 2}
        self.last_valid_matrix = None
    
    def detect_aruco_roi(self, image):
        try:
            dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            parameters = cv2.aruco.DetectorParameters()
            parameters.adaptiveThreshWinSizeMin = 3
            parameters.adaptiveThreshWinSizeMax = 23
            parameters.adaptiveThreshWinSizeStep = 10
            
            detector = cv2.aruco.ArucoDetector(dictionary, parameters)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detector.detectMarkers(gray)
            
            if ids is None or len(ids) < 4:
                return None, None
            
            found_markers = {}
            for marker_corner, marker_id in zip(corners, ids.flatten()):
                c = marker_corner[0]
                center_x = int(c[:, 0].mean())
                center_y = int(c[:, 1].mean())
                found_markers[marker_id] = [center_x, center_y]
            
            req_ids = [self.marker_map["TL"], self.marker_map["TR"], 
                       self.marker_map["BR"], self.marker_map["BL"]]
            
            if all(mid in found_markers for mid in req_ids):
                pts_source = np.array([
                    found_markers[self.marker_map["TL"]],
                    found_markers[self.marker_map["TR"]],
                    found_markers[self.marker_map["BR"]],
                    found_markers[self.marker_map["BL"]]
                ], dtype="float32")
                
                matrix = cv2.getPerspectiveTransform(pts_source, self.pts_dst)
                self.last_valid_matrix = matrix
                return pts_source, matrix
            
        except Exception:
            pass
        
        return None, None
    
    def extract_roi(self, image, matrix=None, fallback_points=None):
        if matrix is None:
            _, matrix = self.detect_aruco_roi(image)
        
        if matrix is None and self.last_valid_matrix is not None:
            matrix = self.last_valid_matrix
        
        if matrix is None and fallback_points is not None:
            try:
                pts_source = np.float32(fallback_points)
                pts_dst_simple = np.float32([[0, 0], [self.width, 0], 
                                             [self.width, self.height], [0, self.height]])
                matrix = cv2.getPerspectiveTransform(pts_source, pts_dst_simple)
            except:
                return None
        
        if matrix is None:
            return None
        
        warped = cv2.warpPerspective(image, matrix, (self.width, self.height))
        return warped
