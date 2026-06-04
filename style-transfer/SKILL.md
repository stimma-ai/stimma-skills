---
name: style-transfer
display_name: Style Transfer
description: Extract style from a reference image and apply it to new subjects
author: system
tags: [style, transfer, img2img, reference]
---

# Style Transfer

Apply the visual style of a reference image to a new subject or scene.

## Critical: Separate Style from Subject

When analyzing a reference image, you must carefully distinguish between **style** (how it's rendered) and **subject** (what it depicts). Only transfer the style.

**Style elements** (transfer these):
- Rendering technique / medium (pixel art, oil painting, watercolor, 3D render, etc.)
- Color palette and color treatment (saturated, muted, monochrome, warm/cool)
- Texture and surface quality (smooth, grainy, brushy, blocky)
- Lighting approach (flat, dramatic, rim-lit, ambient)
- Line quality (thick outlines, no outlines, sketchy, clean vectors)
- Level of detail / abstraction

**Subject elements** (do NOT transfer these):
- What the image depicts (a map, a landscape, a car, a building)
- Specific objects, characters, or scenes in the reference
- Setting or environment details (terrain, water, sky)
- Narrative or thematic content

The user's requested subject should fully replace the reference's subject. Nothing about what the reference depicts should appear in the output.

## Use text-to-image, not img2img

Img2img treats `input_images` as a **content/composition** reference — it reproduces what the image depicts, not just how it looks. Passing a style reference as an input image bleeds the reference's subject into the output.

**Default approach: text-to-image with style-descriptive prompt.** Analyze the reference visually, extract style attributes, and encode them entirely in the prompt. The reference stays out of `input_images`.

**Exception:** Only pass the reference as `input_images` if the tool explicitly supports style-only reference modes (e.g., IP-Adapter with a style transfer mode, or a dedicated style-reference parameter). Check the tool schema — most tools don't have this.

## Workflow

1. **Analyze reference**: Use `view_image` on the reference to identify style elements only (see list above). Mentally set aside everything about what the image depicts.
2. **Build prompt**: Start with the user's requested subject. Then append only style descriptors extracted from the reference. Structure: `[user's subject], [medium/technique], [color palette], [texture/detail level], [lighting]`. Be highly specific about each attribute — name the exact medium, describe the color palette in detail, characterize line weight and texture precisely. Vague labels like "in the style of the reference" are not enough.
3. **Choose tool**: Use `discover(action="list_tools", task_type="text-to-image")` to find generation tools. Use text-to-image, not img2img.
4. **Generate**: Use `call_tool` with your style-descriptive prompt. Do **not** include the style reference in `input_images`.
5. **Iterate**: Use `view_image` to check the result. If the style doesn't match well enough, refine the style descriptors in the prompt and regenerate.

## Tips

- If the tool supports loras, search for style-specific loras with `discover(action="search_options", ...)` — a style lora is often more effective than prompt-only style matching.
- Generate 2-3 variations with slightly different style descriptions to find the best match.
- When reviewing your prompt before generating, double-check: does every phrase describe either the user's subject or a visual style attribute? Remove anything that describes what the reference image depicts.
