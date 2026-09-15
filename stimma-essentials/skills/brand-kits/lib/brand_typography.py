"""Prepare portable Latin wordmarks from an agent-selected font.

No font discovery, downloads, styling decisions or package/cover generation.
Uses fontTools and Pillow, both available with the app's rendering stack.
"""
from __future__ import annotations

from html import escape
from io import BytesIO
import math
from pathlib import Path
import re
import unicodedata

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import ImageFont, features


def outline_text(text: str, font_path: str, *, font_size: float = 120,
                 tracking: float = 0, fill: str = "#172334", padding: float = 8,
                 axes: dict[str, float] | None = None) -> str:
    """Return self-contained SVG paths for a single-line Latin wordmark.

    font_size, tracking and padding are SVG units. axes selects variable-font
    axes (e.g. {"wght": 600}) in memory; the original file is never modified.
    Kerning follows Pillow's text metrics; discretionary/standard ligatures
    are disabled so each source character maps to the actual outlined glyph.
    Combining sequences are normalized to precomposed characters when possible.
    Complex scripts need a shaping workflow; unsupported input fails explicitly.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > 200:
        raise ValueError("Supply a nonempty wordmark of at most 200 characters")
    text = unicodedata.normalize("NFC", text)
    for char in text:
        category = unicodedata.category(char)
        if category[0] in "MC" or (category[0] == "L" and "LATIN" not in unicodedata.name(char, "")):
            raise ValueError("outline_text supports single-line Latin text; complex scripts need a shaping workflow")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (font_size, tracking, padding)) or font_size <= 0 or padding < 0:
        raise ValueError("Use positive font_size, nonnegative padding and finite numeric spacing")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}|currentColor", fill):
        raise ValueError("fill must be #RRGGBB or currentColor")
    with TTFont(Path(font_path)) as original:
        if axes:
            known = {a.axisTag: a for a in original.get("fvar", []).axes} if "fvar" in original else {}
            for name, value in axes.items():
                if name not in known or not isinstance(value, (int, float)) or not known[name].minValue <= value <= known[name].maxValue:
                    raise ValueError(f"Unsupported font axis/value: {name}={value}")
            font = instantiateVariableFont(original, axes, inplace=False)
        else:
            font = original
        cmap = font.getBestCmap()
        missing = [char for char in text if ord(char) not in cmap]
        if missing:
            raise ValueError(f"Font lacks these characters: {''.join(dict.fromkeys(missing))}")
        font.flavor = None  # Pillow reads SFNT bytes, including WOFF source fonts.
        data = BytesIO()
        font.save(data)
        data.seek(0)
        upm = font["head"].unitsPerEm
        raqm = features.check_feature("raqm")
        metrics = ImageFont.truetype(data, upm, layout_engine=ImageFont.Layout.RAQM if raqm else ImageFont.Layout.BASIC)
        kwargs = {"features": ["-liga", "-clig"], "direction": "ltr"} if raqm else {}
        glyphs = font.getGlyphSet()
        scale = font_size / upm
        paths = []
        bounds = []
        for index, char in enumerate(text):
            x = (metrics.getlength(text[:index + 1], **kwargs) - metrics.getlength(char, **kwargs)) * scale + index * tracking
            glyph = glyphs[cmap[ord(char)]]
            pen = SVGPathPen(glyphs)
            glyph.draw(pen)
            bounding = BoundsPen(glyphs)
            glyph.draw(bounding)
            if bounding.bounds:
                x0, y0, x1, y1 = bounding.bounds
                bounds.append((x + x0 * scale, -y1 * scale, x + x1 * scale, -y0 * scale))
                paths.append(f'<path transform="translate({x:.6f} 0) scale({scale:.9f} {-scale:.9f})" d="{pen.getCommands()}"/>')
        if not bounds:
            raise ValueError("The chosen text has no visible glyph outlines")
        left = min(b[0] for b in bounds) - padding
        top = min(b[1] for b in bounds) - padding
        width = max(b[2] for b in bounds) + padding - left
        height = max(b[3] for b in bounds) + padding - top
        # A zero-origin canvas composes directly beside a mark. Keep the glyph
        # baseline translation inside the SVG so callers needn't normalize it.
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.6f}" height="{height:.6f}" '
                f'viewBox="0 0 {width:.6f} {height:.6f}" role="img" aria-label="{escape(text, quote=True)}">'
                f'<g fill="{fill}" transform="translate({-left:.6f} {-top:.6f})">{"".join(paths)}</g></svg>')
