"""Conditioning-image prep: frame the locked base for the video model.

i2v models fill their output aspect by scaling and cropping the conditioning
image — a 3:4 base fed to a square video loses the head and feet. Pad the
base to the video's aspect before conditioning instead of letting the model
crop.
"""

from pathlib import Path

import numpy as np

from PIL import Image

from .cleanup import sample_background


def pad_to_aspect(
    image: "Image.Image | str | Path",
    aspect: "tuple[int, int]" = (1, 1),
    *,
    margin: float = 0.05,
    bg: "tuple | None" = None,
) -> Image.Image:
    """Center the image on a canvas of the target aspect, never cropping.

    Args:
        aspect: Target (width, height) ratio — match the video output.
        margin: Extra clear space on every side, as a fraction of the
            canvas dimension, so motion has room before touching an edge.
        bg: Canvas RGB; sampled from the image border if None, so the
            padding is invisible against a plain generated backdrop.
    """
    if not isinstance(image, Image.Image):
        image = Image.open(image)
    image = image.convert("RGB")
    if bg is None:
        bg = sample_background(image)[:3]
    aw, ah = aspect
    w, h = image.size
    canvas_w = max(w, round(h * aw / ah))
    canvas_h = max(h, round(w * ah / aw))
    if margin:
        canvas_w = round(canvas_w * (1 + 2 * margin))
        canvas_h = round(canvas_h * (1 + 2 * margin))
        # Re-snap to the exact aspect after growing.
        canvas_w = max(canvas_w, round(canvas_h * aw / ah))
        canvas_h = max(canvas_h, round(canvas_w * ah / aw))
    canvas = Image.new("RGB", (canvas_w, canvas_h), tuple(bg))
    canvas.paste(image, ((canvas_w - w) // 2, (canvas_h - h) // 2))
    return canvas


# Saturated, off-axis candidates. Real key colours: far from skin, hair,
# metal and cloth, and far from each other so some option always wins.
KEY_COLORS = (
    ("chroma green", (0, 177, 64)),
    ("magenta", (255, 0, 255)),
    ("chroma blue", (0, 71, 187)),
    ("orange", (255, 106, 0)),
    ("violet", (140, 0, 210)),
    ("cyan", (0, 200, 255)),
)


def pick_key_color(subject, *, candidates=KEY_COLORS, percentile: float = 0.5) -> dict:
    """Choose a backdrop colour the character cannot be confused with.

    The key separates by colour distance, so the backdrop must be far from
    every colour the character actually uses — a pale backdrop against
    white sneakers is only ~20 away and gets subtracted out of the shoe.
    Rather than guessing a fixed screen colour (a green screen fails a
    green goblin), score saturated candidates against the *locked
    character* and take the one with the widest margin. Run this once, on
    the cut-out base image, before generating any move.

    Args:
        subject: RGBA image or frame list; only opaque pixels are scored.
        percentile: Robust "closest colour" cut, so a handful of stray
            pixels can't veto an otherwise ideal backdrop.

    Returns:
        {"name", "rgb", "hex", "phrase", "margin"} — ``phrase`` drops
        straight into a prompt, ``margin`` is the CHROMATICITY distance to
        the nearest character colour (higher is safer; under ~0.20 means
        the character shares the backdrop's hue and will half-key out).
    """
    frames = subject if isinstance(subject, (list, tuple)) else [subject]
    pixels = []
    for f in frames:
        arr = np.asarray(f.convert("RGBA"))
        opaque = arr[:, :, 3] > 200
        if opaque.any():
            pixels.append(arr[:, :, :3][opaque])
    if not pixels:
        raise ValueError("subject has no opaque pixels — key or matte it first")
    px = np.concatenate(pixels).astype(np.float32)
    if len(px) > 200_000:                       # scoring is distance-bound
        px = px[:: len(px) // 200_000 + 1]

    from .cleanup import chroma_distance

    best = None
    for name, rgb in candidates:
        # Score in CHROMATICITY, the space the key actually works in. RGB
        # distance would happily hand a purple-robed witch a magenta screen:
        # far apart in RGB, nearly the same hue, so her robe half-keys out.
        d = chroma_distance(px, rgb)
        margin = float(np.percentile(d, percentile))
        if best is None or margin > best["margin"]:
            best = {"name": name, "rgb": tuple(rgb), "margin": round(margin, 3),
                    "hex": "#%02X%02X%02X" % tuple(rgb)}
    best["phrase"] = f"plain solid {best['name']} ({best['hex']}) background"
    return best


def compose_on(cutout, color) -> Image.Image:
    """Put a transparent character onto a solid backdrop for conditioning.

    The video inherits its backdrop from the conditioning image, so after
    choosing a key colour the anchor has to be restaged on it — telling the
    model a colour in the prompt while handing it a different backdrop just
    gets you the backdrop in the image.
    """
    cutout = cutout.convert("RGBA")
    canvas = Image.new("RGB", cutout.size, tuple(color))
    canvas.paste(cutout, mask=cutout)
    return canvas
