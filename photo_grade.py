"""
Deterministic high-key grade — the locked ListingBoost look.

Same math on every photo = perfectly consistent exposure across a listing.
Recipe (validated on Dorcas living room 2026-07-14):
  neutral-cool WB -> gamma lift -> shadow floor -> white-point stretch
  -> soft S-curve -> slight desaturation.
"""
import numpy as np
import cv2


def highkey_grade(jpeg_bytes: bytes) -> bytes:
    arr = np.frombuffer(jpeg_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes
    img = img.astype(np.float32) / 255.0
    img = np.clip(img * np.array([0.99, 1.00, 1.02]), 0, 1)   # neutral-warm WB (BGR)
    img = img ** 0.82                                          # gamma lift
    img = img + 0.035 * (1 - img)                              # shadow floor
    lum = 0.114 * img[..., 0] + 0.587 * img[..., 1] + 0.299 * img[..., 2]
    hi = np.percentile(lum, 97.5)
    img = np.clip(img / max(hi, 0.7) * 0.985, 0, 1)            # white point
    img = np.clip(img + 0.10 * (img - 0.5) * (1 - abs(img - 0.5) * 2), 0, 1)
    g = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    img = np.clip(img * 0.92 + g[..., None] * 0.08, 0, 1)      # airy desat
    ok, out = cv2.imencode(".jpg", (img * 255).astype(np.uint8),
                           [cv2.IMWRITE_JPEG_QUALITY, 93])
    return out.tobytes() if ok else jpeg_bytes
