"""Fonts and outlined lettering for vector work.

``fetch_family`` downloads an agent-chosen Google Fonts family and its license;
``font_face`` embeds an actual font in editable HTML; ``outline_text`` turns a
line of text into self-contained SVG paths. Network acquisition is explicit;
nothing here chooses typography. Uses fontTools and Pillow, both in the app's
rendering stack. Source: https://github.com/google/fonts.
"""
from base64 import b64encode
from html import escape
from io import BytesIO
import json
import math
from pathlib import Path
import re
import unicodedata
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import ImageFont, features

_ROOT = "https://raw.githubusercontent.com/google/fonts/main/"


def _read(path):
    request = Request(_ROOT + quote(path, safe="/"), headers={"User-Agent": "font-workspace/1"})
    with urlopen(request, timeout=20) as response:
        data = response.read(20_000_001)
    if len(data) > 20_000_000:
        raise ValueError("Font resource exceeds 20 MB")
    return data


def describe_font(path):
    """Return actual family, style, CSS weight/range, and variable axes."""
    with TTFont(path) as font:
        names = font["name"]
        family = names.getDebugName(16) or names.getDebugName(1)
        style = names.getDebugName(17) or names.getDebugName(2) or "Regular"
        axes = {a.axisTag: [a.minValue, a.defaultValue, a.maxValue]
                for a in font["fvar"].axes} if "fvar" in font else {}
        weight = str(font["OS/2"].usWeightClass)
        if "wght" in axes:
            weight = f"{axes['wght'][0]:g} {axes['wght'][2]:g}"
        return {"path": str(path), "family": family, "style": style,
                "weight": weight, "css_style": "italic" if font["head"].macStyle & 2 else "normal",
                "axes": axes}


def fetch_family(family, dest="fonts"):
    """Download a named Google Fonts family and its license to dest/<slug>/.

    Returns {family, fonts: [describe_font rows], license, source}. Existing
    complete families are reused. No system font installation or shell needed.
    OFL, Apache and Ubuntu directories are supported; missing families fail
    explicitly. The caller chooses the family and reads its license.
    """
    if not isinstance(family, str) or not re.fullmatch(r"[A-Za-z0-9 -]{1,100}", family):
        raise ValueError("Use the Google Fonts family name, for example Space Grotesk")
    slug = re.sub(r"[^a-z0-9]", "", family.lower())
    if not slug:
        raise ValueError("Supply a font family name")
    folder = Path(dest) / slug
    receipt = folder / "font-source.json"
    if receipt.exists():
        cached = json.loads(receipt.read_text())
        if all(Path(row["path"]).is_file() and not re.search(r"[\[\],]", Path(row["path"]).name)
               for row in cached["fonts"]) and Path(cached["license"]).is_file():
            return cached
    for category, license_name in (("ofl", "OFL.txt"), ("apache", "LICENSE.txt"), ("ufl", "UFL.txt")):
        directory = f"{category}/{slug}"
        try:
            metadata = _read(f"{directory}/METADATA.pb").decode("utf-8")
        except HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        filenames = list(dict.fromkeys(re.findall(r'filename:\s*"([^"/\\]+\.ttf)"', metadata)))
        if not filenames:
            raise ValueError(f"No TTF files declared for {family}")
        license_data = _read(f"{directory}/{license_name}")
        # Validate every payload before writing; a 200 HTML error page is not a font.
        # Google uses brackets/commas for variable axes. Keep font bytes intact
        # but give the downloaded files portable package-safe names.
        payloads = [(name.replace("[", "-").replace("]", "").replace(",", "-"),
                     _read(f"{directory}/{name}")) for name in filenames]
        for _, data in payloads:
            with TTFont(BytesIO(data)):
                pass
        folder.mkdir(parents=True, exist_ok=True)
        for name, data in payloads:
            (folder / name).write_bytes(data)
        license_path = folder / f"{slug}-{license_name}"
        license_path.write_bytes(license_data)
        result = {"family": family, "fonts": [describe_font(folder / n) for n, _ in payloads],
                  "license": str(license_path), "source": f"https://github.com/google/fonts/tree/main/{directory}"}
        receipt.write_text(json.dumps(result, indent=2) + "\n")
        return result
    raise ValueError(f"Google Fonts family not found: {family}. Check the family name or use a supplied font file.")


def font_face(path, family=None):
    """Return @font-face CSS embedding one actual font, with its weight/style.

    Pass the same family alias in application CSS; call for each desired file.
    This embeds bytes only, and does not choose typography or alter a font.
    """
    info = describe_font(path)
    name = family or info["family"]
    if not isinstance(name, str) or not re.fullmatch(r"[\w -]{1,100}", name):
        raise ValueError("Use a simple font-family name or alias")
    data = b64encode(Path(path).read_bytes()).decode("ascii")
    suffix = Path(path).suffix.lower().lstrip(".")
    mime = {"ttf": "ttf", "otf": "otf", "woff": "woff", "woff2": "woff2"}.get(suffix)
    if not mime:
        raise ValueError("Use a TTF, OTF, WOFF or WOFF2 file")
    return (f"@font-face{{font-family:'{name}';src:url(data:font/{mime};base64,{data});"
            f"font-weight:{info['weight']};font-style:{info['css_style']};font-display:block;}}")


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
        placed = []
        for index, char in enumerate(text):
            x = (metrics.getlength(text[:index + 1], **kwargs) - metrics.getlength(char, **kwargs)) * scale + index * tracking
            glyph = glyphs[cmap[ord(char)]]
            bounding = BoundsPen(glyphs)
            glyph.draw(bounding)
            if bounding.bounds:
                x0, y0, x1, y1 = bounding.bounds
                placed.append((x, glyph, (x + x0 * scale, -y1 * scale, x + x1 * scale, -y0 * scale)))
        if not placed:
            raise ValueError("The chosen text has no visible glyph outlines")
        left = min(b[0] for *_, b in placed) - padding
        top = min(b[1] for *_, b in placed) - padding
        width = max(b[2] for *_, b in placed) + padding - left
        height = max(b[3] for *_, b in placed) + padding - top
        # Placement, the font's y-up flip and the zero origin are baked into the
        # coordinates, so the paths carry no transforms for an importer to misread.
        paths = []
        for x, glyph, _ in placed:
            pen = SVGPathPen(glyphs, ntos=_number)
            glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x - left, -top)))
            paths.append(f'<path d="{pen.getCommands()}"/>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{_number(width)}" height="{_number(height)}" '
                f'viewBox="0 0 {_number(width)} {_number(height)}" role="img" aria-label="{escape(text, quote=True)}">'
                f'<g fill="{fill}">{"".join(paths)}</g></svg>')


def _number(value):
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text
