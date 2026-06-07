---
name: character-dataset
display_name: Character Dataset
description: Create consistent multi-view character datasets
author: system
tags: [character, character consistency, character sheet]
---

# Character Dataset

Generate a multi-view character dataset showing front, side, and back views with consistent design, grouped as a set in the library.

## Workflow

1. **Gather info in one pass**: If you need to clarify the character, ask everything in a single grouped `ask_user` call (e.g. tabs for `Character`, `Style`, `Views`). Don't ask serial questions.
2. **Generate views using Python batch**: Use `run_code` to generate all views in a single Python script. This is more efficient than sequential agent loops.
3. **In the Python code**:
   - Import a text-to-image tool from `.stimma/tools/text-to-image/` (read its stub for the exact name) and `await` it for each view, with the same seed and character description
   - **One fixed seed for ALL images** — the same constant seed is what keeps the character's face and body consistent across views
   - Only change the view angle phrase (e.g. "front view", "side view", "back view")
   - Store results in a list
   - **Group into a set** with `await stimma.create_set(results, title="...")` — this bundles the views as a single library item. `create_set` takes only `results` and `title` — no other kwargs.
   - **Call `stimma.show()` at the end** — this displays the images to the user
4. **After Python execution**: The Python script handles display via `stimma.show()` — no additional `show` call needed.

## Example Python Code Pattern

```python
import asyncio
# The text-to-image tool you chose — import by its real name from .stimma/tools/text-to-image/
from stimma.tools.text_to_image import flux_klein_9b  # example; use the tool you picked

SEED = 42  # One constant seed for the entire dataset — this is what keeps the character consistent
base_prompt = "A stunning 24-year-old brunette woman with long flowing dark brown hair and warm hazel eyes, wearing a simple white tank top and jeans, white background, professional photography, natural lighting, high detail, photorealistic, 8k quality"

standing_views = [
    "front view, standing, arms at sides, full body",
    "side view, standing, profile, full body",
    "back view, standing, full body",
    "front 3/4 view, standing, full body",
]
sitting_views = [
    "front view, sitting on chair, full body",
    "side view, sitting, profile, full body",
]
face_views = [
    "extreme closeup face, front view, neutral expression",
    "extreme closeup face, side profile",
    "extreme closeup face, front 3/4 view",
]

all_views = standing_views + sitting_views + face_views

results = await asyncio.gather(*[flux_klein_9b(
    prompt=f"1girl, {view}, {base_prompt}",
    seed=SEED,
    width=768,
    height=1024,
) for view in all_views])

await stimma.create_set(results, title="Character Dataset")
stimma.show(results, title="Character Dataset")
```

If you need to read a generated file back (e.g. for PIL ops):

```python
info = await stimma.library.get(result.media_id)  # await required!
img = Image.open(info["filename"])  # "filename" not "path"
```

## Tips

- Always include "white background" or "simple background" for clean sheets.
- **Seed must be identical for every image** — pass the exact same constant to every generation call. The prompt variation handles pose diversity; the fixed seed keeps the character's identity locked.
- Prompt for one character in one pose per image — multi-pose prompts like "character reference sheet" cause the model to draw multiple figures in a single frame.
- If consistency is poor across views, try img2img with the front view as reference for subsequent views.
- When the user provides a reference image, use its media_id (shown in the `[Attached files …]` metadata) for `input_images`.
- Use `run_code` for batch generation — it's faster and more reliable than sequential agent calls.
- Always call `stimma.create_set()` to group the character views — the user expects these as a single library item.
