"""Join video segments without visible seams, and measure the seams you have.

Generated segments rarely line up with the footage around them. Pins fix
geometry but not photometry: each run lands at its own exposure, its first
frame often repeats the frame it was pinned to, and an image-to-video head can
carry the reference image's texture for a frame. ``join`` fixes the mechanical
part of that at every seam:

* drops a pinned frame that repeats its neighbour, and a head frame that pops;
* fits a per-channel gain and offset at each end of every adjustable segment
  and ramps between them, so a bridge lands exactly on the footage at both
  ends;
* crossfades frames two segments share (``overlap``);
* matches audio loudness at the seams and removes clicks;
* reports every seam before and after, including motion jumps it cannot fix.

``check`` runs the same measurements without writing anything. Both take the
``stimma`` object from ``run_code`` and work on workspace paths. Intermediates
are raw RGB in ``.seamkit/`` and removed afterwards; the output is encoded once.
"""
import json
import math
import shutil
import uuid
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48000
_Q = np.linspace(0.02, 0.98, 25)
_REF_FRAMES = 3
_MATRICES = {"bt709": "bt709", "bt470bg": "bt601", "smpte170m": "bt601", "bt2020nc": "bt2020",
             "fcc": "fcc", "smpte240m": "smpte240m"}
_FADE_SAMPLES = 144  # 3 ms each side of a hard audio join: removes the click, inaudible


# ---------------------------------------------------------------- probing

async def probe(stimma, path):
    """Size, fps, frame count, colour tags and audio presence of a video file."""
    r = await stimma.ffprobe("-v", "error", "-show_streams", "-show_format", "-of", "json", str(path))
    data = json.loads(r.stdout)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"{path} has no video stream")
    num, _, den = video.get("avg_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    if not fps:
        num, _, den = video.get("r_frame_rate", "0/1").partition("/")
        fps = float(num) / float(den or 1)
    return {
        "path": str(path),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": round(fps, 3),
        "duration": float(data.get("format", {}).get("duration") or 0.0),
        "color_range": video.get("color_range", "unknown"),
        "color_space": video.get("color_space", "unknown"),
        "has_audio": any(s.get("codec_type") == "audio" for s in data["streams"]),
    }


# ---------------------------------------------------------------- frame maths

def _small(frame):
    """Subsample a frame to roughly 320px wide, as float32."""
    step = max(1, frame.shape[1] // 320)
    return frame[::step, ::step].astype(np.float32)


def _luma_std(frame):
    """Standardised luma: invariant to exposure, so it compares content only."""
    f = _small(frame)
    y = 0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2]
    return (y - y.mean()) / (y.std() + 1e-6)


def _content_diff(a, b):
    return float(np.abs(_luma_std(a) - _luma_std(b)).mean())


def _typical_step(frames, start, count=8):
    """Median content change between consecutive frames from ``start``."""
    end = min(len(frames) - 1, start + count)
    steps = [_content_diff(frames[i], frames[i + 1]) for i in range(start, end)]
    return float(np.median(steps)) if steps else 0.0


def _quantiles(frames):
    """Per-channel quantiles over a stack of frames, shape (3, len(_Q))."""
    stack = np.stack([_small(f) for f in frames])
    return np.stack([np.quantile(stack[..., c], _Q) for c in range(3)])


def _fit(ref_q, src_q):
    """Per-channel (gain, offset) mapping src quantiles onto ref quantiles."""
    out = []
    for c in range(3):
        x, y = src_q[c], ref_q[c]
        if x.max() - x.min() < 8:
            out.append((1.0, float((y - x).mean())))
            continue
        a, b = np.polyfit(x, y, 1)
        out.append((float(a), float(b)))
    return np.array(out)


def _apply_q(q, t):
    return q * t[:, :1] + t[:, 1:]


def _describe_fit(t, ref_q, src_q):
    delta = (ref_q - src_q)[:, len(_Q) // 2]
    gains, offsets = t[:, 0], t[:, 1]
    if np.abs(ref_q - src_q).max() < 1.0:
        kind = "matched"
    elif np.all(np.abs(gains - 1) < 0.01):
        kind = "offset"
    elif np.all(np.abs(offsets) < 1.5):
        kind = "gain"
    else:
        kind = "gain+offset"
    if (np.all(np.abs(gains - 219 / 255) < 0.03) and np.all(np.abs(offsets - 16) < 4)) or (
            np.all(np.abs(gains - 255 / 219) < 0.03) and np.all(np.abs(offsets + 18.6) < 4)):
        kind = "range-mismatch"
    return {
        "kind": kind,
        "median_delta_rgb": [round(float(d), 2) for d in delta],
        "gain_rgb": [round(float(g), 4) for g in gains],
        "offset_rgb": [round(float(o), 2) for o in offsets],
    }


def _plausible(t):
    return bool(np.all(np.abs(t[:, 0] - 1) < 0.3) and np.all(np.abs(t[:, 1]) < 40))


def _smoothstep(x):
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- segments

class _Segment:
    def __init__(self, spec, index):
        spec = {"path": spec} if isinstance(spec, (str, Path)) else dict(spec)
        unknown = set(spec) - {"path", "lock", "trim_head", "trim_tail", "overlap", "cut"}
        if unknown:
            raise ValueError(f"segment {index}: unknown keys {sorted(unknown)}")
        self.index = index
        self.path = str(spec["path"])
        self.lock = spec.get("lock")
        self.trim_head = int(spec.get("trim_head", 0))
        self.trim_tail = int(spec.get("trim_tail", 0))
        self.overlap = int(spec.get("overlap", 0))
        self.cut = bool(spec.get("cut", False))
        self.actions = []
        self.head_t = self.tail_t = np.array([[1.0, 0.0]] * 3)

    @property
    def frames(self):
        end = len(self.raw) - self.trim_tail
        return self.raw[self.trim_head:end]

    def transform_at(self, i, n):
        """Correction for frame i of n: ramps head -> tail with a smoothstep."""
        if n <= 1:
            return self.head_t
        w = _smoothstep(i / (n - 1))
        return self.head_t * (1 - w) + self.tail_t * w


async def _decode(stimma, seg, work, size, fps, need_audio):
    w, h = size
    raw_path = work / f"{seg.index}.rgb"
    # Read YUV the way players do: the stream's own tags, else BT.709 for HD,
    # BT.601 for SD, limited range. A wrong guess here shifts the footage.
    space = seg.info["color_space"]
    matrix = _MATRICES.get(space) or ("bt709" if seg.info["height"] >= 720 else "bt601")
    in_range = "pc" if seg.info["color_range"] in ("pc", "jpeg", "full") else "tv"
    vf = f"fps={fps}," if fps else ""
    vf += (f"scale={w}:{h}:flags=lanczos:in_color_matrix={matrix}:in_range={in_range},"
           "format=rgb24")
    await stimma.ffmpeg("-v", "error", "-y", "-i", seg.path, "-map", "0:v:0", "-vf", vf,
                        "-f", "rawvideo", "-pix_fmt", "rgb24", str(raw_path), timeout=1800)
    n = raw_path.stat().st_size // (w * h * 3)
    seg.raw = np.memmap(raw_path, dtype=np.uint8, mode="r", shape=(n, h, w, 3))
    seg.audio = None
    if need_audio and seg.info["has_audio"]:
        pcm = work / f"{seg.index}.f32"
        await stimma.ffmpeg("-v", "error", "-y", "-i", seg.path, "-map", "0:a:0", "-ac", "2",
                            "-ar", str(SAMPLE_RATE), "-f", "f32le", str(pcm))
        seg.audio = np.fromfile(pcm, dtype=np.float32).reshape(-1, 2)


async def _load(stimma, specs, work, fps, need_audio):
    segs = [_Segment(s, i) for i, s in enumerate(specs)]
    if not segs:
        raise ValueError("no segments")
    for seg in segs:
        seg.info = await probe(stimma, seg.path)
    base = segs[0].info
    warnings = []
    rates = {s.info["fps"] for s in segs}
    if fps is None and max(rates) - min(rates) > 0.01:
        raise ValueError(
            f"segments run at different frame rates {sorted(rates)}; pass fps= to resample them "
            "all to one rate (better: regenerate at a matching rate)")
    out_fps = fps or base["fps"]
    for seg in segs[1:]:
        if (seg.info["width"], seg.info["height"]) != (base["width"], base["height"]):
            warnings.append(f"segment {seg.index} is {seg.info['width']}x{seg.info['height']}; "
                            f"scaled to {base['width']}x{base['height']}")
        for tag in ("color_range", "color_space"):
            if seg.info[tag] != base[tag]:
                warnings.append(f"segment {seg.index} {tag} is {seg.info[tag]} but segment 0 is "
                                f"{base[tag]}: a constant level offset here is a conversion "
                                "mismatch, not the model")
    for seg in segs:
        await _decode(stimma, seg, work, (base["width"], base["height"]), fps, need_audio)
    if not any(s.lock for s in segs):
        segs[0].lock = True
    return segs, out_fps, warnings


def _seams(segs, loop):
    pairs = [(segs[i], segs[i + 1]) for i in range(len(segs) - 1)]
    if loop:
        pairs.append((segs[-1], segs[0]))
    return pairs


def _trim(segs, loop):
    """Drop head pops on adjustable segments and frames that repeat across a seam."""
    for seg in segs:
        f = seg.frames
        if seg.lock or len(f) < 10:
            continue
        typical = _typical_step(f, 1)
        d = _content_diff(f[0], f[1])
        if d > max(3 * typical, 0.05):
            seg.trim_head += 1
            seg.actions.append(f"dropped head frame that pops (step {d:.3f} vs typical {typical:.3f})")
    for prev, nxt in _seams(segs, loop):
        if nxt.cut or nxt.overlap:
            continue
        # Drop from whichever side is adjustable; footage is never trimmed.
        for _ in range(2):
            pf, nf = prev.frames, nxt.frames
            if len(pf) < 4 or len(nf) < 4:
                break
            d = _content_diff(pf[-1], nf[0])
            typical = _typical_step(nf, 0) if not nxt.lock else _typical_step(pf, max(0, len(pf) - 9))
            if d >= max(0.35 * typical, 0.02):
                break
            if not nxt.lock:
                nxt.trim_head += 1
                nxt.actions.append(f"dropped head frame repeating segment {prev.index}")
            elif not prev.lock:
                prev.trim_tail += 1
                prev.actions.append(f"dropped tail frame repeating segment {nxt.index}")
            else:
                break


def _seam_windows(prev, nxt):
    """Matching frame stacks either side of a seam (the shared frames when overlapping)."""
    k = nxt.overlap or _REF_FRAMES
    return prev.frames[-k:], nxt.frames[:k]


def _solve(segs, loop, match):
    """Fit head and tail corrections for every adjustable segment."""
    fits = {}
    if not match:
        return fits
    order = list(range(len(segs)))
    if loop:
        first_locked = next(i for i, s in enumerate(segs) if s.lock)
        order = order[first_locked:] + order[:first_locked]
    n = len(segs)
    for pos, i in enumerate(order):
        seg = segs[i]
        if seg.lock:
            continue
        has_prev = loop or i > 0
        has_next = loop or i < n - 1
        prev = segs[(i - 1) % n] if has_prev else None
        nxt = segs[(i + 1) % n] if has_next else None
        head = tail = None
        if prev is not None and not seg.cut:
            ref, src = _seam_windows(prev, seg)
            ref_q = _apply_q(_quantiles(ref), prev.tail_t)
            src_q = _quantiles(src)
            t = _fit(ref_q, src_q)
            fits[(prev.index, seg.index)] = _describe_fit(t, ref_q, src_q)
            if _plausible(t):
                head = t
            else:
                seg.actions.append(f"left the seam from segment {prev.index} uncorrected: the two "
                                   "sides differ too much to be the same shot (mark it cut=True)")
        if nxt is not None and nxt.lock and not nxt.cut:
            own, target = _seam_windows(seg, nxt)
            own_q, target_q = _quantiles(own), _quantiles(target)
            t = _fit(target_q, own_q)
            fits[(seg.index, nxt.index)] = _describe_fit(t, target_q, own_q)
            if _plausible(t):
                tail = t
            else:
                seg.actions.append(f"left the seam into segment {nxt.index} uncorrected: the two "
                                   "sides differ too much to be the same shot (mark it cut=True)")
        if head is None and tail is None:
            continue
        seg.head_t = head if head is not None else tail
        seg.tail_t = tail if tail is not None else seg.head_t
        seg.actions.append("corrected exposure/colour " + ("ramping between both seams"
                           if head is not None and tail is not None else "statically"))
    return fits


# ---------------------------------------------------------------- output

def _plan(segs, loop=False):
    """Output frame list: (segment, local index) pairs, or blends for overlaps.

    In a loop, an overlap on the first segment means the last segment's tail
    repeats the first segment's head: the output starts after those frames and
    crossfades into them at the end, so the wrap is a blend too.
    """
    plan = []
    for seg in segs:
        n = len(seg.frames)
        k = min(seg.overlap, n, len(plan)) if plan and not seg.cut else 0
        for j in range(k):
            w = _smoothstep((j + 1) / (k + 1))
            plan[len(plan) - k + j] = ("blend", plan[len(plan) - k + j], (seg, j), w)
        plan.extend((seg, j) for j in range(k, n))
    first = segs[0]
    k = min(first.overlap, len(first.frames)) if loop and not first.cut else 0
    if k:
        head = [i for i, e in enumerate(plan) if e == (first, i)][:k]
        k = min(len(head), len(plan) - k)
        plan = plan[k:]
        for j in range(k):
            w = _smoothstep((j + 1) / (k + 1))
            plan[len(plan) - k + j] = ("blend", plan[len(plan) - k + j], (first, j), w)
    return plan


def _render(entry):
    if entry[0] == "blend":
        _, a, b, w = entry
        return _render(a) * (1 - w) + _render(b) * w
    seg, j = entry
    f = seg.frames[j].astype(np.float32)
    t = seg.transform_at(j, len(seg.frames))
    return f * t[:, 0] + t[:, 1]


def _write_frames(plan, path):
    with open(path, "wb") as fh:
        for entry in plan:
            fh.write(np.clip(np.rint(_render(entry)), 0, 255).astype(np.uint8).tobytes())


def _seam_positions(plan):
    """Segment index -> its first output frame (the start of any crossfade into it)."""
    firsts = {}
    for idx, entry in enumerate(plan):
        seg = entry[2][0] if entry[0] == "blend" else entry[0]
        firsts.setdefault(seg.index, idx)
    return firsts


def _measure_output(frames, at, wrap=False):
    k = _REF_FRAMES
    if wrap:
        before, after = frames[-k:], frames[:k]
    else:
        before, after = frames[max(0, at - k):at], frames[at:at + k]
    if len(before) == 0 or len(after) == 0:
        return None
    qb, qa = _quantiles(before), _quantiles(after)
    delta = (qa - qb)[:, len(_Q) // 2]
    jump = _content_diff(before[-1], after[0])
    local = [_content_diff(before[i], before[i + 1]) for i in range(len(before) - 1)]
    local += [_content_diff(after[i], after[i + 1]) for i in range(len(after) - 1)]
    typical = float(np.median(local)) if local else 0.0
    return {
        "median_delta_rgb": [round(float(d), 2) for d in delta],
        "motion_step_ratio": round(jump / max(typical, 0.01), 2),
    }


# ---------------------------------------------------------------- audio

def _rms_db(x):
    if x is None or len(x) == 0:
        return None
    rms = float(np.sqrt(np.mean(np.square(x))))
    return 20 * math.log10(rms) if rms > 1e-5 else None


def _segment_audio(seg, fps):
    per_frame = SAMPLE_RATE / fps
    start = round(seg.trim_head * per_frame)
    n = round(len(seg.frames) * per_frame)
    if seg.audio is None:
        return np.zeros((n, 2), np.float32), False
    a = seg.audio[start:start + n]
    if len(a) < n:
        a = np.concatenate([a, np.zeros((n - len(a), 2), np.float32)])
    return a.astype(np.float32), True


def _match_loudness(segs, tracks, loop, window_s=2.0):
    """Per-segment gain ramps toward locked neighbours' loudness, clamped to +-6 dB."""
    win = int(window_s * SAMPLE_RATE)
    gains = {}
    n = len(segs)
    for i, seg in enumerate(segs):
        audio, real = tracks[i]
        if seg.lock or not real:
            continue
        head_db = tail_db = None
        if (loop or i > 0) and not seg.cut:
            p_audio, p_real = tracks[(i - 1) % n]
            a, b = _rms_db(p_audio[-win:]) if p_real else None, _rms_db(audio[:win])
            if a is not None and b is not None:
                head_db = float(np.clip(a - b, -6, 6))
        if loop or i < n - 1:
            nxt = segs[(i + 1) % n]
            n_audio, n_real = tracks[(i + 1) % n]
            if nxt.lock and n_real and not nxt.cut:
                a, b = _rms_db(n_audio[:win]), _rms_db(audio[-win:])
                if a is not None and b is not None:
                    tail_db = float(np.clip(a - b, -6, 6))
        if head_db is None and tail_db is None:
            continue
        h = head_db if head_db is not None else tail_db
        t = tail_db if tail_db is not None else h
        ramp = _smoothstep(np.linspace(0, 1, len(audio), dtype=np.float32))
        db = h * (1 - ramp) + t * ramp
        tracks[i] = (audio * (10 ** (db / 20))[:, None], real)
        gains[seg.index] = {"head_db": round(h, 2), "tail_db": round(t, 2)}
    return gains


def _xfade(a, b):
    w = np.linspace(0, 1, len(a), dtype=np.float32)[:, None]
    return a * np.cos(w * np.pi / 2) + b * np.sin(w * np.pi / 2)


def _assemble_audio(segs, tracks, fps, loop=False):
    """Join tracks on the video's timeline: crossfade overlaps, de-click hard joins."""
    per_frame = SAMPLE_RATE / fps
    out = np.zeros((0, 2), np.float32)
    for seg, (audio, _) in zip(segs, tracks):
        audio = audio.copy()
        k = round(min(seg.overlap, len(seg.frames)) * per_frame) if len(out) and not seg.cut else 0
        k = min(k, len(out), len(audio))
        if k:
            out[-k:] = _xfade(out[-k:], audio[:k])
            audio = audio[k:]
        elif len(out):
            f = min(_FADE_SAMPLES, len(out), len(audio))
            ramp = np.linspace(0, 1, f, dtype=np.float32)[:, None]
            out[-f:] *= ramp[::-1]
            audio[:f] *= ramp
        out = np.concatenate([out, audio])
    first = segs[0]
    k = round(min(first.overlap, len(first.frames)) * per_frame) if loop and not first.cut else 0
    k = min(k, len(out) // 2)
    if k:
        out = out[k:].copy()
        out[-k:] = _xfade(out[-k:], tracks[0][0][:k])
    elif loop:
        f = min(_FADE_SAMPLES, len(out) // 2)
        ramp = np.linspace(0, 1, f, dtype=np.float32)[:, None]
        out[:f] *= ramp
        out[-f:] *= ramp[::-1]
    return out


def seamless_loop(audio, n, xfade_s=0.5):
    """``n`` samples of ``audio`` that loop without a seam.

    Repeats the audio with equal-power crossfades until it covers ``n`` plus the
    crossfade, then folds the overshoot back over the start. Use it to give a
    silent bridge the loop's own ambience (``join(..., audio="loop")``).
    """
    x = int(xfade_s * SAMPLE_RATE)
    x = max(1, min(x, len(audio) // 3, n // 3))
    w = np.linspace(0, 1, x, dtype=np.float32)[:, None]
    fade_out, fade_in = np.cos(w * np.pi / 2), np.sin(w * np.pi / 2)
    buf = audio.astype(np.float32)
    while len(buf) < n + x:
        nxt = audio.astype(np.float32).copy()
        buf = np.concatenate([buf[:-x], buf[-x:] * fade_out + nxt[:x] * fade_in, nxt[x:]])
    out = buf[:n].copy()
    out[:x] = buf[n:n + x] * fade_out + out[:x] * fade_in
    return out


# ---------------------------------------------------------------- entry points

async def _encode(stimma, frames_path, audio, size, fps, out, crf):
    w, h = size
    args = ["-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
            "-framerate", f"{fps}", "-i", str(frames_path)]
    if audio is not None:
        pcm = Path(frames_path).with_suffix(".out.f32")
        np.clip(audio, -1, 1).astype(np.float32).tofile(pcm)
        args += ["-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", "2", "-i", str(pcm)]
    args += ["-map", "0:v"] + (["-map", "1:a", "-c:a", "aac", "-b:a", "256k", "-shortest"]
                               if audio is not None else [])
    args += ["-vf", "scale=out_color_matrix=bt709:out_range=tv", "-pix_fmt", "yuv420p",
             "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
             "-color_range", "tv", "-movflags", "+faststart"]
    try:
        await stimma.ffmpeg(*args, "-c:v", "libx264", "-crf", str(crf), "-preset", "slow", str(out),
                            timeout=3600)
    except RuntimeError:
        await stimma.ffmpeg(*args, "-q:v", "2", str(out), timeout=3600)


async def join(stimma, segments, out=None, *, loop=False, match=True, audio="auto",
               fps=None, crf=14, keep_work=False):
    """Join segments into ``out`` with every seam handled; returns a report.

    ``segments`` is a list of paths or dicts with:
      path       workspace path of the clip
      lock       True for footage that must not change (source clips). Unlocked
                 segments are adjusted to fit locked ones; if nothing is locked
                 the first segment is.
      trim_head / trim_tail   frames to drop, on top of automatic de-duplication
      overlap    frames at this segment's head that show the same moments as the
                 previous segment's tail (a pinned clip); they are crossfaded. In a
                 loop, overlap on the first segment means the last segment's tail
                 repeats its head (a clip pinned at the bridge's end)
      cut        True when the join into this segment is a deliberate cut:
                 nothing is matched, trimmed or blended there

    ``loop=True`` treats the last segment as joining back to the first.
    ``audio``: "auto" joins each segment's own audio (silence where it has none);
    "loop" replaces the soundtrack with a seamless loop of the locked
    segments' audio, for silent bridges; "none" drops audio.
    ``out=None`` measures and reports without writing (same as ``check``).
    """
    if audio not in ("auto", "loop", "none"):
        raise ValueError('audio must be "auto", "loop" or "none"')
    work = Path(".seamkit") / uuid.uuid4().hex[:8]
    work.mkdir(parents=True, exist_ok=True)
    try:
        segs, out_fps, warnings = await _load(stimma, segments, work, fps, audio != "none")
        before = {}
        for prev, nxt in _seams(segs, loop):
            if len(prev.frames) and len(nxt.frames):
                before[(prev.index, nxt.index)] = _measure_output(
                    np.concatenate([prev.frames[-_REF_FRAMES:], nxt.frames[:_REF_FRAMES]]),
                    min(_REF_FRAMES, len(prev.frames)))
        _trim(segs, loop)
        fits = _solve(segs, loop, match)
        plan = _plan(segs, loop)
        report = {"frames": len(plan), "fps": out_fps, "warnings": warnings, "seams": [],
                  "segments": [{"index": s.index, "path": s.path, "locked": bool(s.lock),
                                "frames_used": len(s.frames), "trim_head": s.trim_head,
                                "trim_tail": s.trim_tail, "actions": s.actions} for s in segs]}
        if out is None:
            for key, b in before.items():
                report["seams"].append({"between": list(key), "before": b, "fit": fits.get(key)})
            return report

        base = segs[0].info
        size = (base["width"], base["height"])
        frames_path = work / "out.rgb"
        _write_frames(plan, frames_path)
        frames = np.memmap(frames_path, dtype=np.uint8, mode="r", shape=(len(plan), size[1], size[0], 3))

        positions = _seam_positions(plan)
        keys = list(before)
        for i, key in enumerate(keys):
            wrap = loop and i == len(keys) - 1
            at = positions.get(key[1])
            after = _measure_output(frames, 0 if wrap else at, wrap=wrap) if wrap or at is not None else None
            report["seams"].append({"between": list(key), "before": before[key],
                                    "fit": fits.get(key), "after": after})

        track = None
        if audio == "auto" and any(s.audio is not None for s in segs):
            tracks = [_segment_audio(s, out_fps) for s in segs]
            report["audio_gains_db"] = _match_loudness(segs, tracks, loop)
            track = _assemble_audio(segs, tracks, out_fps, loop)
        elif audio == "loop":
            sources = [s.audio for s in segs if s.lock and s.audio is not None]
            if not sources:
                raise ValueError('audio="loop" needs a locked segment with audio')
            n = round(len(plan) * SAMPLE_RATE / out_fps)
            track = seamless_loop(np.concatenate(sources), n)
        del frames
        await _encode(stimma, frames_path, track, size, out_fps, out, crf)
        report["out"] = str(out)
        return report
    finally:
        for seg in locals().get("segs", []):
            seg.raw = None
        if not keep_work:
            shutil.rmtree(work, ignore_errors=True)


async def check(stimma, segments, *, loop=False):
    """Measure seams without writing. A single path with loop=True checks a loop's wrap."""
    if isinstance(segments, (str, Path)):
        segments = [segments]
    return await join(stimma, segments, None, loop=loop, audio="none")


async def motion(stimma, path, *, threshold=0.6):
    """How much the picture moves over time, to find a slow start or a slow end.

    Image-to-video often opens with a lull while motion builds from the still,
    and a clip pinned to a last frame can coast into it. Returns per-second
    motion (1.0 = the clip's steady level), ``settles_at``: the first time
    motion reaches ``threshold`` of steady, and ``fades_at``: the last time it
    is still there. Loop or join inside that window to leave both lulls out.
    """
    info = await probe(stimma, path)
    fps = info["fps"]
    w = 160
    h = max(2, round(info["height"] * w / info["width"] / 2) * 2)
    work = Path(".seamkit") / uuid.uuid4().hex[:8]
    work.mkdir(parents=True, exist_ok=True)
    try:
        raw = work / "gray.raw"
        await stimma.ffmpeg("-v", "error", "-y", "-i", str(path), "-map", "0:v:0",
                            "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", str(raw), timeout=1800)
        frames = np.fromfile(raw, dtype=np.uint8).reshape(-1, h, w).astype(np.float32)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if len(frames) < 4:
        raise ValueError(f"{path} is too short to measure")
    z = (frames - frames.mean(axis=(1, 2), keepdims=True)) / (frames.std(axis=(1, 2), keepdims=True) + 1e-6)
    step = np.abs(np.diff(z, axis=0)).mean(axis=(1, 2))
    win = max(1, round(fps / 4))
    smooth = np.convolve(step, np.ones(win) / win, mode="same")
    steady = float(np.median(smooth)) or 1e-6
    level = smooth / steady
    moving = np.nonzero(level >= threshold)[0]
    settles = (moving[0] + 1) / fps if len(moving) else 0.0
    fades = (moving[-1] + 1) / fps if len(moving) else len(frames) / fps
    per_second = [round(float(level[i:i + round(fps)].mean()), 2) for i in range(0, len(level), round(fps))]
    return {
        "duration": round(len(frames) / fps, 3),
        "fps": fps,
        "per_second": per_second,
        "settles_at": round(settles if settles >= 0.25 else 0.0, 2),
        "fades_at": round(fades if len(frames) / fps - fades >= 0.25 else len(frames) / fps, 2),
    }
