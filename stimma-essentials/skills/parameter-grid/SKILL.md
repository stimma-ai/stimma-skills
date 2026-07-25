---
name: parameter-grid
display_name: Parameter Grid
description: Generate structured comparison grids by sweeping parameters systematically
author: system
tags: [grid, sweep, comparison, lora, parameters]
environments:
  chat: true
  flow: true
---

# Parameter Grid

Generate structured comparison grids by sweeping one or more parameters across a matrix of generations. The output is always a `.stimmagrid.json` with labeled rows and columns.

## Workflow — THREE DISTINCT STEPS

This workflow has three steps that MUST happen in separate turns. Never combine steps 1+2 or 2+3 in the same turn.

### Step 1. Gather information

Gather what you need by browsing the catalog and asking the user. This is the ONLY step where `ask_user` is allowed:
- `glob`/`read_file` `.stimma/tools/<category>/` to pick a tool and read its stub (exact function name + parameters).
- For LoRA/large-option sweeps, find the real option values and copy them verbatim, never transcribe by hand. The stub's docstring says where they are: either listed inline (`loras[].path: one of ...`) or spilled to a file to `grep` (`see .stimma/enums/<tool>_loras_path.txt`).
- `ask_user` for sweep axes/values.

**If an option you expect is missing**, `.stimma/` is a snapshot taken when the turn started — reading it again will not update it. Call `await stimma.refresh_catalog()` in `run_code` to re-read every provider and rewrite the tree (it returns `changed`, the enum files that actually differed), then re-read the file. This is the only thing that refreshes it; re-grepping or waiting does nothing.

### Step 2. Present the plan — MANDATORY GATE

**After gathering information, you MUST present a plan and wait for the user to approve it before generating.**

Rules for this step:
- **Do NOT generate or call any tools** — no `run_code`, no `ask_user`. Output only a text message.
- **Answering your questions in step 1 is NOT plan approval.** You must still present the plan and get explicit approval.
- After outputting the plan, **end your turn and wait**. Do not continue.

Your plan message must contain ALL of the following:

1. **Grid dimensions**: e.g. "8 rows × 8 columns = 64 images"
2. **Row values**: List every row label and what it represents
3. **Column values**: List every column label and what it represents
4. **Prompt template**: Show the actual prompt template with placeholders, e.g. `"A close-up portrait of {subject}, {expression}, natural lighting, 85mm lens"`
5. **Constants**: Tool, seed strategy, shared prompt elements
6. **End with**: "Does this look right, or would you like to adjust anything?"

**Example plan message:**

> Here's the plan:
>
> **8 × 8 grid** (64 images) using `comfyui:flux-klein-9b`
>
> **Rows** (subjects): elderly Japanese woman, young Middle-Eastern man, ...
> **Columns** (expressions): warm smile, belly laugh, joyful surprise, ...
>
> **Prompt template**: `"A close-up portrait of {subject}, {expression}, natural lighting, shallow depth of field, 85mm lens"`
>
> **Seed**: One fixed seed per row, constant across columns
>
> Does this look right, or would you like to adjust anything?

If the user asks for changes, revise and re-present the plan (still no tools). Only move to step 3 when the user says something affirmative like "looks good", "go", "yes", etc.

### 3. Generate and assemble

After user approval, write a single `run_code` block that generates all images and assembles the grid. Follow the reference example below — it covers the complete pattern including path construction, generation order, and assembly.

## Reference example

This example compares LoRA training checkpoints across prompts. Adapt it to your sweep type (LoRA strength, guidance, models, etc.) by changing what varies per column.

```python
# The tool you chose in step 1 — import it by its real name from the catalog.
from stimma.tools.text_to_image import flux_klein_9b  # example; use the tool you picked

# --- 1. Paths: derive from a real path, never transcribe manually ---
# In step 1 you grepped the tool's lora enum file (.stimma/enums/<tool>_loras_path.txt)
# and copied ONE real path verbatim. Use it as a template, then string-replace.
template = "flux2-klein-9b/lora_name/lora_name_000002000.safetensors"  # copied verbatim from the enum file
step_token = "000002000"  # the step substring in the template
steps = [2000, 4000, 6000, 8000]
loras = [{"path": template.replace(step_token, str(s).zfill(len(step_token))), "weight": 1.0} for s in steps]
# Add the base version (no step suffix) — also a real path from the enum file
loras.append({"path": "flux2-klein-9b/lora_name/lora_name.safetensors", "weight": 1.0})

col_headers = [f"{s} steps" for s in steps] + ["v1 base"]

# --- 2. Prompts and seeds ---
prompts = ["prompt A text here", "prompt B text here"]
row_headers = ["Prompt A description", "Prompt B description"]  # use full values, don't truncate
seeds = [42, 100]  # one per row, constant across columns

# --- 3. Build coroutines in column-major order (minimizes LoRA switching) ---
indexed_coros = []
for col_idx, lora in enumerate(loras):
    for row_idx, (prompt, seed) in enumerate(zip(prompts, seeds)):
        coro = flux_klein_9b(prompt=prompt, seed=seed, loras=[lora])
        indexed_coros.append((row_idx, col_idx, coro))

# --- 4. Single gather — one progress bar ---
all_results = await asyncio.gather(*[c for _, _, c in indexed_coros])

# --- 5. Reorder to row-major and assemble ---
grid_cells = [[None] * len(loras) for _ in prompts]
for (row_idx, col_idx, _), result in zip(indexed_coros, all_results):
    grid_cells[row_idx][col_idx] = result

grid = await stimma.create_parameter_sweep(
    media_ids=[r for row in grid_cells for r in row],
    rows=len(prompts), cols=len(loras),
    row_headers=row_headers, col_headers=col_headers,
    title="LoRA Step Comparison"
)
stimma.show(grid)
```

### Key points in this pattern

- **Path construction**: Copy real paths verbatim from what you read in step 1. If you derive a family of paths from a template (`str.replace()` + `str.zfill()`), the derived strings are guesses until checked — a checkpoint sweep whose paths are off by one zero is the exact shape of a sweep that looks finished and compares the wrong things. Assert them against the source list before generating: `assert set(paths) <= set(available)`, where `available` is what you actually read. Never manually type zero-padded filenames.
- **Column-major generation order**: The outer loop is columns (the swept parameter), inner loop is rows (prompts). This groups all work for one LoRA/model together, minimizing expensive VRAM reloads.
- **Single gather**: All coroutines go into one `asyncio.gather()` call → one progress bar.
- **ToolResult handling**: an awaited tool call returns a ToolResult object. Pass them directly to `create_parameter_sweep` (it accepts them). Use `.media_id` (dot notation) if you need the ID — never `['media_id']`.
- **Always assemble**: The output is a grid, not loose images. Call `create_parameter_sweep` then `stimma.show(grid)`.
- **Seed strategy**: One seed per row, constant across columns. This isolates the column variable as the only thing changing.
- **Flat kwargs**: pass each parameter directly to the imported tool — `TOOLNAME(prompt=..., seed=..., loras=[...])` — no nested `inputs={}` or `parameters={}`.

## Growing or fixing an existing grid

When a sweep gains an axis value, or one row needs regenerating (a prompt detail
caused artifacts, say), do NOT re-list the surviving cells by hand and do NOT
regenerate them. Use `extend_parameter_sweep`, which reads the existing cells off
the old grid and returns a new one:

```python
# Only the new cells get generated — the other 56 are carried over.
new_cols = {}
for step in (1400, 1600, 1800):
    path = f"flux2-klein-9b/dropstock_v1/dropstock_v1_{step:09d}.safetensors"
    assert path in available, f"{path} not in the catalog"   # never guess a path
    new_cols[f"Dropstock {step}"] = await asyncio.gather(*[
        TOOLNAME(prompt=p, seed=s, loras=[{"path": path, "weight": 1.0}])
        for p, s in zip(prompts, seeds)
    ])

grid = await stimma.extend_parameter_sweep(
    grid,                                            # dict or media_id
    add_cols=new_cols,                               # each: one cell per existing row
    replace_rows={"Skatepark ledge": redone_row},    # one cell per existing column
)
stimma.show(grid, role="final")
```

`add_cols` / `add_rows` / `replace_cols` / `replace_rows` all map a header to that
line's cells, ordered along the opposite axis. Replacements match on header text
and must already exist; additions must not. Hand-transcribing a list of old media
ids is the failure this exists to prevent — one transposed id silently mislabels
a cell, and nothing downstream will catch it.

## Adapting to other sweep types

| Sweep type | What varies per column | Path construction |
|---|---|---|
| LoRA checkpoints | `loras.path` (different files) | Template + str.replace |
| LoRA strength | `loras.weight` (same file) | Same path, different weight values |
| Guidance/CFG | `guidance` or `cfg` kwarg | N/A — just pass the number |
| Models | import a different tool per column | N/A — import each tool from `.stimma/tools/` |
| Prompt phrasing | `prompt` text | N/A — swap the target phrase only |

For LoRA checkpoint sweeps specifically: training step numbers in filenames (2000, 4000, etc.) refer to different `.safetensors` files, not the `weight` parameter. The `weight` parameter (0–2) controls LoRA strength and is a separate dimension.
