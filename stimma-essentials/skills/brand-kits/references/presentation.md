# Small components, free composition

These are building blocks for an agent-authored cover, not a brand-kit template
or an approval UI. Choose sections and layout for the work. Read Packaging for
responsive HTML, `stimma-section page`, exact member refs, and PDF previews.

## Artwork and page groups

A dark transparent logo needs a light artwork surface even on a dark guide.
For example, compare prepared treatments without changing the page ground:

```html
<div class="sp-page">
<stimma-section page layout="pair" label="Prepared logo treatments">
  <stimma-media ref="m1" plate style="--sp-plate:#F4F1E9"
    caption="Primary · for light backgrounds"></stimma-media>
  <stimma-media ref="m2"
    caption="Reversed · for dark backgrounds"></stimma-media>
</stimma-section>
</div>
```

Use real refs and inspected artwork; a plate cannot fix a wrongly recolored
master. `pair` takes two direct media children and stacks on phones. `stack`
suits two wide application images. These are optional section compositions,
not a required sequence. Let these shared layouts handle image sizing and print
spacing; add custom layout rules when the design calls for something else.
Media presets reserve the page for their images and a short note. Group swatches
and typography in a section without a media preset. `stimma-grid columns="2"`
can pair two arbitrary content groups, side by side on desktop/PDF and stacked
on phones. Use custom CSS for another composition. A small palette plus two
font specimens usually belongs on one useful page, not two mostly empty ones.
Keep headings, examples and short notes together;
avoid title-only or caption-only spill pages. For custom screen grids with
`auto-fit` or nested `min()`, supply explicit `@media print` columns such as
`grid-template-columns:1fr 1fr`; the PDF engine supports less CSS than a browser.
Give custom `clamp()` typography a concrete print size too. Inspect the rendered
pages: a fourth image spilling onto its own page is a layout failure, even when
the HTML section groups all four. Show application text at a readable scale;
use a dedicated page or a labeled detail crop when a whole image becomes tiny.
The interactive file browser does not fill a PDF page. Put short usage notes
beside relevant artwork or typography, rather than reserving a nearly empty
closing page for it.

Bind artwork and font refs from the IDs your builder actually returns. Font
specimens need their font ref, not merely a family name in their label. For
example, after adding fonts as `heading_font` and `body_font`, this authored
fragment can be inserted into your own composition:

```python
type_group = f'''<div>
  <stimma-type ref="{heading_font}" label="Heading · chosen family / 600"
    style="--sp-type-size:42px;--sp-type-weight:600">A clear, useful heading</stimma-type>
  <stimma-type ref="{body_font}" label="Body · chosen family / 400"
    style="--sp-type-size:22px;--sp-type-weight:400">Readable text for the next thing you make.</stimma-type>
  <p class="sp-note">Explain where to use each style in a sentence.</p>
</div>'''
```

Place this group alongside your authored palette group in
`<stimma-grid columns="2">` within one labeled page section. Keep the two groups
as direct children. This is a composition option, not a prescribed brand layout.

Replace the example labels and copy with the actual choices. Keep the guide's
body prose in the shared defaults unless custom type was requested. A specimen
inherits those defaults when it has no ref; it isn't showing the named font.

## Color swatch

```html
<stimma-swatch value="#172334" label="Ink" usage="Body text on Paper"></stimma-swatch>
```

Use a six-digit hex value from the chosen palette. Text remains outside the
colored area for legibility. Arrange swatches in a `stimma-grid` or your own
responsive layout; use explicit print columns for custom grids. A swatch
doesn't assert approval or calculate contrast. Show actual text/background
pairs in an application and report checked pairs from palette-exports.
Include visible names, hex values and roles; unlabeled colored squares alone
don't help the owner use the palette.
On a narrow screen, keep complete values readable. Use the grid's responsive
columns or provide a breakpoint for a custom palette; five fixed columns are
too narrow for labels and hex values on a phone. Don't clip them or force the
characters into vertical fragments to hide the overflow.

## Typography specimen

```html
<stimma-type ref="m4" label="Heading · Example Sans Medium">
  A useful heading, in the actual font.
</stimma-type>
```

`ref` resolves to a bundled TTF, OTF, WOFF or WOFF2 member/file. It embeds a
local font face for this sample; Packaging export makes the font portable.
Use the actual manifest ref and actual family/weight in the label. Include
license text when bundling fonts. The specimen's text is authored HTML.

Without `ref`, typography inherits the cover's font unless the author sets
`--sp-type-family`. `--sp-type-size` (default 36px) and `--sp-type-weight`
(default 400) are overridable CSS variables. For separate static font weights,
use each weight's own file/ref. Layout, wording, scale and color are yours.
Demonstrate a hierarchy, not three equally large samples: for example a 36px
heading, 22px body and 15px label. Use `--sp-type-weight` for a variable font's
chosen weight; the font face supports the range, while a static font remains
its actual supplied weight.

## Review versus delivery

For alternatives, compare the same application with each direction. Make
candidate labels and the question visible in both HTML and PDF. For delivery,
lead with the chosen system and its immediate uses, then give enough guidance
to repeat it. Retained alternatives belong in clearly labeled sections with
their own file access. Do not turn reserved pick/approve tags into pretend
working controls.

Apps can show a wordmark in a product header and their icon in a separate
app-icons study; a software startup can show a landing header and product UI;
a maker can show a shop banner and care card. Choose different compositions
when those surfaces need them. Avoid forcing everything into square tiles.

Custom brand-colored application panels do not change the neutral cover ground.
The HTML/PDF default remains #0d0d0e with #ededee text unless the user explicitly
asks for a different cover color. Split sections deliberately for PDF; essential
usage instructions and decisions must remain visible outside disclosures.
