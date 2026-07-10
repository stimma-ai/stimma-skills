---
name: variations
display_name: Variations
description: Create controlled variations of an existing media asset by preserving selected visual traits while changing seeds, prompts, or image-reference settings
author: system
tags: [variations, image generation, img2img, seeds, exploration, prompt editing]
environments:
  chat: true
---

# Variations

Create variations of an existing image, prompt, character, style, scene, or loose idea. A variation is not one technique. It is a choice about what should stay fixed, what should drift, and how much creative risk is useful.

## Core Judgment

Start by inferring the user's real goal. People often ask for "variations" when they mean one of these:

- **Lucky roll**: Same concept, same prompt/config, different seeds. They like the image and want a better draw.
- **Near misses**: Keep the concept and style, make small prompt changes to discover better phrasing.
- **Controlled alternatives**: Change one or two named elements, such as hair, outfit, pose, expression, lighting, crop, colorway, or background.
- **More of this**: Preserve the identity, style, or product language closely while producing sibling images.
- **Creative directions**: Use the source as a starting point and explore meaningfully different treatments.
- **Recovery from weak source info**: The user only has a random image or a past asset with little or no lineage.

Do not ask the user to pick from a menu of techniques. Choose the technique that matches their intent, and explain the tradeoff in one short sentence when it matters.

## Intake

Use the least amount of clarification needed.

Ask one focused question only when the request is underdetermined in a way that changes the output:

- "Keep this very close to the original, or explore?"
- "What should vary: seed/composition, style, or a specific element?"
- "How many variations do you want?"

If the user gives a direction like "show variations of this character's hair style", do not ask. Generate a compact batch of labeled choices.

If the user does not specify count, use:

- 4 variations for close/lucky-roll work.
- 6 variations for a single element sweep.
- 8-12 variations for broad creative exploration.

## Technique Selection

### Same prompt, different seed

Use when the source prompt/config is good and the user wants a better version, more options, or a "lucky roll."

Rules:

- Reuse the same tool/model and core config when lineage or current context gives it.
- Change only `seed` unless the original had obvious prompt problems.
- Generate in a batch with `run_code` and `asyncio.gather()`.
- Show the results individually with `stimma.show(results)` so the user can compare and pick.

### Same seed, near-miss prompt

Use when the user likes the composition but wants to tune wording or nudge a
result — including any "same but ..." ask (same but at night, same but in
watercolor).

Rules:

- Keep the seed fixed. The mechanic: call the tool with `params_from=` the
  original's media id AND pass that result's own `seed=` explicitly (both are
  shown in its generation summary). That reuses the recorded settings so the
  composition holds while your prompt edit shifts the one detail.
- Change one prompt axis at a time.
- Prefer small, legible prompt edits over paraphrasing the whole prompt.
- Use row/column labels when making a comparison grid.

### Prompt salting

Use when the user wants tiny stochastic differences but the tool does not expose seed well, seed reuse is unreliable, or repeated calls with the same prompt collapse toward similar results.

Rules:

- Add a visually inert salt to the prompt, such as a private batch token or production note, not visible content.
- Keep the salt unobtrusive: "variation token 7f3a" is acceptable; do not add fake objects or style words.
- Do not use prompt salting when a real seed parameter is available and works.

### Surgical prompt edits

Use when the user names a specific element to vary.

Rules:

- Keep everything else explicit and stable.
- Generate a small labeled sweep of alternatives.
- Change only the target element unless related details must change to stay coherent.
- For people/characters, preserve identity descriptors, face, body, pose, and style unless the user asks to vary them.

Examples of good axes:

- Hair: bob, long braid, undercut, loose curls, slicked-back, high ponytail.
- Wardrobe: linen suit, leather jacket, work apron, ceremonial robe, raincoat.
- Lighting: soft window light, neon rim light, overcast daylight, golden backlight.
- Composition: close portrait, waist-up, full body, low angle, overhead crop.

### Image-to-image without preprocessing

Use when the user references an existing image and wants recognizable similarity but not exact structure lock.

Rules:

- Pass the source as `input_images`.
- Prompt the desired target, not an analysis report of the source.
- Explicitly say what to preserve: identity, pose, framing, palette, style, product shape, or composition.
- Keep edit language imperative for edits: "Keep the character's face, pose, and framing. Change only the hairstyle to..."

### Image-to-image with ControlNet

Use when the image structure must stay close: pose, silhouette, layout, edges, depth, product geometry, room composition, or camera framing.

Rules:

- Check the tool schema for supported `controlnet` or equivalent preprocessors.
- Use `canny` or edge-like preprocessing for outlines, product shape, graphic layout, and crisp geometry.
- Use `depth` for scenes, rooms, poses, perspective, and spatial composition.
- Prompt for the target image. ControlNet preserves structure, not semantic content.
- Do not use ControlNet for broad creative exploration unless the user wants the structure anchored.

### Same model/config from lineage

Use when the source has lineage and the user wants more of the same thing.

Rules:

- Prefer the original tool, model, LoRAs, aspect ratio, dimensions, seed strategy, and key parameters.
- Preserve known successful config instead of upgrading models without being asked.
- If using a premium/final-quality alternative would materially change cost or behavior, flag the tradeoff before running.

### Random photo or no lineage

Use when the user provides only an image with no prompt/config.

Rules:

- Use `view_image` to describe what matters: subject identity, style, composition, palette, lighting, and distinctive details.
- Decide whether the user wants visual siblings or an edit of the source.
- For siblings: write a fresh prompt from the analysis and use text-to-image or reference-guided image-to-image depending on needed fidelity.
- For close preservation: use image-to-image and possibly ControlNet.
- Do not pretend to know the original seed, model, LoRA, or prompt.

## Output Patterns

### Close Variations

Use for lucky-roll and "more like this."

```python
import asyncio
# Browse .stimma/tools/text-to-image/ and read a tool's stub for its exact
# function name, then import it (replace TOOLNAME with that real name).
from stimma.tools.text_to_image import TOOLNAME

seeds = [101, 202, 303, 404]
results = await asyncio.gather(*[
    TOOLNAME(prompt=prompt, seed=seed, width=width, height=height)
    for seed in seeds
])
stimma.show(results)
```

Replace `TOOLNAME` with a real tool from `.stimma/tools/text-to-image/`, and `prompt`, `width`, `height` with values from the source lineage. Never invent a tool name — read the catalog.

### Single-Axis Sweep

Use for "show hair variations", "try different backgrounds", or "explore lighting."

```python
import asyncio
from stimma.tools.text_to_image import TOOLNAME  # real name from .stimma/tools/text-to-image/

variants = [
    ("Short bob", prompt.replace("{hair}", "a sharp chin-length bob")),
    ("Loose curls", prompt.replace("{hair}", "loose shoulder-length curls")),
    ("High ponytail", prompt.replace("{hair}", "a high ponytail with soft flyaways")),
    ("Undercut", prompt.replace("{hair}", "a clean side undercut with longer hair swept over")),
]

results = await asyncio.gather(*[
    TOOLNAME(prompt=p, seed=seed, width=width, height=height)
    for _, p in variants
])

grid = await stimma.create_parameter_sweep(
    media_ids=results,
    rows=1,
    cols=len(results),
    row_headers=[""],
    col_headers=[label for label, _ in variants],
    title="Hair Variations",
)
stimma.show(grid)
```

### Reference-Guided Variations

Use when preserving an attached or selected image matters.

```python
import asyncio
# Reference-guided = image-to-image: browse .stimma/tools/image-to-image/ for the tool.
from stimma.tools.image_to_image import TOOLNAME  # real name from the catalog

source = "MEDIA_ID"
prompts = [
    "Keep the character's face, pose, and framing. Change only the hairstyle to a sharp chin-length bob.",
    "Keep the character's face, pose, and framing. Change only the hairstyle to loose shoulder-length curls.",
    "Keep the character's face, pose, and framing. Change only the hairstyle to a high ponytail.",
]

results = await asyncio.gather(*[
    TOOLNAME(prompt=p, input_images=[source], seed=seed + i)
    for i, p in enumerate(prompts)
])
stimma.show(results)
```

If structure must stay close and the selected tool supports it, add the appropriate `controlnet=` parameter — the tool's `.stimma` stub lists which preprocessors it supports.

## Comparison and Presentation

- Show variations individually by default — the user is choosing among peers, and `stimma.show(results)` is the comparison surface.
- Use a **set** only when the user wants the variations kept as one collection in their library (a pack or series they asked for as a unit).
- Use a **grid** when the user needs to compare named changes.
- Use 1 row with labeled columns for a single axis.
- Use rows for source prompts/images and columns for the varied parameter when comparing multiple sources.
- Label with the actual changed value, not generic "Variation 1."

## Quality Control

Before showing final results, inspect the output when the task depends on preservation, identity, product shape, text, or a named element. Regenerate or revise if:

- The supposedly fixed element drifted.
- The changed element did not change enough.
- Variations are near-duplicates in an exploration set.
- The image-to-image output copied unwanted artifacts from the source.
- ControlNet over-constrained the result and made it stiff.

## Talking to the User

Be direct and brief.

- For close work: "I kept the prompt/config stable and varied seeds."
- For surgical work: "I held the character and framing steady and swept hairstyle only."
- For exploration: "I made these wider so we can find a direction, not just a better roll."
- For no-lineage images: "There was no generation lineage, so I treated the image as a visual reference and rebuilt the prompt."

After showing results, suggest one concrete next step the user can take: pick a favorite to refine, run more seeds around a chosen one, or change a named axis (hairstyle, lighting, framing). Frame the suggestion around what you set up — the user is best positioned to judge which result they like.
