"""Font acquisition validates bytes and carries the actual license; no network in tests."""
from base64 import b64decode
from pathlib import Path
import re
import sys

from PIL import ImageFont
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "skills/brand-kits/lib"))
import brand_fonts  # noqa: E402


def test_fetch_validates_copies_license_and_reuses_complete_family(tmp_path, monkeypatch):
    data = ImageFont.load_default(size=16).path.getvalue()
    requests = []

    def read(path):
        requests.append(path)
        return {"ofl/example/METADATA.pb": b'fonts { filename: "Example[opsz,wght].ttf" }',
                "ofl/example/OFL.txt": b"The actual license",
                "ofl/example/Example[opsz,wght].ttf": data}[path]

    monkeypatch.setattr(brand_fonts, "_read", read)
    result = brand_fonts.fetch_family("Example", tmp_path)
    assert Path(result["license"]).read_bytes() == b"The actual license"
    font = result["fonts"][0]
    assert Path(font["path"]).name == "Example-opsz-wght.ttf"
    assert Path(font["path"]).read_bytes() == data
    assert font["family"]
    assert brand_fonts.fetch_family("Example", tmp_path) == result
    assert len(requests) == 3
    css = brand_fonts.font_face(font["path"], family="Chosen")
    assert b64decode(re.search(r"base64,([^)]*)", css)[1]) == data
    assert "font-family:'Chosen'" in css
    assert f"font-weight:{font['weight']}" in css


def test_downloaded_html_is_not_saved_as_a_font(tmp_path, monkeypatch):
    monkeypatch.setattr(brand_fonts, "_read", lambda path:
                        b'filename: "Example.ttf"' if path.endswith("METADATA.pb") else b"<html>error</html>")
    with pytest.raises(Exception, match="Not a TrueType|bad sfntVersion"):
        brand_fonts.fetch_family("Example", tmp_path)
    assert not list(tmp_path.rglob("*.ttf"))


@pytest.mark.parametrize("family", ["../secret", "", "Example<script>", "https://example.org"])
def test_family_is_a_name_not_a_path_or_url(family, tmp_path):
    with pytest.raises(ValueError):
        brand_fonts.fetch_family(family, tmp_path)
