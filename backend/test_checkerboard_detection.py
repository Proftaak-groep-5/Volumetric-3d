"""
Test checkerboard detection on a saved image with all possible sizes
"""
import cv2
import sys
from pathlib import Path

def test_all_sizes(image_path: str):
    """Test all common checkerboard sizes on an image"""
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load image {image_path}")
        return
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    print(f"\n{'='*60}")
    print(f"Testing checkerboard detection on: {image_path}")
    print(f"Image size: {gray.shape}")
    print(f"{'='*60}\n")
    
    # Try all common checkerboard sizes
    all_sizes = []
    for cols in range(3, 12):
        for rows in range(3, 9):
            all_sizes.append((cols, rows))
    
    print(f"Testing {len(all_sizes)} pattern sizes...\n")
    
    found_sizes = []
    
    # Try with different preprocessing
    methods = [
        ("Original", gray),
        ("CLAHE", cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(gray)),
        ("Adaptive Threshold", cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)),
    ]
    
    for size in all_sizes:
        for method_name, processed_img in methods:
            try:
                ret, corners = cv2.findChessboardCorners(processed_img, size, None)
                if ret:
                    found_sizes.append((size, method_name, len(corners)))
                    print(f"✓ FOUND: {size[0]}x{size[1]} inner corners using {method_name} ({len(corners)} corners)")
            except:
                pass
    
    if found_sizes:
        print(f"\n{'='*60}")
        print(f"Found {len(found_sizes)} matching pattern(s)!")
        print(f"{'='*60}")
        print("\nMost likely pattern sizes:")
        for size, method, corner_count in found_sizes:
            print(f"  - {size[0]}x{size[1]} ({method}) - {corner_count} corners")
    else:
        print(f"\n{'='*60}")
        print("No checkerboard pattern found with any size!")
        print(f"{'='*60}")
        print("\nPossible issues:")
        print("  1. Image quality too low")
        print("  2. Checkerboard not fully visible")
        print("  3. Poor lighting or contrast")
        print("  4. Blur or motion")
        print("  5. Wrong pattern type (not a standard checkerboard)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_checkerboard_detection.py <image_path>")
        print("Example: python test_checkerboard_detection.py calibration_images/debug/cam0_1234567890.png")
        sys.exit(1)
    
    image_path = sys.argv[1]
    test_all_sizes(image_path)

