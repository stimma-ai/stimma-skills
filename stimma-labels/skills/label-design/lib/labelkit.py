"""Offline label stock lookup, frozen sheet sources and physical-size PDF output.

Coordinates are PDF points (72/in), measured from the sheet's top-left.
The catalog is community-maintained geometry, not a print certification.
"""

from __future__ import annotations

import base64
import copy
import io
import json
import math
import re
import zipfile
from pathlib import Path

from PIL import Image

_DATA = Path(__file__).parent / "data"
MAX_PAGES = 100
MAX_SOURCE_BYTES = 128 * 1024 * 1024


def _json(value):
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    )


def _number(value, name, minimum=0):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < minimum
    ):
        raise ValueError(f"{name} must be a finite number >= {minimum}")
    return float(value)


def _catalog():
    return json.loads((_DATA / "avery.json").read_text())


def lookup(code: str) -> dict:
    """Resolve an exact Avery code or alias; return a fresh frozen stock dict."""
    key = re.sub(r"^avery\s*", "", str(code).strip(), flags=re.I).upper()
    c = _catalog()
    keys = {k.upper(): k for k in [*c["stocks"], *c["aliases"]]}
    if key not in keys:
        raise ValueError(
            f"Avery {key} is not in the bundled catalog. Ask for the corrected product number or obtain its official template, including paper, margins and slot positions. Label dimensions and count alone cannot establish the sheet layout. Use search() to find verified catalog codes, not to substitute a similar size."
        )
    requested = keys[key]
    canonical = c["aliases"].get(requested, requested)
    result = copy.deepcopy(c["stocks"][canonical])
    result["requested_code"] = requested
    validate_stock(result)
    return result


def search(query="", limit=30) -> list[dict]:
    """Search codes/descriptions/shapes. Summary includes aliases and physical size."""
    c = _catalog()
    rows = []
    for code in sorted([*c["stocks"], *c["aliases"]]):
        s = c["stocks"][c["aliases"].get(code, code)]
        if query.casefold() not in f"{code} {s['description']} {s['shape']}".casefold():
            continue
        rows.append(
            {
                "code": code,
                "canonical_code": s["code"],
                "description": s["description"],
                "shape": s["shape"],
                "size_in": [
                    round(s["width_pt"] / 72, 4),
                    round(s["height_pt"] / 72, 4),
                ],
                "labels_per_sheet": len(s["slots_pt"]),
            }
        )
    return rows[:limit]


def validate_stock(stock):
    if not isinstance(stock, dict):
        raise ValueError("stock must be a resolved geometry dict")
    w = _number(stock.get("width_pt"), "label width", 0.01)
    h = _number(stock.get("height_pt"), "label height", 0.01)
    paper = stock.get("paper_pt", [])
    if len(paper) != 2:
        raise ValueError("paper_pt must contain width and height")
    pw, ph = [_number(x, "paper dimension", 1) for x in paper]
    if max(pw, ph) > 7200:
        raise ValueError("paper exceeds 100 inches")
    shape = stock.get("shape")
    if shape not in ("rectangle", "round", "ellipse", "cd"):
        raise ValueError(f"Unsupported shape {shape!r}")
    if shape in ("round", "cd") and abs(w - h) > 0.001:
        raise ValueError("Round labels require equal width and height")
    corner = _number(stock.get("corner_pt", 0), "corner radius")
    hole = _number(stock.get("hole_radius_pt", 0), "hole radius")
    safe = _number(stock.get("safe_inset_pt", 0), "safe inset")
    if corner > min(w, h) / 2 or hole >= min(w, h) / 2 or safe >= min(w, h) / 2:
        raise ValueError("Corner/hole/safe inset does not fit the label")
    slots = stock.get("slots_pt", [])
    if not slots or len(slots) > 1000:
        raise ValueError("A sheet must contain 1 to 1000 slots")
    seen = set()
    for p in slots:
        if len(p) != 2:
            raise ValueError("Each slot needs [x,y] in points")
        x, y = [_number(v, "slot coordinate") for v in p]
        if x + w > pw + 0.05 or y + h > ph + 0.05:
            raise ValueError(
                f"Stock {stock.get('code')}: a label extends outside the paper; verify the source template"
            )
        k = (round(x, 5), round(y, 5))
        if k in seen:
            raise ValueError("Duplicate slot")
        seen.add(k)
    return stock


def design_spec(stock, dpi=300, bleed_mm=0, pixel_multiple=1) -> dict:
    """Compute trim/artwork sizes, safe boundary and target pixels before design."""
    s = lookup(stock) if isinstance(stock, str) else validate_stock(stock)
    dpi = _number(dpi, "dpi", 72)
    bleed = _number(bleed_mm, "bleed_mm") * 72 / 25.4
    w, h = s["width_pt"], s["height_pt"]
    pixels = [
        math.ceil((w + 2 * bleed) * dpi / 72),
        math.ceil((h + 2 * bleed) * dpi / 72),
    ]
    if (
        isinstance(pixel_multiple, bool)
        or not isinstance(pixel_multiple, int)
        or not 1 <= pixel_multiple <= 256
    ):
        raise ValueError(
            "pixel_multiple must be an integer from 1 to 256, taken from the generation tool"
        )
    generation = pixels
    if pixel_multiple > 1:
        m = pixel_multiple
        cw, ch = [math.ceil(v / m) for v in pixels]
        ratio = (w + 2 * bleed) / (h + 2 * bleed)
        candidates = [
            (a * m, b * m)
            for a in range(cw, cw + 32)
            for b in range(ch, ch + 32)
            if abs((a / b) / ratio - 1) <= 0.015
        ]
        if not candidates:
            raise ValueError(
                "No nearby supported generation size; use a composed final canvas"
            )
        generation = list(
            min(candidates, key=lambda p: (p[0] * p[1], abs(p[0] / p[1] - ratio)))
        )
    code = s.get("requested_code", s["code"])
    summary = f"{s.get('brand', 'Custom')} {code}: {w / 72:g} x {h / 72:g} inch labels; {len(s['slots_pt'])} per {s['paper_pt'][0] / 72:g} x {s['paper_pt'][1] / 72:g} inch sheet."
    return {
        "stock": code,
        "summary": summary,
        "shape": s["shape"],
        "trim_in": [w / 72, h / 72],
        "paper_in": [v / 72 for v in s["paper_pt"]],
        "generation_px": generation,
        "pixel_multiple": pixel_multiple,
        "trim_mm": [w * 25.4 / 72, h * 25.4 / 72],
        "trim_aspect": w / h,
        "artwork_aspect": (w + 2 * bleed) / (h + 2 * bleed),
        "artwork_px": pixels,
        "safe_inset_mm": s.get("safe_inset_pt", 0) * 25.4 / 72,
        "hole_radius_mm": s.get("hole_radius_pt", 0) * 25.4 / 72,
        "bleed_mm": bleed_mm,
        "labels_per_sheet": len(s["slots_pt"]),
        "paper_mm": [v * 25.4 / 72 for v in s["paper_pt"]],
        "dpi": dpi,
    }


def _png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _validate_job(job, images):
    if job.get("format") != 1:
        raise ValueError("Unsupported label source format")
    s = validate_stock(job["stock"])
    bleed = _number(job.get("bleed_pt", 0), "bleed")
    if bleed > 18:
        raise ValueError("Bleed exceeds 0.25 inch")
    min_dpi = _number(job.get("min_dpi", 150), "min_dpi", 72)
    pages = job.get("pages", [])
    if not 1 <= len(pages) <= MAX_PAGES:
        raise ValueError(f"Use 1 to {MAX_PAGES} pages")
    if not images or len(images) > 1000:
        raise ValueError("Use 1 to 1000 designs")
    used = set()
    for page in pages:
        if not isinstance(page, list) or len(page) != len(s["slots_pt"]):
            raise ValueError(
                f"Each page needs exactly {len(s['slots_pt'])} slots in catalog order; use None for blanks"
            )
        for key in page:
            if key is not None:
                if not isinstance(key, str) or key not in images:
                    raise ValueError(f"Unknown design in page: {key!r}")
                used.add(key)
    if not used:
        raise ValueError("At least one slot must contain a design")
    w, h = s["width_pt"] + 2 * bleed, s["height_pt"] + 2 * bleed
    # Full bleed is only safe when every expanded bounding box fits the sheet and
    # stays outside every other label, even an intentionally blank label.
    if bleed:
        pw, ph = s["paper_pt"]
        slots = s["slots_pt"]
        for i, (x, y) in enumerate(slots):
            if (
                x - bleed < 0
                or y - bleed < 0
                or x + s["width_pt"] + bleed > pw
                or y + s["height_pt"] + bleed > ph
            ):
                raise ValueError(
                    "Bleed extends beyond the sheet; use zero bleed or a suitable stock"
                )
            for xx, yy in slots[i + 1 :]:
                if (
                    x - bleed < xx + s["width_pt"] + bleed - 0.001
                    and xx - bleed < x + s["width_pt"] + bleed - 0.001
                    and y - bleed < yy + s["height_pt"] + bleed - 0.001
                    and yy - bleed < y + s["height_pt"] + bleed - 0.001
                ):
                    raise ValueError(
                        "Bleed overlaps neighboring label areas; use zero bleed or a suitable stock"
                    )
    checks = {}
    for key in sorted(used):
        d = job["designs"][key]
        fit = d.get("fit", "strict")
        if fit not in ("strict", "contain", "cover"):
            raise ValueError("fit must be strict, contain or cover")
        rotation = d.get("rotation", 0)
        if rotation not in (0, 90, 180, 270):
            raise ValueError("rotation must be 0,90,180,270 clockwise degrees")
        image = images[key]
        iw, ih = image.size if rotation in (0, 180) else image.size[::-1]
        mismatch = abs((iw / ih) / (w / h) - 1)
        if fit == "strict" and mismatch > 0.015:
            raise ValueError(
                f"{key}: aspect {iw / ih:.4f} does not match artwork {w / h:.4f}; prepare the correct canvas or explicitly choose contain/cover"
            )
        scale = min(w / iw, h / ih) if fit == "contain" else max(w / iw, h / ih)
        effective_dpi = 72 / scale
        if effective_dpi < min_dpi:
            raise ValueError(
                f"{key}: only {effective_dpi:.0f} effective dpi (minimum {min_dpi:g}); use higher-resolution artwork"
            )
        checks[key] = {
            "effective_dpi": round(effective_dpi, 2),
            "pixels": [iw, ih],
            "fit": fit,
            "rotation": rotation,
        }
    return checks


def prepare_source(
    stock, designs, pages, out="label-source.zip", *, bleed_mm=0, min_dpi=150
):
    """Freeze geometry + artwork + explicit assignments into a portable recipe input.

    designs={name: PNG/JPEG path OR {path,fit='strict',rotation=0}}.
    pages=[[design_name or None, ...]]; one entry per slot, row-major catalog order.
    All layouts including repeats/rows/quantities compile to this same form.
    Artwork is stored losslessly without source paths or image metadata.
    Returns {path, stock, pages, labels, designs} with actual effective dpi.
    """
    s = (
        lookup(stock)
        if isinstance(stock, str)
        else copy.deepcopy(validate_stock(stock))
    )
    job = {
        "format": 1,
        "stock": s,
        "pages": pages,
        "bleed_pt": _number(bleed_mm, "bleed_mm") * 72 / 25.4,
        "min_dpi": min_dpi,
        "designs": {},
    }
    images = {}
    for n, (key, value) in enumerate(sorted(designs.items())):
        if not isinstance(key, str) or not key or len(key) > 120:
            raise ValueError(
                "Design names must be nonempty strings up to 120 characters"
            )
        d = {"path": value} if isinstance(value, (str, Path)) else dict(value)
        with Image.open(d["path"]) as image:
            images[key] = image.convert("RGBA")
        job["designs"][key] = {
            "file": f"artwork/{n:04d}.png",
            "fit": d.get("fit", "strict"),
            "rotation": d.get("rotation", 0),
        }
    checks = _validate_job(job, images)
    payload = {
        "source.json": _json(job).encode(),
        **{job["designs"][key]["file"]: _png(im) for key, im in images.items()},
    }
    if sum(map(len, payload.values())) > MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds 128 MiB")
    output = Path(out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return {
        "path": str(output),
        "stock": s.get("requested_code", s["code"]),
        "summary": design_spec(s)["summary"],
        "pages": len(pages),
        "labels": sum(v is not None for p in pages for v in p),
        "designs": checks,
    }


def read_source(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if (
            len(names) != len(set(names))
            or sum(i.file_size for i in z.infolist()) > MAX_SOURCE_BYTES
        ):
            raise ValueError("Duplicate entries or oversized label source")
        if len(names) > 1001 or any(
            n.startswith("/") or ".." in n.split("/") or "\\" in n for n in names
        ):
            raise ValueError("Unsafe label source paths")
        job = json.loads(z.read("source.json"))
        images = {}
        for key, d in job["designs"].items():
            with Image.open(io.BytesIO(z.read(d["file"]))) as im:
                images[key] = im.convert("RGBA")
    return job, images, _validate_job(job, images)


def _shape(s, x, y, bleed=0, attrs=""):
    w, h = s["width_pt"], s["height_pt"]
    if s["shape"] == "rectangle":
        return f'<rect x="{x - bleed}" y="{y - bleed}" width="{w + 2 * bleed}" height="{h + 2 * bleed}" rx="{s.get("corner_pt", 0) + bleed}" {attrs}/>'
    cx, cy = x + w / 2, y + h / 2
    if s["shape"] != "cd":
        return f'<ellipse cx="{cx}" cy="{cy}" rx="{w / 2 + bleed}" ry="{h / 2 + bleed}" {attrs}/>'
    r = w / 2 + bleed
    hole = max(0, s["hole_radius_pt"] - bleed)
    # Opposite winding punches out the center, including in the PDF clipping path.
    path = f"M {cx - r},{cy} a {r},{r} 0 1,0 {2 * r},0 a {r},{r} 0 1,0 {-2 * r},0 Z "
    path += f"M {cx - hole},{cy} a {hole},{hole} 0 1,1 {2 * hole},0 a {hole},{hole} 0 1,1 {-2 * hole},0 Z"
    return f'<path d="{path}" {attrs}/>'


def render_source(path, *, offset_x_mm=0, offset_y_mm=0, alignment=True):
    """Return deterministic run files; preview PNGs are renders of labels.pdf itself."""
    from weasyprint import HTML, default_url_fetcher
    import pypdfium2 as pdfium

    job, images, checks = read_source(path)
    s = job["stock"]
    pw, ph = s["paper_pt"]
    bleed = job["bleed_pt"]
    offsets = []
    for v in (offset_x_mm, offset_y_mm):
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or abs(v) > 10
        ):
            raise ValueError("Printer offsets must be finite millimeters within +/-10")
        offsets.append(v * 72 / 25.4)
    ox, oy = offsets
    prepared = {}
    for key, im in images.items():
        rotation = job["designs"][key]["rotation"]
        if rotation:
            im = im.rotate(-rotation, expand=True)
        prepared[key] = (im.size, base64.b64encode(_png(im)).decode("ascii"))

    def svg(page, guides=False):
        content = []
        for i, ((x, y), key) in enumerate(zip(s["slots_pt"], page)):
            x += ox
            y += oy
            if key is not None and not guides:
                w, h = s["width_pt"] + 2 * bleed, s["height_pt"] + 2 * bleed
                if (
                    x - bleed < -0.05
                    or y - bleed < -0.05
                    or x + w - bleed > pw + 0.05
                    or y + h - bleed > ph + 0.05
                ):
                    raise ValueError(
                        "Printer offset moves printed artwork outside the paper"
                    )
                (iw, ih), data = prepared[key]
                fit = job["designs"][key]["fit"]
                scale = min(w / iw, h / ih) if fit == "contain" else max(w / iw, h / ih)
                dw, dh = iw * scale, ih * scale
                content.append(
                    f'<defs><clipPath id="c{i}">'
                    + _shape(s, x, y, bleed)
                    + "</clipPath></defs>"
                )
                content.append(
                    f'<g clip-path="url(#c{i})"><image x="{x - bleed + (w - dw) / 2}" y="{y - bleed + (h - dh) / 2}" width="{dw}" height="{dh}" href="data:image/png;base64,{data}"/></g>'
                )
            if guides:
                content.append(
                    _shape(
                        s, x, y, attrs='fill="none" stroke="#333333" stroke-width="0.4"'
                    )
                )
                content.append(
                    f'<text x="{x + 4}" y="{y + 10}" font-size="7" fill="#333333">{i + 1}</text>'
                )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{pw}pt" height="{ph}pt" viewBox="0 0 {pw} {ph}">'
            + "".join(content)
            + "</svg>"
        )

    def pdf(pages, guides=False):
        def local_only(url, **kwargs):
            if not url.startswith("data:"):
                raise ValueError("Label PDF resources must be embedded")
            return default_url_fetcher(url, **kwargs)

        html = f"<style>@page{{size:{pw}pt {ph}pt;margin:0}}html,body{{margin:0;padding:0;font-size:0}}.sheet{{width:{pw}pt;height:{ph}pt;break-after:page}}.sheet:last-child{{break-after:auto}}svg{{display:block}}</style>"
        html += "".join(
            '<div class="sheet">' + svg(p, guides) + "</div>" for p in pages
        )
        return HTML(string=html, url_fetcher=local_only).write_pdf()

    data = pdf(job["pages"])
    outputs = {"labels.pdf": data}
    if alignment:
        outputs["alignment-test.pdf"] = pdf([[None] * len(s["slots_pt"])], True)
    doc = pdfium.PdfDocument(data)
    try:
        if len(doc) != len(job["pages"]):
            raise ValueError("PDF page count differs from sheet plan")
        for n in range(len(doc)):
            page = doc[n]
            try:
                if any(
                    abs(a - b) > 0.02 for a, b in zip(page.get_size(), s["paper_pt"])
                ):
                    raise ValueError("PDF paper size differs from sheet plan")
                bitmap = page.render(scale=1.5)
                try:
                    outputs[f"preview/sheet-{n + 1:03d}.png"] = _png(bitmap.to_pil())
                finally:
                    bitmap.close()
            finally:
                page.close()
    finally:
        doc.close()
    report = {
        "format": 1,
        "summary": design_spec(s)["summary"],
        "stock": s,
        "pages": job["pages"],
        "designs": checks,
        "bleed_mm": bleed * 25.4 / 72,
        "printer_offset_mm": [offset_x_mm, offset_y_mm],
        "physical_print_tested": False,
    }
    outputs["sheet-plan.json"] = _json(report).encode()
    code = s.get("requested_code", s["code"])
    instructions = f"""Avery {code} - printable label sheets

Print labels.pdf, not the package cover/guide PDF.
Label trim: {s["width_pt"] / 72:g} x {s["height_pt"] / 72:g} inches.
Paper: {pw / 72:.5g} x {ph / 72:.5g} inches; {len(job["pages"])} sheet(s).
Print at Actual Size / 100%. Disable Fit, Shrink, and multiple pages per sheet.
Use the correct paper size, single-sided printing and a label-compatible printer/media setting.
Test on plain paper and compare against the physical sheet before using label stock.
The separate alignment-test.pdf (when included) is a numbered outline proof for plain paper only.
Preview images are screen proofs of the same PDF, not print substitutes.
Printer shift: {offset_x_mm:g} mm right, {offset_y_mm:g} mm down.

Geometry source: {s.get("source", "user-supplied geometry")}
Frozen stock, slot assignments and effective image resolution are in sheet-plan.json.
A blank slot intentionally prints nothing. Source artwork and geometry are retained by the package.
The PDF contains prepared raster artwork at the reported effective resolution; it is not PDF/X.
No physical print/alignment test has been performed by this recipe.
"""
    outputs["PRINTING.txt"] = instructions.encode()
    return outputs
