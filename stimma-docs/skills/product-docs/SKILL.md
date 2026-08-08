---
name: product-docs
display_name: Product Docs
description: Answering questions about Stimma itself — features, setup, ComfyUI or local AI onboarding, FFmpeg, chat models, configuration, or how any part of the product works
author: system
tags: [docs, support, onboarding]
environments:
  chat: true
---

# Product Docs

Use this skill when the user asks how Stimma works, how to set something up, or why a part of the app isn't behaving — anything where the answer should come from Stimma's documentation rather than general knowledge.

## Reading the docs

1. Fetch the page index: `browse_web(action="fetch", url="https://docs.stimma.ai/llms-pages.txt")`. It lists every documentation page with a one-line description.
2. Pick the one to three most relevant pages and fetch their `.md` URLs from the index.
3. Answer from what the pages actually say. Link the human-readable page (the same URL without the `.md` suffix) so the user can follow along.

Fetch the index fresh rather than answering from memory — the docs change with releases, and the index is the source of truth for what's covered.

If the docs don't cover the question, say so and answer from what you can observe in the app instead.

## Setup and onboarding walkthroughs

For setup tasks (ComfyUI, FFmpeg, STP providers, chat models), fetch the relevant setup page and then work through its steps *conversationally* — one step at a time, confirming the result before moving on, adapting to the user's OS and answers. Don't paste the whole page at the user.

The user's ComfyUI (or other local AI) installation is their environment, not your workspace. Guide them to run steps there and report back rather than inspecting or modifying their installation directories yourself.
