---
name: mood-board
display_name: Mood Board Studio
description: Create exploratory visual direction boards with palettes, type, references, and layout cues
author: system
tags: [mood board, design, art direction, branding, palette, exploration]
---

# Mood Board Studio

Create mood boards that help people find a visual direction before they know how to describe it. Treat the board as an alignment tool, not a decoration exercise: it should make a fuzzy idea concrete enough to discuss, compare, and build from.

## What a Good Board Contains

A strong mood board usually combines:

- **Reference imagery**: 6-12 images that show atmosphere, subject treatment, lighting, composition, audience, or world.
- **Color palette**: 5-8 swatches, including neutrals, with plain-language roles like "background", "accent", "signal", or "skin/warmth".
- **Typography direction**: 1-3 type moods, such as editorial serif, technical mono, soft grotesk, expressive display, or quiet utilitarian sans.
- **Texture and material cues**: grain, paper, fabric, metal, glass, interface chrome, lighting quality, line treatment, or surface finish.
- **Layout behavior**: whether the final product should feel grid-based, collage-like, cinematic, dense, sparse, symmetrical, scrapbook, brutalist, luxury, playful, etc.
- **Annotation**: short notes explaining why each cluster belongs. A board without rationale is just a collage.

The user does not need to know these categories. You translate their rough words, references, audience, and use case into this structure.

## Product Promise

Make exploratory work easy for non-designers:

- Ask little. Infer generously. Show options early.
- Prefer 2-3 distinct directions over one "perfect" board when the user is still exploring.
- Name directions with memorable labels, not generic numbers.
- Use concrete visual language: "sun-faded terrace", "glossy arcade enamel", "quiet clinical precision".
- Provide a bridge from mood to production: palette roles, image prompt seeds, type guidance, and layout principles.

## Intake

If the user has not provided enough direction, ask at most three questions in one message. Good questions:

1. What is this for? Brand, app, game, event, film, interior, fashion, product, campaign, character, environment, or something else.
2. Who should it resonate with, and what should they feel?
3. Any references, constraints, words to avoid, brand colors, or existing images?

If the user wants momentum or says they do not know, do not interrogate them. Pick a reasonable direction and state your assumptions briefly.

## Exploration Modes

Choose the mode that matches the user's ambiguity.

### Compass Mode

Use when the user has only a vague vibe. Create 3 sharply different directions. Each direction should include:

- A name and 3-5 mood words.
- A palette with roles.
- Image/reference prompt themes.
- Typography and layout behavior.
- What this direction is good for and what it avoids.

After presenting the directions, ask which direction to turn into a finished board.

### Board Mode

Use when the user already knows the direction. Build one finished board with imagery, palette, type, texture, layout cues, and annotations.

### Refinement Mode

Use when the user provides an existing image, board, or set of assets. Analyze it, identify what is working, remove contradictions, extract palette/type/layout cues, then produce a cleaner board or variant directions.

### Production Handoff Mode

Use when the user needs to make something after the board. Convert the board into:

- A concise art direction brief.
- 3-6 generation prompts.
- Palette values and color roles.
- Layout rules.
- Things to avoid.

## Workflow in Stimma

Use Stimma's visual tools to make the result real, not just textual.

**Before you start**: a mood board ends in a composed layout (step 3). If the `layout-design` stimpack is surfaced and you haven't loaded it yet, load it now, in the same step as this stimpack — not when you reach assembly. Loading a stimpack mid-workflow injects new instructions that can pull your focus back to step one and cause you to regenerate references you've already produced.

1. **Gather assets**:
   - Use `library(action="get")` or `library(action="search")` for user-provided or existing assets.
   - Use `browse_web` only when the user requests research, current references, competitors, trends, or real-world source material.
   - Browse `.stimma/tools/text-to-image/` and import a tool to generate missing reference imagery in `run_code`.
2. **Generate in batches**:
   - Use `run_code` with `asyncio.gather()` for batches of references.
   - Generate several small, directed images rather than one overloaded prompt.
   - Group references with `stimma.create_set(results, title="...")` when useful.
3. **Assemble the board** with `create_layout` (using the `layout-design` stimpack you already loaded):
   - Use a fixed artboard unless the user specifies otherwise:
     - Presentation board: 1600 x 1000
     - Square social board: 1080 x 1080
     - Tall concept board: 1080 x 1600
   - The layout should include reference clusters, palette swatches, short labels, texture/type samples, and a concise direction statement.
4. **Inspect and iterate**:
   - Always `view_image` the final board.
   - Fix crowded text, weak hierarchy, clashing colors, repeated imagery, and unlabeled swatches before showing the final.

## Direction Design

Each direction needs a point of view. Avoid bland labels like "modern", "clean", or "bold" unless you qualify them.

Better direction names:

- **Sunlit Archive**: warm paper, quiet nostalgia, annotated fragments, restrained serif.
- **Signal Bloom**: electric accents, kinetic shapes, saturated product photography, high contrast UI.
- **Soft Lab**: milky neutrals, translucent materials, precise spacing, calm clinical trust.
- **Night Market Chrome**: neon reflections, dense signage, glossy surfaces, compressed compositions.
- **Field Notes**: natural textures, handwritten marks, documentary images, utility typography.
- **Future Folk**: handcrafted patterns, optimistic tech, tactile color, modular layout.

When creating multiple directions, vary more than palette. Change the visual logic: image style, density, typography, texture, framing, and emotional temperature.

## Palette Rules

Extract or invent palettes with roles:

- 1-2 base colors for background and broad surfaces.
- 1 primary text or structure color.
- 1-2 accents for emphasis.
- 1 quiet support color for dividers, shadows, secondary content, or texture.

Prefer named swatches and hex values when creating a finished board. Do not let the board become a rainbow unless the concept explicitly depends on maximal color. A useful palette is a working system, not a collection of favorite colors.

## Imagery Rules

Use imagery to answer different questions:

- **World**: where this aesthetic lives.
- **Subject**: what people, objects, or products look like in it.
- **Light**: how scenes are illuminated.
- **Texture**: what surfaces and materials feel like.
- **Composition**: how elements are framed or cropped.
- **Behavior**: motion, gesture, energy, or interaction.

Do not fill a board with near-duplicate images. If two images say the same thing, keep the stronger one or annotate the difference.

## Layout Rules

The board itself should demonstrate the intended design language.

- Editorial directions can use oversized type, strong margins, and asymmetric crops.
- Product/UI directions should use cleaner grids, tighter annotations, and role-based palette blocks.
- Fashion/interior directions can lean into material samples, silhouette, and layered collage.
- Film/game/worldbuilding directions should foreground atmosphere, lighting, environments, props, and character/world logic.
- Brand directions should show how the style behaves across hero imagery, typography, palette, icons/patterns, and campaign tone.

Annotations should be short: 2-7 words per label. Use them to name intent, not describe the obvious.

## Prompting Reference Images

When generating imagery, create targeted prompt families. Example:

```python
import asyncio
from stimma.tools.text_to_image import TOOLNAME  # real name from .stimma/tools/text-to-image/

prompts = [
    "A sunlit editorial photograph of worn cream paper, pencil notes, and translucent vellum layered on a wooden table, soft natural shadows, warm archival mood",
    "A close cropped product photograph of matte ceramic packaging on a pale oat background, restrained luxury, soft side light, minimal composition",
    "A quiet interior scene with linen curtains, raw plaster walls, warm morning light, natural textures, calm design studio atmosphere",
]
results = await asyncio.gather(*[
    TOOLNAME(prompt=p, width=1024, height=768)
    for p in prompts
])
ref_set = await stimma.create_set(results, title="Sunlit Archive References")
stimma.show(ref_set)
```

Replace `TOOLNAME` with a real tool from `.stimma/tools/text-to-image/` (read the catalog — never invent a name). Keep prompts visually specific and avoid asking one image to contain the whole board.

## Finished Board Checklist

Before finalizing, confirm:

- The board has a clear direction statement.
- The imagery is varied but coherent.
- Palette swatches have names, hex values, and roles.
- Typography guidance is present even if no external fonts are available.
- Texture/material/layout notes are visible.
- The board could guide a next design step without another explanation.
- The layout feels intentionally designed and readable at the output size.

## Response Style

When showing results, keep the text concise:

- Name the direction.
- State what was created.
- Mention any assumptions.
- Offer the next logical action: variants, production prompts, or refining toward a chosen direction.

Do not over-explain mood boarding theory to the user unless they ask. The stimpack should make them feel capable by doing the design translation for them.
