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

MAX_CORRECTION_DEG = 20.0   # refuse crazy warps — better untouched than distorted
STRENGTH = 0.65             # partial correction: straight enough, without extreme crop
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


def _vertical_lines(gray):
    """Near-vertical segments as (x_center, angle_deg) pairs."""
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 40, 120, apertureSize=3)
    h = gray.shape[0]
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=40,
                            minLineLength=int(h * 0.10), maxLineGap=20)
    if lines is None:
        return []
    out = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        dx, dy = x2 - x1, y2 - y1
        if dy == 0:
            continue
        ang = math.degrees(math.atan2(dx, dy))
        if ang > 90:
            ang -= 180
        if ang < -90:
            ang += 180
        if abs(ang) <= 15:
            out.append(((x1 + x2) / 2.0, ang))
    return out


def straighten(jpeg_bytes: bytes) -> tuple[bytes, bool]:
    """Correct BOTH rotation and keystone (vertical convergence) so structural
    verticals are truly vertical. Returns (jpeg, applied)."""
    arr = np.frombuffer(jpeg_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes, False
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = img.shape[:2]

    pairs = _vertical_lines(gray)
    if len(pairs) < MIN_LINES:
        return jpeg_bytes, False

    xs = np.array([p[0] for p in pairs])
    angs = np.array([p[1] for p in pairs])
    # angle as a linear function of x: a(x) = k*(x-cx) + b
    #   b = global rotation, k = keystone (verticals converging)
    cx = w / 2.0
    sel = np.ones(len(xs), bool)
    for _ in range(3):          # robust fit: drop outlier segments (furniture edges)
        A = np.vstack([xs[sel] - cx, np.ones(int(sel.sum()))]).T
        (k, b), *_ = np.linalg.lstsq(A, angs[sel], rcond=None)
        sel = np.abs(k * (xs - cx) + b - angs) < 2.5

    aL = float(k * (0 - cx) + b) * STRENGTH   # implied lean at left edge
    aR = float(k * (w - cx) + b) * STRENGTH   # implied lean at right edge
    if max(abs(aL), abs(aR)) < 0.4:
        return jpeg_bytes, False
    if max(abs(aL), abs(aR)) > MAX_CORRECTION_DEG:
        return jpeg_bytes, False

    # Perspective warp: shift edge endpoints horizontally so each edge's lean
    # becomes vertical. A line leaning `a` deg means its top is offset by
    # -tan(a)*h/2 relative to its bottom (about its center).
    dL = math.tan(math.radians(aL)) * h / 2.0
    dR = math.tan(math.radians(aR)) * h / 2.0
    src = np.float32([[0 + dL, 0], [w + dR, 0], [w - dR, h], [0 - dL, h]])
    dst = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, M, (w, h), flags=cv2.INTER_LANCZOS4,
                                 borderMode=cv2.BORDER_REPLICATE)

    # inner crop to hide replicated borders
    margin = int(max(abs(dL), abs(dR))) + 2
    if margin * 2 < min(w, h) * 0.2:
        warped = warped[margin:h - margin, margin:w - margin]
        warped = cv2.resize(warped, (w, h), interpolation=cv2.INTER_LANCZOS4)

    ok, out = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 92])
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
