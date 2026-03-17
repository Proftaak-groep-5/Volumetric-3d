"""
Debug script to test checkerboard detection on saved images
"""
import cv2
import numpy as np
from pathlib import Path
import sys

def test_checkerboard_detection(image_path: str, cols: int, rows: int):
    """Test checkerboard detection on an image"""
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load image {image_path}")
        return
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    checkerboard_size = (cols, rows)
    
    print(f"\nTesting checkerboard detection on {image_path}")
    print(f"Image size: {gray.shape}")
    print(f"Looking for pattern: {cols}x{rows} inner corners")
    print(f"This means {cols+1}x{rows+1} squares\n")
    
    # Try different methods
    methods = [
        ("Standard with flags", lambda: cv2.findChessboardCorners(gray, checkerboard_size, 
            cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK)),
        ("Adaptive threshold", lambda: (
            lambda: cv2.findChessboardCorners(
                cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2),
                checkerboard_size, cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK)
        )()),
        ("No flags", lambda: cv2.findChessboardCorners(gray, checkerboard_size, None)),
    ]
    
    for method_name, method_func in methods:
        try:
            ret, corners = method_func()
            print(f"{method_name}: {'✓ FOUND' if ret else '✗ NOT FOUND'}")
            if ret:
                print(f"  Found {len(corners)} corners")
        except Exception as e:
            print(f"{method_name}: ERROR - {e}")
    
    # Try alternative sizes
    print("\nTrying alternative pattern sizes:")
    for alt_cols in range(max(3, cols-2), cols+3):
        for alt_rows in range(max(3, rows-2), rows+3):
            if alt_cols == cols and alt_rows == rows:
                continue
            alt_size = (alt_cols, alt_rows)
            try:
                ret, _ = cv2.findChessboardCorners(gray, alt_size, None)
                if ret:
                    print(f"  ✓ Found with size {alt_cols}x{alt_rows} (instead of {cols}x{rows})")
            except:
                pass

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python debug_checkerboard.py <image_path> <cols> <rows>")
        print("Example: python debug_checkerboard.py calibration_images/cam0_000.png 9 6")
        sys.exit(1)
    
    image_path = sys.argv[1]
    cols = int(sys.argv[2])
    rows = int(sys.argv[3])
    
    test_checkerboard_detection(image_path, cols, rows)

