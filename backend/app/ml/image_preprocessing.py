import io

import cv2
import numpy as np
from PIL import Image, ImageOps


def _decode_oriented(image_bytes: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def _resize_for_text(image: np.ndarray) -> tuple[np.ndarray, bool]:
    height, width = image.shape[:2]
    max_dim = max(height, width)
    min_dim = min(height, width)

    # Downscale overly large images to avoid excessive CPU inference latency
    if max_dim > 1800:
        scale = 1800.0 / max_dim
        resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        return resized, True

    # Moderately upscale small images so text is readable
    if min_dim < 600:
        scale = min(2.0, max(1.0, 900.0 / max(min_dim, 1)))
        if scale > 1.05:
            resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            return resized, True

    return image, False



def _correct_perspective(image: np.ndarray) -> tuple[np.ndarray, bool]:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
        if cv2.contourArea(contour) < height * width * 0.35:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) != 4:
            continue
        points = polygon.reshape(4, 2).astype("float32")
        if np.any(points[:, 0] < width * 0.005) or np.any(points[:, 0] > width * 0.995):
            continue
        if np.any(points[:, 1] < height * 0.005) or np.any(points[:, 1] > height * 0.995):
            continue
        sums = points.sum(axis=1)
        differences = np.diff(points, axis=1).reshape(-1)
        ordered = np.array(
            [
                points[np.argmin(sums)],
                points[np.argmin(differences)],
                points[np.argmax(sums)],
                points[np.argmax(differences)],
            ],
            dtype="float32",
        )
        top_left, top_right, bottom_right, bottom_left = ordered
        target_width = int(max(np.linalg.norm(bottom_right - bottom_left), np.linalg.norm(top_right - top_left)))
        target_height = int(max(np.linalg.norm(top_right - bottom_right), np.linalg.norm(top_left - bottom_left)))
        if target_width < 200 or target_height < 300:
            continue
        target = np.array(
            [[0, 0], [target_width - 1, 0], [target_width - 1, target_height - 1], [0, target_height - 1]],
            dtype="float32",
        )
        return cv2.warpPerspective(image, cv2.getPerspectiveTransform(ordered, target), (target_width, target_height)), True
    return image, False


def _deskew(gray: np.ndarray) -> tuple[np.ndarray, bool]:
    threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coordinates = cv2.findNonZero(threshold)
    if coordinates is None or len(coordinates) < 100:
        return gray, False
    raw_angle = cv2.minAreaRect(coordinates)[-1]
    if raw_angle < -45:
        angle = -(90 + raw_angle)
    elif raw_angle > 45:
        angle = -(raw_angle - 90)
    else:
        angle = -raw_angle
    if abs(angle) < 1.5 or abs(angle) > 15:
        return gray, False
    height, width = gray.shape
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(gray, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE), True


def preprocess_image(image_bytes: bytes) -> tuple[bytes, list[str]]:
    """Create one conservative OCR variant; the caller compares it to untouched pixels."""
    image = _decode_oriented(image_bytes)
    steps = ["orientation"]
    image, resized = _resize_for_text(image)
    if resized:
        steps.append("resize_for_text")
    image, perspective_corrected = _correct_perspective(image)
    if perspective_corrected:
        steps.append("perspective_correction")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray, deskewed = _deskew(gray)
    if deskewed:
        steps.append("deskew")

    contrast = float(gray.std())
    brightness = float(gray.mean())
    local_background = cv2.morphologyEx(gray, cv2.MORPH_OPEN, np.ones((21, 21), np.uint8))
    uneven_lighting = float(np.percentile(local_background, 95) - np.percentile(local_background, 5)) > 35
    if uneven_lighting:
        gray = cv2.divide(gray, np.maximum(local_background, 1), scale=255)
        steps.append("shadow_correction")

    if contrast < 55 and brightness < 225:
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        steps.append("contrast_enhancement")

    median = cv2.medianBlur(gray, 3)
    noise_level = float(np.percentile(cv2.absdiff(gray, median), 95))
    if noise_level > 12:
        gray = cv2.medianBlur(gray, 3)
        steps.append("noise_reduction")

    if contrast < 25 and brightness < 160:
        gray = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        steps.append("adaptive_threshold")

    output = io.BytesIO()
    Image.fromarray(gray).save(output, format="PNG")
    return output.getvalue(), steps


def preprocess_for_ocr(
    image_bytes: bytes,
    max_long_side: int = 1800,
    enhance_contrast: bool = True,
) -> tuple[np.ndarray, list[str]]:
    """Fast, accurate preprocessing for PaddleOCR:
    1. EXIF orientation + convert to RGB
    2. Resize so longest side <= max_long_side (~1600-2000px, NEVER upscale)
    3. Optional light contrast enhancement
    Returns RGB numpy ndarray ready for PaddleOCR predict().
    """
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")

    width, height = image.size
    steps = ["orientation", "rgb_convert"]

    longest = max(width, height)
    if longest > max_long_side:
        scale = max_long_side / longest
        new_w, new_h = max(1, int(width * scale)), max(1, int(height * scale))
        image = image.resize((new_w, new_h), Image.Resampling.BILINEAR)
        steps.append(f"resize_longest_{max_long_side}")

    img_arr = np.asarray(image)

    if enhance_contrast:
        gray = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY)
        std_dev = float(gray.std())
        mean_val = float(gray.mean())
        if std_dev < 50 and mean_val < 220:
            lab = cv2.cvtColor(img_arr, cv2.COLOR_RGB2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
            cl = clahe.apply(l_channel)
            enhanced_lab = cv2.merge((cl, a_channel, b_channel))
            img_arr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)
            steps.append("clahe_contrast_enhancement")

    return img_arr, steps
