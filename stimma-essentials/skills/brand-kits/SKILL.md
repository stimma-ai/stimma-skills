---
name: brand-kits
display_name: Brand Kits
description: Explore, refine, and deliver practical visual identities for apps, startups, shops, and independent businesses.
author: system
tags: [brand, identity, logo, typography, palette, startup, maker]
environments:
  chat: true
provides:
  - brand_typography
---

# Brand kits

Help the owner launch their next few things and make another matching thing
themselves. A brand kit is a creative project that can contain alternatives,
prepared artwork, useful exports, applications, and a short visual guide.
Invoke **Packaging** for the package API, authored HTML cover and PDF inspection.
Use **Vector Design**, image tools, and other skills where the artwork needs them.

## Understand the business and the next use

Start with what the person has supplied: the actual business name, offering,
audience, existing artwork, preferences, and immediate uses. Ask for missing
consequential decisions together, briefly. Reuse answers already given. An
undecided name can remain an explicit placeholder during visual exploration;
developing names, positioning, slogans, claims, and business stories requires
the person's request or agreement. Sample copy must be recognizable as sample
copy, not a claimed fact about the business.

Apps and software startups are first-class audiences. Their useful surfaces
include a product header, onboarding, a launch graphic, a website, and an app
icon. For makers, a shop banner, care card, sign, sticker, or price card may
matter more. Ask what they will actually use and in which editing tools.

## Start where the artwork is

- **SVG:** preserve the original bytes in the package. Inspect the mark at its
  natural aspect ratio and at useful sizes. Check lettering, embedded images,
  external dependencies, and whether it is genuinely vector artwork. Develop
  around an existing identity unless the person wants it changed.
  Library import can normalize SVG XML. For a supplied source whose exact bytes
  matter, also include it unchanged with `pkg.add_file(source, name="original.svg")`
  and compare its hash. Distinguish this original from normalized working
  members and intentionally edited artwork; don't claim raw-byte equality
  without checking it. Existing library members keep their frozen source bytes.
- **Raster:** inspect resolution, background, and edges. Keep an adequate
  raster for its intended use; vectorize when requested or needed for scalable
  output. Compare any trace/redraw with the original before using it as a master.
- **App icon:** preserve it. A square icon may be a side asset in a wider
  identity, not the only logo. Separating its symbol, adding a wordmark, and
  extending its colors/type are creative decisions. Reuse its master for a
  separate app-icons run when needed.
- **Rough idea or no artwork:** explore coherent directions using generation,
  drawing, typography, and composition. A strong wordmark can be enough;
  there is no obligation to invent a mascot or a symbol.

One-color, reversed, compact and wide versions are prepared artwork. Inspect
them for negative space and legibility. Making every pixel black is often not
a usable one-color mark. Keep originals and changed versions distinguishable.

For a wordmark set in a chosen font, the bundled helper prepares actual glyph
outlines directly in `run_code`; no shell or font-tool installation is needed:

```python
from brand_typography import outline_text
svg = outline_text("The supplied name", "fonts/chosen.ttf",
                   font_size=120, tracking=1, fill="#172334", padding=8)
open("wordmark.svg", "w").write(svg)
```

`outline_text(text, font_path, *, font_size=120, tracking=0, fill="#172334",
padding=8, axes=None) -> str` accepts a local TTF/OTF/WOFF/WOFF2 and returns
self-contained SVG. Sizes/spacing are SVG units; optional variable-font axes
such as `axes={"wght": 600}` affect only the in-memory outline, not the original
font. It supports single-line Latin text with kerning, without ligatures;
complex scripts fail explicitly and need a shaping workflow. Missing glyphs
also fail rather than silently substituting. Save/inspect with Vector Design
tools and adjust spacing visually. Font choice and composition remain yours.

## Explore and choose

Adapt the amount of exploration to the brief. When the direction is open,
two or three substantially different answers are usually enough. Compare
systems—artwork, type, color and one relevant application—not just hue swaps.
Show comparable applications and enough detail to judge each fairly. Give a
recommendation with concrete tradeoffs, such as small-size clarity, fitting a
long name, product imagery, or one-ink reproduction.

Read feedback as design intent. Combining elements from directions is another
design pass: reconcile stroke weight, geometry, spacing, typographic character
and color relationships rather than pasting mismatched ingredients together.
Check revised artwork against the brief and the real use. A selected direction
can still have unresolved typography or color choices.

For a completed exploration round, save and show a polished options package
and ask the decision that moves it forward. It is a complete deliverable for
that round even though the identity is not approved. When the user has already
delegated design choices, make and explain them; don't add approval rituals.

## Keep decisions honest as the package evolves

Use one package for related directions, multiple recipe runs and extras.
Distinguish **candidate**, **selected for refinement**, **approved for use**,
and **archived** in captions and in PDF-visible prose. Several alternatives
may be intended deliverables. A recommendation or selecting a direction does
not by itself mean the owner approved every detail.

Keep a short `decisions.json` or `decisions.txt` extra when multiple directions
or rounds make it useful. Record each direction, its member/run refs and frozen
hashes from the actual manifest, status, what the person decided or delegated,
and remaining questions. This is a design record, not an approval mechanism.
Do not fabricate an approval or require marker files to continue working.
Use descriptive run labels and file names so a ZIP opened without its cover
still distinguishes candidates from delivery artwork.

Revisions preserve history. Revise the existing artwork asset for refinement;
keep a new alternative separate. Rebuild dependent runs, then refresh the cover
and decision record. Approval attaches to the version reviewed, not to new
bytes produced later. Keep the old approval identifiable and describe the
changed version accurately. Put selected delivery files first and retained
exploration in clearly labeled sections. Essential status belongs in the PDF,
not only a collapsed HTML disclosure.

## A small, useful delivery

Usually include:

- The main mark or wordmark and only the prepared variations needed for actual
  backgrounds, scales, and reproduction. Preserve vector masters.
- A small palette with named roles and useful foreground/background pairs.
  Check ordinary text contrast; keep a vivid accent for decoration if it is
  unsuitable for small text. A palette is not automatically a UI design system.
- One family or a complementary type pair: names, exact weights, heading/body
  examples, fallback and installation/use instructions. Use fonts the owner
  can obtain and edit with; bundle font files and license text when permitted.
  Keep editable lettering source where useful and outlined logo delivery where
  portability matters. Identify actual fonts, not a guess from generated text.
- One or two relevant applications. For a launch delivery, make at least one
  useful asset, not only a photorealistic mockup. Include editable source where
  practical and say how to change it. Label mockups and sample copy clearly.
  Ensure the delivered source resolves its images and actual fonts offline;
  naming a CSS font family alone does not load the bundled font. Re-render
  after adding those dependencies so the source and image export agree.
- A short visual guide and a file index explaining which file to use where.
  Keep print production dimensions separate from the cover PDF.
  Write the index from the actual manifest after assembly: workspace folders
  such as `fonts/` or `applications/` may become `members/` or `extras/` in the
  ZIP. Check README paths too. A self-contained HTML application can open
  without installing its embedded fonts; installation is for other editors.

Add patterns, photography examples, voice guidance, packaging, or more templates
when useful. Avoid filling a kit with unused stationery, abstract brand
archetypes, invented construction geometry, or unsupported business claims.

## Production and presentation

Discover installed recipes before preparing inputs. **logo-exports** exports
one prepared treatment without redesigning it; repeat for other variants.
**palette-exports** serializes chosen colors and can check supplied contrast
pairs. Their guidance describes inputs and files. App icons can be another run
from the same master. Creative application layouts and editable sources can
be members or extras; they do not need a deterministic recipe just to belong.
For an editable application made with `create_layout`, export its authored
canvas with `await stimma.rasterize_layout(media_id, out="application.png")`.
Keep its editable source and assets as well as the PNG; don't search render
caches. Use `view_image` to inspect the layout or exported PNG.

Author the cover for this business and this stage. It may lead with an
application, a wide wordmark, an options comparison, or a restrained opening.
The cover is the whole visual guide, not only its opening sheet. A contents list
does not substitute for showing the actual identity, readable palette/type
specimens and relevant applications. Use responsive sections, not a fixed canvas
with clipped overflow; fit PDF pages with `stimma-section` boundaries. Choose
the amount of detail the kit needs, rather than a mandatory page count.
Use the kit's typography, spacing, hierarchy and footer for a coherent feel.
The default HTML and PDF ground is exactly `#0d0d0e`, text `#ededee`, unless
the person explicitly requests another cover color. Artwork/application
surfaces can have their own colors. Respect requested custom typography,
composition and corporate-logo placement; templates are starting points.

Use `stimma-media` for artwork, `stimma-grid`/`stimma-compare` for comparisons,
and `stimma-files` for file access. The small reusable `stimma-swatch` and
`stimma-type` elements are documented in `references/presentation.md`.
They do not determine your layout. Do not build a fixed cover generator.

Inspect the actual files, the responsive HTML and every PDF page using the
Packaging preview APIs. Verify spelling, artwork proportions, legible type,
working color pairs, coherent applications, accurate statuses, local fonts,
and easy access to the right files. The PDF is a visual guide; the ZIP holds
the usable originals and derivatives. The renderer supplies the required
“Made with Stimma” footer; production files and README text have no extra
Stimma branding.
