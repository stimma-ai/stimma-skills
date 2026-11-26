---
name: element-builder
display_name: Element Builder
description: Build and refine elements, the reusable characters, products, places, styles and brands that tools and agents keep consistent from one generation to the next.
author: system
tags: [element, character, product, style, place, brand, consistency, reference, lora]
environments:
  chat: true
---

# Element builder

An element is a reusable ingredient in the library: a character, a product, a
place, a style or a brand. It holds plain-language instructions, a labeled set of
reference images, optional LoRAs and companion files. When someone adds it on a
tool page or in chat, Stimma reads the instructions, picks the reference images
that suit the prompt, switches on a matching LoRA and keeps the locked traits
intact. A good element makes the hundredth image look like the first one without
the user restating anything.

Talk with the user about the subject, not the file format. They care that Mira
always has the scar over her left eyebrow; they don't need to hear about
`media_menu` or block syntax.

## The tool and the folder

Use the `element` tool for the four things files can't do, and your ordinary file
tools for everything else.

- `element(action="list")` shows the library's elements with their `asset_id`.
  Pass `query` or `kind` to narrow it.
- `element(action="open", asset_id=...)` puts one at `elements/<slug>/` and shows
  its media, LoRAs, files and instructions.
- `element(action="init", slug=..., name=..., kind=..., description=...)` starts a
  new one there. `kind` is `character`, `product`, `place`, `style`, `brand` or
  another word.
- `element(action="save", slug=..., note=...)` checks the folder and saves it as
  the element's next version. Nothing reaches the library until it's saved. Use
  `force=true` only when the user agrees to replace changes made elsewhere.

The folder:

```text
elements/<slug>/
  element.json   name, kind, description, tags, media_menu, loras, files, cover_member_key
  ELEMENT.md     the instructions
  files/         companion files (palettes, measurements, logo SVGs, color references)
  media/         read-only copies of the current reference images, named <key>.<ext>
```

Look at `media/` with `view_image` before you relabel or reorder anything. Every
save is a version the user can go back to, so save at natural milestones with a
short `note` ("Added three-quarter views", "Locked the jacket color") rather
than after every edit.

## Instructions: locked and free

Write `ELEMENT.md` as a short brief to another artist. The starter has two
sections; keep that shape.

- **Always the same** lists the traits that must never drift: face shape and eye
  color, a birthmark, the bottle's exact silhouette and cap color, the logo's
  clear space, the palette's five colors. Be specific and visual. "Hazel eyes,
  thin gold ring in the left ear, a small scar through the right eyebrow" beats
  "distinctive look".
- **Free to change** lists what prompts may vary: outfit, hair styling, setting,
  lighting, pose, expression, season, camera. Listing these matters as much as
  locking traits. It tells the writer it may follow the prompt instead of
  repeating the reference.

Add a default where one helps ("usually in her green field jacket unless the
prompt says otherwise"), but keep defaults few. Every unnecessary rule becomes a
fight with the user's prompt.

Keep it short: a dozen lines of sharp, visual facts work better than a page of
backstory. Write what a camera would see. Leave out personality and history
unless they change how the subject looks.

## Reference media

Each entry in `media_menu` points at a library image:

```json
{
  "key": "face-front",
  "asset_id": 812,
  "title": "Front, neutral",
  "labels": ["face", "front", "neutral", "close-up"],
  "status": "canonical",
  "usage_hint": "Any shot where her face is clearly visible; the default identity reference."
}
```

- `asset_id` is the image's library asset. The `library` tool's results and the
  receipt from `show` both give it next to the `media_id`. Images you generate in
  chat need to be in the library first (`show` with `role="final"`, or
  `stimma.library.save` in `run_code`).
- `key` is a short lowercase name such as `face-front`, `three-quarter-left` or
  `label-closeup`. Keys are stable handles; don't rename them casually.
- `title` and `labels` describe what the image shows: angle (front,
  three-quarter, profile, back), distance (close-up, half-body, full-body,
  detail), expression (neutral, smiling, angry, surprised), lighting, outfit.
- `usage_hint` says when to pick it, in one plain sentence. When the tool page
  has fewer reference slots than the element has images, a model chooses from the
  titles, labels and hints alone, so write them for that choice. "Use for a
  laughing or joyful expression" lets a prompt about a birthday party land on the
  right face. "Nice shot" doesn't.
- `status` is `canonical` (a trusted reference), `candidate` (being tried out)
  or `rejected` (kept for the record, never used). Promote candidates only after
  checking them.
- `"conditional": true` marks a situational image that should be picked only when
  the prompt calls for it (the winter coat, the night version of the storefront).
- `cover_member_key` names the image used as the library card. Pick the clearest,
  most typical one.

Coverage beats quantity. For a character, one clean neutral front face, a
three-quarter view, a profile and a full-body shot cover most prompts; add a few
expressions if the user cares about them. Five excellent images beat twenty
mixed ones. Leave out images where the subject is small, blurred, heavily
stylized or partly hidden; one bad reference pulls every result toward it.

## Checking candidates

In `run_code`, the `stimma` helpers tell you whether candidates really match
before you promote them:

- `await stimma.face_similarity(a, b)` asks "is this the same person?" for two
  media ids or workspace image paths. Above about 0.5 is a confident match, and
  0.35 to 0.5 is worth a look with `view_image`. Different people usually score
  below 0.2. Profiles and stylized faces score lower, so judge those by eye too.
- `await stimma.clip_similarity(a, b)` asks "does this look alike?" for scenes,
  products, places and styles. Above about 0.95 is a near-duplicate, which adds
  nothing as a second reference.
- `await stimma.pairwise_similarity([ids...], kind="face")` (or `kind="clip"`)
  scores a whole set at once. It's the quickest way to find the outlier in a
  batch of turnaround candidates.
- `await stimma.find_faces_like(ref)` and `await stimma.find_similar(ref)` search
  the library for more shots of the same person or subject the user already has.

Compare each candidate with the cover, not with each other. A set whose members
all resemble one another but drift from the cover drifts as a group. Show the
user the shortlist and say which ones you would keep and why; they decide what
counts as "her".

## LoRAs

Each entry in `loras` names a LoRA the user has:

```json
{"key": "mira-krea2", "display_name": "Mira v3", "fingerprint": "…", "model_family": "krea-2",
 "default_weight": 0.8, "trigger": "m1ra", "notes": "Strong at 0.8; drop to 0.6 for wide shots."}
```

A LoRA needs a `fingerprint` or a `display_name`. Set `model_family` so it is
only offered on matching tools, and add a `trigger` word if the LoRA needs one.

When a LoRA is active it owns the identity. Describing the face again in the
prompt fights it and usually makes the likeness worse, so the instructions should
say so. Use the `lora_active` condition:

```markdown
{{#if lora_active}}
Her likeness comes from the LoRA. Don't describe her face, eyes or hair color;
describe outfit, pose, expression and setting only.
{{else}}
Hazel eyes, a short black bob, a small scar through the right eyebrow.
{{/if}}
```

## Per-model instructions

Models follow different prompting styles, so `ELEMENT.md` can carry blocks that
apply only on some models:

```markdown
{{#if model_family == "sdxl" or model_family == "sd-1.5"}}
Short comma-separated tags: brushed aluminum bottle, matte black cap, studio light.
{{#elif model_family in ["krea-2", "flux-1-dev", "qwen-image"]}}
Describe the bottle in full sentences, with the label text in quotes.
{{else}}
Describe the bottle plainly in a sentence or two.
{{/if}}
```

Only block tags are read: `{{#if …}}`, `{{#elif …}}`, `{{else}}`, `{{/if}}` and
`{{#unless …}}`. Conditions can use `==`, `!=`, `<`, `>`, `in`, `not in`, `and`,
`or`, `not`, quoted text, numbers and lists. Any other `{{…}}`, such as a
wildcard, passes through untouched.

The conditions you can count on:

- `model_family`: the model line, such as `krea-2`, `flux-1-dev`, `flux-3-klein`,
  `qwen-image`, `sdxl`, `sd-1.5`, `nano-banana`, `gpt-image`, `seedream`,
  `wan-2.2` or `veo-3`. It is `other` or `unknown` when the model isn't
  recognized, so always give an `{{else}}`.
- `task_type` and `media_kind` (image or video), `supports_images` and
  `max_ref_images` (how many reference slots the tool has).
- `lora_available` and `lora_active`.
- `aspect_ratio` and `orientation` (`portrait`, `landscape` or `square`).
- `surface`: `chat` when you read it yourself.

Keep shared facts outside the blocks and put only the real differences inside
them. If you haven't seen a model behave differently, don't write a block for it.
Test a prompt on each model before writing its block, and keep what worked.
`open` shows the instructions as they read in chat, with notes on any condition
it doesn't recognize.

## By kind

**Character.** Lock the face, build, skin, eyes, hair color and distinguishing
marks; leave clothes, hair styling, expression and setting free unless the user
says otherwise. Cover angles and distances first, then expressions. Check every
face reference with `face_similarity` against the cover. If there's a LoRA, the
instructions should stop describing the face when it's active.

**Product.** Lock silhouette, proportions, materials, colors, finish, logo
placement and any text on the product, word for word. Reference the front, a
three-quarter view, the back or label, and a detail of the logo or texture. Put
exact colors, dimensions and label copy in `files/` (for example
`files/spec.md`) and mention them in the instructions. Free: setting, props,
lighting, scale in the scene.

**Style.** Describe the look in terms a model can act on: medium, line quality,
palette, lighting, texture, composition habits, and what the style never does.
Use reference images that share the style but show different subjects, so the
subject doesn't leak; check with `clip_similarity` that they aren't
near-duplicates. Style is where per-model blocks earn their keep.

**Place.** Lock the architecture, layout, landmarks, materials and signature
colors; leave time of day, weather, season and crowd free unless the user wants
them fixed. Reference an establishing wide shot plus the views people will ask
for (entrance, interior, a signature corner). Mark night or seasonal versions
`"conditional": true`.

**Brand.** Lock the logo usage, colors (exact hex values in `files/`), type
feel, photography or illustration style, and what's off-brand. Keep logo files
and palettes in `files/`. Reference images show the brand applied, not just the
logo by itself. Remind the writer that generated text is unreliable, so exact
wordmarks are best added afterward.

## Working with the user

1. Find out what it is and what must stay the same. If they gave you images, look
   at them first.
2. `init` (or `open` an existing one), write a first `ELEMENT.md`, add the best
   references with clear hints, set the cover and save.
3. Try it: generate a few varied prompts with the element and show the results
   side by side. Note where it drifts.
4. Fix what drifted: sharpen a locked trait, swap a weak reference, add a missing
   angle, write a per-model block. Save with a note saying what changed.

When the user asks to change something ("make her jacket red from now on"),
open the element, edit the instructions, and save. Don't just remember it for
this chat. If a save reports warnings, fix them or tell the user what they mean
in plain words.
