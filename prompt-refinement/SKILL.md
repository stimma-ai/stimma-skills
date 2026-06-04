---
name: prompt-refinement
display_name: Prompt Refinement
description: Iterative generate-review-refine loop for prompt optimization
author: system
tags: [prompt, refinement, iteration, quality]
---

# Prompt Refinement

Iteratively improve generation quality through a generate → review → refine cycle.

## Workflow

1. **Initial generation**: Start with the user's prompt as-is. Generate one image with `call_tool`.
2. **Review**: Use `view_image(detail="high")` to examine the result carefully. Identify specific issues: wrong composition, missing details, style mismatch, artifacts.
3. **Refine prompt**: Adjust the prompt to address identified issues:
   - Add emphasis to missing elements
   - Add negative terms if unwanted elements appeared
   - Adjust style keywords if the mood is off
   - Change aspect ratio or resolution if composition doesn't work
4. **Regenerate**: Use the same seed to isolate prompt changes, or a new seed if seeking variety.
5. **Compare**: Use `show` to display both versions side by side for the user.
6. **Repeat**: Continue refining until the result meets expectations. Typically 2-4 iterations.

## Tips

- Change one thing at a time between iterations so you can attribute improvements.
- If the model ignores a prompt element, try moving it earlier in the prompt or adding emphasis.
- Keep a mental note of what worked — you can save effective prompt patterns as a new skill.
- After finding a good prompt, generate 3-4 seed variations to pick the best composition.
