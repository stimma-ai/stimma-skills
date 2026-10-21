"""Prepare cut files for Cricut Design Space.

``prepare_svg`` rewrites an SVG into one flat-colour path per cut layer:
transforms baked into coordinates, overlapping and duplicate contours merged
into a single outline (curves kept wherever an outline survives untouched),
strokes outlined to fills, and the canvas sized at 96 units per inch. It then
renders the original and the repaired file and reports how closely they agree
under both fill rules, since an importer may apply either.

``make_sticker`` gives transparent artwork an even die-cut border and sizes it
for Print Then Cut. ``prepare_raster`` crops, sizes and tags a finished PNG for
upload as a cut image or a Print Then Cut image, and reports what Design Space
will see in it.

Pure Python over fontTools, numpy, scipy and Pillow, all in the app's stack.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from fontTools.pens.basePen import BasePen
from fontTools.svgLib.path.parser import parse_path
from PIL import Image

PX_PER_IN = 96
# Cricut help, "How large can I Print Then Cut?" (edited 2025-03-19): Explore,
# Maker and Venture. Width x height in inches, portrait; Design Space may rotate.
PRINT_THEN_CUT_MAX_IN = {"letter": (7.44, 9.94), "a4": (7.2, 10.62)}
MAT_MARGIN_IN = 0.25

_UNITS = {"in": 96.0, "cm": 96 / 2.54, "mm": 96 / 25.4, "pt": 96 / 72, "pc": 16.0}
_NAMED = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000",
    "blue": "#0000ff", "yellow": "#ffff00", "orange": "#ffa500", "purple": "#800080",
    "pink": "#ffc0cb", "gray": "#808080", "grey": "#808080", "brown": "#a52a2a",
    "navy": "#000080", "teal": "#008080", "gold": "#ffd700", "silver": "#c0c0c0",
}
_INHERITED = {"fill", "fill-rule", "fill-opacity", "stroke", "stroke-width", "stroke-linecap",
              "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray", "stroke-opacity",
              "visibility", "color"}
_SHAPES = {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line"}
_SNAP = 1e-4          # px: intersection parameters closer than this to an end are that end
_GRID = 1e-3          # px (about 1e-5 in): the outline graph's vertex grid


# ---------------------------------------------------------------- SVG input

def _tag(el):
    return el.tag.rsplit("}", 1)[-1]


def _length(value, axis_px=None):
    """Parse an SVG length into px at 96/in. Returns (px, absolute_unit?)."""
    m = re.fullmatch(r"\s*([-+]?[\d.]+(?:e[-+]?\d+)?)\s*([a-z%]*)\s*", str(value), re.I)
    if not m:
        raise ValueError(f"Unreadable SVG length: {value!r}")
    number, unit = float(m.group(1)), m.group(2).lower()
    if unit == "%":
        if axis_px is None:
            raise ValueError("Percentage sizes need an explicit canvas size")
        return number / 100 * axis_px, False
    if unit in ("", "px"):
        return number, False
    if unit not in _UNITS:
        raise ValueError(f"Unsupported SVG unit: {unit}")
    return number * _UNITS[unit], True


def _mul(a, b):
    """Affine product a*b (apply b first); matrices are (a, b, c, d, e, f)."""
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
            a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _transform(text):
    m = _IDENTITY
    for name, args in re.findall(r"([a-zA-Z]+)\s*\(([^)]*)\)", text or ""):
        v = [float(x) for x in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", args)]
        name = name.lower()
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate":
            r = math.radians(v[0])
            t = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)
            if len(v) == 3:
                t = _mul(_mul((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == "skewx":
            t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewy":
            t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            raise ValueError(f"Unsupported transform: {name}({args})")
        m = _mul(m, t)
    return m


def _apply(m, p):
    return (m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5])


def _color(value, current="#000000"):
    v = (value or "").strip().lower()
    if v in ("", "none", "transparent"):
        return None
    if v == "currentcolor":
        return _color(current)
    if v in _NAMED:
        return _NAMED[v]
    if re.fullmatch(r"#[0-9a-f]{3}", v):
        return "#" + "".join(c * 2 for c in v[1:])
    if re.fullmatch(r"#[0-9a-f]{6}", v):
        return v
    m = re.fullmatch(r"rgba?\(\s*([\d.]+%?)\s*,?\s*([\d.]+%?)\s*,?\s*([\d.]+%?)[^)]*\)", v)
    if m:
        ch = [float(c[:-1]) * 2.55 if c.endswith("%") else float(c) for c in m.groups()]
        return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in ch)
    return v


def _css_rules(root):
    rules = {}
    for style in root.iter():
        if _tag(style) != "style" or not style.text:
            continue
        css = re.sub(r"/\*.*?\*/", "", style.text, flags=re.S)
        for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
            decls = _declarations(body)
            for sel in selectors.split(","):
                sel = sel.strip()
                if re.fullmatch(r"\.[\w-]+", sel):
                    rules.setdefault(sel[1:], {}).update(decls)
    return rules


def _declarations(text):
    out = {}
    for part in (text or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


class _Recorder(BasePen):
    """Collect contours as segment lists in local coordinates."""

    def __init__(self):
        super().__init__(None)
        self.contours = []

    def _moveTo(self, pt):
        self.contours.append({"start": pt, "segs": [], "closed": False})

    def _lineTo(self, pt):
        self.contours[-1]["segs"].append(("L", pt))

    def _curveToOne(self, p1, p2, p3):
        self.contours[-1]["segs"].append(("C", p1, p2, p3))

    def _qCurveToOne(self, p1, p2):
        self.contours[-1]["segs"].append(("Q", p1, p2))

    def _closePath(self):
        self.contours[-1]["closed"] = True

    def _endPath(self):
        pass


def _num(el, name, default=0.0):
    v = el.get(name)
    return default if v is None else float(re.sub(r"[a-z%]+$", "", v.strip(), flags=re.I) or default)


def _shape_d(el):
    tag = _tag(el)
    if tag == "path":
        return el.get("d", "")
    if tag == "rect":
        x, y, w, h = (_num(el, k) for k in ("x", "y", "width", "height"))
        if w <= 0 or h <= 0:
            return ""
        rx, ry = el.get("rx"), el.get("ry")
        rx = _num(el, "rx") if rx is not None else (_num(el, "ry") if ry is not None else 0)
        ry = _num(el, "ry") if ry is not None else rx
        rx, ry = min(rx, w / 2), min(ry, h / 2)
        if rx <= 0 or ry <= 0:
            return f"M{x} {y}H{x + w}V{y + h}H{x}Z"
        return (f"M{x + rx} {y}H{x + w - rx}A{rx} {ry} 0 0 1 {x + w} {y + ry}V{y + h - ry}"
                f"A{rx} {ry} 0 0 1 {x + w - rx} {y + h}H{x + rx}A{rx} {ry} 0 0 1 {x} {y + h - ry}"
                f"V{y + ry}A{rx} {ry} 0 0 1 {x + rx} {y}Z")
    if tag in ("circle", "ellipse"):
        cx, cy = _num(el, "cx"), _num(el, "cy")
        rx = _num(el, "r") if tag == "circle" else _num(el, "rx")
        ry = _num(el, "r") if tag == "circle" else _num(el, "ry")
        if rx <= 0 or ry <= 0:
            return ""
        return (f"M{cx - rx} {cy}A{rx} {ry} 0 1 0 {cx + rx} {cy}"
                f"A{rx} {ry} 0 1 0 {cx - rx} {cy}Z")
    if tag in ("polygon", "polyline"):
        pts = re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", el.get("points", ""))
        if len(pts) < 4:
            return ""
        d = "M" + " ".join(pts[:2]) + "L" + " ".join(pts[2:])
        return d + ("Z" if tag == "polygon" else "")
    if tag == "line":
        return f"M{_num(el, 'x1')} {_num(el, 'y1')}L{_num(el, 'x2')} {_num(el, 'y2')}"
    return ""


def _walk(root, warnings):
    """Yield (element, style, ctm) for every drawable shape, resolving <use>."""
    ids = {el.get("id"): el for el in root.iter() if el.get("id")}
    classes = _css_rules(root)
    seen_warnings = set()

    def warn(text):
        if text not in seen_warnings:
            seen_warnings.add(text)
            warnings.append(text)

    def visit(el, style, ctm, depth):
        tag = _tag(el)
        if depth > 32 or tag in ("defs", "symbol", "style", "title", "desc", "metadata",
                                 "clipPath", "mask", "linearGradient", "radialGradient",
                                 "pattern", "filter", "marker"):
            return
        own = {}
        for cls in (el.get("class") or "").split():
            own.update(classes.get(cls, {}))
        for k, v in el.attrib.items():
            k = k.rsplit("}", 1)[-1]
            if k in _INHERITED or k in ("opacity", "display"):
                own[k] = v
        own.update(_declarations(el.get("style")))
        if own.get("display", "").strip() == "none":
            return
        s = {k: v for k, v in style.items() if k in _INHERITED}
        s.update(own)
        s["opacity"] = float(style.get("opacity", 1)) * float(own.get("opacity", 1))
        ctm = _mul(ctm, _transform(el.get("transform")))
        for attr, label in (("clip-path", "clip-path"), ("mask", "mask"), ("filter", "filter")):
            if el.get(attr) or own.get(attr):
                warn(f"{label} ignored: Design Space cannot use it; everything under it is cut whole. "
                     "Redraw the visible result as plain shapes.")
        if tag == "use":
            ref = ids.get((el.get("href") or el.get("{http://www.w3.org/1999/xlink}href") or "").lstrip("#"))
            if ref is not None:
                ctm = _mul(ctm, (1, 0, 0, 1, _num(el, "x"), _num(el, "y")))
                if _tag(ref) == "symbol":
                    for child in ref:
                        visit(child, s, ctm, depth + 1)
                else:
                    visit(ref, s, ctm, depth + 1)
            return
        if tag in ("text", "tspan", "textPath"):
            warn("Live <text> dropped: Design Space substitutes fonts. Outline text to paths first "
                 "and prepare again.")
            return
        if tag in ("image", "foreignObject"):
            warn(f"<{tag}> dropped: an embedded picture is not a cut path. Deliver it as a Print Then Cut PNG.")
            return
        if tag in _SHAPES:
            yield el, s, ctm
            return
        if tag == "svg" and depth > 0:
            warn("Nested <svg> treated as a group; its own viewBox and clipping are ignored.")
        for child in el:
            yield from visit(child, s, ctm, depth + 1)

    yield from visit(root, {"fill": "#000000", "opacity": 1}, _IDENTITY, 0)


def _gradient_color(root, value):
    ident = re.fullmatch(r"\s*url\(\s*['\"]?#([^)'\"]+)['\"]?\s*\).*", value or "")
    if not ident:
        return None
    for el in root.iter():
        if el.get("id") == ident.group(1):
            for stop in el.iter():
                if _tag(stop) == "stop":
                    st = _declarations(stop.get("style"))
                    return _color(st.get("stop-color") or stop.get("stop-color") or "#000000")
    return None


# ---------------------------------------------------------------- geometry

def _flatten_contours(contours, m, tol, close=True):
    """Transform contours by m and flatten. Returns pieces and the curve table.

    Each piece row: x0 y0 x1 y1 seg t0 t1. ``curves[seg]`` keeps the exact
    transformed segment so untouched outline can be written back as curves.
    """
    pieces, curves, closed_open = [], [], 0
    for contour in contours:
        start = _apply(m, contour["start"])
        cur = start
        segs = list(contour["segs"])
        if not segs:
            continue
        if (close or contour["closed"]) and math.dist(_apply(m, segs[-1][-1]), start) > _SNAP:
            segs.append(("L", contour["start"]))
            closed_open += not contour["closed"]
        for seg in segs:
            pts = [cur] + [_apply(m, p) for p in seg[1:]]
            kind = seg[0]
            if kind == "L":
                n = 1
            else:
                a = np.array(pts)
                if kind == "C":
                    second = max(np.linalg.norm(a[2] - 2 * a[1] + a[0]), np.linalg.norm(a[3] - 2 * a[2] + a[1]))
                    n = math.ceil(math.sqrt(0.75 * second / tol)) if second > 0 else 1
                else:
                    second = np.linalg.norm(a[2] - 2 * a[1] + a[0])
                    n = math.ceil(math.sqrt(0.25 * second / tol)) if second > 0 else 1
                n = max(1, min(n, 2000))
            sid = len(curves)
            curves.append((kind, pts))
            ts = np.linspace(0, 1, n + 1)
            xy = _bezier(kind, pts, ts)
            xy[0], xy[-1] = pts[0], pts[-1]
            for i in range(n):
                pieces.append((xy[i, 0], xy[i, 1], xy[i + 1, 0], xy[i + 1, 1], sid, ts[i], ts[i + 1]))
            cur = pts[-1]
    return pieces, curves, closed_open


def _bezier(kind, pts, ts):
    p = np.array(pts, float)
    t = np.asarray(ts, float)[:, None]
    if kind == "L":
        return p[0] + (p[1] - p[0]) * t
    if kind == "Q":
        return (1 - t) ** 2 * p[0] + 2 * (1 - t) * t * p[1] + t * t * p[2]
    return ((1 - t) ** 3 * p[0] + 3 * (1 - t) ** 2 * t * p[1]
            + 3 * (1 - t) * t * t * p[2] + t ** 3 * p[3])


def _split(pts, t):
    """de Casteljau: (left, right) control points of a bezier split at t."""
    left, right, cur = [pts[0]], [pts[-1]], list(pts)
    while len(cur) > 1:
        cur = [tuple(a + (b - a) * t for a, b in zip(p, q)) for p, q in zip(cur, cur[1:])]
        left.append(cur[0])
        right.append(cur[-1])
    return left, right[::-1]


def _sub_bezier(pts, ta, tb):
    if ta > tb:
        return _sub_bezier(pts, tb, ta)[::-1]
    if tb < 1:
        pts = _split(pts, tb)[0]
    if ta > 0:
        pts = _split(pts, ta / tb if tb else 0)[1]
    return pts


def _stroke_polygons(contours, m, width, cap, join, miter_limit, tol):
    """Outline strokes as offset polygons, one per subpath side.

    Open subpaths become a single loop (left side, end cap, right side back,
    start cap); closed subpaths become a ring of two opposed loops. Inner
    corners use the intersection of the neighbouring offsets, falling back to
    a pivot through the centre line when the turn is too tight for that, so
    the polygons fill correctly under the nonzero rule.
    """
    det = abs(m[0] * m[3] - m[1] * m[2]) or 1.0
    local_tol = tol / math.sqrt(det)
    r = width / 2
    step = 2 * math.acos(max(-1.0, 1 - local_tol / max(r, 1e-9)))  # arc step within tolerance
    polys = []

    def arc(c, n0, n1, sgn):
        a0 = math.atan2(n0[1], n0[0])
        sweep = math.atan2(n0[0] * n1[1] - n0[1] * n1[0], n0[0] * n1[0] + n0[1] * n1[1])
        if sweep * sgn < 0:  # outer arc always turns with the path
            sweep += 2 * math.pi * sgn
        n = max(1, math.ceil(abs(sweep) / step))
        return [(c[0] + r * math.cos(a0 + sweep * k / n), c[1] + r * math.sin(a0 + sweep * k / n))
                for k in range(1, n)]

    def side(pts, normals, closed):
        """Offset the polyline by +normals; returns the outline points along it."""
        out = [(pts[0][0] + normals[0][0], pts[0][1] + normals[0][1])] if not closed else []
        count = len(pts) - 1
        joints = range(count) if closed else range(1, count)
        for j in joints:
            n0, n1 = normals[j - 1], normals[j % count]
            c = pts[j]
            a = (c[0] + n0[0], c[1] + n0[1])
            b = (c[0] + n1[0], c[1] + n1[1])
            turn = n0[0] * n1[1] - n0[1] * n1[0]
            cos = (n0[0] * n1[0] + n0[1] * n1[1]) / (r * r)
            if abs(turn) <= 1e-12 * r * r and cos > 0:
                out.append(a)
                continue
            # Positive turn: the offset side is on the inside of the bend.
            inner = turn > 0
            if inner:
                prev_len = math.dist(pts[j - 1], c)
                next_len = math.dist(c, pts[(j + 1) % (count + 1)] if not closed else pts[(j + 1) % count])
                back = r * math.sqrt(max(0.0, (1 - cos) / (1 + cos))) if cos > -1 + 1e-12 else math.inf
                if back < min(prev_len, next_len):
                    bx, by = n0[0] + n1[0], n0[1] + n1[1]
                    k = r / math.sqrt((1 + cos) / 2) / math.hypot(bx, by)
                    out.append((c[0] + bx * k, c[1] + by * k))
                else:
                    out += [a, c, b]
                continue
            out.append(a)
            if join == "round":
                out += arc(c, n0, n1, -1 if turn < 0 else 1)
            elif join == "miter" and cos > -1 + 1e-12 and 1 / math.sqrt((1 + cos) / 2) <= miter_limit:
                bx, by = n0[0] + n1[0], n0[1] + n1[1]
                k = r / math.sqrt((1 + cos) / 2) / math.hypot(bx, by)
                out.append((c[0] + bx * k, c[1] + by * k))
            out.append(b)
        if not closed:
            out.append((pts[-1][0] + normals[-1][0], pts[-1][1] + normals[-1][1]))
        return out

    def cap_points(end, n, outward):
        """Points from end+n round/square to end-n, on the outward side."""
        if cap == "round":
            return arc(end, n, (-n[0], -n[1]), 1 if (n[0] * outward[1] - n[1] * outward[0]) > 0 else -1)
        if cap == "square":
            ox, oy = outward[0] * r, outward[1] * r
            return [(end[0] + n[0] + ox, end[1] + n[1] + oy), (end[0] - n[0] + ox, end[1] - n[1] + oy)]
        return []

    for contour in contours:
        pieces, _, _ = _flatten_contours([contour], _IDENTITY, local_tol, close=False)
        pts = [(p[0], p[1]) for p in pieces if math.dist(p[:2], p[2:4]) > _SNAP]
        if pieces:
            pts.append((pieces[-1][2], pieces[-1][3]))
        if len(pts) < 2:
            continue
        closed = contour["closed"] and math.dist(pts[0], pts[-1]) <= _SNAP
        if closed:
            pts[-1] = pts[0]
        normals = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            length = math.hypot(x1 - x0, y1 - y0)
            normals.append((-(y1 - y0) / length * r, (x1 - x0) / length * r))
        rev_pts = pts[::-1]
        rev_normals = [(-n[0], -n[1]) for n in normals[::-1]]
        left = side(pts, normals, closed)
        right = side(rev_pts, rev_normals, closed)
        if closed:
            polys += [left, right]
            continue
        end_dir = ((pts[-1][0] - pts[-2][0]), (pts[-1][1] - pts[-2][1]))
        start_dir = ((pts[0][0] - pts[1][0]), (pts[0][1] - pts[1][1]))
        el, sl = math.hypot(*end_dir), math.hypot(*start_dir)
        loop = left + cap_points(pts[-1], normals[-1], (end_dir[0] / el, end_dir[1] / el)) + right \
            + cap_points(pts[0], rev_normals[-1], (start_dir[0] / sl, start_dir[1] / sl))
        polys.append(loop)
    return [[_apply(m, p) for p in poly] for poly in polys if len(poly) >= 3]


def _winding_inside(probes, edges, elem, rules):
    """True where a probe is inside any element under that element's fill rule."""
    k = len(probes)
    inside = np.zeros(k, bool)
    if not len(edges) or not k:
        return inside
    y0, y1 = edges[:, 1], edges[:, 3]
    ylo, yhi = np.minimum(y0, y1), np.maximum(y0, y1)
    order = np.argsort(probes[:, 1])
    for start in range(0, k, 256):
        idx = order[start:start + 256]
        P = probes[idx]
        sel = np.nonzero((yhi >= P[:, 1].min()) & (ylo <= P[:, 1].max()))[0]
        if not len(sel):
            continue
        E = edges[sel]
        py, px = P[:, 1:2], P[:, 0:1]
        up = E[None, :, 1] <= py
        cond = up != (E[None, :, 3] <= py)
        dy = E[:, 3] - E[:, 1]
        dy = np.where(dy == 0, 1, dy)
        xint = E[None, :, 0] + (py - E[None, :, 1]) * (E[None, :, 2] - E[None, :, 0]) / dy[None]
        contrib = (cond & (xint > px)) * np.where(E[:, 3] > E[:, 1], 1.0, -1.0)[None]
        groups, local = np.unique(elem[sel], return_inverse=True)
        onehot = np.zeros((len(sel), len(groups)), np.float32)
        onehot[np.arange(len(sel)), local] = 1
        w = np.rint(contrib.astype(np.float32) @ onehot).astype(int)
        evenodd = np.array([rules[g] == "evenodd" for g in groups])
        hit = np.where(evenodd[None], w % 2 != 0, w != 0)
        inside[idx] = hit.any(1)
    return inside


def _candidate_pairs(E):
    m = len(E)
    xmin, xmax = np.minimum(E[:, 0], E[:, 2]), np.maximum(E[:, 0], E[:, 2])
    ymin, ymax = np.minimum(E[:, 1], E[:, 3]), np.maximum(E[:, 1], E[:, 3])
    extent = max(xmax.max() - xmin.min(), ymax.max() - ymin.min(), 1e-9)
    lengths = np.hypot(xmax - xmin, ymax - ymin)
    cell = max(extent / max(1.0, math.sqrt(m)), float(np.median(lengths)) * 2, 1e-6)
    gx0 = np.floor((xmin - xmin.min()) / cell).astype(np.int64)
    gx1 = np.floor((xmax - xmin.min()) / cell).astype(np.int64)
    gy0 = np.floor((ymin - ymin.min()) / cell).astype(np.int64)
    gy1 = np.floor((ymax - ymin.min()) / cell).astype(np.int64)
    nx, ny = gx1 - gx0 + 1, gy1 - gy0 + 1
    cnt = nx * ny
    eid = np.repeat(np.arange(m), cnt)
    off = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    cx = gx0[eid] + off % nx[eid]
    cy = gy0[eid] + off // nx[eid]
    key = cx * (int(gy1.max()) + 2) + cy
    order = np.argsort(key, kind="stable")
    key, eid = key[order], eid[order]
    pairs = []
    d = 1
    while d < len(key):
        same = key[d:] == key[:-d]
        if not same.any():
            break
        pairs.append(np.stack([eid[:-d][same], eid[d:][same]], 1))
        d += 1
    if not pairs:
        return np.zeros((0, 2), np.int64)
    p = np.concatenate(pairs)
    p = np.sort(p, 1)
    p = p[p[:, 0] != p[:, 1]]
    return np.unique(p, axis=0)


def _split_edges(E):
    """Split edges at every crossing, T-junction and collinear overlap."""
    splits = [[] for _ in range(len(E))]
    crossings = 0
    pairs = _candidate_pairs(E)
    if len(pairs):
        a, b = E[pairs[:, 0]], E[pairs[:, 1]]
        p, r = a[:, :2], a[:, 2:4] - a[:, :2]
        q, s = b[:, :2], b[:, 2:4] - b[:, :2]
        rl, sl = np.hypot(*r.T), np.hypot(*s.T)
        denom = r[:, 0] * s[:, 1] - r[:, 1] * s[:, 0]
        qp = q - p
        tnum = qp[:, 0] * s[:, 1] - qp[:, 1] * s[:, 0]
        unum = qp[:, 0] * r[:, 1] - qp[:, 1] * r[:, 0]
        parallel = np.abs(denom) <= 1e-12 * rl * sl
        with np.errstate(divide="ignore", invalid="ignore"):
            t = tnum / denom
            u = unum / denom
        for k in np.nonzero(~parallel & (t * rl >= -_SNAP) & ((t - 1) * rl <= _SNAP)
                            & (u * sl >= -_SNAP) & ((u - 1) * sl <= _SNAP))[0]:
            i, j = pairs[k]
            ti, uj = float(t[k]), float(u[k])
            t_end = ti * rl[k] <= _SNAP or (1 - ti) * rl[k] <= _SNAP
            u_end = uj * sl[k] <= _SNAP or (1 - uj) * sl[k] <= _SNAP
            if t_end and u_end:
                continue
            if t_end:
                pt = tuple(E[i, :2]) if ti * rl[k] <= _SNAP else tuple(E[i, 2:4])
            elif u_end:
                pt = tuple(E[j, :2]) if uj * sl[k] <= _SNAP else tuple(E[j, 2:4])
            else:
                pt = (p[k, 0] + ti * r[k, 0], p[k, 1] + ti * r[k, 1])
            if not t_end:
                splits[i].append((ti, pt))
            if not u_end:
                splits[j].append((uj, pt))
            crossings += 1
        # Collinear overlaps: split each edge at the other's interior endpoints.
        with np.errstate(divide="ignore", invalid="ignore"):
            offline = np.abs(unum) / np.where(rl > 0, rl, 1)
        for k in np.nonzero(parallel & (offline <= _SNAP))[0]:
            i, j = pairs[k]
            for (src, dst) in ((i, j), (j, i)):
                d0, d1 = E[dst, :2], E[dst, 2:4] - E[dst, :2]
                ll = float(d1 @ d1)
                if ll <= 0:
                    continue
                for pt in (E[src, :2], E[src, 2:4]):
                    tt = float((pt - d0) @ d1) / ll
                    if _SNAP < tt * math.sqrt(ll) < math.sqrt(ll) - _SNAP:
                        splits[dst].append((tt, (float(pt[0]), float(pt[1]))))
    out_e, out_i, out_f = [], [], []
    for i, row in enumerate(E):
        pts = [(0.0, (row[0], row[1]))] + sorted(splits[i]) + [(1.0, (row[2], row[3]))]
        for (fa, pa), (fb, pb) in zip(pts, pts[1:]):
            if math.dist(pa, pb) > _SNAP:
                out_e.append((pa[0], pa[1], pb[0], pb[1]))
                out_i.append(i)
                out_f.append((fa, fb))
    return np.array(out_e, float).reshape(-1, 4), np.array(out_i, int), np.array(out_f, float).reshape(-1, 2), crossings


def _route_through_vertices(E, src, frac):
    """Split every edge that passes within one grid step of another vertex.

    This is the "hot pixel" half of snap rounding: once vertices are snapped,
    an edge that runs through a vertex must bend through it, or the outline
    graph is left with dangling ends where nearly collinear edges meet.
    """
    for _ in range(4):
        V = np.unique(np.concatenate([E[:, :2], E[:, 2:4]]), axis=0)
        both = np.concatenate([E, np.concatenate([V, V], 1)])
        pairs = _candidate_pairs(both)
        if not len(pairs):
            return E, src, frac
        pairs = pairs[(pairs[:, 0] < len(E)) & (pairs[:, 1] >= len(E))]
        e, v = E[pairs[:, 0]], V[pairs[:, 1] - len(E)]
        d = e[:, 2:4] - e[:, :2]
        length = np.hypot(*d.T)
        t = ((v - e[:, :2]) * d).sum(1) / length ** 2
        off = np.abs((v[:, 0] - e[:, 0]) * d[:, 1] - (v[:, 1] - e[:, 1]) * d[:, 0]) / length
        hit = (off <= _GRID) & (t * length > _GRID / 2) & ((1 - t) * length > _GRID / 2)
        if not hit.any():
            return E, src, frac
        cuts = {}
        for k in np.nonzero(hit)[0]:
            cuts.setdefault(int(pairs[k, 0]), []).append((float(t[k]), (float(v[k, 0]), float(v[k, 1]))))
        out_e, out_s, out_f = [], [], []
        for i in range(len(E)):
            fa, fb = frac[i]
            pts = [(0.0, tuple(E[i, :2]))] + sorted(cuts.get(i, [])) + [(1.0, tuple(E[i, 2:4]))]
            for (ta, pa), (tb, pb) in zip(pts, pts[1:]):
                if pa != pb:
                    out_e.append((*pa, *pb))
                    out_s.append(src[i])
                    out_f.append((fa + ta * (fb - fa), fa + tb * (fb - fa)))
        E, src, frac = np.array(out_e, float), np.array(out_s, int), np.array(out_f, float)
    return E, src, frac


def _snap(a):
    return np.round(np.asarray(a, float) / _GRID) * _GRID


def _union(pieces, elem, rules):
    """Boundary of the union of elements, as oriented loops of pieces.

    Vertices are snapped to a fine grid so that nearly coincident points are
    one point, coincident segments are merged whichever way they were drawn,
    and each remaining segment is kept when exactly one side of it is inside.
    """
    P = _snap([p[:4] for p in pieces])
    meta = np.array([(p[4], p[5], p[6]) for p in pieces], float)
    real = (P[:, 0] != P[:, 2]) | (P[:, 1] != P[:, 3])
    P, meta, elem = P[real], meta[real], np.asarray(elem)[real]
    if not len(P):
        return [], 0, 0, 0
    E, src, frac, crossings = _split_edges(P)
    E = _snap(E)
    real = (E[:, 0] != E[:, 2]) | (E[:, 1] != E[:, 3])
    E, src, frac = E[real], src[real], frac[real]
    if not len(E):
        return [], crossings, 0, 0
    E, src, frac = _route_through_vertices(E, src, frac)
    # The snapped arrangement, still carrying each piece's direction and element,
    # is the reference for inside/outside, so probes agree with the edges they test.
    reference, ref_elem = E.copy(), elem[src]
    ik = np.rint(E / _GRID).astype(np.int64)
    swap = (ik[:, 0] > ik[:, 2]) | ((ik[:, 0] == ik[:, 2]) & (ik[:, 1] > ik[:, 3]))
    canon = np.where(swap[:, None], ik[:, [2, 3, 0, 1]], ik)
    first = np.sort(np.unique(canon, axis=0, return_index=True)[1])
    duplicates = len(E) - len(first)
    E, src, frac = E[first], src[first], frac[first]
    d = E[:, 2:4] - E[:, :2]
    length = np.hypot(*d.T)
    normal = np.stack([-d[:, 1], d[:, 0]], 1) / length[:, None]
    eps = np.minimum(length * 0.25, _GRID / 100)[:, None]
    mid = (E[:, :2] + E[:, 2:4]) / 2
    left = _winding_inside(mid + normal * eps, reference, ref_elem, rules)
    right = _winding_inside(mid - normal * eps, reference, ref_elem, rules)
    seg = meta[src, 0].astype(int)
    t0 = meta[src, 1] + frac[:, 0] * (meta[src, 2] - meta[src, 1])
    t1 = meta[src, 1] + frac[:, 1] * (meta[src, 2] - meta[src, 1])
    edges = []
    for k in np.nonzero(left != right)[0]:
        a, b, ta, tb = (E[k, 0], E[k, 1]), (E[k, 2], E[k, 3]), t0[k], t1[k]
        if right[k]:  # inside on the right: flip so the inside is always on the left
            a, b, ta, tb = b, a, tb, ta
        edges.append(((float(a[0]), float(a[1])), (float(b[0]), float(b[1])), int(seg[k]), float(ta), float(tb)))
    loops, gaps = _chain(edges)
    return loops, crossings, duplicates, gaps


def _key(p):
    return (round(p[0] / _GRID), round(p[1] / _GRID))


def _chain(edges):
    """Walk oriented edges into loops, preferring to continue along one curve.

    Where the outline graph is not perfectly balanced (tiny faces around
    cusps), a walk continues from the nearest unused edge within a few grid
    steps. Returns (loops, gaps): gaps counts walks that still had to be
    closed by a straight join, which the caller reports.
    """
    reach = 5
    starts = {}
    for idx, e in enumerate(edges):
        starts.setdefault(_key(e[0]), []).append(idx)
    used = [False] * len(edges)

    def outgoing(p):
        kx, ky = _key(p)
        exact = [i for i in starts.get((kx, ky), []) if not used[i]]
        if exact:
            return exact
        near = [(abs(dx) + abs(dy), i) for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1)
                for i in starts.get((kx + dx, ky + dy), []) if not used[i]]
        return [i for _, i in sorted(near)]

    def near_key(p, q):
        (ax, ay), (bx, by) = _key(p), _key(q)
        return abs(ax - bx) <= reach and abs(ay - by) <= reach

    loops, open_chains = [], []
    for first in range(len(edges)):
        if used[first]:
            continue
        chain, cur = [], first
        while cur is not None:
            used[cur] = True
            chain.append(edges[cur])
            b, sid, tb = edges[cur][1], edges[cur][2], edges[cur][4]
            if _key(b) == _key(chain[0][0]):
                break
            options = outgoing(b)
            if not options and near_key(b, chain[0][0]):
                break
            cont = [i for i in options if edges[i][2] == sid and abs(edges[i][3] - tb) < 1e-9]
            cur = (cont or options or [None])[0]
        (loops if near_key(chain[-1][1], chain[0][0]) else open_chains).append(chain)
    # Hairline fragments left over by an unbalanced vertex are dropped; anything
    # longer is joined to the nearest open chain, or closed on itself.
    open_chains = [c for c in open_chains if sum(math.dist(e[0], e[1]) for e in c) > reach * 4 * _GRID]
    gaps = len(open_chains)
    while open_chains:
        chain = open_chains.pop()
        while True:
            end = chain[-1][1]
            gap = math.dist(end, chain[0][0])
            best = min(range(len(open_chains)), key=lambda i: math.dist(end, open_chains[i][0][0]), default=None)
            if best is None or gap <= math.dist(end, open_chains[best][0][0]):
                break
            chain = chain + open_chains.pop(best)
        loops.append(chain)
    return loops, gaps


def _area(loop):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b, *_ in loop) / 2


def _fmt(v):
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _loop_d(loop, curves):
    """Path data for one loop, writing contiguous runs of one curve as that curve."""
    n = len(loop)
    breaks = [i for i in range(n) if not (loop[i - 1][2] == loop[i][2] and abs(loop[i - 1][4] - loop[i][3]) < 1e-9)]
    if breaks:
        loop = loop[breaks[0]:] + loop[:breaks[0]]
    runs = []
    for e in loop:
        if runs and runs[-1][-1][2] == e[2] and abs(runs[-1][-1][4] - e[3]) < 1e-9:
            runs[-1].append(e)
        else:
            runs.append([e])
    start = loop[0][0]
    out = [f"M{_fmt(start[0])} {_fmt(start[1])}"]
    nodes = 0
    for run in runs:
        kind, pts = curves[run[0][2]]
        end = run[-1][1]
        ta, tb = run[0][3], run[-1][4]
        if kind == "L" or len(run) == 1 and kind != "L" and math.dist(run[0][0], end) < 0.05:
            out.append(f"L{_fmt(end[0])} {_fmt(end[1])}")
        else:
            sub = _sub_bezier([tuple(p) for p in pts], ta, tb)
            ctrl = " ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in sub[1:-1])
            out.append(f"{kind}{ctrl} {_fmt(end[0])} {_fmt(end[1])}")
        nodes += 1
    out.append("Z")
    return "".join(out), nodes


def _raster(edge_sets, x0, y0, scale, W, H):
    """Scanline-fill (edges, rule) sets; returns the union mask."""
    mask = np.zeros((H, W), bool)
    for E, rule in edge_sets:
        if not len(E):
            continue
        X = np.stack([(E[:, 0] - x0) * scale, (E[:, 1] - y0) * scale,
                      (E[:, 2] - x0) * scale, (E[:, 3] - y0) * scale], 1)
        r0 = max(0, int(math.floor(min(X[:, 1].min(), X[:, 3].min()))))
        r1 = min(H, int(math.ceil(max(X[:, 1].max(), X[:, 3].max()))) + 1)
        for band in range(r0, r1, 64):
            rows = np.arange(band, min(band + 64, r1)) + 0.5
            yy = rows[:, None]
            cond = (X[None, :, 1] <= yy) != (X[None, :, 3] <= yy)
            dy = X[:, 3] - X[:, 1]
            dy = np.where(dy == 0, 1, dy)
            xs = X[None, :, 0] + (yy - X[None, :, 1]) * (X[None, :, 2] - X[None, :, 0]) / dy[None]
            xs = np.where(cond, xs, np.inf)
            sign = np.where(cond, np.where(X[:, 3] > X[:, 1], 1, -1)[None], 0)
            order = np.argsort(xs, 1)
            xs = np.take_along_axis(xs, order, 1)
            w = np.cumsum(np.take_along_axis(sign, order, 1), 1)
            filled = (w % 2 != 0) if rule == "evenodd" else (w != 0)
            filled[:, :-1] &= np.isfinite(xs[:, 1:])
            filled[:, -1] = False
            diff = np.zeros((len(rows), W + 1), np.int32)
            ri, ci = np.nonzero(filled)
            if len(ri):
                s = np.clip(np.ceil(xs[ri, ci] - 0.5), 0, W).astype(int)
                e = np.clip(np.ceil(xs[ri, ci + 1] - 0.5), 0, W).astype(int)
                np.add.at(diff, (ri, s), 1)
                np.add.at(diff, (ri, e), -1)
                mask[band:band + len(rows)] |= np.cumsum(diff, 1)[:, :W] > 0
    return mask


# ---------------------------------------------------------------- public API

def _collect(root, root_m, tol, skip, warnings):
    """Flatten every filled or stroked shape into per-colour cut layers."""
    layers, curve_tables, open_closed = {}, {}, {}
    for el, style, ctm in _walk(root, warnings):
        if float(style.get("opacity", 1)) <= 0 or style.get("visibility") in ("hidden", "collapse"):
            continue
        d = _shape_d(el)
        if not d.strip():
            continue
        pen = _Recorder()
        try:
            parse_path(d, pen)
        except Exception as exc:  # malformed path data is the author's to fix
            warnings.append(f"Skipped a <{_tag(el)}> with unreadable path data: {exc}")
            continue
        m = _mul(root_m, ctm)
        current = style.get("color", "#000000")
        fill_value = style.get("fill", "#000000")
        fill = _color(fill_value, current)
        if fill and fill.startswith("url("):
            fill = _gradient_color(root, fill_value) or "#000000"
            warnings.append(f"Gradient or pattern fill flattened to {fill}: Design Space cuts flat colours only.")
        if float(style.get("fill-opacity", 1)) <= 0 or _tag(el) == "line":
            fill = None
        stroke = _color(style.get("stroke"), current)
        if stroke and stroke.startswith("url("):
            stroke = _gradient_color(root, style.get("stroke")) or "#000000"
        if float(style.get("stroke-opacity", 1)) <= 0:
            stroke = None
        stroke_w = _length(style.get("stroke-width", "1"))[0] if stroke else 0
        if fill and fill not in skip:
            pieces, curves, oc = _flatten_contours(pen.contours, m, tol)
            table = curve_tables.setdefault(fill, [])
            base = len(table)
            table.extend(curves)
            pieces = [(a, b, c, e, sid + base, t0, t1) for a, b, c, e, sid, t0, t1 in pieces]
            rule = "evenodd" if style.get("fill-rule", "").strip() == "evenodd" else "nonzero"
            layers.setdefault(fill, []).append((pieces, rule))
            if _tag(el) == "path":
                open_closed[fill] = open_closed.get(fill, 0) + oc
        if stroke and stroke_w > 0 and stroke not in skip:
            if style.get("stroke-dasharray", "none").strip() not in ("none", ""):
                warnings.append("Dashed stroke outlined solid: draw the dashes as separate shapes to cut them.")
            join = style.get("stroke-linejoin", "miter").strip()
            if join not in ("miter", "round", "bevel"):
                warnings.append(f"Stroke join {join} outlined as miter.")
            table = curve_tables.setdefault(stroke, [])
            for contour in pen.contours:
                polys = _stroke_polygons([contour], m, stroke_w, style.get("stroke-linecap", "butt").strip(),
                                         join, float(style.get("stroke-miterlimit", 4)), tol)
                pieces = []
                for poly in polys:
                    for a, b in zip(poly, poly[1:] + poly[:1]):
                        pieces.append((a[0], a[1], b[0], b[1], len(table), 0.0, 1.0))
                        table.append(("L", [a, b]))
                if pieces:  # each subpath is its own element, so crossing subpaths never cancel
                    layers.setdefault(stroke, []).append((pieces, "nonzero"))
    return layers, curve_tables, open_closed


def _iou(a, b):
    u = (a | b).sum()
    return round(float((a & b).sum() / u), 4) if u else 1.0


def prepare_svg(src, out, *, canvas_in=None, artwork_width_in=None, artwork_height_in=None,
                material_in=None, skip_colors=(), diff_png=None, tolerance_in=0.0005) -> dict:
    """Rewrite ``src`` as a cut-ready SVG at ``out`` and report on it.

    Physical size, pick one:
      canvas_in=(w, h)     the source canvas is this many inches (artwork keeps
                           its place on the sheet, e.g. an 8 x 12 in vinyl sheet)
      artwork_width_in=w   scale so the artwork itself is w inches wide (or
      artwork_height_in=h  tall); the canvas is cropped to the artwork
    If none is given, the source's own width/height must use in, mm, cm or pt.

    material_in=(w, h) checks the artwork fits the person's material with a
    0.25 in margin. skip_colors drops whole colour layers (a background, say).
    diff_png writes a red/blue image of where the repaired cut differs from the
    original render. Returns a report dict; read every warning.
    """
    if sum(v is not None for v in (canvas_in, artwork_width_in, artwork_height_in)) > 1:
        raise ValueError("Give one of canvas_in, artwork_width_in or artwork_height_in")
    root = ET.parse(src).getroot()
    warnings = []
    vb = [float(v) for v in re.split(r"[\s,]+", (root.get("viewBox") or "").strip()) if v]
    width_attr, height_attr = root.get("width"), root.get("height")
    if len(vb) == 4 and vb[2] > 0 and vb[3] > 0:
        vx, vy, vw, vh = vb
        W, aw = _length(width_attr, vw) if width_attr else (vw, False)
        H, ah = _length(height_attr, vh) if height_attr else (vh, False)
    elif width_attr and height_attr:
        (W, aw), (H, ah) = _length(width_attr), _length(height_attr)
        vx, vy, vw, vh = 0.0, 0.0, W, H
    else:
        raise ValueError("The SVG needs a viewBox or width and height")
    s = min(W / vw, H / vh)
    root_m = (s, 0, 0, s, -vx * s + (W - vw * s) / 2, -vy * s + (H - vh * s) / 2)
    tol = tolerance_in * PX_PER_IN
    skip = {_color(c) for c in skip_colors}
    if canvas_in is not None:
        cw, ch = (float(v) for v in canvas_in)
        k = cw * PX_PER_IN / W
        if abs(ch * PX_PER_IN / H - k) > 1e-3 * k:
            raise ValueError(f"canvas_in {cw} x {ch} in does not match the source aspect {W:g}:{H:g}")
        root_m = _mul((k, 0, 0, k, 0, 0), root_m)
        W, H = cw * PX_PER_IN, ch * PX_PER_IN
    elif artwork_width_in is not None or artwork_height_in is not None:
        # Measure the artwork at source scale, then rebase it onto a canvas of exactly its size.
        probe, _, _ = _collect(root, root_m, tol * 4, skip, [])
        pts = np.array([p[:4] for els in probe.values() for pcs, _ in els for p in pcs], float).reshape(-1, 4)
        if not len(pts):
            raise ValueError("Nothing to cut: no filled or stroked shapes in the SVG.")
        x0, y0 = min(pts[:, 0].min(), pts[:, 2].min()), min(pts[:, 1].min(), pts[:, 3].min())
        x1, y1 = max(pts[:, 0].max(), pts[:, 2].max()), max(pts[:, 1].max(), pts[:, 3].max())
        k = (artwork_width_in * PX_PER_IN / (x1 - x0)) if artwork_width_in is not None \
            else (artwork_height_in * PX_PER_IN / (y1 - y0))
        root_m = _mul((k, 0, 0, k, -x0 * k, -y0 * k), root_m)
        W, H = (x1 - x0) * k, (y1 - y0) * k
    elif not (aw and ah):
        raise ValueError("This SVG has no physical size (its width/height are px or unitless). "
                         "Pass canvas_in=(w, h) or artwork_width_in=... in inches.")

    layers, curve_tables, open_closed = _collect(root, root_m, tol, skip, warnings)
    if not layers:
        raise ValueError("Nothing to cut: no filled or stroked shapes survived. " + " ".join(warnings))
    min_area = (0.002 * PX_PER_IN) ** 2
    results = []
    for color, elements in layers.items():
        pieces = [p for pcs, _ in elements for p in pcs]
        elem = np.concatenate([np.full(len(pcs), i) for i, (pcs, _) in enumerate(elements)]).astype(int)
        loops, crossings, duplicates, gaps = _union(pieces, elem, [rule for _, rule in elements])
        loops = [lp for lp in loops if abs(_area(lp)) > min_area]
        if gaps:
            warnings.append(f"Layer {color}: closed {gaps} hairline gap(s) in the repaired outline; "
                            "check the diff closely.")
        if loops:
            results.append((color, elements, loops, crossings, duplicates))
    if not results:
        raise ValueError("Nothing to cut after repair: every outline cancelled out.")

    def bbox(loops):
        xs = [a[0] for lp in loops for a, *_ in lp]
        ys = [a[1] for lp in loops for a, *_ in lp]
        return min(xs), min(ys), max(xs), max(ys)

    bx0, by0, bx1, by1 = bbox([lp for r in results for lp in r[2]])
    raster_scale = min(1600 / max(bx1 - bx0, 1e-9), 1600 / max(by1 - by0, 1e-9), 8.0)
    RW = int(math.ceil((bx1 - bx0) * raster_scale)) + 2
    RH = int(math.ceil((by1 - by0) * raster_scale)) + 2
    ox, oy = bx0 - 1 / raster_scale, by0 - 1 / raster_scale
    diff_img = np.full((RH, RW, 3), 255, np.uint8) if diff_png else None
    paths, out_layers = [], []
    for n, (color, elements, loops, crossings, duplicates) in enumerate(results, 1):
        ds, nodes = [], 0
        for lp in loops:
            d, count = _loop_d(lp, curve_tables[color])
            ds.append(d)
            nodes += count
        paths.append(f'<path id="cut-{n}" fill="{color}" d="{"".join(ds)}"/>')
        orig = _raster([(np.array([p[:4] for p in pcs], float).reshape(-1, 4), rule) for pcs, rule in elements],
                       ox, oy, raster_scale, RW, RH)
        # Rasterize exactly what is written: each loop as emitted, closed back to its start.
        rep = np.array([(a[0], a[1], b[0], b[1]) for lp in loops
                        for a, b in [(e[0], e[1]) for e in lp] + [(lp[-1][1], lp[0][0])]], float).reshape(-1, 4)
        nz = _raster([(rep, "nonzero")], ox, oy, raster_scale, RW, RH)
        eo = _raster([(rep, "evenodd")], ox, oy, raster_scale, RW, RH)
        if diff_img is not None:
            diff_img[orig & ~nz] = (220, 40, 40)
            diff_img[nz & ~orig] = (40, 90, 220)
        outer = [lp for lp in loops if _area(lp) > 0]
        small = 0
        for lp in outer:
            x0, y0, x1, y1 = bbox([lp])
            small += max(x1 - x0, y1 - y0) < PX_PER_IN / 16
        lx0, ly0, lx1, ly1 = (float(v) for v in bbox(loops))
        layer = {
            "color": color, "pieces": len(outer), "holes": len(loops) - len(outer), "nodes": nodes,
            "size_in": [round((lx1 - lx0) / PX_PER_IN, 3), round((ly1 - ly0) / PX_PER_IN, 3)],
            "overlaps_resolved": int(crossings), "duplicate_edges_removed": int(duplicates),
            "open_contours_closed": int(open_closed.get(color, 0)), "pieces_under_1_16_in": int(small),
            "match_nonzero": _iou(orig, nz), "match_evenodd": _iou(orig, eo),
        }
        if nz.sum() / raster_scale ** 2 > 0.9 * W * H:
            warnings.append(f"Layer {color} covers almost the whole canvas: if it is a background, "
                            f"prepare again with skip_colors=['{color}'].")
        if min(layer["match_nonzero"], layer["match_evenodd"]) < 0.995:
            warnings.append(f"Layer {color} differs from the original render "
                            f"({layer['match_nonzero']} / {layer['match_evenodd']}); inspect diff_png.")
        if small:
            warnings.append(f"Layer {color} has {small} piece(s) under 1/16 in: likely too small to cut or weed.")
        out_layers.append(layer)

    Path(out).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{_fmt(W)}" height="{_fmt(H)}" '
                         f'viewBox="0 0 {_fmt(W)} {_fmt(H)}">' + "".join(paths) + "</svg>\n")
    if diff_img is not None:
        Image.fromarray(diff_img).save(diff_png)
    if bx0 < -0.5 or by0 < -0.5 or bx1 > W + 0.5 or by1 > H + 0.5:
        warnings.append("Artwork extends past the canvas; Design Space imports it anyway at the artwork size.")
    report = {
        "out": str(out), "units_per_inch": PX_PER_IN,
        "canvas_in": [round(W / PX_PER_IN, 3), round(H / PX_PER_IN, 3)],
        "artwork_in": {"x": round(bx0 / PX_PER_IN, 3), "y": round(by0 / PX_PER_IN, 3),
                       "width": round((bx1 - bx0) / PX_PER_IN, 3), "height": round((by1 - by0) / PX_PER_IN, 3)},
        "layers": out_layers, "warnings": warnings, "diff_png": str(diff_png) if diff_png else None,
    }
    if material_in is not None:
        mw, mh = (float(v) for v in material_in)
        aw_in, ah_in = report["artwork_in"]["width"], report["artwork_in"]["height"]
        room = (mw - 2 * MAT_MARGIN_IN, mh - 2 * MAT_MARGIN_IN)
        fits = (aw_in <= room[0] and ah_in <= room[1]) or (ah_in <= room[0] and aw_in <= room[1])
        report["material"] = {"size_in": [mw, mh], "margin_in": MAT_MARGIN_IN, "fits": bool(fits)}
        if not fits:
            warnings.append(f"Artwork {aw_in} x {ah_in} in does not fit {mw} x {mh} in material with "
                            f"{MAT_MARGIN_IN} in margins.")
    warnings[:] = list(dict.fromkeys(warnings))
    return report



def prepare_raster(src, out, *, width_in, ppi=300, purpose="cut", paper="letter") -> dict:
    """Crop, size and tag a PNG for Design Space.

    purpose="cut": Design Space traces the opaque silhouette into a cut line.
    purpose="print_then_cut": the picture is printed and cut around; checked
    against the Print Then Cut maximum for ``paper`` ("letter" or "a4").
    The PNG is cropped to its visible pixels, resampled so it is width_in
    inches at ppi, and tagged with that resolution. Design Space does not
    reliably honour the tag, so tell the person the intended size.
    """
    from scipy import ndimage

    if purpose not in ("cut", "print_then_cut"):
        raise ValueError("purpose is 'cut' or 'print_then_cut'")
    img = Image.open(src)
    img.load()
    rgba = img.convert("RGBA")
    a = np.asarray(rgba)[..., 3]
    warnings = []
    if (a > 250).all():
        rgb = np.asarray(rgba)[..., :3].astype(int)
        corners = np.array([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]])
        if np.abs(corners - corners[0]).max() < 12:
            warnings.append("Opaque background: Design Space would cut it as a rectangle. Remove the "
                            "background to transparency first (Subject Isolation), then prepare again.")
        else:
            warnings.append("No transparency: the cut line will be the image rectangle.")
    ys, xs = np.nonzero(a > 8)
    if not len(xs):
        raise ValueError("The image is fully transparent")
    rgba = rgba.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    effective = rgba.width / width_in
    target = (max(1, round(width_in * ppi)), max(1, round(rgba.height * width_in * ppi / rgba.width)))
    if target != rgba.size:
        rgba = rgba.resize(target, Image.LANCZOS)
    rgba.save(out, dpi=(ppi, ppi))
    height_in = rgba.height / ppi
    alpha = np.asarray(rgba)[..., 3]
    solid = alpha > 127
    _, pieces = ndimage.label(solid, structure=np.ones((3, 3)))
    background, regions = ndimage.label(~solid)
    border = set(np.unique(np.concatenate([background[0], background[-1], background[:, 0], background[:, -1]])))
    holes = len(set(range(1, regions + 1)) - border)
    sizes = ndimage.sum(solid, ndimage.label(solid, structure=np.ones((3, 3)))[0], range(1, pieces + 1))
    tiny = int((np.asarray(sizes) < (ppi / 16) ** 2).sum()) if pieces else 0
    soft = float(((alpha > 8) & (alpha < 247)).sum() / max(1, (alpha > 8).sum()))
    if effective < 150 and purpose == "print_then_cut":
        warnings.append(f"Source is only {effective:.0f} ppi at {width_in} in wide; the print will look soft.")
    if tiny:
        warnings.append(f"{tiny} piece(s) under 1/16 in: they will cut as specks or not at all.")
    if purpose == "cut" and soft > 0.2:
        warnings.append("Soft or feathered edges: Design Space thresholds them, so the cut line may wander.")
    report = {"out": str(out), "size_px": list(rgba.size), "ppi": ppi,
              "size_in": [round(width_in, 3), round(height_in, 3)], "source_ppi_at_size": round(effective),
              "pieces": int(pieces), "holes": holes, "purpose": purpose, "warnings": warnings}
    if purpose == "print_then_cut":
        if paper not in PRINT_THEN_CUT_MAX_IN:
            raise ValueError(f"paper is one of {sorted(PRINT_THEN_CUT_MAX_IN)}")
        mw, mh = PRINT_THEN_CUT_MAX_IN[paper]
        fits = (width_in <= mw and height_in <= mh) or (height_in <= mw and width_in <= mh)
        report["print_then_cut"] = {"paper": paper, "max_in": [mw, mh], "fits": bool(fits)}
        if not fits:
            warnings.append(f"{width_in} x {height_in:.2f} in exceeds the Print Then Cut maximum "
                            f"{mw} x {mh} in on {paper}.")
    return report


def make_sticker(src, out, *, width_in, border_in=0.08, border_color="#ffffff", smooth_in=None,
                 ppi=300, paper="letter") -> dict:
    """Give transparent artwork a die-cut border and size it for Print Then Cut.

    The cut line is the outer edge of the result, so it is built to cut well:
    holes in the artwork are filled (a sticker is one piece), the border is a
    constant ``border_in`` wide, and notches narrower than about twice
    ``smooth_in`` (default: the border width) are rounded over so the blade
    follows a smooth curve. ``width_in`` is the finished width including the
    border. border_in=0 cuts at the artwork's own edge (use Design Space's
    bleed); prefer a border unless the person wants full-colour edges.
    """
    from scipy import ndimage

    color = _color(border_color)
    if not color or not re.fullmatch(r"#[0-9a-f]{6}", color):
        raise ValueError("border_color must be a colour such as #ffffff")
    if width_in <= 0 or border_in < 0:
        raise ValueError("width_in must be positive and border_in not negative")
    img = Image.open(src)
    img.load()
    art = img.convert("RGBA")
    alpha = np.asarray(art)[..., 3]
    warnings = []
    if (alpha > 250).all():
        raise ValueError("The artwork has no transparency, so there is no shape to cut around. "
                         "Remove the background first, then make the sticker.")
    ys, xs = np.nonzero(alpha > 8)
    art = art.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    smooth_in = border_in if smooth_in is None else smooth_in
    art_w_in = width_in - 2 * border_in
    if art_w_in <= 0:
        raise ValueError("The border is wider than the sticker")
    source_ppi = art.width / art_w_in
    art_px = (max(1, round(art_w_in * ppi)), max(1, round(art.height * art_w_in * ppi / art.width)))
    art = art.resize(art_px, Image.LANCZOS)
    r, s = border_in * ppi, smooth_in * ppi
    pad = int(math.ceil(r + s)) + 4
    canvas = Image.new("RGBA", (art.width + 2 * pad, art.height + 2 * pad), (0, 0, 0, 0))
    canvas.alpha_composite(art, (pad, pad))
    solid = ndimage.binary_fill_holes(np.asarray(canvas)[..., 3] > 127)
    grown = ndimage.distance_transform_edt(~solid) <= r + s
    shape = ndimage.distance_transform_edt(grown) > s if s > 0 else grown
    shape |= solid
    # One-pixel antialiased edge from the signed distance to the shape boundary.
    edge = np.clip(ndimage.distance_transform_edt(shape) - ndimage.distance_transform_edt(~shape) + 0.5, 0, 1)
    rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    base = np.zeros(edge.shape + (4,), np.uint8)
    base[..., :3] = rgb
    base[..., 3] = np.round(edge * 255).astype(np.uint8)
    result = Image.fromarray(base, "RGBA")
    result.alpha_composite(canvas)
    ys, xs = np.nonzero(np.asarray(result)[..., 3] > 8)
    result = result.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    result.save(out, dpi=(ppi, ppi))
    _, pieces = ndimage.label(np.asarray(result)[..., 3] > 127, structure=np.ones((3, 3)))
    size_in = [round(result.width / ppi, 3), round(result.height / ppi, 3)]
    if pieces > 1:
        warnings.append(f"Cuts as {pieces} separate stickers: parts of the artwork are further apart than "
                        "twice the border. Widen border_in, or join the parts in the artwork.")
    if source_ppi < 150:
        warnings.append(f"Artwork is only {source_ppi:.0f} ppi at this size; the print will look soft.")
    if 0 < border_in < 1 / 32:
        warnings.append("A border under 1/32 in leaves no room for cut drift; 1/16 to 1/8 in is typical.")
    if border_in == 0 and float(((np.asarray(result)[..., 3] > 8) & (np.asarray(result)[..., 3] < 247)).mean()) > 0.02:
        warnings.append("Soft artwork edges with no border: the cut line will follow a blurry edge.")
    mw, mh = PRINT_THEN_CUT_MAX_IN[paper]
    fits = (size_in[0] <= mw and size_in[1] <= mh) or (size_in[1] <= mw and size_in[0] <= mh)
    if not fits:
        warnings.append(f"{size_in[0]} x {size_in[1]} in exceeds the Print Then Cut maximum {mw} x {mh} in on {paper}.")
    return {"out": str(out), "size_in": size_in, "size_px": list(result.size), "ppi": ppi,
            "border_in": border_in, "pieces": int(pieces), "source_ppi_at_size": round(source_ppi),
            "print_then_cut": {"paper": paper, "max_in": [mw, mh], "fits": bool(fits)}, "warnings": warnings}
