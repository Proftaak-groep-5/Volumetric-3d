"""
Simple camera test script based on original code
Use this to verify your Orbbec Femto Bolt camera works before running the full application
"""
from pyorbbecsdk import *
import numpy as np
import cv2


def get_best_depth_profile(profiles):
    """Select the best available depth profile ss"""
    resolutions = [
        (1024, 1024, OBFormat.Y16, 30),
        (1024, 1024, OBFormat.Y16, 15),
        (640, 400, OBFormat.Y16, 30),
        (640, 400, OBFormat.Y16, 15),
        (512, 512, OBFormat.Y16, 30),
        (512, 512, OBFormat.Y16, 15),
        (1280, 800, OBFormat.Y16, 30),
        (1280, 800, OBFormat.Y16, 15),
    ]
    
    for width, height, fmt, fps in resolutions:
        try:
            profile = profiles.get_video_stream_profile(width, height, fmt, fps)
            print(f" ✓ Found depth profile: {width}x{height} @ {fps}fps")
            return profile
        except:
            continue
    
    raise RuntimeError("No compatible depth profile found!")


def start_depth_pipeline(device):
    """Start pipeline for depth stream only"""
    pipeline = Pipeline(device)
    config = Config()
    
    depth_profiles = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
    print(f"Found {depth_profiles.get_count()} depth profiles")
    
    depth_profile = get_best_depth_profile(depth_profiles)
    config.enable_stream(depth_profile)
    
    print(f"Starting pipeline: {depth_profile.get_width()}x{depth_profile.get_height()} @ {depth_profile.get_fps()}fps")
    pipeline.start(config)
    
    return pipeline, depth_profile


def main():
    print("=" * 60)
    print("Orbbec Femto Bolt - Camera Test")
    print("=" * 60)
    print()
    
    # Initialize context and find device
    ctx = Context()
    device_list = ctx.query_devices()
    
    if device_list.get_count() == 0:
        print("❌ ERROR: No Orbbec camera found!")
        print()
        print("Troubleshooting:")
        print("  1. Check USB connection (must be USB 3.0)")
        print("  2. Install Orbbec SDK drivers")
        print("  3. Try a different USB port")
        print("  4. Check Device Manager (Windows) or lsusb (Linux)")
        return
    
    device = device_list.get_device_by_index(0)
    info = device.get_device_info()
    
    print(f"✓ Camera found!")
    print(f"  Name: {info.get_name()}")
    print(f"  Serial: {info.get_serial_number()}")
    print()
    
    # Start pipeline
    try:
        pipeline, depth_profile = start_depth_pipeline(device)
    except Exception as e:
        print(f"❌ ERROR: Failed to start pipeline: {e}")
        return
    
    print()
    print("✓ Camera started successfully!")
    print()
    print("Controls:")
    print("  ESC - Exit")
    print("  S   - Save screenshot")
    print()
    
    frame_count = 0
    
    try:
        while True:
            frames = pipeline.wait_for_frames(1000)
            depth_frame = frames.get_depth_frame()
            
            if depth_frame is None:
                continue
            
            frame_count += 1
            
            # Convert depth to numpy array
            depth_data = np.frombuffer(
                depth_frame.get_data(), 
                dtype=np.uint16
            ).reshape((depth_frame.get_height(), depth_frame.get_width()))
            
            # Normalize to 0-255 for display
            if np.max(depth_data) > 0:
                depth_display = cv2.convertScaleAbs(depth_data, alpha=255.0/np.max(depth_data))
            else:
                depth_display = np.zeros_like(depth_data, dtype=np.uint8)
            
            # Add frame counter
            cv2.putText(
                depth_display, 
                f"Frame: {frame_count}", 
                (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                1, 
                255, 
                2
            )
            
            cv2.imshow("Orbbec Femto Bolt - Depth Preview (Press ESC to exit)", depth_display)
            
            key = cv2.waitKey(1)
            if key == 27:  # ESC key
                break
            elif key == ord('s') or key == ord('S'):
                # Save screenshot
                filename = f"depth_screenshot_{frame_count}.png"
                cv2.imwrite(filename, depth_display)
                print(f"✓ Screenshot saved: {filename}")
    
    except KeyboardInterrupt:
        print("\n⚠ Interrupted by user")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
        print()
        print("✓ Pipeline stopped, resources cleaned up.")
        print(f"✓ Processed {frame_count} frames")
        print()


if __name__ == "__main__":
    main()

