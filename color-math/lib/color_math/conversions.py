"""Color space conversions — all vectorized NumPy, no per-pixel loops."""

import numpy as np


def srgb_to_linear(img: np.ndarray) -> np.ndarray:
    """Convert sRGB [0,1] to linear RGB [0,1]."""
    return np.where(img <= 0.04045, img / 12.92, ((img + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(img: np.ndarray) -> np.ndarray:
    """Convert linear RGB [0,1] to sRGB [0,1]."""
    return np.where(img <= 0.0031308, img * 12.92, 1.055 * np.power(np.maximum(img, 0), 1.0 / 2.4) - 0.055)


def luminance(img: np.ndarray) -> np.ndarray:
    """Rec. 709 luminance from linear or sRGB RGB. Returns (H, W) array."""
    return 0.2126 * img[:, :, 0] + 0.7152 * img[:, :, 1] + 0.0722 * img[:, :, 2]


def rgb_to_hsl(img: np.ndarray) -> np.ndarray:
    """Vectorized RGB [0,1] to HSL [0,1]. Returns (H, W, 3) float32 array."""
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin

    # Lightness
    l = (cmax + cmin) / 2.0

    # Saturation
    s = np.where(delta == 0, 0.0, delta / (1.0 - np.abs(2.0 * l - 1.0) + 1e-10))

    # Hue
    h = np.zeros_like(l)
    mask_r = (delta > 0) & (cmax == r)
    mask_g = (delta > 0) & (cmax == g) & ~mask_r
    mask_b = (delta > 0) & ~mask_r & ~mask_g

    h[mask_r] = ((g[mask_r] - b[mask_r]) / delta[mask_r]) % 6.0
    h[mask_g] = ((b[mask_g] - r[mask_g]) / delta[mask_g]) + 2.0
    h[mask_b] = ((r[mask_b] - g[mask_b]) / delta[mask_b]) + 4.0
    h = h / 6.0

    return np.stack([h, s, l], axis=-1).astype(np.float32)


def hsl_to_rgb(hsl: np.ndarray) -> np.ndarray:
    """Vectorized HSL [0,1] to RGB [0,1]. Returns (H, W, 3) float32 array."""
    h, s, l = hsl[:, :, 0], hsl[:, :, 1], hsl[:, :, 2]

    c = (1.0 - np.abs(2.0 * l - 1.0)) * s
    hp = h * 6.0
    x = c * (1.0 - np.abs(hp % 2.0 - 1.0))
    m = l - c / 2.0

    r = np.zeros_like(h)
    g = np.zeros_like(h)
    b = np.zeros_like(h)

    mask0 = (hp >= 0) & (hp < 1)
    mask1 = (hp >= 1) & (hp < 2)
    mask2 = (hp >= 2) & (hp < 3)
    mask3 = (hp >= 3) & (hp < 4)
    mask4 = (hp >= 4) & (hp < 5)
    mask5 = (hp >= 5) & (hp < 6)

    r[mask0], g[mask0] = c[mask0], x[mask0]
    r[mask1], g[mask1] = x[mask1], c[mask1]
    g[mask2], b[mask2] = c[mask2], x[mask2]
    g[mask3], b[mask3] = x[mask3], c[mask3]
    r[mask4], b[mask4] = x[mask4], c[mask4]
    r[mask5], b[mask5] = c[mask5], x[mask5]

    return np.clip(np.stack([r + m, g + m, b + m], axis=-1), 0, 1).astype(np.float32)
