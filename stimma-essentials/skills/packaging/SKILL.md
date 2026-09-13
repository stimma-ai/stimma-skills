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

Discover what is installed and what each recipe wants before gathering inputs:

```python
for r in stimma.packages.recipes():
    print(r["id"], [(i["name"], i["kind"], i["required"]) for i in r["inputs"]], [p["name"] for p in r["params"]])
```

Built in: `app-icons` (one square master — an SVG, or a raster ≥1024px → iOS asset catalog,
Android mipmaps, macOS `.icns`, Windows `.ico`, web favicons), `logo` (primary lockup
plus optional mark, wordmark and stacked → SVG/PDF masters where the source is vector,
PNGs in full color, one-color black and reversed, social avatars), `key-art-crops` (one
hero raster → crops at standard aspects around a focal point).

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

The cover is a responsive web page: any HTML, CSS and classic JavaScript you write, plus
kit elements wherever the page touches package content. Write it to a workspace file and
pass it to `set_cover`. Start from a template in this skill's `templates/` folder
(`options-board.html` for exploring, `delivery.html` for finalizing) and depart from it
when you have a reason; the templates carry the studio look so every package reads as
one family.

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
