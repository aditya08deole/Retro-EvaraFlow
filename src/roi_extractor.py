"""
ROI Extractor - ArUco Marker-based Region of Interest Extraction
Extracts meter display region using ArUco markers only (no fallback)
"""

import cv2
import numpy as np
import logging


def extract_roi(image):
    """
    Extract ROI from image using ArUco markers.
    
    This function looks for 4 ArUco markers (IDs: 0, 1, 2, 3) that define
    the corners of the meter display region. If all 4 markers are found,
    it extracts and perspective-corrects the region with 10% padding.
    
    Args:
        image: Input image (numpy array in BGR format)
        
    Returns:
        numpy.ndarray: Extracted and perspective-corrected ROI, or None if markers not found
    
    Marker Layout:
        ID 1 (TL) -------- ID 3 (TR)
           |                  |
           |   METER DISPLAY  |
           |                  |
        ID 2 (BL) -------- ID 0 (BR)
    """
    if image is None or image.size == 0:
        logging.error("❌ Invalid input image for ROI extraction")
        return None
    
    try:
        # Convert to grayscale for marker detection
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Initialize ArUco detector (compatible with OpenCV 4.5.x AND 4.7+)
        # OpenCV 4.7+ uses ArucoDetector class; 4.5.x uses module-level functions
        try:
            # Try new API first (OpenCV 4.7+)
            aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            parameters = cv2.aruco.DetectorParameters()
            parameters.adaptiveThreshWinSizeMin = 3
            parameters.adaptiveThreshWinSizeMax = 23
            parameters.adaptiveThreshWinSizeStep = 10
            detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
            corners, ids, _ = detector.detectMarkers(gray)
        except AttributeError:
            # Fall back to legacy API (OpenCV 4.5.x and earlier)
            aruco_dict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)
            parameters = cv2.aruco.DetectorParameters_create()
            parameters.adaptiveThreshWinSizeMin = 3
            parameters.adaptiveThreshWinSizeMax = 23
            parameters.adaptiveThreshWinSizeStep = 10
            corners, ids, _ = cv2.aruco.detectMarkers(gray, aruco_dict, parameters=parameters)
        
        if ids is None or len(ids) < 4:
            logging.warning(f"⚠️  ArUco markers not detected (found {len(ids) if ids is not None else 0}/4)")
            return None
        
        # Extract marker centers
        found_markers = {}
        for marker_corner, marker_id in zip(corners, ids.flatten()):
            c = marker_corner[0]
            center_x = int(c[:, 0].mean())
            center_y = int(c[:, 1].mean())
            found_markers[marker_id] = [center_x, center_y]
        
        # Check if all required markers are present
        required_ids = [0, 1, 2, 3]  # BR, TL, BL, TR
        marker_map = {"TL": 1, "TR": 3, "BR": 0, "BL": 2}
        
        if not all(mid in found_markers for mid in required_ids):
            missing = [mid for mid in required_ids if mid not in found_markers]
            logging.warning(f"⚠️  Missing ArUco markers: {missing}")
            return None
        
        # Define source points (detected marker positions)
        pts_source = np.array([
            found_markers[marker_map["TL"]],  # Top-left
            found_markers[marker_map["TR"]],  # Top-right
            found_markers[marker_map["BR"]],  # Bottom-right
            found_markers[marker_map["BL"]]   # Bottom-left
        ], dtype="float32")
        
        # Calculate bounding rectangle
        x_coords = [pt[0] for pt in pts_source]
        y_coords = [pt[1] for pt in pts_source]
        
        roi_width = int(max(x_coords) - min(x_coords))
        roi_height = int(max(y_coords) - min(y_coords))
        
        # Add padding around ROI (configurable via config.ROI_PADDING_PERCENT)
        try:
            import config
            padding_percent = config.ROI_PADDING_PERCENT / 100.0
        except Exception:
            padding_percent = 0.1  # Default 10%
        padding_w = int(roi_width * padding_percent)
        padding_h = int(roi_height * padding_percent)
        
        # Define destination points with padding
        pts_dst = np.float32([
            [-padding_w, -padding_h],
            [roi_width + padding_w, -padding_h],
            [roi_width + padding_w, roi_height + padding_h],
            [-padding_w, roi_height + padding_h]
        ])
        
        # Calculate perspective transformation matrix
        matrix = cv2.getPerspectiveTransform(pts_source, pts_dst)
        
        # Apply perspective warp to extract ROI
        output_width = roi_width + 2 * padding_w
        output_height = roi_height + 2 * padding_h
        
        roi = cv2.warpPerspective(image, matrix, (output_width, output_height))
        
        logging.debug(f"✓ ROI extracted: {output_width}x{output_height} px from ArUco markers")
        
        return roi
    
    except Exception as e:
        logging.error(f"❌ ROI extraction failed: {e}")
        return None
