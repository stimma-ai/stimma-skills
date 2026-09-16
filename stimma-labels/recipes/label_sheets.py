"""Deterministic sheet imposition from frozen artwork, geometry and placements."""

import importlib.util
from pathlib import Path

from packages.recipes import Build, Input, Param, recipe

_spec = importlib.util.spec_from_file_location(
    "_stimma_labelkit_recipe",
    Path(__file__).resolve().parents[1] / "skills/label-design/lib/labelkit.py",
)
_labelkit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_labelkit)


@recipe(
    id="label-sheets",
    version=2,
    display_name="Printable label sheets",
    description="Exact-size Avery or custom label sheet PDFs from prepared label artwork and explicit slot assignments; repeats, mixed designs, rows, blanks and multiple pages.",
    inputs=[
        Input(
            "source",
            kind="file",
            description="Frozen ZIP from labelkit.prepare_source: stock geometry, designs and per-page slot assignments",
        )
    ],
    params=[
        Param(
            "offset_x_mm",
            type="number",
            default=0,
            minimum=-10,
            maximum=10,
            description="Measured printer correction, positive moves right",
        ),
        Param(
            "offset_y_mm",
            type="number",
            default=0,
            minimum=-10,
            maximum=10,
            description="Measured printer correction, positive moves down",
        ),
        Param("alignment_test", type="boolean", default=True),
    ],
    guidance="""Invoke label-design to resolve Avery stock, compute the artwork aspect/pixels and
prepare a frozen source with labelkit.prepare_source. This recipe imposes already-reviewed
artwork; it never designs, fetches a template, invents copy or changes label proportions.
Every page has an explicit assignment for every catalog slot, including None for blanks.
The source stores exact geometry, so rebuilds work offline even if the catalog changes.

labels.pdf is the production deliverable: exact paper dimensions, no guides or branding.
preview/sheet-001.png (and following pages) is rendered from that same PDF. Inspect it.
alignment-test.pdf is an optional plain-paper test only. sheet-plan.json records assignments
and actual effective dpi. PRINTING.txt gives 100% / Actual Size instructions.

Use exact run-file path values from await pkg.manifest() as stimma-media refs.
Author a compact package cover with Packaging: show the actual designs large enough to
read, a sheet preview, design quantities, stock code, paper size and printing instructions.
Provide prominent access to labels.pdf using the package file browser. Distinguish the
package guide PDF from the printable sheet PDF. Preserve prepared originals as members.
Keep the cover's normal branding/background out of the printable sheets.
For changes, open the existing package, replace its source member and rerun this run;
retain unchanged artwork and show the result as a revision of the same package asset.""",
)
def build(b: Build):
    try:
        files = _labelkit.render_source(
            b.path("source"),
            offset_x_mm=b.params.offset_x_mm,
            offset_y_mm=b.params.offset_y_mm,
            alignment=b.params.alignment_test,
        )
    except (ValueError, KeyError) as exc:
        b.fail(str(exc))
    for name, data in files.items():
        b.derive(name, data, source="source", fixed=True)
