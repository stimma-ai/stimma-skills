"""Run with the app's Python environment; no downloaded test fonts needed."""
from pathlib import Path
import sys
from xml.etree import ElementTree as ET

import pytest
from PIL import ImageFont

sys.path.insert(0, str(Path(__file__).parents[1] / "skills/brand-kits/lib"))
from brand_typography import outline_text  # noqa: E402


@pytest.fixture
def font(tmp_path):
    path = tmp_path / "font.ttf"
    # Pillow ships this font as part of its default text renderer.
    path.write_bytes(ImageFont.load_default(size=16).path.getvalue())
    return path


def test_real_outlines_and_escaped_name_preserve_font(font):
    before = font.read_bytes()
    svg = outline_text("Tandem & Relaydesk", str(font), tracking=1)
    root = ET.fromstring(svg)
    assert len(root.findall(".//{http://www.w3.org/2000/svg}path")) == 16
    assert not root.findall(".//{http://www.w3.org/2000/svg}text")
    assert root.attrib["aria-label"] == "Tandem & Relaydesk"
    assert root.attrib["viewBox"].split()[:2] == ["0", "0"]
    assert root.find("{http://www.w3.org/2000/svg}g").attrib["transform"].startswith("translate(")
    assert float(root.attrib["width"]) > float(root.attrib["height"]) * 5
    assert font.read_bytes() == before
    assert outline_text("Tandem & Relaydesk", str(font), tracking=1) == svg


def test_tracking_changes_positions_and_canvas(font):
    a = ET.fromstring(outline_text("AV", str(font)))
    b = ET.fromstring(outline_text("AV", str(font), tracking=10))
    assert float(b.attrib["width"]) - float(a.attrib["width"]) == pytest.approx(10)


@pytest.mark.parametrize("kwargs", [
    {"text": ""}, {"text": "two\nlines"}, {"text": "مرحبا"},
    {"text": "Test", "fill": "red;bad"}, {"text": "Test", "font_size": 0},
    {"text": "Test", "axes": {"wght": 600}},
])
def test_unsupported_inputs_fail_explicitly(font, kwargs):
    with pytest.raises(ValueError):
        outline_text(font_path=str(font), **kwargs)
