"""
Deterministic perspective correction pre-pass (OpenCV, free, predictable).

Detects near-vertical structural lines (wall edges, door frames, window frames)
with Hough transform, estimates the perspective distortion, and applies a
homography that makes those lines truly vertical. Conservative by design:
if detection is ambiguous or correction would exceed MAX_CORRECTION degrees,
returns the image unchanged.

Usage:
    from perspective_fix import straighten
    fixed_jpeg_bytes, applied = straighten(jpeg_bytes)
"""
from __future__ import annotations
import math

import cv2
import numpy as np

MAX_CORRECTION_DEG = 8.0    # refuse crazy warps — better untouched than distorted
MIN_LINES = 4               # need at least this many vertical candidates


def _vertical_angles(gray: np.ndarray) -> list[float]:
    """Angles (deg, signed, 0 = perfectly vertical) of near-vertical lines."""
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 40, 120, apertureSize=3)
    h = gray.shape[0]
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=40,
                            minLineLength=int(h * 0.10), maxLineGap=20)
    if lines is None:
        return []
    angles = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        dx, dy = x2 - x1, y2 - y1
        if dy == 0:
            continue
        # angle from vertical axis
        ang = math.degrees(math.atan2(dx, dy))
        if ang > 90:
            ang -= 180
        if ang < -90:
            ang += 180
        if abs(ang) <= 15:          # near-vertical structural lines only
            angles.append(ang)
    return angles


def straighten(jpeg_bytes: bytes) -> tuple[bytes, bool]:
    """Rotate/warp so structural verticals are vertical. Returns (jpeg, applied)."""
    arr = np.frombuffer(jpeg_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes, False
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    angles = _vertical_angles(gray)
    if len(angles) < MIN_LINES:
        return jpeg_bytes, False

    tilt = float(np.median(angles))
    if abs(tilt) < 0.4:              # already straight
        return jpeg_bytes, False
    if abs(tilt) > MAX_CORRECTION_DEG:
        return jpeg_bytes, False     # something weird — do not touch

    h, w = img.shape[:2]
    # Rotate around center by the median tilt, expand canvas, then crop the
    # largest axis-aligned rectangle to avoid black borders.
    M = cv2.getRotationMatrix2D((w / 2, h / 2), -tilt, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += (nw - w) / 2
    M[1, 2] += (nh - h) / 2
    rotated = cv2.warpAffine(img, M, (nw, nh), flags=cv2.INTER_LANCZOS4,
                             borderMode=cv2.BORDER_REPLICATE)

    # crop back to original aspect, scaled to stay inside the rotated frame
    rad = math.radians(abs(tilt))
    scale = 1.0 / (math.cos(rad) + (h / w) * math.sin(rad))
    cw, ch = int(w * scale), int(h * scale)
    x0, y0 = (nw - cw) // 2, (nh - ch) // 2
    cropped = rotated[y0:y0 + ch, x0:x0 + cw]
    cropped = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LANCZOS4)

    ok, out = cv2.imencode(".jpg", cropped, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        return jpeg_bytes, False
    return out.tobytes(), True


if __name__ == "__main__":
    import sys
    data = open(sys.argv[1], "rb").read()
    fixed, applied = straighten(data)
    out = sys.argv[1].replace(".jpg", "_straightened.jpg")
    open(out, "wb").write(fixed)
    print(f"applied={applied} -> {out}")
