---
name: cricut-design
display_name: Cricut Design
description: "Making files for a Cricut cutting machine (Design Space): printable stickers, vinyl decals, iron-on/HTV, stencils, cardstock and paper cuts, layered vinyl. Prepares die-cut sticker PNGs for Print Then Cut and cut-safe SVG layers at true physical size."
author: system
tags: [cricut, design-space, cutting-machine, stickers, vinyl, htv, stencil, svg, print-then-cut]
environments:
  chat: true
provides: [cricutkit]
---

# Cricut design

A Cricut cuts along outlines with a blade. Design Space imports the file, turns each
flat colour into a cut layer, and cuts every edge it finds. Its importer is not a
browser. A file that looks right in a browser can still import wrong: wrong size,
missing parts, or holes punched where shapes overlap. **A browser render does not
prove a file will cut correctly**, and that includes your own `view_image`. Prepare
every deliverable with `cricutkit` and read its report.

## Start from the physical job

Before designing, know three things. Ask for any you cannot infer:

- **Finished size**, in inches or mm: "a 3 in decal", "fits an 8 x 12 in sheet".
  Getting this right matters most. The person cares about the size it cuts at.
- **Material and use**: adhesive vinyl, iron-on (HTV), cardstock, sticker paper
  (Print Then Cut), stencil.
- **Machine**, if it limits anything. Explore and Maker cut on 12 x 12 in or
  12 x 24 in mats. Joy Xtra takes 8.5 in wide material and the original Joy 4.5 in.
  Smart Materials can run longer than a mat without one. Leave about 0.25 in margin
  inside the material. The original Joy cannot do Print Then Cut.

Choose the format by job:

- **A picture printed, then cut around** (stickers, printed tags, cake toppers on
  printable paper): **raster**. Any image works, generated art included; only the
  outline has to be clean. See Stickers below.
- **Shapes cut from solid material, one or more colours** (decals, HTV, layered
  vinyl, stencils, paper cuts): **SVG**, one flat colour per layer. A raster can be
  uploaded as a "cut image" too, but Design Space then traces only its silhouette,
  which is worse than a real SVG for anything with interior detail.

## Design for a blade

Treat these as rules of thumb. Thinner and smaller cuts depend on the material and
blade, so suggest a test cut of the smallest detail.

- **Every closed region is a separate piece of material.** Floating parts such
  as the counters of O, A and e fall out of a stencil. Bridge them, or use a stencil
  font. In a decal they need weeding.
- **No hairlines.** Keep lines and gaps at least about 1/16 in (1.5 mm) for vinyl,
  and more for glitter HTV or thick cardstock. Fine serifs and script tails tear or
  vanish when cut small. Bold, simple letterforms cut well. Keep text at least about
  1/4 in tall.
- **Layered vinyl: one layer per colour.** Let a lower layer extend about 1/16 in
  under the layer above instead of butting edges, so small placement error leaves
  no gap.
- **Iron-on is mirrored at cut time.** The person turns on Mirror for the mat in
  Design Space. Do not mirror the file.
- **Flat colours only.** Gradients, textures, soft shadows and photos are not cut
  shapes. If the design needs them, it is a Print Then Cut job.
- Pens and scoring follow outlines. A filled shape draws as its outline, not as a
  centre line.

## Making the SVG

Draw the artwork with the **Vector Design** skill. Invoke it if it is not already
loaded. It covers concept, geometry and the `create_svg` loop, and its `typekit`
outlines text from a real font. Never deliver live `<text>`: Design Space does not
have the person's fonts. Outlined text from variable fonts still has overlapping
pieces, which `prepare_svg` below merges.

Three things Cricut needs that ordinary vector work does not:

1. **Merged geometry.** Font outlines, especially from variable fonts, and shapes
   stacked to build a mark contain overlapping contours. They look solid in a browser
   (nonzero fill), but an importer that reads them differently cuts holes where strokes
   cross: the crossbars of F, H, E and A. Changing `fill-rule` does not fix it. The
   overlaps have to be merged into one outline, with real counters kept.
2. **No transforms, true units.** Rotations, flips (`scale(1 -1)`, as in font
   outlines), nested groups and inch-based viewBoxes are common sources of import
   errors. The prepared file has every transform baked into coordinates, and is
   96 units per inch with matching `width`, `height` and `viewBox`. An 8 x 12 in
   sheet is `width="768" height="1152" viewBox="0 0 768 1152"`.
3. **Nothing Design Space ignores.** Clipping paths, masks, gradients, patterns,
   filters, embedded images and live text are dropped or misread. Strokes need to be
   real filled outlines.

Prepare the finished artwork:

```python
import cricutkit
report = cricutkit.prepare_svg(
    "mark.svg", "mark-cricut.svg",
    artwork_width_in=3,            # or artwork_height_in=..., or canvas_in=(8, 12)
    material_in=(12, 12),          # optional: checks it fits with 0.25 in margins
    diff_png="mark-cricut-diff.png",
)
print(report)
```

Use `artwork_width_in`/`artwork_height_in` when the person gave the size of the
design itself. The canvas is cropped to the artwork. Use `canvas_in` when the
source canvas *is* the sheet and placement on it matters. Pass
`skip_colors=["#ffffff"]` to drop a background or other colour that should not be
cut.

`prepare_svg` merges overlaps, keeps counters, removes duplicate and internal edges,
closes open contours, outlines strokes at their true width, bakes transforms and
writes one flat path per colour at 96 per inch. Curves stay curves wherever an
outline was not cut by a merge.

**Read the report before presenting anything:**

- `match_nonzero` and `match_evenodd` compare the prepared layer with the original
  render under both fill rules. Both should be 0.995 or better. A low score means
  the cut differs from what the person saw. `view_image` the diff (red: in the
  original only; blue: added) and fix the source.
- `pieces` and `holes` per layer should match what you drew. For example, "HELLO"
  as one layer is 5 pieces and 1 hole. An unexpected number means shapes merged or
  separated in a way you did not intend.
- `pieces_under_1_16_in` will not cut or weed cleanly at this size.
- Every entry in `warnings` is either fixed in the source, or explained to the
  person.

Then save and look at the prepared file itself, not your source:
`create_svg(file="mark-cricut.svg", title="...")` and `view_image`.

## Stickers (Print Then Cut)

The printer prints the picture with registration marks, then the machine reads the
marks and cuts around the image's outer edge. The picture can be anything. What
decides whether the sticker comes out well is **the cut line**: one smooth, closed
outline that the blade can follow at its small size.

1. **Make the artwork** as one image per sticker: a bold subject with clear edges.
   Ask the image model for the subject on a plain background, then remove the
   background to transparency (Subject Isolation). Do not ask the model to draw the
   white border. Its border comes out uneven, and the next step builds a better one.
2. **Make the sticker**:

   ```python
   import cricutkit
   report = cricutkit.make_sticker("cat.png", "cat-sticker.png", width_in=3, border_in=0.08)
   ```

   This adds an even die-cut border (white by default; `border_color` sets it),
   fills holes so the sticker is one piece, rounds over notches too tight for the
   blade, and sizes the result to `width_in` *including* the border at 300 ppi.
   A border of 1/16 to 1/8 in hides the small drift every Print Then Cut has.
   Without a border (`border_in=0`) the cut sits right on the art's edge, so any
   drift shows a sliver of paper or clips the art. Use that only when the person
   wants colour to the edge.
3. **Read the report.** `pieces` should be 1. More means parts of the art are too
   far apart to share a border: widen it, or bring the parts together.
   `source_ppi_at_size` under about 150 prints soft, so generate larger or make the
   sticker smaller. `print_then_cut.fits` checks the maximum printable area: about
   7.44 x 9.94 in on Letter and 7.2 x 10.62 in on A4 (Explore, Maker, Venture). The
   original Joy cannot print and cut.
4. **Look at it** on a dark background with `view_image`. A white border is
   invisible against white.

For a sheet, make each sticker separately. The person uploads them all, sizes them,
and Design Space arranges them inside the printable area. Tell them:

- upload as a **Print Then Cut** image
- keep **Add Bleed** on
- print at high quality and let inkjet ink dry before cutting
- for stickers that stay on the backing sheet (kiss cut), pick the material setting
  for their sticker paper and test-cut one sticker first

`prepare_raster(src, out, width_in=..., purpose="print_then_cut")` sizes and checks a
finished image without adding a border. Use it when the art already has the edge the
person wants. `purpose="cut"` checks a single-colour silhouette meant for upload as
a cut image.

## Size: say it out loud

Design Space can import files at the wrong size. It trims empty canvas, and imported
PNGs do not reliably keep their resolution tag. So always tell the person the
**artwork size** from the report (`artwork_in` width x height), separately from any
sheet size: "The design is 7.2 x 10.4 in." If it imports at a different size, they
should lock proportions in Design Space and type that width.

## Handing it over

Present the prepared file, not the source, and say:

- what each layer is: colour, and which material it cuts from
- the artwork size in inches
- how to upload it: Upload, then the SVG; or for a PNG, choose Print Then Cut image
  or cut image. Keep layers grouped or attached so they cut in place. Mirror for
  iron-on.
- that you checked it against the original render, and that a test cut of the
  smallest detail is worth doing on new material.

Be honest about limits. You prepared the file to Design Space's known requirements
and verified the geometry, but you did not import it into Design Space.
