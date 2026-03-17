"""
Stereo Calibration Tool for Orbbec Femto Bolt Cameras
This script helps you calibrate two cameras using a checkerboard pattern
"""
import numpy as np
import cv2
import argparse
from pathlib import Path
from camera_manager import CameraManager
from calibration import CalibrationManager

def capture_calibration_images(camera_manager: CameraManager, 
                               output_dir: Path,
                               num_images: int = 20,
                               checkerboard_size: tuple = (9, 6)):
    """
    Capture synchronized images from both cameras for calibration
    
    Press SPACE to capture an image, ESC to finish
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print("Stereo Calibration Image Capture")
    print(f"{'='*60}")
    print(f"\nInstructions:")
    print(f"  1. Place a {checkerboard_size[0]}x{checkerboard_size[1]} checkerboard in view of both cameras")
    print(f"  2. Move the checkerboard to different positions and orientations")
    print(f"  3. Press SPACE to capture a synchronized image pair")
    print(f"  4. Press ESC when you have captured {num_images} images")
    print(f"\nImages will be saved to: {output_dir}")
    print(f"\nPress any key to start...")
    input()
    
    captured = 0
    camera_ids = list(camera_manager.cameras.keys())
    
    if len(camera_ids) < 2:
        print("ERROR: Need at least 2 cameras for stereo calibration!")
        return False
    
    cam1_id, cam2_id = camera_ids[0], camera_ids[1]
    
    print(f"\nUsing cameras: {cam1_id} and {cam2_id}")
    print(f"Capturing images... (Press SPACE to capture, ESC to finish)\n")
    
    while captured < num_images:
        # Get frames from both cameras
        frames = camera_manager.get_all_latest_frames()
        
        if cam1_id not in frames or cam2_id not in frames:
            continue
        
        frame1 = frames[cam1_id]
        frame2 = frames[cam2_id]
        
        if frame1.color_data is None or frame2.color_data is None:
            continue
        
        # Convert to BGR for OpenCV display
        img1 = cv2.cvtColor(frame1.color_data, cv2.COLOR_RGB2BGR)
        img2 = cv2.cvtColor(frame2.color_data, cv2.COLOR_RGB2BGR)
        
        # Try to find checkerboard
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        
        ret1, corners1 = cv2.findChessboardCorners(gray1, checkerboard_size, None)
        ret2, corners2 = cv2.findChessboardCorners(gray2, checkerboard_size, None)
        
        # Draw checkerboard if found
        if ret1:
            cv2.drawChessboardCorners(img1, checkerboard_size, corners1, ret1)
        if ret2:
            cv2.drawChessboardCorners(img2, checkerboard_size, corners2, ret2)
        
        # Add text
        status = "✓ Both found" if (ret1 and ret2) else "✗ Not found"
        cv2.putText(img1, f"Camera 1 - {status} - {captured}/{num_images}", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if ret1 else (0, 0, 255), 2)
        cv2.putText(img2, f"Camera 2 - {status} - {captured}/{num_images}", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if ret2 else (0, 0, 255), 2)
        
        # Combine images side by side
        combined = np.hstack([img1, img2])
        cv2.imshow("Stereo Calibration - Press SPACE to capture, ESC to finish", combined)
        
        key = cv2.waitKey(1) & 0xFF
        
        if key == 27:  # ESC
            break
        elif key == 32:  # SPACE
            if ret1 and ret2:
                # Save images
                img1_path = output_dir / f"{cam1_id}_{captured:03d}.png"
                img2_path = output_dir / f"{cam2_id}_{captured:03d}.png"
                cv2.imwrite(str(img1_path), img1)
                cv2.imwrite(str(img2_path), img2)
                captured += 1
                print(f"Captured image pair {captured}/{num_images}")
            else:
                print("Checkerboard not found in both images! Try again.")
    
    cv2.destroyAllWindows()
    print(f"\nCaptured {captured} image pairs")
    return captured >= 10  # Need at least 10 for calibration


def calibrate_from_images(calibration_manager: CalibrationManager,
                          image_dir: Path,
                          camera_id_1: str,
                          camera_id_2: str,
                          checkerboard_size: tuple = (9, 6),
                          square_size: float = 0.025):
    """Perform stereo calibration from saved images"""
    print(f"\n{'='*60}")
    print("Performing Stereo Calibration")
    print(f"{'='*60}\n")
    
    # Load images
    images_1 = []
    images_2 = []
    
    img_files_1 = sorted(image_dir.glob(f"{camera_id_1}_*.png"))
    img_files_2 = sorted(image_dir.glob(f"{camera_id_2}_*.png"))
    
    if len(img_files_1) != len(img_files_2):
        print(f"ERROR: Mismatched number of images ({len(img_files_1)} vs {len(img_files_2)})")
        return False
    
    print(f"Loading {len(img_files_1)} image pairs...")
    
    for img1_path, img2_path in zip(img_files_1, img_files_2):
        img1 = cv2.imread(str(img1_path))
        img2 = cv2.imread(str(img2_path))
        
        if img1 is None or img2 is None:
            continue
        
        images_1.append(img1)
        images_2.append(img2)
    
    if len(images_1) < 10:
        print(f"ERROR: Need at least 10 image pairs, found {len(images_1)}")
        return False
    
    print(f"Loaded {len(images_1)} image pairs")
    
    # Perform calibration
    try:
        stereo = calibration_manager.calibrate_stereo_from_checkerboard(
            camera_id_1, camera_id_2,
            images_1, images_2,
            checkerboard_size, square_size
        )
        
        # Save calibration
        calibration_manager.save_stereo_calibration(camera_id_1, camera_id_2)
        print(f"\n✓ Stereo calibration completed and saved!")
        print(f"  Translation: [{stereo.T[0,0]:.4f}, {stereo.T[1,0]:.4f}, {stereo.T[2,0]:.4f}]")
        
        return True
    except Exception as e:
        print(f"ERROR: Calibration failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Stereo calibration for Orbbec Femto Bolt cameras")
    parser.add_argument("--capture", action="store_true", help="Capture calibration images")
    parser.add_argument("--calibrate", action="store_true", help="Perform calibration from images")
    parser.add_argument("--images-dir", type=str, default="./calibration_images", 
                       help="Directory for calibration images")
    parser.add_argument("--checkerboard-cols", type=int, default=9, 
                       help="Number of inner corners (columns)")
    parser.add_argument("--checkerboard-rows", type=int, default=6, 
                       help="Number of inner corners (rows)")
    parser.add_argument("--square-size", type=float, default=0.025, 
                       help="Size of checkerboard square in meters")
    parser.add_argument("--num-images", type=int, default=20, 
                       help="Number of images to capture")
    
    args = parser.parse_args()
    
    # Initialize camera manager
    camera_manager = CameraManager()
    camera_count = camera_manager.discover_cameras()
    
    if camera_count < 2:
        print(f"ERROR: Need at least 2 cameras, found {camera_count}")
        return
    
    camera_manager.start_all()
    
    calibration_manager = camera_manager.get_calibration_manager()
    image_dir = Path(args.images_dir)
    checkerboard_size = (args.checkerboard_cols, args.checkerboard_rows)
    
    try:
        if args.capture:
            success = capture_calibration_images(
                camera_manager, image_dir, args.num_images, checkerboard_size
            )
            if not success:
                print("Failed to capture enough images")
                return
        
        if args.calibrate or args.capture:
            camera_ids = list(camera_manager.cameras.keys())
            calibrate_from_images(
                calibration_manager,
                image_dir,
                camera_ids[0],
                camera_ids[1],
                checkerboard_size,
                args.square_size
            )
    
    finally:
        camera_manager.stop_all()
        print("\nCameras stopped")


if __name__ == "__main__":
    main()

