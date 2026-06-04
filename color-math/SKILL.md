---
name: color-math
display_name: Color Math
description: Color space conversions, blending modes, and channel math for run_code
author: system
tags: [color, image-processing]
provides:
  - color_math
---

# Color Math

Importable Python library for color space conversions, blending modes, and per-channel math in `run_code`.

## Usage

```python
from color_math import rgb_to_hsl, hsl_to_rgb, blend, adjust_temperature

img = np.array(Image.open("photo.png").convert("RGB"), dtype=np.float32) / 255.0

# Convert to HSL, boost saturation, convert back
hsl = rgb_to_hsl(img)
hsl[:, :, 1] = np.clip(hsl[:, :, 1] * 1.3, 0, 1)
result = hsl_to_rgb(hsl)

# Warm up an image
result = adjust_temperature(img, shift=15)

# Blend two images with soft-light
blended = blend(base, overlay, mode="soft-light", opacity=0.6)
```

## Available functions

- `rgb_to_hsl(img)` / `hsl_to_rgb(img)` — vectorized color space conversion (float32 arrays, [0,1] range)
- `srgb_to_linear(img)` / `linear_to_srgb(img)` — gamma conversions
- `luminance(img)` — Rec. 709 luminance
- `adjust_temperature(img, shift)` — warm (positive) or cool (negative) color temperature shift
- `blend(base, overlay, mode, opacity)` — blending modes: normal, multiply, screen, overlay, soft-light
- `channel_mix(img, matrix)` — apply a 3x3 channel mixing matrix

All functions operate on float32 numpy arrays in [0,1] range with shape (H, W, 3).
