"""Fetch agent-chosen Google Fonts and embed actual fonts in editable HTML.

Network acquisition is explicit; this is not a recipe or a font selector.
Source: https://github.com/google/fonts (family metadata and license files).
"""
from base64 import b64encode
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fontTools.ttLib import TTFont

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
