"""
ROI Extractor - ArUco Marker-based Region of Interest Extraction
Extracts meter display region using ArUco markers only (no fallback)

Pinned to OpenCV 4.5.x Legacy ArUco API for ARMv6 compatibility.
"""

import cv2
import numpy as np
import logging
import config

# Resolve ArUco module once at import time (not every call)
_aruco = getattr(cv2, 'aruco', None)
if _aruco is None:
    try:
        import cv2.aruco as _aruco
    except ImportError:
        _aruco = None

if _aruco is None:
    logging.critical("ArUco module not found. OpenCV-contrib is not installed correctly.")


def extract_roi(image):
    """
    Extract ROI from image using ArUco markers.

    Looks for 4 ArUco markers (IDs 0-3) defining the meter display corners.
    If all 4 are found, extracts and perspective-corrects the region.

    Args:
        image: Input image (numpy array in BGR format)

    Returns:
        numpy.ndarray: Extracted ROI, or None if markers not found

    Marker Layout:
        ID 1 (TL) -------- ID 3 (TR)
           |                  |
           |   METER DISPLAY  |
           |                  |
        ID 2 (BL) -------- ID 0 (BR)
    """
    if image is None or image.size == 0:
        logging.error("Invalid input image for ROI extraction")
        return None

    if _aruco is None:
        logging.error("ArUco module unavailable — cannot extract ROI")
        return None

    try:
        # Convert to grayscale for marker detection
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Legacy ArUco API (OpenCV 4.5.x) — deterministic, no fallback needed
        aruco_dict = _aruco.Dictionary_get(_aruco.DICT_4X4_50)
        parameters = _aruco.DetectorParameters_create()
        corners, ids, _ = _aruco.detectMarkers(gray, aruco_dict, parameters=parameters)

        # Free grayscale immediately
        del gray

        if ids is None or len(ids) < 4:
            detected = 0 if ids is None else len(ids)
            logging.warning(f"ArUco detection: found {detected}/4 markers")
            return None

        # Build marker center map
        found = {}
        for corner, mid in zip(corners, ids.flatten()):
            c = corner[0]
            found[mid] = [int(c[:, 0].mean()), int(c[:, 1].mean())]

        # Verify all 4 required markers exist
        required = [0, 1, 2, 3]
        if not all(m in found for m in required):
            missing = [m for m in required if m not in found]
            logging.warning(f"Missing ArUco markers: {missing}")
            return None

        # Map: TL=1, TR=3, BR=0, BL=2
        pts_source = np.float32([
            found[1],  # Top-left
            found[3],  # Top-right
            found[0],  # Bottom-right
            found[2],  # Bottom-left
        ])

        # Calculate ROI dimensions
        x_coords = pts_source[:, 0]
        y_coords = pts_source[:, 1]
        roi_w = int(x_coords.max() - x_coords.min())
        roi_h = int(y_coords.max() - y_coords.min())

        # Padding
        pad_frac = config.ROI_PADDING_PERCENT / 100.0
        pad_w = int(roi_w * pad_frac)
        pad_h = int(roi_h * pad_frac)

        # Destination points with padding
        pts_dst = np.float32([
            [-pad_w, -pad_h],
            [roi_w + pad_w, -pad_h],
            [roi_w + pad_w, roi_h + pad_h],
            [-pad_w, roi_h + pad_h],
        ])

        # Perspective transform
        out_w = roi_w + 2 * pad_w
        out_h = roi_h + 2 * pad_h
        matrix = cv2.getPerspectiveTransform(pts_source, pts_dst)
        roi = cv2.warpPerspective(image, matrix, (out_w, out_h))

        logging.debug(f"ROI extracted: {out_w}x{out_h} px from ArUco markers")
        return roi

    except Exception as e:
        logging.error(f"ROI extraction failed: {e}")
        return None
