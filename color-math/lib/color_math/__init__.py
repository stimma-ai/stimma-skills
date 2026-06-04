"""Color Math — color space conversions, blending modes, and channel math.

All functions operate on float32 numpy arrays in [0,1] range with shape (H, W, 3).
"""

from .conversions import rgb_to_hsl, hsl_to_rgb, srgb_to_linear, linear_to_srgb, luminance
from .blend import blend
from .adjust import adjust_temperature, channel_mix

__all__ = [
    "rgb_to_hsl", "hsl_to_rgb", "srgb_to_linear", "linear_to_srgb", "luminance",
    "blend", "adjust_temperature", "channel_mix",
]
