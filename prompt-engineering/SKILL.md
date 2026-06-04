---
name: prompt-engineering
display_name: Prompt Engineering
description: Guide for writing effective natural-language prompts for modern text-to-image models
author: system
tags: [prompt, writing, guide, fundamentals, prose]
---

# Prompt Engineering

## Core Principle: Write Prose, Not Keywords

Write prompts as flowing descriptive sentences — like describing a scene to a photographer.

**Bad**: `woman, curly hair, blue dress, kitchen, morning light, 35mm`
**Good**: `A woman with curly dark hair stands in a sunlit kitchen, wearing a flowing blue summer dress. Morning light streams through the window, casting soft shadows across her face. Shot on 35mm film with natural grain.`

## Prompt Structure

Front-load the most important elements. Order: **Subject** → **Action/Pose** → **Style/Medium** → **Setting** → **Lighting & Atmosphere** → **Technical details**. Flex order based on what matters most (landscape: lead with setting; portrait: lead with subject).

## Key Rules

- **Default to photography** — unless user requests illustration/painting/cartoon/etc., assume realistic photo. Include photographic language ("photograph of", "natural lighting", "shallow depth of field"). Many models default to surreal style without photo specifics.
- **Describe people thoroughly** — facial features, hair, skin, body type, expression, ethnicity, clothing, unique characteristics. Never just "a woman." Weave details into coherent sentences.
- **Be decisive** — never give the model a choice ("standing or sitting" produces blended results). Commit to one option.
- **Repetition reinforces** — describe important details in multiple phrasings to help the model lock on.
- **Avoid equipment nouns** — "camera", "studio lights" may render literally. Use "looking at the viewer" not "looking at the camera"; "shot from a low angle" not "camera angle from below."
- **Describe what you want, not what you don't** — many models lack negative prompts. Use positive opposites ("tack-sharp focus" not "no blur").
- **Preserve unusual details** — distinctive/unexpected details (a scar, paint-stained fingers, mismatched socks) elevate prompts from generic to specific.

## What to Describe

- **Subject**: physical features, age, ethnicity, expression, clothing (material/color/fit), pose, props
- **Setting**: location, indoor/outdoor, foreground/background, time of day, season, weather, textures
- **Lighting**: direction (side-lit, backlit, Rembrandt), quality (soft, harsh, volumetric), color (golden, cool blue, neon), source (sunlight, firelight), time (golden hour, blue hour)
- **Mood**: emotional tone (serene, tense, nostalgic) + atmospheric effects (fog, dust motes, rain, haze)
- **Style**: be specific — "editorial fashion photograph", "oil painting with visible brushstrokes", "1970s Kodachrome", not just "painting" or "photo"
- **Composition**: shot type (close-up, medium, wide), depth of field (models default to shallow — specify if you want deep focus), perspective (bird's-eye, Dutch angle), lens (85mm, wide-angle 24mm)

## Prompt Length

Simple subjects: 20–50 words. Complex scenes: 80–150 words. Over ~200 words: diminishing returns. Focus on 3–5 main components.

## Making Changes to Existing Prompts

Every detail exists in a web of relationships (clothing↔setting, lighting↔time of day, framing↔visible elements). When changing one thing, trace every connected thread and update holistically. Remove orphaned details. Test: could someone reading the revised prompt, with no knowledge of the original, find anything contradictory?

## Image-to-Image Prompts

**Imperative language**: Write commands describing the transformation, not captions of the final result. Start with action verbs: "Change", "Replace", "Add", "Remove". Only describe what changes.

**Explicitly preserve**: State what to hold constant (pose, facial features, expression, camera framing) — models drift without preservation instructions.

**Verb intensity**: Use the mildest verb that fits. "Change/Replace/Swap" for targeted edits, "Add/Place" for additions, "Remove/Delete" for removal, "Render in the style of" for style shifts. "Transform/Reimagine" gives maximum creative license — use sparingly.

**Name subjects**: No pronouns. "Change the woman with short black hair's outfit" not "Change her outfit."

**Edit iteratively**: Complex changes produce better results as sequential single-purpose edits than one compound prompt.

## Multi-Image Composition

Pass all source images as `input_images`. Write a compositional caption (not imperative commands) describing arrangement in the final scene. Input images provide appearance; the prompt provides arrangement and setting.

## Inpainting

Exception to the imperative rule: when a mask defines the edit region, prompt should caption the replacement content, not command placement. "A vintage wooden rocking chair with a red velvet cushion" — not "Place a rocking chair here."
