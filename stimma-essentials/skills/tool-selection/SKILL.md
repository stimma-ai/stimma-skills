---
name: tool-selection
display_name: Tool Selection
description: Guidelines for picking image and video tools when the user hasn't specified one
author: system
tags: [tools, routing, guidelines]
environments:
  chat: true
  flow: true
---

# Tool Selection

Use this skill when the user asks for image or video generation and **hasn't named a specific tool or model**. If they named one, use it — don't second-guess.

**These are guidelines, not defaults.** Your job is to read what the user is actually doing, briefly ask when you must, describe the tradeoff, and remember what they tell you.

## Decision order

1. **User named a model?** → Use it. Stop.
2. **Memory has a relevant preference?** (board, task-type, or user level) → Use it. 
3. **Read the context.** Board/project name, word choice ("hero image" vs "just something quick"), what they've been running recently, what providers they have. Don't label the user or ask them to pick a persona.
4. **Match guideline to context below.** Announce the pick + the tradeoff in one short line.
5. **If genuinely ambiguous, ask one short question.** Never dump the menu.

## On cost

**Never quote prices or dollar amounts.** Ever. Not even approximate, not even "about $0.XX". Describe cost only as a relative tradeoff: *low-cost tier*, *mid-tier*, *premium*, *most-expensive option*, *cheaper sibling*, *significantly more expensive*. The user can see live pricing in the UI (shown as "from $X.XX" since final cost depends on asset size).

When cost is part of the tradeoff, frame it comparatively:
- "Klein 9B is in the low-cost tier — Flux Max is significantly more expensive for final-quality work."
- "Veo 3.1 sits at the most-expensive tier for video. Seedance is a commercial mid-tier alternative."

## Image (T2I / I2I)

**Flux.2 Klein 9B is an all-in-one surface** — T2I, reference-guided I2I, and instruction-style edits all on the same model, fast inference, low-cost tier. No quality tradeoff for using it on edits. A strong starting point when the user is exploring, iterating, or not yet committed to a look.

### Guidelines

**Exploring / iterating / fast feedback:**
- **Klein 9B** — fast, low-cost, all-in-one (T2I + I2I + edits).
- **Z-Image Turbo** — cheapest tier, quick, especially for photorealistic images of people, T2I only. Good for batch.
- **Nano Banana 2 Lite** — cheapest of the Nano Banana line, 1K only. Good for batch and for drafts you'll finish on Nano Banana 2 or Pro.

**Going for final / hero / production output:**
- **Flux.2 Max** — top quality from Flux family, premium tier.
- **Nano Banana Pro** — premium tier, strong composition and prompt adherence, 4K optional.
- **Seedream 4.5** — premium tier, 4K sharpness out of the box.
- **GPT Image 2** (high) — slow and premium, but uniquely good at readable text and exact instruction following. Don't use it when text isn't the point — it's overkill. And it's VERY slow and fairly expensive.

**Instruction-style edits on a specific image:**
- **Klein 9B** handles this (no quality penalty), including controlnets and up to 9 reference images.
- **Nano Banana 2 Edit** or **Nano Banana Pro Edit** — natural-language edit specialists; use when the user describes a surgical change ("remove the car", "change shirt color"). Up to 10 reference images (6 on Pro).
- **Qwen Edit 2511** — low-cost, open-weights, good for reference-guided edits with up to 3 inputs and ControlNet.

### ComfyUI users

ComfyUI users vary enormously. Some use stock Comfyui-Stimma workflows; others have deep SDXL ecosystems with custom LoRAs or many-stage workflows; **Don't assume a default.** and be sensitive to the fact that these people know what they like. Instead:

- Check what tools they've made available via ComfyUI
- If they clearly work in one ecosystem (e.g. SDXL + LoRAs), suggest from there first.
- If they have stock Stimma workflows and no clear pattern, briefly mention fitting options based on the above
- Ask one short question when you can't tell: "Stick with your [ecosystem they use] setup, or try [alternative]?"

**Route ComfyUI users to Stimma Cloud only** when the request explicitly needs something only cloud offers (Nano Banana family, GPT Image 2, Flux.2 Max, Seedream 4.5) or the user says "use stimma cloud". For these people, cloud is an escape hatch and an exception, not the point.

## Video (T2V / I2V)

Video splits along **audio, duration, quality, open-weights, cost**. There's no single right answer — ask what matters.

**Audio-capable cloud:**
- **Seedance 1.5 Pro** — ByteDance, strong camera control, up to 12s/1080p, mid tier. Common commercial choice.
- **Veo 3.1** — most-expensive tier. 4K, best dialogue/lip-sync. For final / presentation work.
- **Veo 3.1 Fast** — same family, cheaper sibling of full Veo (still on the higher end).
- **Grok Imagine Video** — mid tier, audio, middle-ground option.
- **LTX 2.3** — open weights, up to 4K/20s/audio, mid tier. Strongest open-weights with audio.
- **Wan 2.6** — 1080p/15s/audio, mid tier. **Wan 2.6 Flash** is the cheaper sibling.

**Open-weights / ComfyUI:**
- **Wan 2.2** — open-source quality benchmark. Stock workflows: `Stimma-Wan22-T2V`, `-I2V`, `-FLF2V`, plus `-Lightning` fast variants.
- **LTX 2.3** — also stock (`Stimma-LTX2-T2V`, `-I2V`, and Distilled). Supports audio. Lower visual quality than Wan 2.2.

Generally the open source models need a fair amount of massaging and help to make anything production-ready. Set expectations accordingly. People who know how to use them make great stuff, but it doesn't happen out of the box.

### Guidelines

- **Audio matters a lot (dialogue, sync, music-driven):** Veo 3.1 if budget allows, otherwise Seedance / LTX 2.3 / Wan 2.6.
- **"Best" / "final" / "presentation":** Veo 3.1. *Flag that it's the most-expensive tier before submitting.*
- **Commercial mid-tier:** Seedance 1.5 Pro.
- **Low-cost + fast + acceptable quality:** Veo 3.1 Fast or Wan 2.6 Flash.
- **ComfyUI user with stock Stimma workflows:** Wan 2.2 or LTX 2.3 local. Lightning/Distilled variants for speed.
- **Genuinely unclear:** one question — "Cinematic premium (Veo), commercial mid-tier (Seedance), or open-source (Wan 2.2 or LTX)?"

## Specialty

- Remove background → **RMBG-2.0** (only option)
- Upscale image → **SeedVR2 Image Upscale** (prefer 7B when available)
- Upscale video → **SeedVR2 Video Upscale**

## How to talk to the user

**Announce pick + tradeoff in one short line.** Don't dump the matrix. Describe cost in relative terms only — never a number.

- Good: "Going with Klein 9B — fast, low-cost tier, handles edits too. Say the word if you want Flux Max for final quality."
- Good: "Using GPT Image 2 High — slow and premium, but nails embedded text."
- Good: "Seedance 1.5 Pro for this. Veo 3.1 if you want top-shelf, but it's our most-expensive tier."
- Bad: "I considered six tools and here's my analysis…"
- Bad: "Klein 9B costs about $0.017." ← never quote numbers.

**Be explicit when you're at neither max-speed nor max-quality** — the user should know what corner of the tradeoff space they're in.

**Flag premium picks (especially most-expensive-tier video) before running.** No hard gate — just don't let the user accidentally commit to a premium-tier run they didn't realize they were ordering. Describe the tier, don't quote a number.

## Asking (when you must)

One focused question. Good framings:
- "Fast draft or final quality?"
- "Need audio on the video or visuals only?"
- "Low-cost prototype or hero output?"
- "Stick with your ComfyUI setup or try cloud?"
- "Photoreal batch or stylized single hero?"

Never list the whole catalog. Two or three named options max.

## Remembering

Save to memory **only on explicit durable language**:
- "Always use X"
- "From now on, X"
- "On this board, default to X"
- "For video, I always want Y"

Everything else is a one-off — don't save. If the user contradicts a saved preference later, treat that as a one-off too unless they say something durable.

## Respecting signals

- Named a model → use it, no lecture.
- "cheap" / "low-cost" → Klein 9B / Z-Image / Wan Flash / Lightning workflows
- "best" / "hero" / "final" → Flux Max / Veo 3.1 / Nano Banana Pro / Seedream 4.5
- "fast" → Klein 9B / Z-Image Turbo / Veo Fast / Lightning workflows
- "open source" / "local" → ComfyUI (their existing ecosystem first)
- "for a client" / "production" → premium tier, flag that before running
- "like last time" / "same as before" → check memory + recent history
