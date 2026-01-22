"""
Image processing utilities.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Tuple, Optional


def load_image(path: Path) -> np.ndarray:
    """Load an image from disk."""
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Could not load image: {path}")
    return image


def save_image(image: np.ndarray, path: Path) -> None:
    """Save an image to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)


def resize_image(
    image: np.ndarray,
    width: Optional[int] = None,
    height: Optional[int] = None,
    max_size: Optional[int] = None,
) -> np.ndarray:
    """
    Resize image maintaining aspect ratio.

    Args:
        image: Input image
        width: Target width (optional)
        height: Target height (optional)
        max_size: Maximum dimension (optional)

    Returns:
        Resized image
    """
    h, w = image.shape[:2]

    if max_size:
        if max(h, w) <= max_size:
            return image
        if h > w:
            height = max_size
            width = int(w * max_size / h)
        else:
            width = max_size
            height = int(h * max_size / w)
    elif width and not height:
        height = int(h * width / w)
    elif height and not width:
        width = int(w * height / h)
    elif not width and not height:
        return image

    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)


def crop_image(
    image: np.ndarray,
    x: int,
    y: int,
    width: int,
    height: int,
    padding: int = 0,
) -> np.ndarray:
    """
    Crop a region from an image with optional padding.
    """
    h, w = image.shape[:2]

    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(w, x + width + padding)
    y2 = min(h, y + height + padding)

    return image[y1:y2, x1:x2]


def enhance_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    Enhance image for better OCR accuracy.
    """
    # Convert to grayscale if needed
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # Apply adaptive thresholding
    enhanced = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2,
    )

    # Denoise
    enhanced = cv2.fastNlMeansDenoising(enhanced, h=10)

    return enhanced


def deskew(image: np.ndarray) -> np.ndarray:
    """
    Deskew a scanned image.
    """
    # Convert to grayscale
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # Threshold
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Find all non-zero pixels
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) < 100:
        return image

    # Get rotation angle
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle

    # Only deskew if angle is significant
    if abs(angle) < 0.5:
        return image

    # Rotate
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        image,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )

    return rotated


def remove_borders(image: np.ndarray, threshold: int = 10) -> np.ndarray:
    """
    Remove dark borders from an image.
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # Find non-black regions
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return image

    # Get bounding box of largest contour
    largest = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest)

    return image[y : y + h, x : x + w]


def split_page_columns(image: np.ndarray, num_columns: int = 2) -> list:
    """
    Split a page image into columns.
    """
    h, w = image.shape[:2]
    column_width = w // num_columns

    columns = []
    for i in range(num_columns):
        x_start = i * column_width
        x_end = (i + 1) * column_width if i < num_columns - 1 else w
        columns.append(image[:, x_start:x_end])

    return columns


def combine_images_vertical(images: list, spacing: int = 10) -> np.ndarray:
    """
    Combine multiple images vertically.
    """
    if not images:
        return np.zeros((100, 100, 3), dtype=np.uint8)

    # Get maximum width
    max_width = max(img.shape[1] for img in images)

    # Pad images to same width
    padded = []
    for img in images:
        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        h, w = img.shape[:2]
        if w < max_width:
            pad = np.ones((h, max_width - w, 3), dtype=np.uint8) * 255
            img = np.hstack([img, pad])
        padded.append(img)

    # Add spacing
    if spacing > 0:
        spacer = np.ones((spacing, max_width, 3), dtype=np.uint8) * 255
        result = []
        for i, img in enumerate(padded):
            result.append(img)
            if i < len(padded) - 1:
                result.append(spacer)
        padded = result

    return np.vstack(padded)


def get_image_hash(image: np.ndarray, hash_size: int = 8) -> str:
    """
    Compute perceptual hash of an image for duplicate detection.
    """
    # Resize
    resized = cv2.resize(image, (hash_size + 1, hash_size))

    # Convert to grayscale
    if len(resized.shape) == 3:
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    else:
        gray = resized

    # Compute difference hash
    diff = gray[:, 1:] > gray[:, :-1]
    return "".join(str(int(b)) for row in diff for b in row)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        image_path = Path(sys.argv[1])
        image = load_image(image_path)
        print(f"Loaded image: {image.shape}")

        # Test enhancement
        enhanced = enhance_for_ocr(image)
        output_path = image_path.parent / f"{image_path.stem}_enhanced.png"
        save_image(enhanced, output_path)
        print(f"Saved enhanced image to: {output_path}")
    else:
        print("Usage: python image_utils.py <image_path>")
