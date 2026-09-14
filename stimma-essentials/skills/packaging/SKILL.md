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

Reach for a package when the request calls for a coherent deliverable, a set of
choices, or files to hand on. A single image someone asked to see does not need
to become a package.

Use the installed recipe for a supported file set instead of implementing its
formats and sizes yourself. Deliver the saved package; a prepared source image
or a folder left in the workspace is an intermediate step.

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
for recipe in await stimma.packages.recipes():
    print(recipe["id"], recipe["description"], recipe["inputs"], recipe["params"])
# recipe_id is the id you selected from those results.
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

Add as many members and runs as the deliverable needs. Members can be anything
the library can hold; workspace files are saved with lineage on the way in.
`new`, `add_file`, `set_cover`, and `set_tile` are synchronous; call them without
`await`. The reads, member imports, recipe runs, previews, and saves shown above
are asynchronous. `save()` writes the bundle. Use `show(role="final")` for the completed result
and `role="intermediate"` for work still being developed.

Inspect a draft with `await pkg.manifest()` and `await pkg.preview()` before writing
the cover. The latter returns a workspace folder containing the current cover
and all files, with the rendered cover at `index.html`. Pass the returned
folder directly to `view_image` to review the cover, and use `view_image` for
individual images. Read text with `read_file` and find paths with `glob`.
Use Python when a numerical check is needed. Use the manifest's exact paths as cover
refs. A run id identifies a file browser, not a path prefix. These operations
do not create library items. `set_cover()` validates refs immediately.

Python locals do not persist between calls. Keep the build in a workspace
Python file and execute it with `run_file` again after writing the cover, using
the same saved members and parameters; recipe runs are cached.
Save only the finished package.

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

Templates are starting points. Choose sections and components because they help
the recipient understand this package. Replace all sample words, refs, and facts;
omit irrelevant sections and add groups when the work needs them.

Write responsive HTML, CSS, and optional classic JavaScript to a workspace file.
Use kit elements wherever the page touches package content. Reuse the kit's page
classes (`sp-page`, `sp-title`, `sp-sub`, `sp-label`, `sp-note`); add CSS only for
what the work needs. Resolve refs from the actual manifest, never guessed paths.

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
- `stimma-media` shows a member or run file by `ref`, with optional `caption` and
  `plate` attributes.
- `stimma-grid` groups media for scanning or comparison.
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
When recipe guidance supplies a **Platform Study**, use that name for the context
section. Include every requested target and inspect its actual outputs in context
before saving. Recipe guidance links the relevant reference; read it from this
skill's resource directory. Preview files come from the recipe run, not from a
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
Light and dark examples are both printed. Interactive file browsing remains in
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

## When a member changes

Save revised work as a revision of its existing asset
(`show(..., revises=<asset_id>)`). Rebuild the package when appropriate so the
person receives an up-to-date result. Rebuild carries the authored cover forward;
review its words and composition against the revised contents and refresh it
when needed.
