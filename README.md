# stimma-skills

Source for Stimma's **built-in agent stimpacks** — the first-party stimpacks published to
the Stimma Cloud marketplace and auto-installed for users.

Each top-level directory is one stimpack — a *package* of one or more skills:

```
<stimpack-name>/
  stimpack.json     # pack identity: name, display_name, description, version, tags
  skills/
    <skill-slug>/
      SKILL.md      # frontmatter (name, description, tags, environments) + markdown body
      lib/          # optional bundled Python
```

Each skill declares which environments it's eligible for in its frontmatter
(`environments:` with `chat` / `flow` / `tool` keys; `tool` is `true` or
`{ task_types: [...] }`; an absent block means chat-only). A legacy layout with a
single root `SKILL.md` (no `skills/` dir) still loads as a one-skill pack.

`shelved/` holds retired stimpacks awaiting a retest/repack — nothing in there is
published or loaded.

## Why this is its own repo

These stimpacks are *content*, not app code. The Stimma desktop app loads them only after
they've been published to the cloud and installed into a profile — nothing in the
`stimma` or `stimma-cloud` codebases references this directory directly. Keeping them
in a dedicated repo lets us iterate on stimpacks without touching either app.

## Workflow

This repo is consumed by two CLIs (both being wired up):

- **Dev (live iteration):** point the Stimma desktop app at this checkout so edits are
  picked up live — no zip, no publish, no reinstall.
  `stimma stimpacks dev <path-to-this-repo>`
- **Publish (when ready):** ship changed stimpacks to the cloud marketplace.
  `stimmacloud stimpacks status`   — show which stimpacks have drifted from what's published
  `stimmacloud stimpacks publish [all|<name>]` — publish changed, already-listed stimpacks

Publishing only ever bumps a **new version** of an **already-published** stimpack. The
initial publish (entering listing metadata) stays manual.

Default checkout location: `~/stimma/stimma-skills` (sibling to `stimma` and `stimma-cloud`).
