---
name: video-production
display_name: Video Production
description: "Producing finished video from generated clips: loops, continuations and long takes, transitions between clips, talking heads and dialogue, multi-shot sequences, and any join between two clips. Plans the shots, picks how to generate each one, and runs every join through seamkit."
author: system
tags: [video, loop, continuation, extend, long take, stitch, transition, seams, talking head, editing]
environments:
  chat: true
  flow: false
provides: [seamkit]
---

# Video Production

Making several clips play as one is where video work goes wrong, and it goes wrong
the same ways every time. This skill plans the shots, picks how to generate each,
and joins them so the joins can't be seen.

Use **Tool Selection** to pick a model family. Each video tool's own instructions
record what it can do and how it misbehaves (pin types, native length and frame
rate, crops, audio limits). Read them before planning around a tool.

## What goes wrong at a join

A pin fixes what's in the frame (geometry), not its exposure and color (photometry).
Every join between two clips can carry any of these:

- **Exposure and color offset.** Each run lands at its own exposure, a few levels
  apart. It pulses at the seam even when everything else matches.
- **A repeated frame.** A pinned clip starts or ends on a copy of the pinned frame,
  which plays twice and reads as a hitch.
- **A head that pops.** An image-to-video clip's first frame is often the reference
  image itself, crisper than what follows, and pops for one frame.
- **A motion jump.** A still pin fixes position, not speed or direction.
- **An audio jump.** Loudness and room tone change between runs; a hard splice clicks.
- **A slow start.** Image-to-video often opens with a lull of a second or so while
  motion builds (MiniMax H3 often), and a clip pinned to a last frame can coast
  into one. Loop or join across a lull and the rhythm breaks.

`seamkit` fixes exposure, repeated frames, popping heads and audio, and measures
motion; motion is fixed by what you use of each clip, how you pin, and where you join.

## Working rules

**Design the key frames as stills first.** Settle composition, character, look and
the frames that pin each segment as images, and get them approved: they're cheap
to iterate and predict the video. Then render the video once, at final settings.

**Make the stills at the video's shape.** Choose the video tool and output size
first and make every pinned frame at that aspect; a frame of another shape gets
stretched or cropped without warning. Crop or outpaint other images yourself, so
you choose what's kept.

**No draft video rounds.** A faster variant (⚡, Turbo, Fast, Max) doesn't predict
the full model from the same prompt and seed; motion and look differ in kind. If
speed matters, make the faster model the final one and say so. Test at lower
resolution or length only when the user asks.

**Cuts are free.** If the story allows a cut, cut; it needs no matching. Cuts written
into one prompt (H3 shot syntax, Wan 2.7 multi-shot, LTX multishot) are better
still, since the model keeps the look consistent. Join continuously only when the
shot must be continuous.

**Put joins where there's motion.** A join disappears under fast action or
something crossing the frame, and shows in slow, static moments. A still pin
can't carry speed, so with still pins join where motion momentarily stops.

**Work at the tool's native length and frame rate**, and plan segment counts from
them. Clips in a join share one frame rate; regenerate rather than resample.

**Every join goes through seamkit.** It matches, blends and records lineage; a bare
ffmpeg edit loses lineage and stored state. Check the report, look at the frames
either side of each seam, then deliver.

## Long takes

**Error compounds with every hop, stored state or not.** A continuation re-renders
the clip it's pinned to and builds on the result, so each hop inherits all the
error before it: colors saturate and darken, fine detail smears, the framing
creeps. Each hop looks fine next to the last, so it goes unnoticed until the end.
Stored state (a clip pinned from the library) removes the re-encode and roughly
halves the color drift, but the pin is still re-rendered: it slows drift without
bounding it. So continue for short extensions (two or three hops) or a tracking
shot nobody can plan; for anything longer, keep every frame at most two
generations from a clean still.

**A planned long take renders in one parallel wave of still-to-still segments**,
with a tool that pins frames at both ends:

1. **Anchor stills**, one per key moment, each made directly from the source image
   (never an edit of an edit), at the video's shape, sharing its framing, lens and
   look. Pick moments where motion briefly settles: the take passes through each
   anchor, and a still carries no speed.
2. **Segments:** one between each pair of neighboring anchors, at the tool's native
   length, the earlier anchor pinned at the start and the later one at the end, both
   passed as references, the same voice reference on every segment, and the prompt
   describing the action that takes one into the other.
3. **Join** them in order with seamkit, `trim_head: 1` on every segment after the
   first (its opening repeats the anchor the previous one ended on). Trim the last
   segment's tail so the take is exactly the requested length.

Every segment renders at once, so every GPU works. Submit them together, sized to
`await stimma.tasks.workers(tool)`, inside `stimma.batch(title, total=N)` so the
count is right from the start. On local H3 (5 s native) each segment adds 5 s.

**Don't bridge with clips pinned at both ends.** Local H3 treats a pinned clip as a
shot of its own: when the prompt asks for anything other than what the clip is
already doing, it leaves the start clip, or enters the end clip, with a hard cut.
Tested on consistent anchors, bridges between keys cut in 46 of 50, whatever the
pin lengths (22 or 39 frames), the bridge length (5 or 10 s), the end pin (clip or
still) or the keys; still-to-still segments cut in 2 of 10. The crossfade hides
the join, not the cut inside the bridge, so a seam report alone looks fine.

**A take that travels** (a walk, a drive, a tracking shot moving through a place)
can't be planned as anchors: nothing predicts where each segment ends, so the next
anchor is never where the last one stopped, and the model cuts to it. Continue it
instead, each hop pinning the previous tail and describing the same ongoing action
(those hops didn't cut, 0 of 20), in runs of two or three hops with stored state;
for anything longer, end a run on a planned cut and start the next from a fresh
still.

**Anchors must agree before any video.** A segment between differently framed
stills resolves the difference with a cut, not a move. View them side by side and
run `seamkit.anchors`; redo any that reframed or shifted (an edit model often zooms
in: try another seed). Render every still before any video: swapping image and
video models on a GPU costs minutes.

**Check every segment; fix only what failed.** Run `seamkit.cuts` on each segment
before assembly; a cut in the first few frames means it popped off its start anchor.
After joining, check each seam's motion ratio and run `seamkit.drift` on the take.
Regenerate only the segment that failed, with a new seed; if the same pair fails
twice, redo the anchor.

## How much a pin carries

From strongest to weakest:

1. **A clip pinned with its sound** (local MiniMax H3 Reference to Video keyframes).
   Carries picture, motion and audio; the output repeats the pinned clip, giving
   real overlap to crossfade. LTX keyframes pin clips too, picture only. It carries
   on only what the clip is already doing; ask for a different action or framing and
   local H3 cuts away from it.
2. **A reference video plus a voice reference** (H3 Reference to Video on Stimma
   Cloud). Carries motion and voice; opens near the reference's last frame, not on it.
3. **An extend tool** (SkyReels V4 Extend on the cloud, LTX Extend Video locally).
   The model continues the clip from its own context.
4. **First and last still frames** (most image-to-video tools). Fixes position at
   both ends, not motion, and usually no audio.
5. **The last frame as a first frame.** Fine for one or two continuations; warn that
   the join may show, since neither motion nor voice carries over.

Pick the strongest one the available tools offer.

## Recipes

### Loop an existing clip

The clip's last frame and first frame are close but not equal. Generate a bridge
from the end back to the start, then join with `loop=True`.

**Choose the loop window first, before generating the bridge.** The bridge is
pinned to the window's ends, so the window can't change afterwards.

- **By default, leave out a few frames at each end** (2–4 at 24 fps), where
  reference frames, pinned frames and slow-downs sit.
- **Then measure the motion:** `await seamkit.motion(stimma, path)`. If `settles_at`
  is past about half a second, the clip opens with a lull: start the window
  there. If `fades_at` is well before the end, it slows down into its last frame:
  end the window there.
- **Keep the length if it matters:** make the bridge longer by however much you cut.
- Take the bridge's pins (frames or clips) from the window's ends, not the clip's.
  Join with the same window: `trim_head` and `trim_tail` on the locked segment.

Then generate the bridge:

- **Local MiniMax H3 Reference to Video:** pin the window's last second (with sound)
  at 0 and its first second at the end, with the clip in `input_audios` for the
  voice. Join with `overlap` set to the pinned frame count on both segments. Clip pins carry motion, so the bridge has no lull of its own.
  Run `seamkit.cuts` on the bridge: when the window's ends differ much, H3 jumps
  into the end clip with a cut. Then pin the window's last and first frames as
  stills instead.
- **LTX Loop (local):** bridges and joins in one step. Trim the clip to its window
  first, then `seamkit.check` the result with `loop=True`.
- **Cloud, or any first/last-frame tool:** first frame = the window's last frame,
  last frame = its first frame. Pick a tool that returns its pinned frames exactly;
  LTX 2.5 returns them cropped.
- **Sound:** if the bridge comes back silent (Kling with frames), `audio="loop"`
  builds a seamless loop of the clip's own sound.

### Loop from scratch

Pin the same image as both the first and the last frame. Describe motion that goes
out and comes back. Check the wrap with `seamkit.check(stimma, path, loop=True)`.

### Continue a clip

For a short extension (see [Long takes](#long-takes) for anything longer):

- Check where the previous segment's motion fades (`seamkit.motion`). Continue from
  before a slow ending, not from inside it.
- **Local:** H3 Reference to Video, pinning the previous segment's tail clip with
  sound at 0 (length per the tool's instructions) from the library, with the same
  voice and reference images. The pinned clip already sets the opening framing, so the prompt
  describes what happens next and any change of framing as camera movement; a
  different framing written in the prompt is reached with a cut. Run
  `seamkit.cuts` with the pinned length as `ignore_before`, and regenerate a
  segment that cuts. Join with `overlap`.
- **Cloud:** SkyReels V4 Extend, or MiniMax H3 Reference to Video with the clip's last
  few seconds in `input_videos` and `input_audios`. Join without `overlap`; seamkit
  drops repeated frames and matches the exposure.

### Bridge two different clips

The bridge's first frame is clip A's last frame and its last frame is clip B's
first. Locally, LTX Stitch does this and keeps the source audio. Otherwise use a
first/last-frame tool, or local H3 with those two frames pinned as stills (H3 cuts
into a clip pinned at the end unless the two clips nearly match). Lock both clips;
the bridge is adjusted to fit both.

### Talking head and dialogue

- Generate one sentence or line per segment and **cut** between segments (a new
  angle, or B-roll) rather than making spoken segments continuous.
- Use the same voice reference (`input_audios` on H3 Reference to Video) and face
  references on every segment.
- If the voiceover is given or comes from TTS, fix its timing first, then generate
  each segment to its piece, with a driving-audio tool if there is one.
- For dialogue, models with strong lip-sync (Veo 3.1, MiniMax H3, Seedance 2.0)
  beat generating silent video and syncing it afterwards.

### Multi-shot sequence

Write the cuts into one generation when the shots fit its length. Across separate
generations, keep the same reference images and voice and join with `cut=True`;
seamkit still encodes every clip once, consistently.

## Join

`seamkit` is importable in `run_code`. Pass workspace paths: library media is already
in the workspace, and `stimma.library.get(media_id)` gives its path.

```python
import seamkit
report = await seamkit.join(stimma, [
    {"path": "source.mp4", "lock": True},
    "bridge.mp4",
], "loop.mp4", loop=True)
print(report)
```

Each segment is a path, or a dict with:

- `lock: True` for footage that must not change (the user's clip, a loop's source).
  Unlocked segments get a gain and offset fitted at each end and ramped between;
  if nothing is locked, the first segment is.
- `overlap: N` when this segment's first N frames show the same moments as the
  previous segment's last N (a pinned clip). They're crossfaded, picture and sound,
  which hides the join; use it for every delivered take.
  For local H3 the overlap is the pinned clip's frame count after H3 rounds it to
  17k+5 frames: about 1 second pins 22 frames at 24 fps. In a loop, `overlap` on the
  first segment means the bridge's tail repeats the first segment's head.
- `cut: True` when the join into this segment is a deliberate cut. Nothing is
  matched, trimmed or blended there.
- `trim_head` / `trim_tail` to drop frames yourself. Repeated pinned frames and
  popping head frames are dropped automatically.

Options: `loop=True` joins the end back to the start. `audio="auto"` (the default)
joins each segment's sound, matches loudness at the seams and removes clicks;
`"loop"` makes a seamless loop of the locked segments' sound; `"none"` drops audio.
`fps=` resamples mismatched frame rates as a last resort. The output is H.264,
BT.709, encoded once at high quality. `preserve_state=True` instead cuts hard after
each overlap and keeps stored state on the joined file, so the joins can show; to
extend a finished take, pin its last segment from the library instead.

`seamkit.check(stimma, segments_or_path, loop=False)` measures without writing.
`seamkit.motion(stimma, path)` reports motion per second against the clip's steady
level, with `settles_at` and `fades_at`, the window where it's actually moving.
`seamkit.cuts(stimma, path, ignore_before=0, seams=None)` finds hard cuts inside a
clip or a joined video, with a time and confidence for each. Pass the pinned length
as `ignore_before` for a continuation (the boundary where the pin ends is still
checked), and your own join times as `seams` for a joined take, so a cut you made
is marked `at_seam` and a cut inside a segment is not.
`seamkit.drift(stimma, video_or_segments, reference=None)` compares each stretch of
a take with its opening (framing with `reference`, such as the start image): `ok`,
a `summary`, and per-window shifts with `flags`. A planned change (a new place, a
push-in) flags too; read flags against the plan. `seamkit.anchors(stimma, source,
stills)` checks anchor stills against the source the same way, before rendering.

### Read the report

For each seam, `before` and `after` give `median_delta_rgb` (level difference) and
`motion_step_ratio` (the jump across the seam over a normal frame step); `fit` says
what kind of mismatch it was, and each segment lists its `actions`.

- **After:** deltas within 1–2 levels and a motion ratio under about 2 are invisible.
- **`motion_step_ratio` well above 2 after the join:** the motion jumps, and color
  can't fix that. Regenerate the bridge with a stronger pin, move the join, or cut.
- **`fit.kind` is `range-mismatch`, or `warnings` mention color range or matrix:** a
  file was converted wrongly somewhere. Fix the source file, not the correction.
- **"left the seam uncorrected":** the sides don't look like one shot. Mark a
  deliberate cut `cut=True`; otherwise the bridge missed its pin, so regenerate it.

Then `view_image` the frames either side of each seam: numbers catch exposure, eyes
catch everything else.

## Finishing

Join with seamkit → interpolate if wanted → upscale if wanted → deliver. Processing
segments separately treats each a little differently and makes new seams, so
process the joined video once, without re-encoding between steps.

## Talking to the user

- Before a long render, show the plan in one short message: the segments, the tool,
  the lengths, the waves and roughly how long they'll take, which joins are cuts.
  Show the start frame and anchors as pictures with it. Before committing hours of
  GPU, wait for a go-ahead, unless the user said they're away: then show it and go.
- When it's done, describe the joins in plain words ("both joins in the loop are
  invisible; the second one needed a small exposure correction"), not the numbers,
  unless they ask.
- If a join can't be made invisible, say why and offer a fix: a cut, another join
  point, or a stronger pin.
