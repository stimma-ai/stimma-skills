---
name: label-design
display_name: Label Design
description: Design artwork for Avery or custom label sheets, resolve product codes and physical geometry, and deliver printable PDFs with repeated, mixed or per-row designs.
author: system
tags: [labels, avery, stickers, print, packaging]
environments:
  chat: true
provides: [labelkit]
---

# Label design

Design for the physical label first, then package reviewed artwork into precisely
positioned sheets. Use `labelkit` for stock knowledge and mechanics; use your
visual judgment for the design. The person supplies their business, copy and
intent, not export settings or code.

## Resolve the stock before designing

`import labelkit` exposes an offline Avery catalog with exact product aliases,
paper size, shape, trim dimensions, safe insets and slot positions. Codes are
strings, including letters and variant suffixes. Use `labelkit.lookup(code)` and
`labelkit.design_spec(stock, dpi=300, bleed_mm=0)` before image generation.
`labelkit.search(query='', limit=30)` searches product codes/descriptions/shapes.

The catalog covers the imported gLabels Avery definitions, not every current
Avery product. An unknown code needs the manufacturer's actual template and
geometry. Similar label dimensions do not establish identical sheet placement.
Custom geometry can be passed as a stock dict in the same documented fields as
lookup returns (points, 72/in, top-left origin); retain its authoritative source.
Catalog safe insets are design guides, not manufacturer-certified bleed limits.

Use the returned physical-size `summary` for stock facts in the cover and
handoff; `trim_aspect` describes proportions, not inches. Use the artwork aspect
and target pixels in your design request. When a generation tool requires size
increments, pass its increment as `pixel_multiple` to `design_spec` (for example
64 when the tool says 64). `generation_px` gives compatible dimensions at or
above the target density; `artwork_px` remains the exact print canvas. Check
the tool's maximum size too. Compose the final canvas at the exact print aspect. Allow
for the safe inset: names and other essential copy stay comfortably inside the
cut. Round/oval labels use a rectangular canvas but an elliptical visible area;
keep text inside that shape, not merely inside the rectangle. CD stock also has
a central hole. A very thin border near a cut makes small printer shifts obvious.

Default to zero bleed and a design with deliberate edge whitespace unless the
person wants edge-to-edge color. For that default, use a white canvas with the
illustration and all lettering inset by at least the stock safe inset or 2 mm,
whichever is larger. Carry this physical margin into the generation prompt and
inspect it on the finished master. Avoid a frame following the cut: it makes
ordinary printer shifts conspicuous. A tinted background reaching the trim is
edge-to-edge color even when the text is inset; it needs a bleed decision too.
Bleed extends artwork beyond the trim; it
changes the artwork aspect and requires room between labels. The helper checks
that bleed regions fit without overlapping adjacent labels. Shared edges cannot
support arbitrary different full-bleed designs. Explain a material limitation in
plain language and offer an appropriate treatment.

## Create and review the artwork

Use the person's requested image model (for example local Klein 9B), discovered
through the normal tool catalog. Create one label design at a time, filling the
artwork canvas; a sheet mockup or photograph of packaging is not a label master.
Make the business and variant legible at the real physical size. Inspect exact
wording, spelling, margins and cropping before multiplying a design over a sheet.
A finished generated label with correct wording is a valid master; separate
text composition is optional. For small copy or typography needing more control,
retain the generated illustration and compose reviewed text with layout tools.
For portable font acquisition, Brand Kits provides `brand_fonts.fetch_family`;
invoke that skill when needed and keep the font in the workspace. Use supplied copy; ask for missing facts
that actually belong on the label instead of inventing ingredients or claims.
A requested scent/name label need not become an unsolicited regulatory project.

Choose visual options when there is a meaningful creative decision. Once the
person has selected a design, preserve it through quantity/layout changes; use
image editing or the retained editable layout for an actual design revision.
Use 300 dpi as the design target. The helper reports effective resolution and
rejects below 150 dpi; enlarging pixels does not add print detail. Prepare raster
label masters at their intended aspect. `strict` fitting tolerates small model
size rounding; `contain` preserves the whole image with whitespace, `cover`
explicitly crops. None stretches artwork. Inspect any deliberate crop.

## Prepare a sheet source

`labelkit.prepare_source(stock, designs, pages, out='label-source.zip',
bleed_mm=0, min_dpi=150)` writes a portable ZIP retaining geometry, lossless
artwork and exact assignments. `designs` maps meaningful names to image paths,
or to `{path: ..., fit: 'strict'|'contain'|'cover', rotation: 0|90|180|270}`.
Rotation is clockwise. Each page lists one design name or `None` per stock slot;
lookup's `slots_pt` are ordered top to bottom, left to right. Blank slots remain
blank. Repetition, rows, half-and-half and multiple sheets are ordinary lists.
Make counts and the arrangement clear in the delivery; resolve ambiguity only
when it matters. Use the person's quantities, not an arbitrary full sheet.

```python
import labelkit
stock = labelkit.lookup('5163')
print(labelkit.design_spec(stock))
# After designing and reviewing the prepared label artwork:
result = labelkit.prepare_source(
    stock, {'selected': 'label.png'},
    pages=[['selected'] * len(stock['slots_pt'])], out='label-source.zip')
print(result)  # actual dpi, page count and occupied labels
```

The helper performs no generation and adds no names or copy. For nontrivial
placement, derive row groups from slot y-coordinates; do not assume every stock
is a regular grid. `read_source(path)` returns `(job, images, checks)` to recover
frozen art/assignments for a revision without regeneration. `images` maps design
names to PIL images; save unchanged images and pass them to `prepare_source`.

## Package and deliver

Invoke Packaging and discover `label-sheets` recipe guidance. Pass the source
ZIP as its `source` input. Keep individual prepared label artwork as package
members so people can see and reuse it. The recipe produces `labels.pdf`, a
numbered `alignment-test.pdf`, per-sheet preview PNGs, `sheet-plan.json` and
`PRINTING.txt`. Inspect the actual run previews and the label masters at readable
size. The sheet preview comes from the production PDF, not another mockup.

Author a compact cover leading with the designs and stock/counts, then sheet
preview and file access. Combine brief stock facts and print instructions with
the artwork or sheet preview; a few lines of facts need no separate guide page.
Use actual run-file `path` values from `await pkg.manifest()` as media refs. Explain that **labels.pdf** is the file to print at
**Actual Size / 100%**, on the stated paper size with Fit/Shrink disabled. A plain
paper test checks alignment against the physical sheet. The package guide PDF
is a separate presentation, not the print file. Show the production `labels.pdf`
in chat alongside the package so the person has direct access to the actual
printable file. Do not claim physical testing.

Place a direct `<a href="ACTUAL_LABELS_PDF_PATH" download>Download printable
labels</a>` link near the sheet preview and an equally clear plain-paper
alignment-test link. Use the actual manifest paths. The app's **Download guide
PDF** exports the presentation, so the printable-file link belongs in the cover
itself as well as the chat handoff.

For a revision, recover the frozen source and prepare the new assignments or
changed artwork. Open the saved package, replace the source member and rerun
its recipe. Print `await pkg.preview()` and inspect it. In the next call, use
`await stimma.packages.open(preview_folder)` to resume those exact unsaved edits;
the original media id would reopen the original saved version. Visual previews
also return this resumable folder as `draft`. Update the cover/extras, inspect,
then save and show a revision of the existing package asset.

For a printer correction, keep the source and artwork unchanged and rerun with
updated offsets. Positive offsets move right/down. A measured result 1 mm right
and 2 mm low needs -1 mm x and -2 mm y added to the run's existing offsets.
Preserve other run parameters. A constant shift can be corrected; drift that
grows down the sheet calls for checking paper size/scaling/template instead.
Report the correction in plain language and supply another plain-paper proof.
Quantities, arrangement and alignment changes need no image generation.
