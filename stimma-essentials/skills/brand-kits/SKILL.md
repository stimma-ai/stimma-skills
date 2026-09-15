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
  - brand_fonts
---

# Brand kits

Make an identity the owner can launch with and use again. Take responsibility
for the files and presentation: the conversation is about their business and
design preferences, not how to build a package or fix a PDF. Invoke **Packaging**
for assembly and its HTML/PDF kit. Use other creative tools when needed.
Give a brief design intent, then work through tools. Return to the conversation
for a meaningful creative choice or the finished result; don't narrate recipe
discovery, font setup, file bookkeeping or each QA step. Use `run_code` for Python work and `write_file`/`run_file` for
reusable build scripts. These native workspace tools handle SVG composition,
fonts and packaging without asking the owner to authorize shell commands.

## Work like a designer helping a small business

Use the supplied name, offering, audience, artwork and immediate uses. Ask only
for missing decisions that materially affect the result, together and briefly.
A short brief with a name, purpose and permission to choose is enough to start.
Choose sensible visual details and useful formats; explain the few decisions
that matter when showing the result. Ask about an editing tool if compatibility
is consequential, rather than making every owner complete a questionnaire.
Names, positioning, slogans and business claims require the owner's input or
explicit delegation. Mark illustrative application copy as sample copy.
For unprovided product facts, use editable placeholders: a care card can say
“Add your tested care instructions here” rather than inventing dishwasher,
microwave or food-safety claims. A fictional demo still needs this distinction.

When asked to choose a direction and package it, do that in one delivery.
When asked to explore, show two or three meaningfully different systems and
recommend one with concrete tradeoffs. Compare the same uses, such as an app
screen or shop banner, so the choice is understandable. Save both alternatives
in one package. Ask a creative question, not permission to run exports.

Feedback such as “B's symbol with A's warmth” is a design pass: reconcile
geometry, spacing, type and color into one system. Preserve the original
candidates and revise the package. Label candidates, selected-for-refinement
work and approved work accurately; choosing a concept isn't approval of later
changes. A brief decision note is enough when useful. The package manifest
already records frozen files, hashes and runs; don't duplicate it in a hand-
maintained approval ledger. Link relevant files using actual manifest refs.

## Start with what they have

- **SVG:** keep the supplied master and natural aspect ratio. Library import
  may normalize XML; include the untouched source as an extra with
  `pkg.add_file(source, name="original.svg")` when preserving supplied bytes.
  Develop around the existing identity unless asked to change it.
- **Raster:** inspect resolution, edges and background. Preserve the original;
  vectorize if useful for scalable delivery. Compare the trace or redraw with
  the original before using it. Describe an intentional redraw honestly.
- **App icon:** preserve it, then consider a wider wordmark and complementary
  type/color system. An icon export can be a side run from the same master.
- **Idea or blank slate:** use generation, drawing and typography to explore.
  A strong wordmark can be sufficient. Only add a symbol when it helps.

Prepared monochrome, reversed, wide or compact versions are design work.
Inspect their negative space and intended backgrounds before exporting them.
`create_svg(file="artwork.svg")` saves authored vector artwork; it is a native
tool, not an STP catalog entry. Use `stimma.rasterize_svg` when pixels are needed.

## Typography without setup work

Choose fonts for this business. Use supplied files when available. Otherwise,
fetch a chosen Google Fonts family and its license directly into the workspace;
there is no need to inspect the owner's machine or install fonts system-wide:

```python
from brand_fonts import fetch_family, font_face
from brand_typography import outline_text
family = fetch_family("Space Grotesk")  # agent-selected example, not a default
print(family)  # actual font paths, weights, axes, license path and source
font = family["fonts"][0]["path"]  # choose the actual style from these rows
css = font_face(font, family="Brand Heading")
svg = outline_text("The supplied name", font, font_size=120, fill="#172334")
```

`fetch_family(family, dest="fonts")` downloads open font files plus their license
from the official Google Fonts repository and reuses a complete local copy.
It returns `{family, fonts:[{path,family,style,weight,css_style,axes}], license, source}`.
Read the license and bundle the chosen fonts and license with the kit.
`font_face(path, family=None)` returns data-embedded `@font-face` CSS with the
actual weight/range and style; use that same family name in editable HTML.
Write the returned CSS into the artwork; don't print its large embedded font data.
`describe_font(path)` reads this metadata for a supplied font. No network is
needed to embed supplied/local files. A failed download is a concrete font
availability issue, not a reason to search unrelated folders.

`outline_text(text, font_path, *, font_size=120, tracking=0, fill="#172334",
padding=8, axes=None) -> str` makes portable SVG lettering with actual glyphs
and kerning. Optional variable axes such as `{"wght":600}` affect outlines only.
It supports single-line Latin text without ligatures; unsupported scripts or
missing glyphs fail explicitly and need a shaping workflow. Inspect spacing.
The returned SVG already has a zero-origin viewBox and padded bounds; use it
directly or place it in a lockup without re-normalizing its glyph coordinates.
Keep live text in editable application sources; outline logo delivery artwork.

## A small, usable delivery

Include what helps the next use, usually:

- A primary logo and the few background/size variations it needs; vector
  masters where available, plus practical raster exports.
- A small palette with roles and checked text/background pairs.
- Actual type specimens with family, weight, hierarchy and brief use guidance.
- One or two useful applications, including an editable source and usable
  export. Apps/startups might need onboarding, a product header or launch
  graphic; shops/makers might need a banner, care card or sign. Photorealistic
  mockups alone aren't editable assets. Keep live copy, embed fonts/images,
  render at the authored dimensions, and inspect the final export.
- A concise visual guide and useful file access. A short README may explain
  editing or production details; write paths from the assembled manifest.

Avoid inflating the job with unused stationery, elaborate strategy documents,
platform icon sets nobody requested, or a long account of how the tools worked.
For print work, keep the production document's dimensions separate from the
visual guide. A care card's editable text and print size matter more than
multiple decorative mockups.

## Deliver without packaging back-and-forth

Read `.stimma/skills/stimma-essentials/skills/brand-kits/references/presentation.md`
before composing the guide. It shows how to
use the shared components for readable pages while keeping your design freedom.
Use `await stimma.packages.recipes()` to discover `logo-exports` and
`palette-exports`, then `await stimma.packages.guidance(recipe_id)` for their
exact inputs. These are package recipes, not tools in the STP catalog. The first
exports one prepared treatment; the second writes chosen color values and
checks supplied contrast pairs. Repeat runs as needed; recipes don't design.
Use `await stimma.rasterize_layout(layout_media_id, out="application.png")`
for an authored application's PNG. Export the editable source with
`await stimma.export_layout_html(layout_media_id, out="application.html")`
and include that returned file. This uses the app's HTML exporter to embed the
actual fonts and images; raw workspace HTML may have broken refs after delivery.

Author the complete guide with the kit's page groups and typography defaults:

- Put real artwork on the opening page, with its title and brief explanation.
  Avoid a title-only opening or a mostly empty contents/closing page. Group
  short color/type/use notes into a considered composition instead of giving
  every heading a whole PDF page.
  `stimma-grid columns="2"` can pair palette and typography on one page;
  its content groups stack on phones.
- A dark transparent logo needs a light surface: use, for example,
  `<stimma-media ref="actual-ref" plate style="--sp-plate:#f4f4f5">`.
  Bare `plate` is a subtle dark surface, not a contrasting logo background.
  Choose the artwork surface deliberately; don't recolor the guide to fix it.
- Show actual font specimens at useful scale and applications with readable
  detail. Notes belong beside their subject, not on a spill page.
  On phones, palette names, whole hex values and roles must remain readable.
  Kit swatches in a responsive grid handle this; a custom row also needs a
  narrow-screen layout. An overflow-hidden box with clipped text fails review
  even when the page itself has no horizontal scrollbar.
- File navigation already comes from `stimma-files`. Don't invent a directory
  tree in a README. If editing instructions need a filename, obtain it from
  `await pkg.manifest()` after adding that file; workspace and ZIP paths differ.

The guide defaults to neutral #0d0d0e
with #ededee text; artwork may have its own surfaces. Honor explicit custom
cover colors, type, composition and corporate-logo placement.

Check the actual HTML and PDF yourself through Packaging previews, correct
concrete defects, then save/show the completed package for this round. Routine
QA and export are your job; the owner should only need to discuss the design.
The exporter supplies the required “Made with Stimma” footer. README and
production files carry no extra Stimma branding.
