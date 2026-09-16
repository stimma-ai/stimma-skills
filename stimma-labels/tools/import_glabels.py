"""Refresh the Avery catalog from a pinned gLabels database (maintainer task)."""

import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen
import xml.etree.ElementTree as ET

REVISION = "554c9f04389f7a1afa18685cab015273f0b21d94"
BASE = f"https://raw.githubusercontent.com/j-evins/glabels-qt/{REVISION}/templates/"
DEST = Path(__file__).resolve().parents[1] / "skills/label-design/lib/data"


def points(value):
    m = re.fullmatch(r"([0-9.]+)\s*(in|mm|cm|pt)?", value)
    if not m:
        raise ValueError(f"Unknown measurement {value!r}")
    return round(
        float(m[1])
        * {"in": 72, "mm": 72 / 25.4, "cm": 72 / 2.54, "pt": 1, None: 1}[m[2]],
        8,
    )


def main():
    stocks, aliases, sources = {}, {}, []
    for filename in [
        "avery-us-templates.xml",
        "avery-iso-templates.xml",
        "avery-other-templates.xml",
    ]:
        raw = urlopen(BASE + filename).read()
        sources.append(
            {"url": BASE + filename, "sha256": hashlib.sha256(raw).hexdigest()}
        )
        for t in ET.fromstring(raw).findall("Template"):
            code = t.attrib["part"]
            if "equiv" in t.attrib:
                aliases[code] = t.attrib["equiv"]
                continue
            labels = [c for c in t if c.tag.startswith("Label-")]
            if len(labels) != 1:
                raise ValueError(f"{code}: expected one label shape")
            label = labels[0]
            shape = label.tag.removeprefix("Label-")
            a = label.attrib
            w = points(a["width"]) if "width" in a else 2 * points(a["radius"])
            h = points(a["height"]) if "height" in a else w
            paper = {
                "US-Letter": [612, 792],
                "A4": [210 * 72 / 25.4, 297 * 72 / 25.4],
            }.get(t.get("size"))
            if paper is None:
                paper = [points(t.attrib["width"]), points(t.attrib["height"])]
            slots = []
            for layout in label.findall("Layout"):
                for row in range(int(layout.get("ny"))):
                    for col in range(int(layout.get("nx"))):
                        slots.append(
                            [
                                points(layout.get("x0"))
                                + col * points(layout.get("dx")),
                                points(layout.get("y0"))
                                + row * points(layout.get("dy")),
                            ]
                        )
            slots.sort(key=lambda p: (round(p[1], 4), p[0]))
            margin = label.find("Markup-margin")
            stocks[code] = {
                "code": code,
                "brand": "Avery",
                "description": t.get("_description", t.get("description", "Labels")),
                "paper_pt": paper,
                "shape": shape,
                "width_pt": w,
                "height_pt": h,
                "corner_pt": points(a.get("round", "0")),
                "hole_radius_pt": points(a.get("hole", "0")),
                "safe_inset_pt": points(margin.get("size"))
                if margin is not None
                else 4.5,
                "slots_pt": slots,
                "source": BASE + filename,
                "source_revision": REVISION,
            }
    for code, target in aliases.items():
        seen = {code}
        while target in aliases:
            if target in seen:
                raise ValueError("Cyclic alias")
            seen.add(target)
            target = aliases[target]
        if target not in stocks:
            raise ValueError(f"Missing alias {target}")
        aliases[code] = target
    # Community definitions can be stale. Keep reviewed manufacturer fixes
    # separate from the pinned import so refreshing never loses their provenance.
    fixes = json.loads(Path(__file__).with_name("avery-corrections.json").read_text())
    for code, stock in fixes["stocks"].items():
        aliases.pop(code, None)
        stocks[code] = stock
    for code, target in fixes["aliases"].items():
        stocks.pop(code, None)
        aliases[code] = target
    DEST.mkdir(parents=True, exist_ok=True)
    catalog = {
        "format": 1,
        "upstream_revision": REVISION,
        "sources": sources,
        "stocks": stocks,
        "aliases": aliases,
    }
    (DEST / "avery.json").write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n"
    )
    (DEST / "GLABELS-LICENSE.txt").write_bytes(urlopen(BASE + "LICENSE").read())
    print(f"{len(stocks)} geometries, {len(aliases)} aliases")


if __name__ == "__main__":
    main()
