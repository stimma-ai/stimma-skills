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

**Design the key frames as stills first.** Settle composition, character, look and
the frames that pin each segment as images: they're cheap to iterate and predict
the video. Then render the video once, at final settings.

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

**Work at the tool's native length and frame rate**: the duration parameter states
them. A take needs (its length ÷ the native length) segments, rounded up; a longer
run per segment costs more GPU time and is redone whole when it fails. Clips in a join share one frame rate; regenerate rather than resample.

**Every join goes through seamkit.** It matches, blends and records lineage; a bare
ffmpeg edit loses lineage and stored state. Check the report, look at the frames
either side of each seam, then deliver.

## Long takes

**Error compounds with every hop, stored state or not.** A continuation re-renders
the clip it's pinned to and builds on the result: colors saturate and darken, detail
smears, the framing creeps, and each hop looks fine next to the last. Stored state
(a clip pinned from the library) roughly halves the color drift without bounding
it. So continue for short extensions (two or three hops) or a tracking shot nobody
can plan; for anything longer, keep every frame at most two generations from a
clean still.

**A planned long take renders in one parallel wave of still-to-still segments**,
with a tool that pins frames at both ends:

1. **Anchor stills**, one per key moment, each made directly from the source image
   (never an edit of an edit), at the video's shape, sharing its framing, lens and
   look. Pick moments where motion briefly settles: the take passes through each
   anchor, and a still carries no speed.
2. **Show the anchors and the plan, then wait for a go-ahead.** Show the stills as
   pictures with one short message: segments and their length, waves, which joins
   are cuts, and roughly how long the GPU work takes (`stimma.tasks.run_time` per
   call, times the waves: segments ÷ `stimma.tasks.capacity`). The anchors are the cheap preview of hours of GPU:
   changing one now costs a still, later a wave. If the user said they're away,
   show it and go on.
3. **Segments:** one between each pair of neighboring anchors, at the tool's native
   length, the earlier anchor pinned at the start and the later one at the end, both
   passed as references, the same voice reference on every segment, and the prompt
   describing the action that takes one into the other.
4. **Join** them in order with seamkit, `trim_head: 1` on every segment after the
   first (its opening repeats the anchor the previous one ended on), none of them
   locked. Each segment slows into the still it ends on and starts slowly from the
   next; seamkit leaves those slow frames out (up to about half a second per
   join), so plan a little extra length. Trim the last segment's tail so the take
   is exactly the requested length.

**Speech in a long take comes from one track.** Segments that each invent their own
lines can't add up to continuous speech. Use the user's track, or generate the
speech first (a talking take of the full length, or TTS); its length sets the
segment count. Segments keep the native length and the track is sliced to them,
wherever a slice ends in a sentence: with N-frame segments sharing a frame at each
join, segment k pins the track as sound from `k × (N − 1) / fps` seconds for
`N / fps` seconds, with its two anchor stills, and passes the whole track as the
voice reference. The model speaks that slice and lip-syncs to it, so the prompt
says who speaks and how, not the words. Join with `audio=` set to the track: each
frame keeps its place on it, so pacing stays off and a slow moment at a seam stays.

Every segment renders at once, so every GPU works. Submit them together, sized to
`await stimma.tasks.workers(tool)`, inside `stimma.batch(title, total=N)` so the
count is right from the start. A pilot segment first buys nothing: segments are
independent, each is checked and regenerated on its own, and the anchors already
preview the look, so the wave is the test and a pilot only adds a render's wait.

**Segments pin stills, not clips.** Local H3 treats a pinned clip as a shot of its
own and cuts out of a start clip, or into an end clip, whenever the prompt asks for
something the clip isn't already doing: segments bridged with clips at both ends
cut in 46 of 50 tests, still-to-still segments in 2 of 10. The crossfade hides the
join, not a cut inside, so a seam report alone looks fine.

**A take that travels** (a walk, a drive, a tracking shot moving through a place)
can't be planned as anchors: nothing predicts where each segment ends, so the next
anchor is never where the last one stopped, and the model cuts to it. Continue it
instead, each hop pinning the previous tail and describing the same ongoing action
(those hops didn't cut, 0 of 20), in runs of two or three hops with stored state;
for anything longer, end a run on a planned cut and start the next from a fresh
still. Show that plan, with its cuts, the same way as step 2.

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

1. **Sound pinned over a span** (local MiniMax H3 keyframes: an audio item, or a
   video with `picture: false`). The output plays that sound with its timing and
   lip-syncs to it; it carries speech, and stills or clips pinned with it the picture.
2. **A clip pinned with its sound** (local MiniMax H3 Reference to Video keyframes).
   Carries picture, motion and audio, and repeats the clip, giving real overlap to
   crossfade (LTX keyframes pin clips too, picture only). It carries on only what the
   clip is already doing; ask for another action or framing and local H3 cuts.
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
first/last-frame tool, or local H3 with those two frames pinned as stills (H3 cuts
into a clip pinned at the end unless the two clips nearly match). Lock both clips;
the bridge is adjusted to fit both.

### Talking head and dialogue

- Generate one sentence or line per segment and **cut** between segments (a new
  angle, or B-roll). When the speech must run continuously through one take,
  pin each segment's slice of one track instead (see [Long takes](#long-takes)).
- Use the same voice reference (`input_audios` on H3 Reference to Video) and face
  references on every segment.
- A given or TTS voiceover sets the timing: pin each segment's piece as sound where
  the tool can, or use a driving-audio tool.
- For dialogue, models with strong lip-sync (Veo 3.1, MiniMax H3, Seedance 2.0)
  beat generating silent video and syncing it afterwards.

### Multi-shot sequence

Write the cuts into one generation when the shots fit its length. Across separate
generations, keep the same reference images and voice and join with `cut=True`;
seamkit still encodes every clip once, consistently.

## seamkit

`import seamkit` in `run_code`. Every call is async, takes `stimma` first, and works
on workspace paths (`stimma.library.get(media_id)` gives a library item's path).
This index is its whole API; the source adds nothing you need to read.

| call | returns |
|---|---|
| `join(stimma, segments, out=None, *, loop=False, audio="auto", pace=True, repair=True, fps=None, preserve_state=False)` | `{frames, fps, out, warnings, seams: [{between, before, moment, after, fit, at_frame, slow_frames_left_out}], segments: [{index, path, locked, frames_used, trim_head, trim_tail, actions}], audio_gains_db, sound}` |
| `check(stimma, segments_or_path, *, loop=False)` | the same report without writing: no `out` or `after` |
| `motion(stimma, path)` | `{duration, fps, per_second, settles_at, fades_at}` |
| `cuts(stimma, path, *, ignore_before=0, seams=None)` | `{duration, fps, checked_from, continuous, cuts: [{at, frame, confidence, at_seam}]}` |
| `drift(stimma, video_or_segments, *, reference=None)` | `{ok, summary, worst, windows: [{start, end, flags, ...}]}` |
| `anchors(stimma, source, stills)` | `{ok, stills: [{path, aspect, framing_scale, comparable, flags, ...}]}` |
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
print(report)
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

`motion` gives motion per second against the clip's steady level; `settles_at`
and `fades_at` bound where it's actually moving. `cuts` finds hard cuts inside a
clip or a joined video: pass the pinned length as `ignore_before` for a continuation
(the boundary where the pin ends is still checked), and your own join times as
`seams` for a joined take, so a cut you made is marked `at_seam`. `drift` compares
each stretch of a take with its opening (framing with `reference`, such as the start
image); a planned change (a new place, a push-in) flags too, so read flags against
the plan. `anchors` checks anchor stills against the source the same way, before
rendering.

### Read the report

Per seam, `median_delta_rgb` is the level difference and `motion_step_ratio` the
jump over a normal frame step; each segment lists its `actions`.

- **`moment.same` is false (a warning says "different moments"):** pacing and
  blending smooth the numbers, not what the eye sees. Bridge it
  ([Bridge two clips](#bridge-two-clips)), or mark a wanted cut `cut=True`.
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

- When it's done, describe the joins in plain words ("both joins in the loop are
  invisible; the second one needed a small exposure correction"), not the numbers,
  unless they ask.
- If a join can't be made invisible, say why and offer a fix: a cut, another join
  point, or a stronger pin.
