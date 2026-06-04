"""Photoshop-style blending modes — all vectorized NumPy."""

import numpy as np


def _blend_normal(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return overlay


def _blend_multiply(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return base * overlay


def _blend_screen(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return 1.0 - (1.0 - base) * (1.0 - overlay)


def _blend_overlay(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return np.where(
        base < 0.5,
        2.0 * base * overlay,
        1.0 - 2.0 * (1.0 - base) * (1.0 - overlay),
    )


def _blend_soft_light(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return np.where(
        overlay < 0.5,
        base - (1.0 - 2.0 * overlay) * base * (1.0 - base),
        base + (2.0 * overlay - 1.0) * (np.sqrt(base) - base),
    )


_MODES = {
    "normal": _blend_normal,
    "multiply": _blend_multiply,
    "screen": _blend_screen,
    "overlay": _blend_overlay,
    "soft-light": _blend_soft_light,
}


def blend(base: np.ndarray, overlay: np.ndarray, mode: str = "normal", opacity: float = 1.0) -> np.ndarray:
    """Blend two images using the given mode and opacity.

    Args:
        base: Background image (H, W, 3) float32 [0,1].
        overlay: Foreground image (H, W, 3) float32 [0,1].
        mode: One of 'normal', 'multiply', 'screen', 'overlay', 'soft-light'.
        opacity: Blend opacity in [0, 1].
    """
    if mode not in _MODES:
        raise ValueError(f"Unknown blend mode '{mode}'. Available: {', '.join(_MODES)}")
    blended = _MODES[mode](base, overlay)
    result = base * (1.0 - opacity) + blended * opacity
    return np.clip(result, 0, 1).astype(np.float32)
