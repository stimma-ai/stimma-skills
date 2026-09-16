# Stimma Labels

Label Design provides offline Avery stock lookup and design geometry. The
`label-sheets` package recipe produces exact-size PDFs from prepared raster
artwork and explicit per-page slot assignments. It supports repeated/mixed
labels, blanks, multiple pages, rounded rectangles, circles, ellipses and CD
rings. Custom stocks use the same geometry structure as catalog stocks.

The bundled catalog has 82 geometries and 303 product aliases from gLabels-qt,
pinned to revision `554c9f04389f7a1afa18685cab015273f0b21d94`. All three Avery
catalog files are imported. Coverage is not exhaustive; missing products need
manufacturer geometry. This is not an Avery endorsement or physical print test.
Reviewed manufacturer corrections live in `tools/avery-corrections.json` and
are applied after import. They retain template URLs and PDF hashes: the tested
5163 and 5294 layouts and the conflicting 5195/8195 return-address definitions
use official PDF outline coordinates. Other entries remain community data,
not manufacturer-verified definitions; compare a paper proof with the stock.
`tools/import_glabels.py` regenerates the catalog; source URLs and hashes are
recorded in the JSON. Keep the accompanying `GLABELS-LICENSE.txt` with it. The
gLabels template data has its own MIT/X license, separate from Stimma code.

Frozen source ZIPs retain geometry, normalized lossless artwork and slot
assignments. They exclude machine paths and original image metadata. The
recipe uses the app's existing WeasyPrint/PDFium dependencies, runs offline,
and emits deterministic bytes. Sheet previews render the actual PDF. Production
sheets contain no guides or package-cover branding. Safe margins are design
guides, and full bleed is rejected where expanded label regions overlap.

Tests run in the Stimma backend environment:

```
uv run pytest ../../stimma-skills/stimma-labels/tests -q
```
