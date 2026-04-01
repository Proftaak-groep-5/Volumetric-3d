"""
Standalone camera calibration using an ArUco cube.

Example:
  python calibration.py --images "data/*.png" --output calib.json \
    --dict DICT_4X4_50 --marker-length 0.04 --cube-length 0.04
"""
import argparse
import json
from pathlib import Path
from calibration_core import LiveCaptureConfig, calibrate_from_images, calibrate_from_live


def main() -> None:
    parser = argparse.ArgumentParser(description="ArUco cube camera calibration")
    parser.add_argument(
        "--images",
        default=None,
        help="Glob for calibration images (required unless --live is set)",
    )
    parser.add_argument(
        "--output", required=True, help="Path to output calibration JSON"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live Orbbec camera capture instead of image files",
    )
    parser.add_argument(
        "--dict",
        default="DICT_4X4_50",
        help="ArUco dictionary (e.g., DICT_4X4_50)",
    )
    parser.add_argument(
        "--marker-length",
        type=float,
        required=True,
        help="Marker side length in meters",
    )
    parser.add_argument(
        "--cube-length",
        type=float,
        default=None,
        help="Cube edge length in meters (defaults to marker length)",
    )
    parser.add_argument(
        "--ids",
        default="0,1,2,3,4,5",
        help="Comma-separated 6 marker IDs used on the cube",
    )
    parser.add_argument(
        "--min-images",
        type=int,
        default=10,
        help="Minimum images per camera for live capture",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=60.0,
        help="Max live capture duration in seconds",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Seconds between live captures",
    )
    parser.add_argument(
        "--color-res",
        default="1920x1080",
        help="Color resolution, e.g. 1920x1080",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Color frames per second",
    )
    parser.add_argument(
        "--save-frames",
        default=None,
        help="Optional directory to save live grayscale frames",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Disable the live preview windows",
    )
    parser.add_argument(
        "--keep-preview-open",
        action="store_true",
        help="Keep preview windows open after capture completes",
    )
    args = parser.parse_args()

    cube_length = args.cube_length if args.cube_length is not None else args.marker_length
    ids = [int(v.strip()) for v in args.ids.split(",") if v.strip()]

    if not args.live and not args.images:
        parser.error("--images is required unless --live is set")

    if args.live:
        color_res_parts = args.color_res.lower().split("x")
        if len(color_res_parts) != 2:
            raise ValueError("--color-res must be like 1920x1080")
        color_res = (int(color_res_parts[0]), int(color_res_parts[1]))
        capture_config = LiveCaptureConfig(
            min_images=max(1, args.min_images),
            max_seconds=args.max_seconds,
            interval_seconds=args.interval,
            depth_res=(0, 0),
            color_res=color_res,
            fps=args.fps,
            save_frames_dir=Path(args.save_frames) if args.save_frames else None,
            preview=not args.no_preview,
            keep_preview_open=args.keep_preview_open,
        )
        results = calibrate_from_live(
            dictionary_name=args.dict,
            marker_length=args.marker_length,
            cube_length=cube_length,
            ids=ids,
            capture_config=capture_config,
        )

        output_path = Path(args.output)
        output_path.mkdir(parents=True, exist_ok=True)
        for camera_id, result in results.items():
            data = result.to_dict()
            data.update(
                {
                    "dictionary": args.dict,
                    "marker_length": float(args.marker_length),
                    "cube_length": float(cube_length),
                    "ids": ids,
                    "camera_id": camera_id,
                }
            )
            file_path = output_path / f"{camera_id}_calibration.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"Saved calibration for {camera_id} to {file_path}")
            print(f"{camera_id} RMS reprojection error: {result.rms:.4f}")
    else:
        result = calibrate_from_images(
            image_glob=args.images,
            dictionary_name=args.dict,
            marker_length=args.marker_length,
            cube_length=cube_length,
            ids=ids,
        )

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = result.to_dict()
        data.update(
            {
                "dictionary": args.dict,
                "marker_length": float(args.marker_length),
                "cube_length": float(cube_length),
                "ids": ids,
            }
        )

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"Saved calibration to {output_path}")
        print(f"RMS reprojection error: {result.rms:.4f}")


if __name__ == "__main__":
    main()
