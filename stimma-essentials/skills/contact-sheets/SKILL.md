---
name: contact-sheets
display_name: Contact sheets
description: Present work for the user to review in a contact sheet, an organized page they read in the chat's panel, with the questions you need answered next to the work. Keep it current as the work changes and read their review.
author: system
tags: [review, present, presentation, contact sheet, choices, directions, batch, rounds, feedback]
environments:
  chat: true
  flow: false
---

# Contact sheets

A contact sheet is your presentation of work for the user to look at and
respond to. It opens beside the chat and stays there while you work. Use one
whenever what you're presenting is more than the user should take in at a
glance: several deliverables, alternatives to choose between, multi-stage work,
or a body of work that keeps growing as you continue. Showing those items one
panel at a time in chat leaves the user to dig results out of the transcript.

A sheet is not a thumbnail dump and not a package. A package is a delivery
(files to hand over). A sheet is for reviewing: you decide what is worth their
attention, in what order, with what explanation, and what you need from them.

## What a good sheet does

- **Reads in the order the user should read it.** Lead with what matters most,
  such as the current round, the best so far, or the decision you need. Put
  older or weaker material lower, or in collapsed sections.
- **Shows only what you want looked at.** Finished work, not the ingredients.
  Intermediates (keyframes, segments, masks) stay out unless the user is
  reviewing them specifically; the media info panel already shows how
  something was made.
- **Says what changed and why.** A one-line note per section is enough:
  "Halved the camera speed after round 2 felt rushed."
- **Asks for decisions next to the work.** Put a choice next to the options it's
  about, a rating on the picture being rated, an approval check on the item it
  approves.
- **Stays current.** As work comes in, add it to the same sheet and publish
  again. Don't start a new sheet for the same work; don't re-show the same
  items in chat.
- **Keeps your judgment visible.** If you set something aside, you can keep it
  in a collapsed section with the reason. The reasons tell the user why it's
  missing and help them steer you.

## The format

Write HTML. Kit elements show media and ask for review; everything else
(headings, prose, layout, your own CSS) is yours to compose. Pictures are never
cropped. There are no scripts and no external URLs.

```html
<stimma-section id="round-2" label="Round 2 · Tide line, developed" note="Cooler grade, the cup in every hero.">
  <stimma-media-group layout="rows" size="m">
    <stimma-media id="r2-hero" ref="812" caption="Rocky point"></stimma-media>
    <stimma-media ref="813" caption="Headland"></stimma-media>
  </stimma-media-group>
</stimma-section>
```

- `stimma-section`: `label`, `note`; `collapsible` and `collapsed` fold it,
  keeping a strip of its pictures in the header.
- `stimma-media`: `ref` names the media (its media id, `asset:<id>`, or a
  workspace path); `caption` is optional.
- `stimma-media-group`: `layout` is `rows` (justified rows, the default; good
  for almost everything, mixed or uniform), `masonry` (portrait-heavy mixes) or
  `uniform` (equal cells set by `aspect="16/9"`, for sweeps where position
  matters). `size` is `s` (a strip of small thumbnails), `m` or `l`.
- `stimma-columns` with `stimma-column`: side-by-side groups such as
  directions, which stack on phones.
- `stimma-compare a="810" b="812" caption="Before and after"`: a slider.

Review elements. Give every one an id you'll keep:

```html
<stimma-choice id="direction" label="Which direction should I develop?">
  <stimma-option value="a" ref="801">Evergreen</stimma-option>
  <stimma-option value="b" ref="805">Tide line</stimma-option>
</stimma-choice>
<stimma-rating id="rate-r2-hero" for="r2-hero"></stimma-rating>
<stimma-check id="ok-r2-hero" for="r2-hero">Approved for the shop</stimma-check>
<stimma-field id="notes" label="Anything else?" placeholder="Steer the next round…"></stimma-field>
```

`for` ties a rating or check to a `stimma-media` id, so it also appears when
the user steps through that picture in the slideshow. `stimma-choice` takes
`multiple` for more than one answer. Every picture and section takes comments
without you adding anything. Markers are the user's own library marks, not
answers.

Your CSS styles only the sheet. The variables `--cs-fg`, `--cs-muted`,
`--cs-faint`, `--cs-line`, `--cs-accent`, `--cs-display` and `--cs-mono` follow
the app's theme in light and dark, so use them rather than fixed colors for text
and rules.

## Working with it in code

```python
sheet = stimma.contact_sheets.new("Spring campaign directions")
sheet.set_html("sheet.html")              # a workspace file you wrote, or an HTML string
print(await sheet.publish("Three directions"))   # opens it for the user: {asset_id, version, warnings}
```

Later, in any code call:

```python
sheet = await stimma.contact_sheets.open()        # this chat's latest sheet
group = sheet.add_section("round-3", "Round 3", "Slower camera moves", position="start")
sheet.add(group, results, captions=["Lighthouse", "Driftwood bay"])
print(await sheet.publish("Round 3"))
```

`add()` takes ToolResults, media ids or workspace paths and returns the new
tiles' ids, for ratings or checks tied to them. For larger edits,
`path = sheet.write_html("sheet.html")`, change the file with `edit_file`, then
`sheet.set_html(path)` and `publish()`. Each publish is the next version of the
same sheet, and the chat gets a one-line update instead of a media panel. Read
the warnings it returns and fix what they name.

Keep component ids stable when you rewrite. The user's answers and comments
are tied to them, and a publish that drops a reviewed id warns you.

## The user's review

The user answers, rates, comments, and then sends the review. It arrives as a
chat message listing each answer and comment with the id and media it's about.
If you're still working, it reaches you at your next step. Act on it: develop
the chosen direction, drop what they rejected, answer their comments in the
next round's notes, and publish. `await stimma.contact_sheets.review()` returns
the whole review at any time, with unsent items marked.

## Shapes this takes

The same few elements cover very different reviews. Compose for the task, not
from a template:

- **Directions to choose from:** columns of alternatives, each with a short
  rationale, followed by the choice and any questions that shape the next round.
- **A body of work that keeps growing:** a "Start here" section with the best so
  far, then one section per round with what changed, older rounds collapsed,
  set-aside work at the bottom.
- **A batch of deliverables:** one row per item with its specs and an approval
  check, plus a comparison wherever you retouched something.
- **A storyboard or sequence:** sections in story order, each with its frames as
  a strip and the shot notes beside it.
