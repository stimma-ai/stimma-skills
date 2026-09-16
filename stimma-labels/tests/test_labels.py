import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

LIB = Path(__file__).resolve().parents[1] / "skills/label-design/lib"
sys.path.insert(0, str(LIB))
import labelkit


def source(tmp_path, code="5163", pages=None, **kwargs):
    stock = labelkit.lookup(code)
    w, h = labelkit.design_spec(stock)["artwork_px"]
    for name, color in [("a", "red"), ("b", "blue")]:
        Image.new("RGB", (w, h), color).save(tmp_path / f"{name}.png")
    return labelkit.prepare_source(
        stock,
        {"a": tmp_path / "a.png", "b": tmp_path / "b.png"},
        pages or [["a"] * len(stock["slots_pt"])],
        tmp_path / "source.zip",
        **kwargs,
    )


def test_aliases_and_complete_catalog():
    c = labelkit._catalog()
    assert len(c["stocks"]) + len(c["aliases"]) == 385
    assert labelkit.lookup("Avery 8160")["code"] == "5160"
    rejected = []
    for code in c["stocks"]:
        try:
            labelkit.lookup(code)
        except ValueError as e:
            rejected.append((code, str(e)))
    assert not rejected, rejected
    assert labelkit.design_spec("5163")["artwork_px"] == [1200, 600]
    with pytest.raises(ValueError, match="not in"):
        labelkit.lookup("unknown")


def test_mixed_blank_multipage_deterministic_pdf(tmp_path):
    pages = [["a"] * 5 + ["b"] * 4 + [None], ["b"] + [None] * 9]
    result = source(tmp_path, pages=pages)
    assert result["labels"] == 10
    first = labelkit.render_source(result["path"])
    second = labelkit.render_source(result["path"])
    assert first == second
    with pdfium.PdfDocument(first["labels.pdf"]) as doc:
        assert len(doc) == 2
        for page in doc:
            assert page.get_size() == pytest.approx((612, 792), abs=0.001)
        im = doc[0].render(scale=1).to_pil()
        assert im.getpixel((60, 72))[:3] == (255, 0, 0)
        assert im.getpixel((370, 400))[:3] == (0, 0, 255)
        assert im.getpixel((370, 700))[:3] == (255, 255, 255)
    assert "sheet-002" in " ".join(first)
    plan = json.loads(first["sheet-plan.json"])
    assert plan["pages"] == pages
    assert plan["designs"]["a"]["effective_dpi"] == 300
    assert "Made with Stimma" not in first["PRINTING.txt"].decode()


def test_frozen_source_ignores_catalog_changes(tmp_path, monkeypatch):
    result = source(tmp_path)
    expected = labelkit.render_source(result["path"])
    monkeypatch.setattr(
        labelkit, "_catalog", lambda: (_ for _ in ()).throw(RuntimeError("offline"))
    )
    assert labelkit.render_source(result["path"]) == expected


def test_resolution_aspect_assignments_and_bleed(tmp_path):
    s = labelkit.lookup("5163")
    Image.new("RGB", (50, 50), "red").save(tmp_path / "small.png")
    with pytest.raises(ValueError, match="aspect"):
        labelkit.prepare_source(
            s, {"a": tmp_path / "small.png"}, [["a"] * 10], tmp_path / "bad.zip"
        )
    with pytest.raises(ValueError, match="dpi"):
        labelkit.prepare_source(
            s,
            {"a": {"path": tmp_path / "small.png", "fit": "contain"}},
            [["a"] * 10],
            tmp_path / "bad.zip",
        )
    with pytest.raises(ValueError, match="exactly"):
        source(tmp_path, pages=[["a"]])
    with pytest.raises(ValueError, match="Unknown design"):
        source(tmp_path, pages=[["z"] * 10])
    with pytest.raises(ValueError, match="overlaps"):
        source(tmp_path, bleed_mm=1)


def test_round_mask_and_offset(tmp_path):
    result = source(tmp_path, code="5294")
    job, _, _ = labelkit.read_source(result["path"])
    s = job["stock"]
    x, y = s["slots_pt"][0]
    w = s["width_pt"]
    files = labelkit.render_source(result["path"], offset_x_mm=1)
    with pdfium.PdfDocument(files["labels.pdf"]) as d:
        im = d[0].render(scale=2).to_pil()
        assert im.getpixel((round((x + 3 + w / 2) * 2), round((y + w / 2) * 2)))[
            :3
        ] == (255, 0, 0)
        assert im.getpixel((round((x + 3) * 2), round(y * 2)))[:3] == (255, 255, 255)


def test_unsafe_source_and_nan(tmp_path):
    with zipfile.ZipFile(tmp_path / "bad.zip", "w") as z:
        z.writestr("../oops", b"x")
    with pytest.raises(ValueError, match="Unsafe"):
        labelkit.read_source(tmp_path / "bad.zip")
    result = source(tmp_path)
    with pytest.raises(ValueError, match="finite"):
        labelkit.render_source(result["path"], offset_x_mm=float("nan"))


def test_recipe_real_build(tmp_path):
    from packages.recipes import Build, ResolvedInput, validate_params

    p = Path(__file__).resolve().parents[1] / "recipes/label_sheets.py"
    spec = importlib.util.spec_from_file_location("test_label_recipe", p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = source(tmp_path)
    recipe = module.build._stimma_recipe
    out = tmp_path / "out"
    out.mkdir()
    b = Build(
        recipe,
        {"source": ResolvedInput("source", Path(result["path"]), "hash", "file")},
        validate_params(recipe, {}),
        out,
    )
    module.build(b)
    assert (out / "labels.pdf").is_file()
    assert {f.source for f in b.files} == {"source"}


def test_a4_exact_size_and_ring_hole(tmp_path):
    result = source(tmp_path, code="L7160")
    files = labelkit.render_source(result["path"], alignment=False)
    assert "alignment-test.pdf" not in files
    with pdfium.PdfDocument(files["labels.pdf"]) as d:
        assert d[0].get_size() == pytest.approx(
            (210 * 72 / 25.4, 297 * 72 / 25.4), abs=0.001
        )
    result = source(tmp_path, code="5824")
    files = labelkit.render_source(result["path"])
    s = labelkit.lookup("5824")
    x, y = s["slots_pt"][0]
    r = s["width_pt"] / 2
    with pdfium.PdfDocument(files["labels.pdf"]) as d:
        im = d[0].render(scale=1).to_pil()
        assert im.getpixel((round(x + r), round(y + r)))[:3] == (255, 255, 255)
        assert im.getpixel((round(x + r + 100), round(y + r)))[:3] == (255, 0, 0)


def test_custom_ellipse_rotated_art_and_dpi(tmp_path):
    s = {
        "code": "custom",
        "paper_pt": [300, 300],
        "shape": "ellipse",
        "width_pt": 144,
        "height_pt": 72,
        "corner_pt": 0,
        "safe_inset_pt": 5,
        "slots_pt": [[40, 40]],
    }
    Image.new("RGB", (300, 600), "red").save(tmp_path / "a.png")
    result = labelkit.prepare_source(
        s,
        {"a": {"path": tmp_path / "a.png", "rotation": 90}},
        [["a"]],
        tmp_path / "oval.zip",
    )
    assert result["designs"]["a"]["effective_dpi"] == 300
    with pdfium.PdfDocument(labelkit.render_source(result["path"])["labels.pdf"]) as d:
        im = d[0].render(scale=1).to_pil()
        assert im.getpixel((40, 40))[:3] == (255, 255, 255)
        assert im.getpixel((112, 76))[:3] == (255, 0, 0)


def test_source_revision_preserves_art_and_changes_only_assignments(tmp_path):
    first = source(tmp_path)
    job, images, _ = labelkit.read_source(first["path"])
    expected = {key: im.tobytes() for key, im in images.items()}
    for key, im in images.items():
        im.save(tmp_path / f"{key}-retained.png")
    revised = labelkit.prepare_source(
        job["stock"],
        {key: tmp_path / f"{key}-retained.png" for key in images},
        [["a"] * 5 + ["b"] * 5],
        tmp_path / "revision.zip",
    )
    actual, ims, _ = labelkit.read_source(revised["path"])
    assert actual["stock"] == job["stock"]
    assert {key: im.tobytes() for key, im in ims.items()} == expected
    assert actual["pages"] == [["a"] * 5 + ["b"] * 5]


def test_design_brief_physical_units_and_generation_quantization():
    s = labelkit.design_spec("5163", pixel_multiple=64)
    assert s["trim_in"] == [4, 2]
    assert "4 x 2 inch labels" in s["summary"]
    assert s["generation_px"] == [1280, 640]
    assert s["artwork_px"] == [1200, 600]
    for code in ("5160", "5294", "L7160"):
        s = labelkit.design_spec(code, pixel_multiple=64)
        w, h = s["generation_px"]
        tw, th = s["artwork_px"]
        assert w % 64 == h % 64 == 0 and w >= tw and h >= th
        assert abs((w / h) / s["artwork_aspect"] - 1) <= 0.015
