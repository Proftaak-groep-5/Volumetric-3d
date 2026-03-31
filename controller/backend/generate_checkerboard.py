"""
Generate printable checkerboard pattern for camera calibration
"""
import cv2
import numpy as np
import argparse
from pathlib import Path

def generate_checkerboard(cols, rows, square_size_mm, margin_mm=20, dpi=300):
    """
    Generate a checkerboard pattern for printing
    
    Args:
        cols: Number of inner corners (columns)
        rows: Number of inner corners (rows)
        square_size_mm: Size of each square in millimeters
        margin_mm: Margin around the pattern in millimeters
        dpi: Dots per inch for printing (300 is standard)
    
    Returns:
        numpy array of the checkerboard image
    """
    # Convert mm to pixels (1 inch = 25.4 mm)
    mm_to_pixels = dpi / 25.4
    square_size_px = int(square_size_mm * mm_to_pixels)
    margin_px = int(margin_mm * mm_to_pixels)
    
    # Calculate board dimensions
    # Inner corners means we need cols+1 squares horizontally, rows+1 vertically
    board_width = (cols + 1) * square_size_px
    board_height = (rows + 1) * square_size_px
    
    # Total image size with margins
    img_width = board_width + 2 * margin_px
    img_height = board_height + 2 * margin_px
    
    # Create white background
    img = np.ones((img_height, img_width), dtype=np.uint8) * 255
    
    # Draw checkerboard pattern
    for row in range(rows + 1):
        for col in range(cols + 1):
            x = margin_px + col * square_size_px
            y = margin_px + row * square_size_px
            
            # Alternate black and white
            if (row + col) % 2 == 0:
                color = 0  # Black
            else:
                color = 255  # White
            
            cv2.rectangle(img, 
                         (x, y), 
                         (x + square_size_px, y + square_size_px), 
                         color, 
                         -1)
    
    return img, square_size_px, margin_px

def add_info_text(img, cols, rows, square_size_mm, square_size_px, margin_px):
    """Add informational text to the checkerboard"""
    # Add text at the bottom
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    thickness = 2
    color = 0  # Black
    
    text_lines = [
        f"Checkerboard: {cols}x{rows} inner corners",
        f"Square size: {square_size_mm}mm ({square_size_px}px)",
        f"Print at 300 DPI for accurate calibration"
    ]
    
    y_offset = img.shape[0] - 80
    for i, line in enumerate(text_lines):
        y = y_offset + i * 25
        cv2.putText(img, line, (10, y), font, font_scale, color, thickness)
    
    return img

def main():
    parser = argparse.ArgumentParser(description="Generate printable checkerboard for calibration")
    parser.add_argument("--cols", type=int, default=9, 
                       help="Number of inner corners (columns), default: 9")
    parser.add_argument("--rows", type=int, default=6, 
                       help="Number of inner corners (rows), default: 6")
    parser.add_argument("--square-size", type=float, default=25.0, 
                       help="Square size in millimeters, default: 25.0")
    parser.add_argument("--margin", type=float, default=20.0, 
                       help="Margin in millimeters, default: 20.0")
    parser.add_argument("--dpi", type=int, default=300, 
                       help="Print resolution in DPI, default: 300")
    parser.add_argument("--output", type=str, default="checkerboard.png", 
                       help="Output filename, default: checkerboard.png")
    parser.add_argument("--pdf", action="store_true", 
                       help="Also generate PDF version")
    
    args = parser.parse_args()
    
    print(f"Generating checkerboard pattern...")
    print(f"  Size: {args.cols}x{args.rows} inner corners")
    print(f"  Square size: {args.square_size}mm")
    print(f"  DPI: {args.dpi}")
    
    # Generate checkerboard
    img, square_size_px, margin_px = generate_checkerboard(
        args.cols, args.rows, args.square_size, args.margin, args.dpi
    )
    
    # Add info text
    img = add_info_text(img, args.cols, args.rows, args.square_size, square_size_px, margin_px)
    
    # Save PNG
    output_path = Path(args.output)
    cv2.imwrite(str(output_path), img)
    print(f"\n✓ Saved checkerboard to: {output_path}")
    print(f"  Image size: {img.shape[1]}x{img.shape[0]} pixels")
    print(f"  Physical size: {img.shape[1]/args.dpi*25.4:.1f}x{img.shape[0]/args.dpi*25.4:.1f} mm")
    
    # Generate PDF if requested
    if args.pdf:
        try:
            from PIL import Image
            pdf_path = output_path.with_suffix('.pdf')
            
            # Convert to PIL Image
            pil_img = Image.fromarray(img)
            
            # Convert to RGB if needed
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            
            # Save as PDF with correct DPI
            pil_img.save(pdf_path, 'PDF', resolution=args.dpi)
            print(f"✓ Saved PDF to: {pdf_path}")
        except ImportError:
            print("⚠ Pillow not installed, skipping PDF generation")
            print("  Install with: pip install Pillow")
    
    print(f"\n📋 Instructions:")
    print(f"  1. Print this image at {args.dpi} DPI (or 'Actual Size' in printer settings)")
    print(f"  2. Measure a square to verify it's exactly {args.square_size}mm")
    print(f"  3. Mount on a flat, rigid surface (cardboard, foam board)")
    print(f"  4. Use for stereo calibration with both cameras")

if __name__ == "__main__":
    main()

