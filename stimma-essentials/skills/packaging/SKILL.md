---
name: packaging
display_name: Packaging
description: Assemble requested packages and ready-to-use file sets from supplied or generated work. Discover recipe requirements before preparing inputs, author a cover, and save the package.
author: system
tags: [package, deliverable, delivery, export, handoff]
environments:
  chat: true
  flow: true
---

# Packaging

A package holds work together: members, any number of recipe runs, loose extras,
and a designed cover. It is one library item, exportable as a zip or a single
HTML cover. Its scope comes from what the person needs to receive. One package
may span many kinds of work; a recipe run is just one contribution to it.

The “cover” is the package's browsable visual guide, including its PDF guide,
not merely a title page or a fixed-size poster. Show the work at useful scale,
explain the decisions that matter, and provide access to the files. Use as many
responsive sections and PDF pages as the content needs; a small delivery can
still be one page. Author page boundaries with `stimma-section` and inspect them.

Reach for a package when the request calls for a coherent deliverable, a set of
choices, or files to hand on. A single image someone asked to see does not need
to become a package.

Use the installed recipe for a supported file set instead of implementing its
formats and sizes yourself. Deliver the saved package; a prepared source image
or a folder left in the workspace is an intermediate step.

## Workspace operations

Packaging itself needs no shell commands. Use `read_file` for recipe READMEs,
manifests, SVG source and skill references; `glob` for paths; `view_image` for
images and cover previews; and `run_code` / `run_file` for Python and the SDK.
For several text files, use multiple `read_file` calls or a short `run_code`
loop with `open(path).read()`. Do not use bash, `cd`, `cat`, shell pipelines or
Python heredocs for these operations: the native tools already do this work
inside the workspace without a shell permission request.

Use this kit reference and the templates to author the cover. Do not reverse-
engineer the expanded auto cover, probe installed render libraries, or search
for another renderer. If a preview reports an unavailable renderer, report that
specific limitation; do not wander outside the workspace to repair the app.

## Start with the purpose

For exploration, organize candidates so the person can compare them and answer
a clear question. For a finished delivery, show the chosen work in context and
make the contents easy to understand and retrieve. Either can include members,
recipe runs, and extras as needed. Read the stage from the conversation.

## Recipes make files; you design the cover

A recipe is a deterministic formula: assets with declared roles plus parameters
in, a file tree out. Gather and prepare its inputs first. Resolve creative
choices before running it; the recorded parameters make the result rebuildable.

Discover recipes from the installed set, then fetch guidance for the recipe you
intend to use:

```python
recipes = {r["id"]: r for r in await stimma.packages.recipes()}
print([(r["id"], r["description"]) for r in recipes.values()])
# recipe_id is the id you selected from those results.
print(recipes[recipe_id])  # roles and parameters for this recipe only
print(await stimma.packages.guidance(recipe_id))
```

Recipe-specific requirements, file paths, previews, and cover suggestions belong
in that recipe's guidance. Use it to understand the output. The recipe never
emits the cover or decides its composition; you design a page for the whole
package, including anything that did not come from a recipe.

## Build around the work

The following uses values gathered from the conversation and recipe discovery;
it does not prescribe a recipe, input role, or parameter set:

```python
pkg = stimma.packages.new(package_title)
member = await pkg.add_member(source)  # ToolResult, media id, or workspace path
# Optional; repeat for each needed run, mapping its declared roles to members.
await pkg.run(recipe_id, {input_role: member}, chosen_params)
# Optional; repeat for loose extras.
pkg.add_file(extra_path)
print(await pkg.manifest())        # actual member ids, run roots and file paths
print(await pkg.preview())  # workspace folder: inspect outputs before designing
pkg.set_cover("cover.html")
media_id = await pkg.save()
stimma.show(media_id=media_id, role="final")
```

The final `show` line above is for a **first delivery**. For an update, use
`stimma.show(media_id=media_id, role="final", revises=existing_asset_id,
revision_note="What changed")` instead. The existing id comes from the earlier
display receipt or `await stimma.packages.status(original_media_id)`. Reusing a
title does not reuse its asset. Check the receipt before claiming a revision.

Loose native document JSON may reference a private media library. It is not a
portable editable file unless its dependencies are embedded or bundled in a
supported format. Deliver portable source files and omit unusable native stubs.

Keep reusable vector masters as SVG members. A derived raster file set is one
run, not a replacement for its source or the whole package. When the person
requests vectorization, use Vector Design first, inspect the resulting SVG,
then reuse it across the relevant runs. Do not vectorize an adequate raster
unless requested or needed for another deliverable.

Honor the person's requested run boundaries. If they ask for separate runs,
make separate `pkg.run(...)` calls, even when one recipe could produce all the
files in a single call. Repeating a recipe with the same member is supported;
do not consolidate those runs just because the source or recipe is shared.

Add as many members and runs as the deliverable needs. Members can be anything
the library can hold; workspace files are saved with lineage on the way in.
`new`, `add_file`, `set_cover`, and `set_tile` are synchronous; call them without
`await`. The reads, member imports, recipe runs, previews, and saves shown above
are asynchronous. `save()` writes the bundle. Use `show(role="final")` for the completed result
and `role="intermediate"` for work still being developed.

Keep the member and run IDs returned by these calls in named Python variables.
Bind those values into your authored HTML (an f-string or named placeholders)
rather than manually numbering `m1`, `m2`, etc. Adding another font or treatment
then won't shift unrelated artwork to the wrong place. For example, a chosen
font returned as `heading_font` goes in `ref="{heading_font}"` on its
`stimma-type`; the label alone does not select a font.

Inspect a draft with `await pkg.manifest()` and `await pkg.preview()` before writing
the cover. The latter returns a workspace folder containing the current cover
and all files, with the rendered cover at `index.html`. Pass the returned
folder directly to `view_image` to review the cover, and use `view_image` for
individual images. Read text with `read_file` and find paths with `glob`.
Use Python when a numerical check is needed. Use the manifest's exact paths as cover
refs. A run id identifies a file browser, not a path prefix. These operations
do not create library items. `set_cover()` validates refs immediately.

Python locals do not persist between calls. Keep the build in `build_package.py`
and use `write_file` or `edit_file` to update that file between these steps:
Calls on `pkg` belong in that script too; a later `run_code` call has no `pkg`.

1. Build members and runs, then print the manifest and preview folder. Run it
   with `run_file`, inspect the outputs, and write `cover.html`.
2. Add `pkg.set_cover("cover.html")` before the script's preview call. Run it
   again and inspect the authored cover with `view_image`. Use
   `await pkg.preview_html(width=390)` and `width=1200` for real phone/desktop
   checks: it returns a full `image` and readable `slices`. View the slices at
   `detail="high"`; check margins, wrapping, image scale and clipped content.
   This renders the screen layout, separately from PDF pagination. Also print
   `await pkg.preview_pdf()`: it returns `page_count`, the PDF path, and a list
   of `pages` image paths. View each with `view_image(path=..., detail="high")`
   so text, artwork contrast and clipping are actually readable. Check that page
   groups fit, the opening makes the contents clear, and captions are readable.
   Fix the cover and repeat this step if the PDF has spillover pages.
3. Once the cover is ready, append `media_id = await pkg.save()` and
   `stimma.show(media_id=media_id, role="final")`. Run the same script again.

Reuse the same saved members and parameters; recipe runs are cached. Inspection
is your own quality check, not a separate approval step. Do not create approval
marker files, shell commands, or an extra user confirmation to advance these
steps. Save the completed deliverable for the current round. A polished options
package is complete for exploration even when its candidates are not approved;
label the stage and unresolved decisions honestly.

## Names and parameters are decisions

Follow naming conventions already given in the profile or conversation. Use a
recipe's declared `naming` fields when it supports them. Preserve filenames the
recipe marks as fixed: the recipient's software may require them.

Do not invent missing names, inputs, or creative choices to get a recipe to run.
Ask for unresolved decisions, using visual alternatives when they help. Respect
a recipe's refusal and resolve its cause. Names that appear in the deliverable
must come from the person; never derive them from a filename, slug, or prompt.

## The cover

The renderer adds the required hairline and “Made with Stimma” mark at the
bottom of the HTML cover and on every PDF slide. Let the kit place it: do not add
other signatures or “generated by” text to the cover, README, or run files.


Always author a cover and attach it with `set_cover` before `save()`. The cover
is where you decide what the person sees first, how the parts relate, and which
facts matter. The auto cover is a plain fallback for packaging without an agent.

Start from a template, then adapt its structure to the work:

- `templates/delivery.html` — a generic finished delivery: lead work, supporting
  context, and access to the contents.
- `templates/collection.html` — a grouped collection example; adapt the groups
  to the recipient's uses and include every relevant run and loose member.
- `templates/options-board.html` — a comparison of directions with a question.

Default the HTML cover AND every PDF page to neutral near-black `#0d0d0e`,
with light text `#ededee`. Keep that exact neutral background unless the person
explicitly requests a different cover color. Do not interpret “dark” as brown,
navy, a warm charcoal, or a color sampled from the artwork. An asset's requested
background color applies to the asset, not the cover or PDF. Do not independently
restyle the PDF with a different ground. For explicitly requested custom themes,
set a coherent text and background palette and inspect file controls as well
as artwork.

The person's requested design takes precedence over template and recipe cover
suggestions. You author the composition: change colors, typography, spacing,
section order and branding placement when requested. Add a corporate logo as a
member and place it with the kit; retain the small required Stimma footer.
Templates are starting points. Choose sections and components because they help
the recipient understand this package. Replace all sample words, refs, and facts;
omit irrelevant sections and add groups when the work needs them.

Write responsive HTML, CSS, and optional classic JavaScript to a workspace file.
Use kit elements wherever the page touches package content. Reuse the kit's page
classes (`sp-page`, `sp-title`, `sp-sub`, `sp-label`, `sp-note`); add CSS only for
what the work needs. Kit print CSS is a default placed before authored CSS.
Use `:root` tokens (`--sp-bg`, `--sp-fg`, `--sp-muted`, `--sp-line`) for shared
colors (include `--sp-faint` for small size captions), and `@media print` / `@page` for PDF-specific overrides. Use this default when writing cover styles:

```css
:root { --sp-bg: #0d0d0e; --sp-fg: #ededee; }
@page { background: var(--sp-bg); }
```

Only replace these colors when the person explicitly requests another cover
color. Keep the PDF on the same background unless they request otherwise.
Use your own section layout when single/pair/stack does not fit. Keep content
legible, local and portable; inspect the authored cover through `pkg.preview()`
after custom styling. Use `preview_pdf()` to inspect the same PDF export rules
before saving; no shell or separate renderer is needed.
For custom grids, use explicit print columns, for example
`@media print { .my-grid { grid-template-columns: repeat(3, 1fr); } }`.
Responsive `auto-fit` / `auto-fill` grids work in browsers but are not supported
by the PDF renderer. Keep each landscape page's content within its available
height; a large image plus captions and prose may need a smaller print image
or another deliberately grouped page. The kit's single/pair/stack layouts
already reserve space for a heading and captions.

Keep the shared studio feel through the kit's typography, generous margins,
clear hierarchy, neutral default ground, and required footer. Choose page
compositions for the work: a logo lockup, animation frames, and a print sheet
need different arrangements. Size rows, device scenes, and platform groupings
are recipe-specific choices, not requirements for every package.

The cover PDF is a visual guide to the package. Recipe-produced documents are
separate deliverables: preserve their required dimensions, scale, margins,
and colors. Do not apply the cover's landscape page format, background, or
footer to a production file such as a printable label sheet. Include essential
usage instructions in PDF-visible content, not only in HTML disclosures.

Resolve refs from the actual manifest, never guessed paths.

The kit vocabulary:

- `stimma-section` groups content, with an optional `label`. Add `page` for a
  landscape PDF page boundary. `layout="single"` fits one media item;
  `layout="pair"` places two side by side, stacking on narrow HTML screens.
  `layout="stack"` fits two wide media items vertically on the same PDF page.
  These layouts take exactly one or two `stimma-media` children respectively.
  Keep page groups as siblings, not nested sections. Author the content once:
  the kit handles responsive HTML and landscape PDF. Split dense groups into
  additional pages; do not shrink text or crop images to force them onto a page.
  A page containing one `stimma-appearance` prints each variant on its own page.
  Add one `<stimma-grid slot="details">` with up to two supporting media items
  inside a section to keep small details beneath its main images on the same
  PDF page. The details grid stacks on narrow HTML screens.
  For optional HTML-only details, use native `<details slot="details">` with a
  `<summary>Details</summary>` inside the section. It starts closed and works
  without scripts. Put an appearance switch and grids inside when useful.
  The PDF omits this disclosure and gives the main images the full page;
  its appearance variants do not create extra PDF pages.
- `stimma-media` shows a member or run file by `ref`, with optional `caption` and
  `plate` attributes. Bare `plate` is a subtle surface, not automatic contrast.
  Set `style="--sp-plate:#f4f4f5"` with `plate` for dark artwork that needs a
  light surface, or choose another appropriate surface explicitly.
- `stimma-grid` groups media or other content. Optional `columns="2"` creates
  two equal columns on desktop and in PDF, stacking on phones. This can hold
  arbitrary authored groups, such as palette and typography, without a media
  page preset. Custom CSS can override its composition.
- `stimma-sizes` groups media whose `size` attributes specify actual pixel sizes,
  when viewing at that scale is useful.
- `stimma-columns` contains `stimma-column` elements with titles and descriptions.
- `stimma-appearance` switches between children marked `when="light"` and
  `when="dark"`. It follows the system until the reader chooses, even without
  scripts. Use it when the work has meaningful appearance variants.
- `stimma-compare` compares refs `a` and `b`, with `label-a`, `label-b`, and an
  optional `mode="slider"`.
- `stimma-files` opens a file browser in place. Give it a run id as `ref`, or omit
  `ref` for the whole package, including loose files.
- `stimma-swatch value="#172334" label="Ink" usage="Body text"` presents a
  color with readable labels outside the colored area. Arrange freely.
- `stimma-type ref="m4" label="Heading · Family / weight"` presents authored
  sample text in a bundled font (TTF/OTF/WOFF/WOFF2). Without a ref it inherits
  typography. CSS variables `--sp-type-family`, `--sp-type-size`, and
  `--sp-type-weight` allow custom treatment. These are presentation components,
  not a fixed brand-kit layout. Invoke Brand Kits for identity exploration.

A member id (`m1`) or declared bundle path identifies media; a run id (`r1`)
identifies a run's files. For example:

```html
<stimma-section label="Included work">
  <stimma-grid>
    <stimma-media ref="m1" caption="First item"></stimma-media>
    <stimma-media ref="m2" caption="Second item"></stimma-media>
  </stimma-grid>
</stimma-section>
<stimma-section label="Files"><stimma-files></stimma-files></stimma-section>
```

The cover must open from a double-clicked file without a network: no external
URLs, no module scripts, and unique ids. Bundle fonts and images as package
content. Fix any problems reported when attaching the cover before saving.

## How a cover should read

Lead with the work. Show how it will be used or how its parts fit together.
Use previews supplied by recipes where useful; create context where needed.
Choose context and comparisons appropriate to the deliverable, following the
recipe guidance and the person's request. Inspect the actual outputs before
saving. Recipe guidance links the relevant reference; read it from this skill's
resource directory. Preview files come from the recipe run, not from a
separate template installation.
Keep supporting details subordinate to the work and put file access near the
words explaining what the recipient receives.

Use the recipient's language. Avoid internal member ids, run ids, hashes, and
bundle paths in prose. State useful facts about the contents without narrating
how they were generated. Show a quality the person can judge instead of claiming
it in a sentence.

Only promise actions the page supports. Do not invent installation, drag, or
folder-download affordances. Use the existing file browser for access to files.

Let whitespace, typography, and the shared kit organize the page. Avoid nested
cards and redundant decoration. Display sizes, counts, and bytes as facts using
the kit's tabular number styling.

The HTML has one closing brand footer; the PDF repeats that footer on every
slide. The package ZIP also includes a static PDF of the cover. The exporter creates
it from the authored HTML; do not generate a second cover or run a PDF tool.
A recipe may separately produce precisely dimensioned printable files (labels,
for example). Those are deliverables inside the package, independent of the
cover PDF.
Light and dark examples are both printed unless inside an optional details disclosure. Interactive file browsing remains in
`index.html`, alongside the actual files in the ZIP.

## The package's face

The library shows one square image for the package. A recipe may supply a tile,
but choose an image that represents the whole deliverable. For a collection,
that may require a composition of several members. Inspect the existing tile
at the manifest's `cover_image` path inside the folder returned by `preview()`.
Keep it when it represents the package well; use `set_tile` to replace it:

```python
pkg.set_tile("tile.png")  # a workspace path, or image bytes
```

The tile is stored outside the deliverable and does not ship to the recipient.

A folder obtained with `library.get` is an input copy of an earlier package.
`pkg.save()` writes a new managed bundle from the members, runs and extras you
explicitly added. Editing or deleting that old input folder does not revise the
saved result. Inspect the new draft via `pkg.preview()` or retrieve the returned
media id; fix the builder inputs and save a revision when needed. Do not delete
source folders or all previews as a speculative packaging recovery step.

## When a member changes

Start from `pkg = await stimma.packages.open(media_id)` for an existing package.
Inspect `await pkg.manifest()` for member ids, runs and paths, and
`await pkg.preview()` for the artwork and `_stimma/cover.src.html`. This works
in a fresh chat: the saved package supplies the context. Existing outputs are
carried byte-for-byte; installed recipe upgrades do not silently rebuild them.
Add new members/runs normally. To replace a source, use
`await pkg.replace_member(member_id, path)` and `await pkg.rerun(run_id)` for
its dependent runs. Their ids and paths stay stable. Save rejects a changed
source whose outputs have not been refreshed. Update the cover from its saved
source so it describes the change while retaining the rest of the guide.

For an existing loose extra (such as a proof image or notes), use
`pkg.replace_file("extras/proof.png", "updated-proof.png")`, taking the first
argument from the manifest. This preserves its name and path. `add_file` adds
another file, and `replace_member` only accepts member ids.

Each `run_code`/`run_file` call has a fresh Python scope. `open` always loads the
saved package, not an earlier unsaved draft. Explore first, then keep the actual
edits, preview and save in one script. For a source replacement:

```python
pkg = await stimma.packages.open(existing_media_id)
await pkg.replace_member(member_id, "revised-source.zip")
await pkg.rerun(run_id)
pkg.set_cover(open("revised-cover.html").read())  # edited authored source
preview = await pkg.preview()
result = await pkg.save()
print(result)
```

Use the returned media id to display the revision. If inspection requires another
call, retain this script and rerun it after corrections, rather than assuming a
Python variable or an unsaved draft survived. Unchanged source frames can be
copied directly into a revised source archive; do not regenerate them to rebuild
one animation's exports.


Save revised work as a revision of its existing asset. For a package update,
save the new media, then call `stimma.show(media_id=new_media_id, role="final",
revises=existing_asset_id, revision_note="What changed")`. The native `show` tool
accepts the same revision arguments. The display receipt returns the asset id;
retain it for the next update. Rebuilding the same title creates new media, so
explicitly identify the existing asset when displaying a revision.
Rebuild the package when appropriate so the
person receives an up-to-date result. Rebuild carries the authored cover forward;
review its words and composition against the revised contents and refresh it
when needed.


Workspace ZIPs, JSON, fonts, code and editable HTML can be package inputs or
extras without being standalone library items. Pass their paths directly to
`pkg.add_member` or `pkg.add_file`; the package retains them. `library.save`
is for supported library datatypes, not arbitrary production files.
