---
name: contact-sheets
display_name: Contact sheets
description: Present work for the user to review in a contact sheet, an organized page they read in the chat's panel, where they rate, label and comment on each picture. Keep it current as the work changes and read their review.
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
  such as what's new, the best so far, or the decision you need. Put older or
  weaker material lower, show it small, collapse it, or take it off.
- **Shows the finished work the review is about.** If the user asked for
  videos, the sheet shows videos. What you made along the way to get there
  (start frames, keyframes, references, segments, masks) stays off the sheet,
  even when making it was a step the user asked for, and even in a collapsed
  section: everything on a sheet is in its slideshow and asks for the user's
  attention. Put it on the sheet only when it is the thing being reviewed,
  such as a request to pick start frames before anything is animated. The
  media info panel already shows how each piece was made.
- **Says what changed and why, in terms the user sees.** A one-line note per
  section is enough: "Halved the camera speed after round 2 felt rushed."
  Leave out models, LoRAs and settings unless they explain a visible
  difference.
- **Leaves the reviewing to the sheet.** Every picture already has a rating,
  comments and your labels beside it, and the sheet ends with an overall
  feedback box. Don't build your own (see "Review is built in"). Ask only for
  real decisions, with a choice next to the options it's about.
- **Stays current.** As work comes in, update the same sheet and publish
  again rather than re-showing items in chat. When you revise after a review,
  lead with what changed and what still needs the user's eyes. Work they've
  already reviewed and you didn't change doesn't need to be in front of them
  again at a large size: show it as a small strip, collapse it, summarize it, or
  take it off, whichever suits the task. Don't assume what they didn't comment
  on is settled; ask when it matters ("Keep the other two as they are?").
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
  workspace path); `caption` is optional. Pictures go in a
  `stimma-media-group`. One on its own is a featured picture, shown larger:
  use that for a single hero, never for a set.
- `stimma-media-group`: `layout` is `rows` (justified rows, the default; good
  for almost everything, mixed or uniform), `masonry` (portrait-heavy mixes) or
  `uniform` (equal cells set by `aspect="16/9"`, for sweeps where position
  matters). `size` is `s` (a strip of small thumbnails), `m` or `l`.
- `stimma-columns` with `stimma-column`: side-by-side groups such as
  directions, which stack on phones.
- `stimma-compare a="810" b="812" caption="Before and after"`: a slider.

## Asking for review

Every sheet starts with a review the user already knows, before you add
anything:

- **Each picture** has a quick rating (thumbs up or down), a comment button,
  and your labels right under it, and again in the slideshow.
- **Each section** takes comments.
- **The sheet** ends with an overall feedback box.

You compose on top of that. Design the review the way you design the layout:
decide what you need to learn from this round, and ask for exactly that, where
the user is looking when they know the answer.

```html
<stimma-review rating="stars" labels="Likeness off, More like this"></stimma-review>
<stimma-check id="ok-r2-hero" for="r2-hero">Approved for the shop</stimma-check>
<stimma-choice id="direction" label="Which direction should I develop?">
  <stimma-option value="a" ref="801">Evergreen</stimma-option>
  <stimma-option value="b" ref="805">Tide line</stimma-option>
</stimma-choice>
<stimma-rating id="rate-evergreen" label="Evergreen as a direction"></stimma-rating>
<stimma-field id="brief" label="What should round 3 explore?" placeholder="A place, a mood, a prop…"></stimma-field>
```

Give every review element an id you'll keep.

- `stimma-review` sets how pictures are reviewed, once for the sheet: the
  rating style (below) and `labels`, up to 8 short tags of a word or two that
  the user can put on any picture. Define labels when you need to know more
  than good or bad: what's wrong ("Likeness off", "Hands") or what to do with
  it ("Hero", "More like this"). A `stimma-section` takes the same attributes
  for its own pictures.
- `stimma-check` is a yes/no. With `for` naming a `stimma-media` id it shows
  on that picture, beside its rating, wherever you wrote it; use that for a
  question about one picture in particular. Without `for` it is a question
  about the whole sheet or a section ("Ready to publish the set?").
- `stimma-choice` is a decision among options; `multiple` allows more than one
  answer. Each option shows in full on its own row, so word it as the answer.
  An option whose `ref` is a picture already on the sheet is picked on that
  picture too and isn't shown again, so a choice never needs its own copy of
  the work.
- `stimma-rating` is 1 to 5 on something that isn't one picture: a direction,
  a section, an approach. Pictures already have their own rating.
- `stimma-field` is a typed answer to a specific open question that shapes
  what you do next.

### Thumbs, stars, or off

The user should never have to wonder why this sheet rates differently from
the last one. The rule:

- **Thumbs** (the default; write nothing) when each picture gets a decision:
  keep or drop, approve or redo, in or out. That is nearly every sheet:
  deliverables, takes, selects, rounds of a campaign, directions.
- **Stars** (`rating="stars"`) only when both are true: the pictures are
  variations of one thing along a variable (prompt wordings, a setting, a LoRA
  strength, seeds), and how much better one is than another changes what you do
  next. If you would act the same on a 3 as on a 4, it's thumbs.
- **Off** (`rating="none"`, on a `stimma-section` only) when the section's
  pictures aren't up for judgment: references, settled work shown as a strip
  for context, the frames of a storyboard reviewed as a sequence. Comments
  stay. A whole sheet is never off.

Pick one style for the sheet and keep it for the sheet's whole life, round
after round. A section differs from the rest of the sheet only when it holds a
different kind of thing, such as one settings sweep (stars) inside a campaign
sheet (thumbs). Never vary the style for variety, and never switch a sheet
from one to the other between rounds.

### What makes a review easy to give


- **A question about a picture is answered on the picture.** If the same
  question applies to every picture, it's a label, or the thumbs already ask
  it. Never list checkboxes or questions about pictures somewhere else on the
  sheet, where the user can't see what they're answering about.
- **Never ask the user to name, number or describe a picture in text.** "Which
  ones feel off?" is a label ("Likeness off") or a thumbs down, not a field.
- **Don't re-ask what the sheet already asks.** "Keep this one?" is the
  thumbs. "Anything else?" and "What next?" are the overall feedback box.
  A field earns its place only with a question the user wouldn't think to
  answer unprompted.
- **Ask little.** Most sheets need no review elements at all beyond a choice
  of rating style and a few labels. A decision you need gets one choice.

Markers are the user's own library marks, not answers.

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
tiles' ids; the user's review of each picture comes back under its id. For larger edits,
`path = sheet.write_html("sheet.html")`, change the file with `edit_file`, then
`sheet.set_html(path)` and `publish()`. Each publish is the next version of the
same sheet, and the chat gets a one-line update instead of a media panel. Read
the warnings it returns and fix what they name.

The user's answers and comments are tied to component ids. Keep an id while
its review is still open; a publish that drops an id with review you haven't
been sent yet warns you. Once you've acted on a review, you're free to take
that item off. To keep an item but start its review fresh (a take the user is
keeping into the next round), give it a new id, such as `hero` becoming
`hero-2`, so last round's rating and comments don't follow it. Overall
feedback starts empty after each send. Say briefly what you did with their
feedback, in the section note or at the top of the sheet.

## The user's review

The user rates, labels, comments, answers, and then sends the review. It
arrives as a chat message listing each rating, label, answer and comment with
the id and media it's about, plus their overall feedback.
If you're still working, it reaches you at your next step. Act on it: develop
the chosen direction, drop what they rejected, answer their comments in the
next round's notes, and publish. Not every review is for you to act on right
away: the user may be collecting feedback, or acting on it themselves, so
follow what they ask. `await stimma.contact_sheets.review()` returns
the whole review at any time, with unsent items marked.

## Shapes this takes

The same few elements cover very different reviews. Compose for the task, not
from a template:

- **Directions to choose from:** columns of alternatives, each with a short
  rationale, followed by the choice.
- **Tuning a prompt or a setting:** `rating="stars"`, uniform cells, the
  variable as each caption.
- **Converging on a set:** what's new or redone first, at size `l`, each with
  what you did about the comment it answers; work that's already settled as a
  small strip; earlier takes collapsed or gone.
- **A body of work that keeps growing:** a "Start here" section with the best so
  far, then the newest work, with older material collapsed, set-aside work at
  the bottom.
- **Something for someone else:** when the user wants to share the result or
  hand it to another person, make a fresh sheet with only the work that's
  ready, not the working sheet with its history.
- **A batch of deliverables:** one row per item with its specs (a thumbs up is
  the approval), plus a comparison wherever you retouched something.
- **A dataset or a frame pull:** dozens of pictures of one subject. One group
  per round or angle at size `s` or `m`, so the whole set reads at a glance and
  gaps stand out; the user opens any frame full size in the slideshow.
- **A storyboard or sequence:** sections in story order, each with its shots
  and the shot notes beside them.
