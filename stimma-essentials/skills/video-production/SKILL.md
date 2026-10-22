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

A single generation is easy. Making several clips play as one is where video work
goes wrong, and it goes wrong the same ways every time. This skill covers planning
the shots, choosing how to generate each one, and joining the results so the joins
can't be seen.

Use **Tool Selection** to pick a model family. Each video tool's own instructions
record what it can do and how it misbehaves (pin types, native length and frame
rate, crops, audio limits). Read them before planning around a tool.

## What goes wrong at a join

A pin fixes what's in the frame (geometry), not its exposure and color (photometry).
Every join between two clips can carry any of these:

- **Exposure and color offset.** Each run lands at its own exposure, usually a
  small gain change of a few levels shared across all three channels. It shows as
  a pulse at the seam even when everything else matches.
- **A repeated frame.** A clip pinned to a frame starts or ends on a copy of it.
  Splice it in as-is and the frame plays twice, which reads as a hitch.
- **A head that pops.** The first frame of an image-to-video clip is often the
  reference image itself, crisper than the frames after it and with a different
  texture. It pops for one frame.
- **A motion jump.** A still pin fixes position, not speed. Two clips can meet on
  the same frame and still visibly change speed or direction.
- **An audio jump.** Loudness, room tone and ambience change between runs just like
  exposure does, and a hard splice clicks.
- **A slow start.** Image-to-video often opens with a lull of a second or so while
  motion builds from the still, before it settles into its rhythm (MiniMax H3 does
  this often). A clip pinned to a last frame can coast into it the same way. Loop
  or join across a lull and the rhythm breaks every time it comes around.

`seamkit` fixes the exposure offset, repeated frames, popping heads and audio
mechanically, and measures motion. Motion is fixed by choosing which part of
each clip to use, by how you pin, and by where you put the join.

## Working rules

**Design the key frames as stills first.** Settle composition, character, look and
the frames that pin each segment as images, and get them approved. Stills are the
preview; they're cheap to iterate and they predict the video. Then render the video
once, at final settings.

**No draft video rounds.** A faster or distilled variant (⚡, Turbo, Fast, Max) does
not predict what the full model will make from the same prompt and seed. Its motion
and look differ in kind, not just in quality. If speed matters, make the faster
model the final model and say so. Lower resolution or a shorter test clip only when
the user asks for one.

**Plan the whole job, then render it in one go.** Local video takes a long time, and
the user walks away while it runs. Ask your questions before rendering, not between
segments. Then queue every segment that doesn't depend on another and finish the
job: render, join, check, deliver. On the cloud, cost is money; flag premium tiers
before running, as Tool Selection says.

**Pin to fixed frames instead of chaining.** Each continuation starts from the last
one's output, so its errors compound: identity, exposure and saturation drift a
little with every hop. Segments pinned at both ends to frames from one master take
or one set of reference images keep their error bounded. Chain at most two or
three hops. Reuse the same reference images and voice reference on every segment.

**Cuts are free.** If the story allows a cut, cut. A cut needs no matching at all.
Cuts written into one prompt (shot syntax in MiniMax H3, Wan 2.7's multi-shot, LTX
multishot text to video) are better still: the model keeps the look consistent
across them for you. Use a continuous join only when the shot must be continuous.

**Put joins where there's motion.** A join disappears under a whip pan, a fast
action, or something crossing the frame. It shows in slow, static moments. When you
can only pin stills, join where motion momentarily stops: the top of a breath, the
turn of a swing, a held pose. A still pin can't carry speed, so meet at a point
where speed is near zero.

**Work at the tool's native length and frame rate.** Plan segment counts from them.
Every clip in a join must share one frame rate. Regenerate rather than resample when
you can.

**Every join goes through seamkit.** Never splice clips with a bare ffmpeg concat.
Check the report, look at the frames either side of each seam, then deliver.

## How much a pin carries

From strongest to weakest:

1. **A clip pinned with its sound** (local MiniMax H3 Reference to Video keyframes).
   Carries picture, motion and audio across the join. The output repeats the pinned
   clip, which gives seamkit real overlap to crossfade. LTX keyframes in ComfyUI pin
   clips too, but picture only.
2. **A reference video plus a voice reference** (MiniMax H3 Reference to Video on
   Stimma Cloud). Carries motion and voice. It opens near the reference's last
   frame, not on it, so there's no exact overlap.
3. **An extend tool** (SkyReels V4 Extend on the cloud, LTX Extend Video locally).
   The model continues the clip from its own context.
4. **First and last still frames** (most image-to-video tools). Fixes position at
   both ends, not motion, and usually no audio.
5. **The last frame as a first frame.** Fine for one or two continuations. Tell the
   user the join may show, because neither motion nor voice carries over.

Pick the strongest one the available tools offer.

## Recipes

### Loop an existing clip

The clip's last frame and first frame are close but not equal. Generate a bridge
from the end back to the start, then join with `loop=True`.

**Choose the loop window first, before generating the bridge.** The bridge is
pinned to the window's ends, so the window can't change afterwards.

- **By default, leave out a few frames at each end** (2–4 at 24 fps). The first
  frame is often the reference image, with its own texture. The ends are where
  pinned frames and slow-downs sit. Losing them costs nothing and removes a
  likely discontinuity.
- **Then measure the motion:** `await seamkit.motion(stimma, path)`. If `settles_at`
  is past about half a second, the clip opens with a lull: start the window
  there. If `fades_at` is well before the end, it slows down into its last frame:
  end the window there.
- **Keep the length if it matters.** Make the bridge longer by however much you
  cut. A 1.5 s lull cut from the start comes back as a bridge 1.5 s longer, so the
  loop runs the same length with the stall gone.
- Take the bridge's pins (frames or clips) from the window's ends, not the clip's.
  Join with the same window: `trim_head` and `trim_tail` on the locked segment.
- If the clip's ends move fast and the tool only pins stills, also prefer window
  ends where motion pauses.

Then generate the bridge:

- **Local MiniMax H3 Reference to Video:** pin the window's last second (with sound)
  at 0 and its first second at the end. Pass the clip in `input_audios` for the
  voice. Join with `overlap` set to the pinned frame count on both segments (see
  [Join](#join)). Clip pins carry motion, so the bridge doesn't open with its own
  lull. A bridge pinned to stills can, which is one more reason to prefer clips.
- **LTX Loop (local):** does the bridge and the join in one step, on the whole clip.
  Trim the clip to its window first, then run `seamkit.check` on the result with
  `loop=True`.
- **Cloud, or any first/last-frame tool:** first frame = the window's last frame,
  last frame = its first frame. Pick a tool that returns its pinned frames exactly;
  LTX 2.5 returns them cropped.
- **Sound:** if the bridge comes back silent (Kling with frames, for example), use
  `audio="loop"`, which builds a seamless loop of the clip's own sound.

### Loop from scratch

Pin the same image as both the first and the last frame. Describe motion that goes
out and comes back. Check the wrap with `seamkit.check(stimma, path, loop=True)`.

### Continue a clip, or build a long take

- Check where the previous segment's motion fades (`seamkit.motion`). Continue from
  before a slow ending, not from inside it.
- **Local:** MiniMax H3 Reference to Video, pinning the previous segment's last
  second with sound at 0, the same voice reference, and the same reference images.
  Pin where each segment should land as a keyframe at its end. Join with `overlap`.
- **Cloud:** SkyReels V4 Extend, or MiniMax H3 Reference to Video with the clip's last
  few seconds in `input_videos` and `input_audios`. Join without `overlap`; seamkit
  drops repeated frames and matches the exposure.
- **For a long take with a known route:** design key-frame stills along the path,
  generate a first/last-frame segment between each consecutive pair, and put each
  join on a moment of motion. The segments never chain, so they never drift.

### Bridge two different clips

The bridge's first frame is clip A's last frame and its last frame is clip B's
first. Locally, LTX Stitch does this and keeps the source audio. Otherwise use a
first/last-frame tool, or local H3 with clips pinned at both ends. Lock both clips;
the bridge is adjusted to fit both.

### Talking head and dialogue

- Split the script at sentence boundaries. Generate one sentence or line per segment
  and **cut** between segments: change the angle, or cut to B-roll. Don't try to
  make spoken segments continuous.
- Keep the voice consistent with a voice reference on every segment (`input_audios`
  on H3 Reference to Video), plus the same face reference images.
- If the user supplies the voiceover, or it comes from a TTS tool, make the audio
  first and fix its timing before generating any video. Then generate each segment
  to its piece of the audio, with a tool that takes driving audio if one is
  available.
- For dialogue, models with strong lip-sync (Veo 3.1, MiniMax H3, Seedance 2.0)
  beat generating silent video and syncing it afterwards.

### Multi-shot sequence

Write the cuts into one generation when the shots fit its length. Across separate
generations, keep identity with the same reference images and voice, and join with
`cut=True`. A cut needs no matching. Run seamkit anyway, so every clip is encoded
once, consistently.

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

- `lock: True` for footage that must not change: the user's clip, the source of a
  loop. Unlocked segments are adjusted to fit the locked ones: a gain and offset
  fitted at each end, ramped across the segment. If nothing is locked, the first
  segment is.
- `overlap: N` when this segment's first N frames show the same moments as the
  previous segment's last N (a pinned clip). They're crossfaded, picture and sound.
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
BT.709, encoded once at high quality.

`seamkit.check(stimma, segments_or_path, loop=False)` measures without writing.
`seamkit.motion(stimma, path)` reports motion per second relative to the clip's
steady level, with `settles_at` and `fades_at`, the window where it's actually
moving.

### Read the report

For each seam, `before` and `after` give `median_delta_rgb` (level difference across
the seam) and `motion_step_ratio` (how much bigger the jump across the seam is than
a normal frame step). `fit` says what kind of mismatch it was. Each segment lists
the `actions` taken.

- **After:** deltas within about 1–2 levels and a motion ratio under about 2 are
  invisible. Say so in one line and move on.
- **`motion_step_ratio` well above 2 after the join:** the motion jumps, and color
  can't fix that. Regenerate the bridge with a stronger pin, move the join to a
  moment of motion or a pause, or make it a cut.
- **`fit.kind` is `range-mismatch`, or `warnings` mention color range or matrix:** a
  file was converted wrongly somewhere. That's a pipeline problem, not the model. Fix
  the source file instead of trusting the correction.
- **"left the seam uncorrected":** the two sides don't look like the same shot. If
  it's meant to be a cut, mark it `cut=True`. If not, the bridge missed its pin;
  regenerate it.

Then look at it: extract the frames either side of each seam with `stimma.ffmpeg`
and `view_image` them. Numbers catch exposure; eyes catch everything else.

## Finishing

The order: join with seamkit → frame interpolation if wanted → upscale if wanted →
deliver. Upscaling or interpolating segments separately treats each one a little
differently, and that creates new seams. Process the joined video once. Don't
re-encode between steps unless a tool requires it.

## Talking to the user

- Before a long render, state the plan in one short message: the segments, the tool,
  the lengths, which joins are cuts and which are continuous. Then run all of it.
- When it's done, describe the joins in plain words ("both joins in the loop are
  invisible; the second one needed a small exposure correction"), not the numbers,
  unless they ask.
- If a join can't be made invisible, say why, and offer the fix: a cut, a different
  join point, or a bridge with a stronger pin.
