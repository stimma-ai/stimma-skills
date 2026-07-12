---
name: subject-isolation
display_name: Subject Isolation
description: Extracting a subject from an image — a person, character, or object isolated on a plain background or cut out for reuse. Covers choosing between background removal and edit-model disentanglement.
author: system
tags: [editing, extraction, background, compositing]
environments:
  chat: true
  flow: true
---

# Subject Isolation

Use this skill when the user wants a subject pulled out of an image: "extract the character on the left", "isolate the dog against a white background", "cut out the product".

## Assess the image before picking an approach

View the source and answer three questions (view_image reports the native pixel size — think in that frame):

1. **What exactly is the subject?** Resolve a positional request ("the middle one in the front row") into a concrete visual identity — "the brown-haired girl with the red backpack". You need this to target the right subject and to verify the result.
2. **How separated is it from the *other subjects*?** Not from the background — background separation is irrelevant (removing background is the easy part). The question that picks the tool: would the crop rectangle you'd draw around the target contain any piece of another subject — an overlapping arm, a shoulder behind, a foot at the edge? If yes, the target is intermingled, no matter how much clear sky and grass surround the group.
3. **How many pixels is it?** A large subject in a high-res image gives every tool plenty to work with. A subject that's a small patch of a small image is fragile — expect to upscale afterward, and expect identity to drift more under any regenerating tool.

## Clean separation → background removal

A well-separated subject is an rmbg job — mechanical, identity-preserving, no regeneration:

- Subject is essentially the whole image → run `remove-background` directly.
- Other subjects present but the target is clear of them → rectangular crop around the target with margin (~10%) first, then `remove-background` on the crop. (Background removal answers "what is foreground?", never "which subject?" — the crop is what does the choosing. It keeps *every* foreground pixel in the crop, so if a neighbor's arm or foot lands inside your rectangle, that fragment survives to the final image — that's the intermingled case, route to the edit model instead.)
- Composite the alpha cutout onto the requested background with PIL:

      fg = Image.open(r.path).convert("RGBA")
      canvas = Image.new("RGB", fg.size, (255, 255, 255))
      canvas.paste(fg, mask=fg.split()[3])

## Occluded or intermingled → edit model

When the subject overlaps or touches others, no mask can decide where a shared edge belongs — disentanglement is what instruction-following edit models are for. Crop roughly to the subject's region (generous margin; include the overlapping neighbors — the model needs to see what it's removing), then image-to-image with an **imperative command**:

    Isolate the girl with the red backpack. Remove all other people and the background;
    replace with a plain white background. Keep her pose, expression, clothing, and
    art style unchanged.

Command the change — don't re-describe the source image. A description ("a cheerful cartoon girl with brown hair...") reads as a request to generate that caption from scratch, and the model happily invents a new character. Keep the tool's tuned defaults; raising steps or switching samplers licenses redrawing, and identity drifts.

## Locating and verifying

- **Locate with your own eyes.** A crop box is a coarse rectangle — estimate it as fractions of the displayed image × the native size. That's the whole locating step; margin absorbs the imprecision, and the isolation step does the fine work. (Pixel-accurate segmentation tools like `detect-objects`/SAM3 belong to mask-based edits such as inpainting — for extraction they're the exception, not the rule.)
- View the crop once before the expensive step; fix the box in one deliberate adjustment, not a loop of blind tweaks. While looking at it, re-check the separation call: any piece of another subject visible in the crop means the rmbg route will keep it — switch to the edit model.
- **View the final image before showing it to the user.** It must contain exactly one subject, matching the identity from your assessment, with no stray fragments (a neighbor's arm, hair, a foot) at the edges. Fragments mean the separation call was wrong — redo the isolation through the edit-model route. If the subject itself drifted, the fix is almost always targeting (the crop), not generation parameters.
