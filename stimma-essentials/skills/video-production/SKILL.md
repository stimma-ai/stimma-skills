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

**A join reads as one shot only when both sides show the same instant**: one clip's
last frame and the next one's first agree on pose, gaze, hands and objects, not just
framing and light. Two clips made from one still share only their first frame, so
their ends show different moments and need a bridge like any other pair.

A pin fixes what's in the frame (geometry), not its exposure and color (photometry).
Every continuous join can also carry any of these:

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
  into one. Loop or join across a lull and the rhythm breaks: slow, pause, jump.
- **Judder.** Some generated clips repeat a frame in a steady cadence, so motion
  stutters inside the clip.

`seamkit` fixes exposure, repeated frames, popping heads, judder, slow frames at a
seam and audio, and flags sides that show different moments. The rest of motion is
fixed by what you use of each clip, how you pin, and where you join.

## Working rules

**Design the key frames as stills first, at the video's shape.** Settle
composition, character, look and the frames that pin each segment as images:
they're cheap to iterate and predict the video; then render it once, at final
settings. Choose the video tool and output size first, since a frame of another
shape gets stretched or cropped without warning: crop or outpaint other images
yourself, so you choose what's kept.

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

**Work at the tool's native length and frame rate**: the duration parameter states
them. Every segment and hop of a longer take runs at the native length, so a take
needs (its length ÷ the native length) segments, rounded up. A longer run suits
only a clip that stands alone and needs it: it costs more GPU time, drifts more
within itself, and a failed one is redone whole instead of one short segment.
Clips in a join share one frame rate; regenerate rather than resample.

**Every join goes through seamkit.** It matches exposure, blends, repairs and
reports each seam, and records the input clips as the joined file's sources. Check
the report, look at the frames either side of each seam, play it through, then deliver.

## Long takes

**Error compounds with every hop, stored state or not.** A continuation re-renders
the clip it's pinned to and builds on the result: colors saturate and darken, detail
smears, the framing creeps, and each hop looks fine next to the last. Stored state
(a clip pinned from the library) slows the color drift without bounding it.
**So choose anchors or continuation by what the take needs.** Anchors fit when the
moments along the take can be planned as stills: each segment runs from one clean
still to the next, so none inherits another's error and they render in parallel.
Continuation fits a take that travels, where no still made ahead can predict where
the previous segment ends; each hop inherits the last one's drift, so runs stay
short. If neither holds the continuity the user asked for over the whole length,
explain the tradeoff (visible drift, or a cut at a point you name) and let them
choose: a requested long take gets no cuts they didn't agree to. Each video tool's
instructions say how it handles each pin.

**Get a go-ahead before the first video of a long take.** The stills are a cheap
preview of a long GPU job: changing one now costs a still, later a batch of
segments. Show them from `run_code` with `stimma.show(paths, role="intermediate",
title=...)`, then call `ask_user` with the plan (segments or hops and their length,
any cuts, roughly how long the GPU work takes) and options to go ahead or change
something; the turn waits for the answer. Estimate from runs here at the planned settings:

```python
t = await stimma.tasks.run_time(tool, duration=segment_s)  # ≈ t["typical_s"] × ceil(segments ÷ await stimma.tasks.capacity(tool))
```

Anything that waits on an earlier result adds its own time; queueing and model
loads add more. If the user said they're away, show the plan and go on.

A planned long take with anchors, using a tool that pins frames at both ends:

1. **Anchor stills**, one per key moment. An anchor is a new moment (the pose,
   gesture and gaze at that point of the take) made by an image edit of the source
   image (never an edit of an edit), at the video's shape, sharing its framing,
   lens and look, where motion briefly settles (a still carries no speed). A crop
   or reframe of the source shows the source's moment again, so it isn't an
   anchor. Check them side by side and with `seamkit.anchors`; when it isn't `ok`,
   redo the stills its `summary` names before any video (edit models often zoom
   in: try another seed), since a segment between stills framed differently may
   reframe with a cut. Make every still before any video: swapping image and video
   models on a GPU costs minutes.
2. **Go-ahead**, as above.
3. **Segments:** one between each pair of neighboring anchors, at the tool's native
   length, the earlier anchor pinned at the start and the later one at the end, both
   passed as references, the same voice reference on every segment, and the prompt
   describing the action that takes one into the other.
4. **Join** them in order with seamkit, none locked, `trim_head: 1` on every
   segment after the first (it opens on the anchor the last one ended on). Segments
   slow near their stills and seamkit leaves those frames out (up to about half a
   second per join), so plan a little extra and trim the last tail to length.

A take that travels, by continuation:

1. **Runs and stills:** split the take into runs of two or three hops, with a cut
   between runs at points you name, and make a fresh still for each run's start at
   the video's shape.
2. **Go-ahead**, as above, with the runs and where they cut.
3. **Hops** at the native length: the first from its run's still, each next one
   pinning the previous hop's tail ([Continue a clip](#continue-a-clip)) and
   describing the same ongoing action.
4. **Join** each run's hops with `overlap`, and the runs with `cut=True`.

**Speech in a long take comes from one track**, since segments that each invent
lines can't add up to continuous speech: the user's, or one made first (a talking
take of the full length, or TTS), whose length sets the segment count. Segments
keep the native length and the track is sliced to them, wherever a slice ends in a
sentence: with N-frame segments sharing a frame at each join, segment k pins the
track as sound from `k × (N − 1) / fps` seconds for `N / fps` seconds, with its two
anchor stills, and passes the whole track as the voice reference. The pinned sound sets the words and timing, so the prompt says who
speaks and how, not the words; watch the lip-sync on playback. Join with `audio=`
set to the track: each frame keeps its place on it, so pacing stays off and a slow
moment at a seam stays.

**Submit independent segments together** after the go-ahead, sized to
`await stimma.tasks.workers(tool)`, inside `stimma.batch(title, total=N)` so the
count is right from the start. A pilot segment only adds a render's wait, since
each segment is checked and regenerated on its own; render one first only when an
untested motion, audio or pinning behavior could spoil the whole batch.

**Check every segment; fix only what failed.** Run `seamkit.cuts` on each segment
(a cut in the first few frames means it popped off its start anchor); after joining,
check each seam's motion ratio, run `seamkit.drift` and watch the take. Regenerate
only what failed, with a new seed; if the same pair fails twice, redo the anchor.

## How much a pin carries

From strongest to weakest:

1. **Sound pinned over a span** (local MiniMax H3 keyframes: an audio item, or a
   video with `picture: false`). The output follows that recording and its timing,
   whether speech, music or ambience; stills or clips pinned with it carry the
   picture. On-screen speech is lip-synced to it, which is worth checking by eye.
2. **A clip pinned with its sound** (local MiniMax H3 Reference to Video keyframes).
   Carries picture, motion and audio, and repeats the clip, giving real overlap to
   crossfade (LTX keyframes pin clips too, picture only). It carries on only what the
   clip is already doing; ask for another action or framing and local H3 tends to cut.
3. **A reference video plus a voice reference** (H3 Reference to Video on Stimma
   Cloud). Carries motion and voice; opens near the reference's last frame, not on it.
4. **An extend tool** (SkyReels V4 Extend on the cloud, LTX Extend Video locally).
   The model continues the clip from its own context.
5. **First and last still frames** (most image-to-video tools). Fixes position at
   both ends, not motion, and usually no audio.
6. **The last frame as a first frame.** Fine for one or two continuations; warn that
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
  voice, and join with `overlap` set to the pinned frame count on both segments;
  clip pins carry motion, so the bridge has no lull. Run `seamkit.cuts` on it: when
  the window's ends differ much, H3 can cut into the end clip; then pin the window's
  last and first frames as stills instead.
- **LTX Loop (local):** bridges and joins in one step. Trim the clip to its window
  first, then `seamkit.check` the result with `loop=True`.
- **Cloud, or any first/last-frame tool:** first frame = the window's last frame,
  last frame = its first frame. Pick a tool that returns its pinned frames exactly;
  LTX 2.5 returns them cropped.
- **Sound:** a silent bridge (Kling with frames) gets `audio="loop"`: a seamless loop of the clip's sound.

### Loop from scratch

Pin the same image as both the first and the last frame. Describe motion that goes
out and comes back. Check the wrap with `seamkit.check(stimma, path, loop=True)`.

### Continue a clip

An extension runs in hops at the native length; past two or three, see
[Long takes](#long-takes).

- Check where the previous segment's motion fades (`seamkit.motion`). Continue from
  before a slow ending, not from inside it.
- **Local:** H3 Reference to Video, pinning the previous segment's tail clip with
  sound at 0 from the library, with the same voice and reference images. The clip
  sets the opening framing, so the prompt describes what happens next and any change
  of framing as camera movement. Run `seamkit.cuts` with the pinned length as
  `ignore_before`, regenerate a segment that cuts, and join with `overlap`.
- **Cloud:** SkyReels V4 Extend, or MiniMax H3 Reference to Video with the clip's last
  few seconds in `input_videos` and `input_audios`. Join without `overlap`; seamkit
  drops repeated frames and matches the exposure.

### Bridge two clips

Any two clips whose ends show different moments, including two made from one still.
The bridge's first frame is clip A's last frame and its last frame is clip B's
first. Locally, LTX Stitch does this and keeps the source audio. Otherwise use a
first/last-frame tool, or local H3 with those two frames pinned as stills (H3 tends
to cut into a clip pinned at the end unless the two clips nearly match). Lock both clips;
the bridge is adjusted to fit both.

### Talking head and dialogue

- Generate one sentence or line per segment and **cut** between segments (a new
  angle, or B-roll). Speech that runs through one take, or a given or TTS
  voiceover, sets the timing: pin each segment's slice of it as sound where the
  tool can ([Long takes](#long-takes)), or use a driving-audio tool.
- Use the same voice reference (`input_audios` on H3 Reference to Video) and face
  references on every segment.
- For dialogue, models with strong lip-sync (Veo 3.1, MiniMax H3, Seedance 2.0)
  beat generating silent video and syncing it afterwards.

### Multi-shot sequence

Write the cuts into one generation when the shots fit its length. Across separate
generations, keep the same reference images and voice and join with `cut=True`;
seamkit still encodes every clip once, consistently.

## seamkit

`import seamkit` in `run_code`. Every call is async, takes `stimma` first, and works
on workspace paths (`stimma.library.get(media_id)` gives a library item's path).
This index covers the common calls; the public docstrings describe further
controls and the limits of each measurement.

| call | returns |
|---|---|
| `join(stimma, segments, out=None, *, loop=False, match=True, audio="auto", pace=True, repair=True, fps=None, preserve_state=False, audio_xfade=0.06, audio_search=0.25)` | `{frames, fps, out, warnings, seams: [{between, before, moment, after, fit, at_frame, slow_frames_left_out}], segments: [{index, path, locked, frames_used, trim_head, trim_tail, actions}], audio_gains_db, sound}` |
| `check(stimma, segments_or_path, *, loop=False)` | the same report without writing: no `out` or `after` |
| `motion(stimma, path)` | `{duration, fps, per_second, settles_at, fades_at}` |
| `cuts(stimma, path, *, ignore_before=0, seams=None, min_confidence=0.5)` | `{duration, fps, checked_from, continuous, cuts: [{at, frame, confidence, at_seam}]}` |
| `drift(stimma, video_or_segments, *, reference=None, window=4.0, limits=None)` | `{ok, summary, worst, windows: [{start, end, flags, ...}]}` |
| `anchors(stimma, source, stills, *, limits=None, framing_tolerance=1.12)` | `{ok, summary, stills: [{path, aspect, framing_scale, comparable, flags, ...}]}` |
| `probe(stimma, path)` | `{width, height, fps, duration, color_range, color_space, has_audio}` |

Times are in seconds; `before` and `after` are `{median_delta_rgb, motion_step_ratio}`;
`moment` is `{jump, ratio, same}`; `sound` (with an `audio=` track) is
`{track, picture_s, track_s, note}`.

```python
import seamkit
report = await seamkit.join(stimma, [
    {"path": "source.mp4", "lock": True},
    "bridge.mp4",
], "loop.mp4", loop=True)
```

Each segment is a path, or a dict with:

- `lock: True` for footage that must not change (the user's clip, a loop's source).
  Unlocked segments get a gain and offset fitted at each end and ramped between;
  if nothing is locked, the first segment is the color reference. Only segments
  you didn't lock are retimed or repaired.
- `overlap: N` when this segment's first N frames show the same moments as the
  previous segment's last N (a pinned clip): they're crossfaded, picture and sound.
  For local H3, N is the pinned clip's frame count rounded to 17k+5 (about 1 second
  pins 22 frames). In a loop, `overlap` on the first segment means the bridge's tail
  repeats the first segment's head.
- `cut: True` when the join into this segment is a deliberate cut. Nothing is
  matched, trimmed or blended there.
- `trim_head` / `trim_tail` to drop frames yourself. Repeated pinned frames and
  popping head frames are dropped automatically.

Options: `loop=True` joins the end back to the start. `audio="auto"` joins each
segment's sound, matches loudness and switches at the quietest moment near each
seam, so speech isn't cut mid-word or doubled; `"loop"` loops the locked segments'
sound; `"none"` drops it. A path is the take's own sound track, for segments pinned
to its slices: every frame keeps its place on it (no automatic drops or pacing).
`pace=True` leaves out slow frames next to a hard seam and blends two across it;
`repair=True` replaces repeated frames with interpolated ones; `fps=` resamples as a
last resort. The output is H.264, BT.709, encoded once. `preserve_state=True` cuts
hard after each overlap and keeps stored state on the joined file, so the joins can
show; to extend a finished take, pin its last segment from the library instead.

`motion`'s `settles_at` and `fades_at` bound where a clip actually moves. `cuts`
finds hard cuts: pass the pinned length as `ignore_before` for a continuation and
your own join times as `seams`, so a cut you made is marked `at_seam`; a slow change
of shot can pass unflagged. `drift` compares each stretch of a take with its opening
(framing with `reference`, such as the start image); a planned change flags too, so
read flags against the plan.

### Read the report

Per seam, `median_delta_rgb` is the level difference and `motion_step_ratio` the
jump over a normal frame step; each segment lists its `actions`.

- **`moment.same` is false (a warning says "different moments"):** pacing and
  blending smooth the numbers, not what the eye sees. Bridge it
  ([Bridge two clips](#bridge-two-clips)), or mark a wanted cut `cut=True`.
- **After:** deltas within 1–2 levels and a motion ratio under about 2 usually don't
  show. These are screening signals, not proof: play the take around each seam.
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

- When it's done, describe the joins in plain words ("both joins look seamless;
  the second needed a small exposure correction"), not the numbers, unless asked.
- If a join can't be made invisible, say why and offer a fix: a cut, another join
  point, or a stronger pin.
