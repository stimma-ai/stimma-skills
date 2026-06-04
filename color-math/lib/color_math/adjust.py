"""Color adjustments — temperature shift and channel mixing."""

import numpy as np


def adjust_temperature(img: np.ndarray, shift: float = 0) -> np.ndarray:
    """Shift color temperature. Positive = warm (more red/yellow), negative = cool (more blue).

    Args:
        img: RGB image (H, W, 3) float32 [0,1].
        shift: Temperature shift in roughly Kelvin-like units. Range ~[-100, 100].
    """
    if shift == 0:
        return img.copy()
    t = shift / 100.0
    r_gain = 1.0 + t * 0.15
    b_gain = 1.0 - t * 0.15
    result = img.copy()
    result[:, :, 0] = np.clip(result[:, :, 0] * r_gain, 0, 1)
    result[:, :, 2] = np.clip(result[:, :, 2] * b_gain, 0, 1)
    return result.astype(np.float32)


def channel_mix(img: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Apply a 3x3 channel mixing matrix.

    Args:
        img: RGB image (H, W, 3) float32 [0,1].
        matrix: 3x3 numpy array. Each row defines output channel as weighted sum of input channels.
                Identity matrix = no change.
    """
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.shape != (3, 3):
        raise ValueError(f"Channel mix matrix must be 3x3, got {matrix.shape}")
    h, w, _ = img.shape
    flat = img.reshape(-1, 3)
    mixed = flat @ matrix.T
    return np.clip(mixed.reshape(h, w, 3), 0, 1).astype(np.float32)
