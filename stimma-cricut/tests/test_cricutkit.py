import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

LIB = Path(__file__).resolve().parents[1] / "skills/cricut-design/lib"
sys.path.insert(0, str(LIB))
import cricutkit  # noqa: E402 - the helper is bundled with the skill, not installed


def write(tmp_path, body, size='width="300" height="200" viewBox="0 0 300 200"', name="in.svg"):
    path = tmp_path / name
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" {size}>{body}</svg>')
    return path


def prepare(tmp_path, body, **kwargs):
    kwargs.setdefault("canvas_in", (3, 2))
    out = tmp_path / "out.svg"
    report = cricutkit.prepare_svg(write(tmp_path, body), out, **kwargs)
    return report, ET.parse(out).getroot()


# Three rectangles in one path, the way variable fonts build an H: they overlap
# at the crossbar and render solid only under the nonzero rule.
OVERLAPPING_H = '<path fill="#112233" d="M10 10H40V190H10Z M110 10H140V190H110Z M10 85H140V115H10Z"/>'


def test_overlapping_contours_become_one_outline(tmp_path):
    report, root = prepare(tmp_path, OVERLAPPING_H)
    layer = report["layers"][0]
    assert layer["pieces"] == 1 and layer["holes"] == 0
    assert layer["overlaps_resolved"] > 0
    assert layer["match_nonzero"] == 1.0 and layer["match_evenodd"] == 1.0
    assert len(re.findall("M", root[0].get("d"))) == 1


def test_counters_survive(tmp_path):
    ring = ('<path fill="#000" fill-rule="evenodd" d="M150 100m-80 0a80 80 0 1 0 160 0a80 80 0 1 0 -160 0Z'
            ' M150 100m-40 0a40 40 0 1 0 80 0a40 40 0 1 0 -80 0Z"/>')
    report, root = prepare(tmp_path, ring)
    layer = report["layers"][0]
    assert (layer["pieces"], layer["holes"]) == (1, 1)
    assert layer["match_evenodd"] == 1.0
    # Untouched arcs are written back as curves, not polylines.
    assert "C" in root[0].get("d") and layer["nodes"] <= 12


def test_transforms_are_baked_and_canvas_is_96_per_inch(tmp_path):
    body = f'<g transform="translate(300 0) scale(-1 1)"><g transform="rotate(90 75 100)">{OVERLAPPING_H}</g></g>'
    report, root = prepare(tmp_path, body, canvas_in=(8 * 1.5, 8))
    assert (root.get("width"), root.get("height"), root.get("viewBox")) == ("1152", "768", "0 0 1152 768")
    assert all("transform" not in el.attrib for el in root.iter())
    assert report["canvas_in"] == [12.0, 8.0]
    # Rotated 90 degrees, the 130 x 180 H is now 180 wide x 130 tall; 300 source units span 12 in.
    assert report["artwork_in"]["width"] == pytest.approx(180 * 12 / 300, abs=0.01)
    assert report["artwork_in"]["height"] == pytest.approx(130 * 12 / 300, abs=0.01)


def test_artwork_width_crops_canvas_to_artwork(tmp_path):
    report, root = prepare(tmp_path, OVERLAPPING_H, canvas_in=None, artwork_width_in=4)
    assert report["artwork_in"] == {"x": 0.0, "y": 0.0, "width": 4.0, "height": pytest.approx(4 * 180 / 130, abs=0.002)}
    assert report["canvas_in"][0] == 4.0
    assert float(root.get("width")) == 384


def test_duplicate_shapes_cut_once(tmp_path):
    rect = '<rect x="20" y="20" width="60" height="60" fill="red"/>'
    report, root = prepare(tmp_path, rect * 3)
    layer = report["layers"][0]
    assert layer["duplicate_edges_removed"] == 8 and layer["pieces"] == 1
    assert len(re.findall("L", root[0].get("d"))) == 4


def test_colours_are_separate_layers_in_order(tmp_path):
    body = ('<rect x="0" y="0" width="50" height="50" fill="#f00"/><circle cx="150" cy="100" r="40" fill="navy"/>'
            '<rect x="200" y="0" width="50" height="50" style="fill: rgb(255,0,0)"/>')
    report, root = prepare(tmp_path, body)
    assert [layer["color"] for layer in report["layers"]] == ["#ff0000", "#000080"]
    assert report["layers"][0]["pieces"] == 2
    assert [p.get("fill") for p in root] == ["#ff0000", "#000080"]


def test_stroke_is_outlined_to_its_true_width(tmp_path):
    body = ('<path d="M40 150 Q 150 -50 260 150" stroke="#0a0" stroke-width="20" fill="none" '
            'stroke-linecap="round" stroke-linejoin="round"/>')
    report, root = prepare(tmp_path, body, canvas_in=(3, 2))
    assert report["layers"][0]["pieces"] == 1
    # Every point of the outline should be stroke-width/2 from the centre line.
    t = np.linspace(0, 1, 4001)[:, None]
    p0, c, p1 = np.array([40, 150.0]), np.array([150, -50.0]), np.array([260, 150.0])
    centre = ((1 - t) ** 2 * p0 + 2 * (1 - t) * t * c + t * t * p1) * (96 / 100)
    pts = np.array([float(v) for v in re.findall(r"-?[\d.]+", root[0].get("d"))]).reshape(-1, 2)
    dist = np.linalg.norm(pts[:, None] - centre[None], axis=2).min(1)
    assert dist.min() == pytest.approx(10 * 0.96, abs=0.05)
    assert dist.max() == pytest.approx(10 * 0.96, abs=0.05)


def test_unsupported_features_are_reported(tmp_path):
    body = ('<defs><linearGradient id="g"><stop offset="0" stop-color="#123456"/></linearGradient>'
            '<clipPath id="c"><rect width="10" height="10"/></clipPath></defs>'
            '<text x="10" y="50">Hi</text><rect width="50" height="50" fill="url(#g)" clip-path="url(#c)"/>')
    report, _ = prepare(tmp_path, body)
    text = " ".join(report["warnings"])
    assert "text" in text and "clip-path" in text and "Gradient" in text
    assert report["layers"][0]["color"] == "#123456"


def test_unitless_svg_needs_a_physical_size(tmp_path):
    with pytest.raises(ValueError, match="no physical size"):
        cricutkit.prepare_svg(write(tmp_path, OVERLAPPING_H), tmp_path / "out.svg")
    sized = write(tmp_path, OVERLAPPING_H, 'width="3in" height="2in" viewBox="0 0 300 200"', "sized.svg")
    report = cricutkit.prepare_svg(sized, tmp_path / "out.svg")
    assert report["canvas_in"] == [3.0, 2.0]


def test_material_fit_and_small_pieces(tmp_path):
    body = OVERLAPPING_H + '<circle cx="250" cy="20" r="0.4" fill="#112233"/>'
    report, _ = prepare(tmp_path, body, canvas_in=(15, 10), material_in=(12, 12))
    assert report["material"]["fits"] is False
    assert report["layers"][0]["pieces_under_1_16_in"] == 1
    assert any("1/16" in w for w in report["warnings"])


def test_open_paths_are_closed_and_counted(tmp_path):
    body = '<path fill="#000" d="M10 10L100 10L100 100"/><path fill="#000" d="M150 10L250 10L250 100L150 10"/>'
    report, _ = prepare(tmp_path, body)
    assert report["layers"][0]["open_contours_closed"] == 1
    assert report["layers"][0]["pieces"] == 2


def test_diff_png_written(tmp_path):
    report, _ = prepare(tmp_path, OVERLAPPING_H, diff_png=tmp_path / "diff.png")
    with Image.open(report["diff_png"]) as im:
        assert im.size[0] > 100


def test_raster_cut_image(tmp_path):
    im = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
    a = np.array(im)
    a[50:150, 50:150] = (200, 0, 0, 255)
    a[80:120, 80:120] = (0, 0, 0, 0)   # a hole
    a[200:280, 250:380] = (0, 0, 200, 255)
    Image.fromarray(a).save(tmp_path / "art.png")
    report = cricutkit.prepare_raster(tmp_path / "art.png", tmp_path / "cut.png", width_in=2, ppi=300)
    assert (report["pieces"], report["holes"]) == (2, 1)
    with Image.open(tmp_path / "cut.png") as out:
        assert out.size[0] == 600
        assert round(out.info["dpi"][0]) == 300


def test_raster_print_then_cut_limits_and_background(tmp_path):
    Image.new("RGB", (900, 1200), "white").save(tmp_path / "flat.png")
    report = cricutkit.prepare_raster(tmp_path / "flat.png", tmp_path / "ptc.png", width_in=8,
                                      purpose="print_then_cut")
    assert report["print_then_cut"]["fits"] is False
    assert any("Opaque background" in w for w in report["warnings"])
    small = cricutkit.prepare_raster(tmp_path / "flat.png", tmp_path / "ptc.png", width_in=6,
                                     purpose="print_then_cut", paper="a4")
    assert small["print_then_cut"]["fits"] is True and math.isclose(small["size_in"][1], 8.0, abs_tol=0.01)


@pytest.mark.parametrize("seed", range(6))
def test_random_overlaps_match_the_original(tmp_path, seed):
    rng = np.random.default_rng(seed)
    shapes = []
    for _ in range(14):
        colour = rng.choice(["#111111", "#cc2200"])
        x, y = rng.uniform(20, 280), rng.uniform(20, 180)
        kind = rng.integers(3)
        if kind == 0:
            shapes.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{rng.uniform(5, 40):.2f}" fill="{colour}"/>')
        elif kind == 1:
            shapes.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{rng.uniform(5, 80):.2f}" height="{rng.uniform(5, 60):.2f}" '
                          f'transform="rotate({rng.uniform(0, 90):.1f} {x:.2f} {y:.2f})" fill="{colour}"/>')
        else:
            pts = " ".join(f"{px:.2f},{py:.2f}" for px, py in rng.uniform(10, 190, (5, 2)) * (1.5, 1))
            rule = rng.choice(["nonzero", "evenodd"])
            shapes.append(f'<polygon points="{pts}" fill-rule="{rule}" fill="{colour}"/>')
    report, _ = prepare(tmp_path, "".join(shapes))
    assert not any("gap" in w for w in report["warnings"]), report["warnings"]
    for layer in report["layers"]:
        assert layer["match_nonzero"] >= 0.999 and layer["match_evenodd"] >= 0.999, layer


def _art(tmp_path):
    a = np.zeros((400, 600, 4), np.uint8)
    a[50:250, 50:250] = (230, 160, 20, 255)
    a[120:180, 120:180] = 0                  # a hole the sticker must not cut
    a[270:330, 60:240] = (20, 40, 160, 255)  # a caption just below the drawing
    Image.fromarray(a).save(tmp_path / "art.png")
    return tmp_path / "art.png"


def test_sticker_is_one_piece_with_filled_holes(tmp_path):
    report = cricutkit.make_sticker(_art(tmp_path), tmp_path / "s.png", width_in=1, border_in=0.1)
    assert report["pieces"] == 1 and not report["warnings"]
    assert report["size_in"][0] == pytest.approx(1, abs=0.01)
    from scipy import ndimage
    with Image.open(tmp_path / "s.png") as im:
        solid = np.asarray(im)[..., 3] > 127
    assert (ndimage.binary_fill_holes(solid) == solid).all()   # the hole became border, not a cut


def test_thin_border_warns_about_separate_pieces(tmp_path):
    report = cricutkit.make_sticker(_art(tmp_path), tmp_path / "s.png", width_in=2, border_in=0.02, smooth_in=0)
    assert report["pieces"] == 2
    assert any("separate stickers" in w for w in report["warnings"])
    assert any("1/32" in w for w in report["warnings"])


def test_sticker_needs_transparency(tmp_path):
    Image.new("RGB", (100, 100), "white").save(tmp_path / "flat.png")
    with pytest.raises(ValueError, match="no transparency"):
        cricutkit.make_sticker(tmp_path / "flat.png", tmp_path / "s.png", width_in=2)
