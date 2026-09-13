---
name: packaging
display_name: Packaging
description: Deliver finished work as a package — masters, recipe-built asset sets (app icons, logo kits, key art crops), extras, and a designed cover — instead of loose files
author: system
tags: [package, deliverable, delivery, app icons, logo, brand, export, handoff]
environments:
  chat: true
  flow: true
---

# Packaging

You finish creative work the way a studio does: as a package. A package is one library
item that holds the masters, every derivative a deliverable needs, any loose extras, and a
cover page that presents it. The person gets a browsable thing they can export as a zip
or a single HTML file, and Stimma can rebuild it when a master changes.

Reach for a package when the request implies a deliverable rather than a picture: a logo,
app or favicon set, brand assets, a campaign's crops, "the final files", "everything for
the developer", "package this up". A single image someone asked to see is not a package.

## Two stages, two kinds of package

- **Exploring.** Candidates are the members, the cover is an options board (a
  contact-sheet grid of the directions with short captions), and the turn ends with a
  question about which direction to take. No recipes yet.
- **Finalizing.** The chosen masters are the members, recipes produce the production
  trees, the cover shows the work in context with the file index underneath, and the
  package is shown as the final result.

Read which stage the person is in from the conversation. "Give me some logo ideas" is
exploring. "Finalize the second one" or "make the icons for it" is finalizing.

## Recipes arrange; you create

A recipe is deterministic code: assets with declared roles plus parameters in, a file
tree out. It never generates, so every input it needs must exist first. If the logo kit
needs a transparent mark and you only have a raster on white, cut it out before packaging.
Judgment goes into parameters: the focal point for crops, the background color behind an
iOS icon, the filename convention. The package records them, so a rebuild replays your
decisions exactly.

Recipes are discovered, never listed here — what is installed varies by profile, and this
skill stays the same length whether that is three or fifty. Ask, then read the notes of
the one you picked:

```python
for r in stimma.packages.recipes():
    print(r["id"], r["description"], [(i["name"], i["kind"], i["required"]) for i in r["inputs"]])
print(stimma.packages.guidance("app-icons"))   # only for the one you are about to use
```

A recipe's `inputs` tell you what to gather and `params` what you get to decide. Its
guidance is where the craft lives: what makes a good master, which parameter matters,
what goes wrong. Fetch it when you commit to a recipe, not before.

## Building one

```python
pkg = stimma.packages.new("Acme app icons")
master = await pkg.add_member(icon_result, role="master")      # ToolResult, media id, or workspace path
await pkg.run("app-icons", {"master": master},
              {"platforms": ["ios", "android", "web"], "background": "#101820", "app_name": "Acme"})
pkg.add_file("brief.md")                                        # optional loose extras
pkg.set_cover("cover.html")                                     # optional; see below
media_id = await pkg.save()
stimma.show(media_id=media_id, role="final")
```

Members can be anything the library can hold; workspace files are saved with lineage on
the way in. Several recipe runs can live in one package (a logo kit plus its app icons).
`save()` writes the bundle and returns its media id; `show(role="final")` is what commits
it as the deliverable, so leave exploration packages at `role="intermediate"` or show
them final only once the person has picked.

## Filenames

People have conventions. Look for one in the profile's instructions and the conversation
(case, separators, a project code, a prefix) and express it through the recipe's `naming`
parameter rather than asking again:

```python
{"naming": {"template": "{slug}-{variant}-{color}-{size}", "case": "kebab"}}
```

Each recipe declares which fields its template may use. Platform-fixed names
(`Contents.json`, `mipmap-xxhdpi/`, `favicon.ico`) are never renamed, so a convention
can't break an Xcode or Android drop-in.

## The cover

Most packages do not need you to write one. A recipe presents its own output — the app
icon set already shows the icon on a home screen and at every real size — so save without
a cover and you get a designed page for free. Write one when you are presenting a choice,
or when the package is going to a client and deserves words.

When you do write it, it is a responsive web page: any HTML, CSS and classic JavaScript,
plus kit elements wherever the page touches package content. Write it to a workspace file
and pass the path to `set_cover`. The shape that works:

```html
<div class="sp-page">
  <h1 class="sp-title">Three directions for the mark</h1>
  <p class="sp-sub">Pick one to develop, or name the parts of two you want combined.</p>
  <div class="sp-section">
    <stimma-grid>
      <stimma-media ref="m1" caption="A · Editorial"></stimma-media>
      <stimma-media ref="m2" caption="B · Brutalist"></stimma-media>
    </stimma-grid>
  </div>
</div>
```

The kit ships the page styling, so reuse its classes — `sp-page`, `sp-title`, `sp-sub`,
`sp-section`, `sp-label`, `sp-note` — instead of inventing a look per package. Add your
own CSS for anything the work itself needs.

Kit elements resolve by ref — a member id (`m1`), a run id (`r1`) or a bundle path from
the manifest:

```html
<stimma-media ref="m1" caption="Primary mark"></stimma-media>
<stimma-grid><stimma-media ref="m1"/><stimma-media ref="m2"/></stimma-grid>
<stimma-files ref="r1"></stimma-files>
<stimma-compare a="m1" b="app-icons/ios/AppIcon.appiconset/icon-180.png" mode="slider"></stimma-compare>
```

Rules the cover must satisfy, because it has to open from a double-clicked file with
no network: no external URLs (fonts and images come in as members), no
`<script type="module">`, unique ids. A cover that breaks a rule is refused with the
reason; fix it and save again. Without a cover the package gets a plain auto-generated
one, which is fine for a quick handoff and wrong for a client-facing delivery.

Show the deliverable in context on a finalizing cover: the icon on a phone home screen,
the logo on a card or a site header, key art in the frame it will run in. That is the
difference between "here are files" and "here is the work".

## Parameters are decisions, so make them

A recipe's parameters are where your judgment goes, and defaults are not
answers — they are what a recipe does when nobody decided. A colour, a focal
point, a naming convention: pick each one for this piece of work and say why in
a sentence when you hand it over. Where a choice can be checked, the recipe
checks it and refuses with the reason, so read the error rather than working
around it.

## How a cover should read

The page is going to a person who is receiving work, not inspecting a build. Hold to
these and it will look like a studio sent it.

**Say what it is, not how it was made.** No members, no runs, no hashes, no bundle paths
in prose. "App icon set · 14 files" is the whole preamble.

**Never claim an affordance the page does not have.** Do not write "drag this into
Xcode" or "click here to install". Name what a folder contains and stop. The reader can
see the download buttons.

**Cut the editorial.** Lines like "every size is its own render, so the mark stays
legible" are the sound of a machine admiring itself. If a fact matters, show it — the
size row proves legibility better than a sentence about it. If it does not, delete it.

**Show the work in the place it will live.** An icon on a home screen, a logo on a card,
key art in its frame. One well-made context beats three captions.

**Lead with the work.** The first screen is the piece, large. Files come last and stay
quiet: a count, one download, and a tree the reader can ignore.

**Let the page breathe, and use one surface.** Space separates sections; hairlines
separate peers. No cards inside cards, no box around everything. The kit's classes
already carry this — reuse them rather than restyling the page.

**Numbers are facts, not decoration.** Sizes, counts and bytes go in the mono, tabular
style the kit provides, never in a sentence.

## The package's face

Every package shows one square image in the library. A recipe that knows what it
made supplies a good one — an icon set shows the icon the way a device draws it.
Override it whenever you can do better, especially for packages you designed:

```python
pkg.set_tile("tile.png")     # a workspace path, or image bytes
```

A designed tile is worth making when the package is a deliverable someone will
scan a grid for. It is stored outside the deliverable, so the client never
receives it.

## When a master changes

If you revise something that belongs to a package, save it as a revision of the existing
asset (`show(..., revises=<asset_id>)`), not a new one. The package notices its member
moved on and offers a rebuild; do the rebuild yourself when you are mid-conversation so
the person sees a fresh package, not a stale one. The cover carries forward verbatim,
so if its prose named the old version, refresh it.
