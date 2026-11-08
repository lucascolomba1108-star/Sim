"""Rebuilds full frames from the shared plates and the per-hand crops.

A crop is pasted only where it really differs from what is underneath (cards,
chips, their shadows and blur). The comparison is done on slightly blurred
images, so the tiny grain differences between two denoiser runs cancel out
while real changes stand out. Felt that did not change keeps the plate's
pixels: no seams around crops, and no shimmer from frame to frame.
"""
import numpy as np
from PIL import Image, ImageFilter

T0, T1 = 2.0, 5.0       # soft threshold (8-bit levels) on the blurred difference
BLUR = 2.0              # px, at 1188 px width (scaled with the frame)
GROW = 5                # px the mask is grown by (odd)


def load(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def _blur(arr, radius):
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)


def change_mask(new, old, scale=1.0):
    r = max(0.6, BLUR * scale)
    d = np.abs(_blur(new, r) - _blur(old, r)).max(axis=2)
    m = np.clip((d - T0) / (T1 - T0), 0.0, 1.0)
    im = Image.fromarray((m * 255).astype(np.uint8))
    grow = max(3, int(round(GROW * scale)) | 1)
    im = im.filter(ImageFilter.MaxFilter(grow)).filter(ImageFilter.GaussianBlur(max(0.8, 1.5 * scale)))
    return np.asarray(im, dtype=np.float32)[..., None] / 255.0


def paste(base, crop, rect, scale=1.0):
    """Returns a copy of `base` with `crop` (pixels of rect x0,y0,x1,y1) merged in where it changed."""
    x0, y0, x1, y1 = rect
    out = base.copy()
    under = base[y0:y1, x0:x1]
    m = change_mask(crop, under, scale)
    out[y0:y1, x0:x1] = crop * m + under * (1 - m)
    return out
