"""Join video segments without visible seams, and measure the seams you have.

Generated segments rarely line up with the footage around them. Pins fix
geometry but not photometry: each run lands at its own exposure, its first
frame often repeats the frame it was pinned to, and an image-to-video head can
carry the reference image's texture for a frame. ``join`` fixes the mechanical
part of that at every seam:

* drops a pinned frame that repeats its neighbor, and a head frame that pops;
* fits a per-channel gain and offset at each end of every adjustable segment
  and ramps between them, so a bridge lands exactly on the footage at both
  ends;
* crossfades frames two segments share (``overlap``);
* matches audio loudness at the seams and removes clicks;
* reports every seam before and after, including motion jumps it cannot fix,
  and flags a seam whose two sides show different moments (it needs a bridge).

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
    """Size, fps, frame count, color tags and audio presence of a video file."""
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
    """Standardized luma: invariant to exposure, so it compares content only."""
    f = _small(frame)
    y = 0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2]
    return (y - y.mean()) / (y.std() + 1e-6)


def _content_diff(a, b):
    return float(np.abs(_luma_std(a) - _luma_std(b)).mean())


def _layout(frame, width=64):
    """Coarse standardized luma (about ``width`` blocks across): where things are
    in the frame, without texture, noise or exposure. Stable across resolutions."""
    f = np.asarray(frame, dtype=np.float32)
    b = max(1, f.shape[1] // width)
    h, w = f.shape[0] // b, f.shape[1] // b
    f = f[:h * b, :w * b].reshape(h, b, w, b, 3).mean(axis=(1, 3))
    y = 0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2]
    return (y - y.mean()) / (y.std() + 1e-6)


def _layout_diff(a, b):
    return float(np.abs(_layout(a) - _layout(b)).mean())


# A seam whose two sides differ this much in layout, and by this many times a
# normal frame step either side, shows two different moments. Calibrated on
# still-to-still joins (jump <= 0.06, ratio <= 5) against two clips made from one
# still and joined directly (jump 0.16, ratio 11-14).
_MOMENT_JUMP = 0.10
_MOMENT_RATIO = 6.0


def _moment(prev_frames, next_frames, overlap=0, count=8):
    """Do the two sides of a seam show the same instant?

    Compares the last frame before the seam with the first after it (for an
    overlap, the first pair of frames meant to be shared), on the raw frames,
    before any pacing or blending, against the frame-to-frame change either side.
    """
    if len(prev_frames) < 2 or len(next_frames) < 2:
        return None
    a = prev_frames[-overlap] if 0 < overlap <= len(prev_frames) else prev_frames[-1]
    pa = prev_frames[max(0, len(prev_frames) - count):]
    nb = next_frames[:count]
    jump = _layout_diff(a, next_frames[0])
    steps = [_layout_diff(pa[i], pa[i + 1]) for i in range(len(pa) - 1)]
    steps += [_layout_diff(nb[i], nb[i + 1]) for i in range(len(nb) - 1)]
    ratio = jump / max(float(np.median(steps)), 0.005)
    return {"jump": round(jump, 3), "ratio": round(ratio, 1),
            "same": not (jump >= _MOMENT_JUMP and ratio >= _MOMENT_RATIO)}


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

class _Frames:
    """A segment's frames with some left out or replaced; indexes like an array."""

    def __init__(self, raw, idx, fix):
        self.raw, self.idx, self.fix = raw, idx, fix

    def __len__(self):
        return len(self.idx)

    def _one(self, i):
        return self.fix[i] if i in self.fix else self.raw[i]

    def __getitem__(self, k):
        if isinstance(k, slice):
            sel = self.idx[k]
            if not sel:
                return np.zeros((0,) + self.raw.shape[1:], np.uint8)
            return np.stack([self._one(i) for i in sel])
        return self._one(self.idx[k])


class _Segment:
    def __init__(self, spec, index):
        spec = {"path": spec} if isinstance(spec, (str, Path)) else dict(spec)
        unknown = set(spec) - {"path", "lock", "trim_head", "trim_tail", "overlap", "cut"}
        if unknown:
            raise ValueError(f"segment {index}: unknown keys {sorted(unknown)}")
        self.index = index
        self.path = str(spec["path"])
        self.lock = spec.get("lock")
        self.footage = bool(self.lock)  # locked by the caller: never retimed or repaired
        self.trim_head = int(spec.get("trim_head", 0))
        self.trim_tail = int(spec.get("trim_tail", 0))
        self.overlap = int(spec.get("overlap", 0))
        self.cut = bool(spec.get("cut", False))
        self.skip = set()       # raw frames left out to keep the pace across a seam
        self.skip_head = self.skip_tail = 0
        self.fix = {}           # raw frame -> replacement (repaired repeats)
        self.blend = 0          # frames crossfaded with the previous segment at a hard seam
        self.audio_pre = self.audio_post = None
        self.actions = []
        self.head_t = self.tail_t = np.array([[1.0, 0.0]] * 3)

    @property
    def frames(self):
        end = len(self.raw) - self.trim_tail
        if not self.skip and not self.fix:
            return self.raw[self.trim_head:end]
        return _Frames(self.raw, [i for i in range(self.trim_head, end) if i not in self.skip], self.fix)

    def raw_index(self, j):
        """Raw frame index of output position j (after trims and skips)."""
        end = len(self.raw) - self.trim_tail
        return [i for i in range(self.trim_head, end) if i not in self.skip][j]

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
        # An overlapping head is crossfaded, which hides a pop; dropping a frame
        # there would misalign the shared frames by one.
        if seg.lock or seg.overlap or len(f) < 10:
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


def _repeats(frames):
    """Frames that nearly repeat the one before while the next step makes up for it.

    Some generators emit these in a regular cadence: the picture holds for a
    frame, then jumps two frames' worth, a judder you see as uneven motion.
    Returns local indices of the repeated frames.
    """
    n = len(frames)
    if n < 8:
        return []
    steps = np.array([_content_diff(frames[i], frames[i + 1]) for i in range(n - 1)])
    floor = 0.3 * float(np.median(steps))
    out = []
    for i in range(1, n - 2):
        local = float(np.median(steps[max(0, i - 6):i + 7]))
        if local > floor and steps[i] < 0.4 * local and steps[i + 1] > 1.4 * local:
            out.append(i + 1)
    return out


async def _repair_repeats(stimma, segs, work):
    """Replace repeated frames in segments the caller did not lock with interpolated ones."""
    for seg in segs:
        if seg.footage:
            continue
        f = seg.frames
        found = [j for j in _repeats(f) if 0 < j < len(f) - 1]
        if not found:
            continue
        h, w = f[0].shape[:2]
        pairs = work / f"{seg.index}.pairs.rgb"
        mids = work / f"{seg.index}.mids.rgb"
        with open(pairs, "wb") as fh:
            for j in found:
                fh.write(np.ascontiguousarray(f[j - 1]).tobytes())
                fh.write(np.ascontiguousarray(f[j + 1]).tobytes())
            fh.write(np.ascontiguousarray(f[found[-1] + 1]).tobytes())  # the filter holds back its last frames
            fh.write(np.ascontiguousarray(f[found[-1] + 1]).tobytes())
        # Doubling the rate puts a motion-compensated middle frame after every
        # input frame; the one after each pair's first frame is the repair.
        await stimma.ffmpeg("-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                            "-framerate", "24", "-i", str(pairs),
                            "-vf", "minterpolate=fps=48:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1:scd=none",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", str(mids), timeout=1800)
        out = np.fromfile(mids, dtype=np.uint8)
        out = out[:len(out) // (w * h * 3) * (w * h * 3)].reshape(-1, h, w, 3)
        base = seg.trim_head
        for n, j in enumerate(found):
            if 4 * n + 1 < len(out):
                seg.fix[base + j] = out[4 * n + 1].copy()
        seg.actions.append(f"replaced {len(found)} repeated frame(s) with interpolated ones")


def _pace_keep(steps, target):
    """Positions to keep along a run of frames so motion advances ~target per frame.

    The first and last positions are always kept; nothing is ever repeated.
    """
    arc = np.concatenate([[0.0], np.cumsum(steps)])
    m = int(np.clip(round(arc[-1] / max(target, 1e-6)), 1, len(steps)))
    keep = []
    for goal in np.linspace(0.0, arc[-1], m + 1):
        i = int(np.argmin(np.abs(arc - goal)))
        if not keep or i > keep[-1]:
            keep.append(i)
    if keep[-1] != len(arc) - 1:
        keep.append(len(arc) - 1)
    return keep


def _match_pace(segs, loop, fps, blend):
    """Keep the motion's pace through hard seams.

    A generated segment pinned to a still at its start or end slows into it:
    the last and first half second barely move, so a join there reads as slow,
    pause, jump. Where the frames next to a seam move clearly slower than the
    footage around it, leave out slow frames from the side(s) not locked so
    the motion advances at the surrounding pace, then blend ``blend`` frames
    across the seam. Returns {(prev, next): frames left out}.
    """
    span = max(4, round(fps / 2))
    done = {}
    for prev, nxt in _seams(segs, loop):
        if nxt.cut or nxt.overlap or (prev.footage and nxt.footage):
            continue
        pf, nf = prev.frames, nxt.frames
        if len(pf) < 3 * span or len(nf) < 3 * span:
            continue
        lp = 0 if prev.footage else span
        ln = 0 if nxt.footage else span
        seq = list(pf[len(pf) - lp - 1:]) + list(nf[:ln + 1])
        steps = np.array([_content_diff(seq[i], seq[i + 1]) for i in range(len(seq) - 1)])
        around = [_content_diff(pf[i], pf[i + 1]) for i in range(len(pf) - 3 * span, len(pf) - span - 1)]
        around += [_content_diff(nf[i], nf[i + 1]) for i in range(span, 3 * span - 1)]
        pace = float(np.median(around))
        dropped = 0
        if pace > 0 and float(np.mean(steps)) < 0.75 * pace:
            keep = set(_pace_keep(steps, pace))
            p_drop = [k for k in range(1, lp + 1) if k not in keep]
            n_drop = [k for k in range(lp + 1, lp + ln + 1) if k not in keep]
            p_raw = [prev.raw_index(len(pf) - lp - 1 + k) for k in p_drop]
            n_raw = [nxt.raw_index(k - lp - 1) for k in n_drop]
            prev.skip.update(p_raw)
            nxt.skip.update(n_raw)
            prev.skip_tail += len(p_raw)
            nxt.skip_head += len(n_raw)
            dropped = len(p_raw) + len(n_raw)
            if p_raw:
                prev.actions.append(f"left out {len(p_raw)} slow frame(s) before the seam into segment {nxt.index}")
            if n_raw:
                nxt.actions.append(f"left out {len(n_raw)} slow frame(s) after the seam from segment {prev.index}")
        if blend and not prev.footage and not nxt.footage:
            nxt.blend = blend
        done[(prev.index, nxt.index)] = dropped
    return done


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
        seg.actions.append("corrected exposure/color " + ("ramping between both seams"
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
        k = min(seg.overlap or seg.blend, n, len(plan)) if plan and not seg.cut else 0
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


def _segment_audio(seg, fps, ext=0):
    """The segment's sound for its output frames, plus up to ``ext`` samples of the
    sound just outside them (frames trimmed or left out) for crossfades."""
    per_frame = SAMPLE_RATE / fps
    start = round((seg.trim_head + seg.skip_head) * per_frame)
    n = round(len(seg.frames) * per_frame)
    if seg.audio is None:
        seg.audio_pre = seg.audio_post = np.zeros((0, 2), np.float32)
        return np.zeros((n, 2), np.float32), False
    a = seg.audio[start:start + n]
    if len(a) < n:
        a = np.concatenate([a, np.zeros((n - len(a), 2), np.float32)])
    seg.audio_pre = seg.audio[max(0, start - ext):start].astype(np.float32)
    seg.audio_post = seg.audio[start + n:start + n + ext].astype(np.float32)
    return a.astype(np.float32), True


def _match_loudness(segs, tracks, loop, window_s=2.0):
    """Per-segment gain ramps toward locked neighbors' loudness, clamped to +-6 dB."""
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
        if seg.audio_pre is not None:
            seg.audio_pre = seg.audio_pre * 10 ** (h / 20)
            seg.audio_post = seg.audio_post * 10 ** (t / 20)
        gains[seg.index] = {"head_db": round(h, 2), "tail_db": round(t, 2)}
    return gains


def _xfade(a, b):
    w = np.linspace(0, 1, len(a), dtype=np.float32)[:, None]
    return a * np.cos(w * np.pi / 2) + b * np.sin(w * np.pi / 2)


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def _assemble_audio(segs, tracks, fps, loop=False, xfade=0, search=0):
    """Join tracks on the video's timeline: crossfade overlaps, de-click hard joins.

    At a seam the sound switches from one segment to the next at the quietest
    moment within ``search`` samples of the seam (or of the middle of the
    frames the two share), with an ``xfade`` crossfade there. Each side keeps its own timing (sound just outside a
    segment's frames covers the difference), so speech stays in sync and is
    never cut mid-word or doubled when a quieter moment is near.
    """
    per_frame = SAMPLE_RATE / fps
    out = np.zeros((0, 2), np.float32)
    dangle = np.zeros((0, 2), np.float32)  # previous segment's sound past its last frame
    win = SAMPLE_RATE // 50
    for seg, (audio, _) in zip(segs, tracks):
        audio = audio.copy()
        joined = len(out) and not seg.cut
        pre = seg.audio_pre if seg.audio_pre is not None else np.zeros((0, 2), np.float32)
        if joined and (xfade or seg.blend or seg.overlap):
            shared = seg.overlap or seg.blend
            kb = min(round(min(shared, len(seg.frames)) * per_frame), len(out), len(audio))
            n_start = len(out) - kb                     # timeline sample where this segment's frames begin
            prev = np.concatenate([out, dangle])        # previous sound, valid up to len(prev)
            nxt = np.concatenate([pre, audio])          # this sound, starting at n_start - len(pre)
            off = n_start - len(pre)
            h = max(xfade // 2, kb // 2, 1)
            center = n_start + kb // 2
            lo = max(center - search, off + h, h)
            hi = min(center + search, len(prev) - h, off + len(nxt) - h)
            ts = center
            if hi >= lo:
                best = None
                for t in range(lo, hi + 1, max(1, SAMPLE_RATE // 200)):
                    loud = _rms(prev[t - win:t + win]) + _rms(nxt[t - off - win:t - off + win])
                    score = loud * (1 + 0.5 * abs(t - center) / max(search, 1))
                    if best is None or score < best:
                        best, ts = score, t
            h = max(1, min(h, ts - off, len(prev) - ts, ts))
            out = np.concatenate([prev[:ts - h], _xfade(prev[ts - h:ts + h], nxt[ts - h - off:ts + h - off]),
                                  nxt[ts + h - off:]])
            dangle = seg.audio_post if seg.audio_post is not None else np.zeros((0, 2), np.float32)
            continue
        k = round(min(seg.overlap, len(seg.frames)) * per_frame) if len(out) and not seg.cut else 0
        k = min(k, len(out), len(audio))
        dangle = seg.audio_post if seg.audio_post is not None else np.zeros((0, 2), np.float32)
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


async def _lay_track(stimma, path, work, frames, fps):
    """The track's sound for ``frames`` output frames from frame 0, and a note on any mismatch."""
    pcm = work / "track.f32"
    await stimma.ffmpeg("-v", "error", "-y", "-i", str(path), "-map", "0:a:0", "-ac", "2",
                        "-ar", str(SAMPLE_RATE), "-f", "f32le", str(pcm))
    sound = np.fromfile(pcm, dtype=np.float32).reshape(-1, 2)
    n = round(frames * SAMPLE_RATE / fps)
    picture_s, track_s = frames / fps, len(sound) / SAMPLE_RATE
    note = None
    if track_s > picture_s + 1 / fps:
        note = (f"the sound track runs {track_s - picture_s:.2f} s past the picture; its end was left out")
    elif track_s < picture_s - 1 / fps:
        note = f"the sound track ends {picture_s - track_s:.2f} s before the picture; the rest is silent"
    if len(sound) < n:
        sound = np.concatenate([sound, np.zeros((n - len(sound), 2), np.float32)])
    f = min(_FADE_SAMPLES, n)
    sound = sound[:n].copy()
    if f and track_s > picture_s + 1 / fps:
        sound[-f:] *= np.linspace(1, 0, f, dtype=np.float32)[:, None]
    return sound, {"track": str(path), "picture_s": round(picture_s, 3), "track_s": round(track_s, 3),
                   "note": note}


async def join(stimma, segments, out=None, *, loop=False, match=True, audio="auto",
               fps=None, crf=14, keep_work=False, preserve_state=False, pace=True,
               repair=True, audio_xfade=0.06, audio_search=0.25):
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
    segments' audio, for silent bridges; "none" drops audio. A workspace path
    instead is the take's own sound track, for segments whose sound was pinned
    to consecutive slices of it: the track is laid back from the first output
    frame, and every frame keeps its place on the track's timeline (no frames
    are left out or dropped automatically; explicit trims, overlaps and repairs
    still apply), so the picture stays in sync with it.
    ``out=None`` measures and reports without writing (same as ``check``).

    ``pace=True`` keeps motion at the surrounding pace through hard seams: where
    a segment slows into or out of a seam (a pinned still at its end or start
    does this), slow frames on a side you did not lock are left out and two frames
    are blended across the seam. ``repair=True`` replaces frames an adjustable
    segment nearly repeats (a judder some generators produce) with interpolated
    ones. At hard seams the sound switches at the quietest moment within
    ``audio_search`` seconds, crossfaded over ``audio_xfade`` seconds, each side
    keeping its own sync.
    """
    if preserve_state:
        if out is None or loop or fps is not None or audio != "auto":
            raise ValueError("preserve_state needs an output, matching native frame rates, original audio and no loop")
        report = await stimma.join_video(segments, out=str(out))
        measured = await check(stimma, [{k: segment[k] for k in ("path", "trim_head", "trim_tail", "lock")}
                                         for segment in report["segments"]])
        report["seams"] = measured["seams"]
        report["warnings"] = measured["warnings"]
        return report
    track_path = None
    if audio not in ("auto", "loop", "none"):
        track_path = Path(str(audio))
        if not track_path.is_file():
            raise ValueError(f'audio must be "auto", "loop", "none" or the path of a sound track; {audio!r} is none of these')
        if loop:
            raise ValueError("a sound track can't be joined as a loop")
    work = Path(".seamkit") / uuid.uuid4().hex[:8]
    work.mkdir(parents=True, exist_ok=True)
    try:
        segs, out_fps, warnings = await _load(stimma, segments, work, fps, audio in ("auto", "loop"))
        before, moments = {}, {}
        for prev, nxt in _seams(segs, loop):
            if len(prev.frames) and len(nxt.frames):
                key = (prev.index, nxt.index)
                before[key] = _measure_output(
                    np.concatenate([prev.frames[-_REF_FRAMES:], nxt.frames[:_REF_FRAMES]]),
                    min(_REF_FRAMES, len(prev.frames)))
                # Judged on the raw sides: pacing and blending later make any jump
                # look smooth in the numbers, not to the eye.
                moment = None if nxt.cut else _moment(prev.frames, nxt.frames, nxt.overlap)
                if moment is not None:
                    moments[key] = moment
                    if not moment["same"]:
                        warnings.append(
                            f"seam {prev.index}->{nxt.index}: the two sides show different moments "
                            f"(the picture jumps {moment['ratio']}x a normal frame step). Bridge it: "
                            f"generate a clip from segment {prev.index}'s last frame to segment "
                            f"{nxt.index}'s first frame and join through it, or mark a wanted cut cut=True.")
        # With a sound track, each frame's place on the timeline is its place on the
        # track: leaving frames out would slip the picture against the sound.
        if track_path is None:
            _trim(segs, loop)
        if repair and out is not None:
            await _repair_repeats(stimma, segs, work)
        paced = _match_pace(segs, loop, out_fps, 2) if pace and track_path is None else {}
        fits = _solve(segs, loop, match)
        plan = _plan(segs, loop)
        report = {"frames": len(plan), "fps": out_fps, "warnings": warnings, "seams": [],
                  "segments": [{"index": s.index, "path": s.path, "locked": bool(s.lock),
                                "frames_used": len(s.frames), "trim_head": s.trim_head,
                                "trim_tail": s.trim_tail, "actions": s.actions} for s in segs]}
        if out is None:
            for key, b in before.items():
                report["seams"].append({"between": list(key), "before": b, "moment": moments.get(key),
                                        "fit": fits.get(key)})
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
                                    "moment": moments.get(key), "fit": fits.get(key), "after": after, "at_frame": 0 if wrap else at,
                                    "slow_frames_left_out": paced.get(key, 0)})

        track = None
        if track_path is not None:
            track, report["sound"] = await _lay_track(stimma, track_path, work, len(plan), out_fps)
            if report["sound"]["note"]:
                warnings.append(report["sound"]["note"])
        elif audio == "auto" and any(s.audio is not None for s in segs):
            xfade = round(max(0.0, audio_xfade) * SAMPLE_RATE)
            search = round(max(0.0, audio_search) * SAMPLE_RATE)
            tracks = [_segment_audio(s, out_fps, search + xfade) for s in segs]
            report["audio_gains_db"] = _match_loudness(segs, tracks, loop)
            track = _assemble_audio(segs, tracks, out_fps, loop, xfade, search)
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


# ---------------------------------------------------------------- cut detection

_CUT_W = 128          # analysis width; cuts are global, so a thumbnail is enough
_CUT_SHIFT = 8        # motion compensation: best match over shifts up to this many px
_CUT_WINDOW = 12      # frames each side that set the local baseline


def _cut_structure(z, a, b):
    """Motion-compensated difference between frames a[k] and b[k] (index arrays).

    Exposure-normalized luma, compared at the best of a grid of shifts, so a pan,
    a step or a fast gesture finds its match and a different picture does not.
    About 0.03-0.1 between neighboring frames of a shot, 0.7-1.1 between
    unrelated pictures.
    """
    r = _CUT_SHIFT
    h, w = z.shape[1:]
    out = []
    for k in range(0, len(a), 256):   # in chunks, so a long take stays small in memory
        core_a = z[a[k:k + 256]][:, r:h - r, r:w - r]
        zb = z[b[k:k + 256]]
        best = None
        for dy in range(-r, r + 1, 2):
            for dx in range(-r, r + 1, 2):
                d = np.abs(core_a - zb[:, r + dy:h - r + dy, r + dx:w - r + dx]).mean(axis=(1, 2))
                best = d if best is None else np.minimum(best, d)
        out.append(best)
    return np.concatenate(out)


def _cut_scores(rgb):
    """Score every frame boundary. ``rgb``: (n, h, w, 3) uint8 thumbnails.

    ``structure``: the change across the boundary; ``ratio``: that change over the
    clip's typical change nearby; ``persists``: the change from two frames before
    to two frames after, over ``structure``. A cut happens in one step, so it
    persists at about 1.0; motion keeps accumulating (1.4 and up); a flash or a
    bad frame comes back (well under 1).
    """
    y = rgb[..., 0] * np.float32(0.2126) + rgb[..., 1] * np.float32(0.7152) + rgb[..., 2] * np.float32(0.0722)
    z = (y - y.mean(axis=(1, 2), keepdims=True)) / (y.std(axis=(1, 2), keepdims=True) + 1e-6)
    n = len(z)
    idx = np.arange(n - 1)
    step = _cut_structure(z, idx, idx + 1)
    across = _cut_structure(z, np.maximum(idx - 1, 0), np.minimum(idx + 2, n - 1))
    out = []
    for i in idx:
        near = [j for j in range(max(0, i - _CUT_WINDOW), min(n - 1, i + _CUT_WINDOW + 1)) if abs(j - i) > 1]
        base = float(np.median(step[near] if near else step))
        out.append({"frame": int(i + 1), "structure": float(step[i]),
                    "ratio": float(step[i] / max(base, 0.02)),
                    "persists": float(across[i] / max(step[i], 1e-6))})
    return out


def _sigmoid(x):
    return 1 / (1 + math.exp(-max(-50.0, min(50.0, x))))


def _cut_confidence(s):
    """0..1: a visible change (structure), sudden for this clip (ratio), done in one step (persists)."""
    if s["persists"] < 0.6:
        return 0.0
    visible = _sigmoid((s["structure"] - 0.10) / 0.02)
    sudden = _sigmoid((math.log(max(s["ratio"], 1e-3)) - math.log(2.5)) / 0.15)
    one_step = _sigmoid((1.3 - s["persists"]) / 0.06)
    return round(visible * sudden * one_step, 3)


async def cuts(stimma, path, *, ignore_before=0.0, seams=None, min_confidence=0.5):
    """Find hard cuts in a clip or an assembled video.

    A generated continuation should be one unbroken shot, but a model sometimes
    jumps to a new framing or a new picture partway through. Watching a contact
    sheet misses that; this measures every frame boundary instead. Each boundary
    is compared with motion compensation (a pan, a step or a fast gesture finds
    its match and scores low), against the clip's own level of change nearby (so
    a busy clip does not read as cuts), and for persistence (a one-frame flash
    that comes back is not a cut). A sudden lasting jump in exposure also reads
    as a cut; look at the frames either side to tell which it is.

    ``ignore_before``: seconds at the start to skip, such as a pinned prefix that
    repeats earlier footage. The boundary where the prefix ends is still checked,
    since a jump right after the pin is a cut in the joined video.
    ``seams``: times (seconds) of your own joins in an assembled video; a cut
    within two frames of one is marked ``at_seam``, so you can tell seams you
    made from cuts inside a segment.

    Returns ``{"duration", "fps", "checked_from", "cuts": [{"at", "frame",
    "confidence", "at_seam"}], "continuous"}``. ``at`` is the time of the first
    frame after the cut. ``continuous`` is True when no boundary reaches
    ``min_confidence``. Confidence near 1 is an unmistakable cut; 0.5-0.8 is
    usually a cut between similar framings of the same scene and is worth a look
    at the frames either side.
    """
    info = await probe(stimma, path)
    fps = info["fps"] or 24.0
    w = _CUT_W
    h = max(2 * _CUT_SHIFT + 8, round(info["height"] * w / info["width"] / 2) * 2)
    work = Path(".seamkit") / uuid.uuid4().hex[:8]
    work.mkdir(parents=True, exist_ok=True)
    try:
        raw = work / "thumbs.rgb"
        await stimma.ffmpeg("-v", "error", "-y", "-i", str(path), "-map", "0:v:0",
                            "-vf", f"scale={w}:{h}:flags=area,format=rgb24", "-f", "rawvideo",
                            str(raw), timeout=1800)
        frames = np.fromfile(raw, dtype=np.uint8).reshape(-1, h, w, 3)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if len(frames) < 4:
        raise ValueError(f"{path} is too short to measure")
    first = int(math.ceil(ignore_before * fps - 1e-6))
    seam_frames = [t * fps for t in (seams or [])]
    found = []
    for s in _cut_scores(frames):
        if s["frame"] < first:
            continue
        c = _cut_confidence(s)
        if c < min_confidence:
            continue
        found.append({"at": round(s["frame"] / fps, 3), "frame": s["frame"], "confidence": c,
                      "at_seam": any(abs(s["frame"] - f) <= 2 for f in seam_frames)})
    return {"duration": round(len(frames) / fps, 3), "fps": fps,
            "checked_from": round(max(first, 0) / fps, 3), "cuts": found,
            "continuous": not any(not c["at_seam"] for c in found)}


# ---------------------------------------------------------------- drift

# Limits, calibrated on 40 s H3 takes (960x544): serial continuation chains,
# with and without stored state, against two-pass anchored assemblies of the
# same scenes. Each is measured on a window against the reference window.
DRIFT_LIMITS = {
    "exposure": 20.0,      # |mean luma shift|, 0-255 levels
    "saturation": 15.0,    # |mean saturation shift|, 0-255 scale
    "color_match": 0.80,   # color histogram overlap with the reference, 0..1
    "sharpness": 0.80,     # fine detail relative to the opening window
    "framing": 1.20,       # apparent zoom vs the reference, either way
    "framing_match": 0.30,  # below this, the picture differs too much to judge framing
}
_DRIFT_W = 640          # analysis width for look and detail
_DRIFT_FPS = 2          # samples per second
_FRAME_W = 96           # analysis width for framing
_FRAME_SCALES = np.exp(np.linspace(math.log(0.6), math.log(1.8), 25))
_FRAME_SHIFTS = [(dy, dx) for dy in (-4, 0, 4) for dx in (-6, 0, 6)]
_STILL_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


async def _samples(stimma, path, size, work, *, start=0, end=None, fps=_DRIFT_FPS):
    """Frames of ``path`` (a still gives one) at ``size``, as a uint8 array."""
    w, h = size
    still = Path(str(path)).suffix.lower() in _STILL_SUFFIXES
    vf = ""
    if not still:
        if start or end is not None:
            vf += f"trim=start_frame={int(start)}" + (f":end_frame={int(end)}" if end is not None else "")
            vf += ",setpts=PTS-STARTPTS,"
        vf += f"fps={fps},"
    vf += f"scale={w}:{h}:flags=area,format=rgb24"
    raw = work / f"{uuid.uuid4().hex[:8]}.rgb"
    await stimma.ffmpeg("-v", "error", "-y", "-i", str(path), "-map", "0:v:0", *(["-frames:v", "1"] if still else []),
                        "-vf", vf, "-f", "rawvideo", str(raw), timeout=1800)
    n = raw.stat().st_size // (w * h * 3)
    if n == 0:
        raise ValueError(f"{path}: nothing to measure in that range")
    return np.memmap(raw, dtype=np.uint8, mode="r", shape=(n, h, w, 3))


def _luma(f):
    return f[..., 0] * 0.2126 + f[..., 1] * 0.7152 + f[..., 2] * 0.0722


def _sharpness(y):
    """Fine detail per unit of edge strength: falls as a picture softens, roughly
    independent of how much texture is in view."""
    lap = np.abs(4 * y[1:-1, 1:-1] - y[:-2, 1:-1] - y[2:, 1:-1] - y[1:-1, :-2] - y[1:-1, 2:])
    gx, gy = y[1:-1, 2:] - y[1:-1, :-2], y[2:, 1:-1] - y[:-2, 1:-1]
    return float(lap.mean() / max(float(np.sqrt(gx * gx + gy * gy).mean()), 1e-3))


def _look(frames):
    """Exposure, saturation, color histogram, sharpness and framing thumbnail of a stack."""
    lumas, sats, sharp, thumbs = [], [], [], []
    hist = np.zeros(512)
    for f in frames:
        f = f.astype(np.float32)
        y = _luma(f)
        hi, lo = f.max(-1), f.min(-1)
        lumas.append(float(y.mean()))
        sats.append(float(((hi - lo) / np.maximum(hi, 1)).mean() * 255))
        q = np.clip((f / 32).astype(np.int32), 0, 7)
        hist += np.bincount((q[..., 0] * 64 + q[..., 1] * 8 + q[..., 2]).ravel(), minlength=512)
        sharp.append(_sharpness(y))
        thumbs.append(_thumb(y))
    return {"luma": float(np.mean(lumas)), "sat": float(np.mean(sats)), "hist": hist / hist.sum(),
            "sharp": float(np.mean(sharp)), "thumbs": thumbs}


def _thumb(y):
    s = max(1, y.shape[1] // _FRAME_W)
    h, w = y.shape[0] // s, y.shape[1] // s
    return y[:h * s, :w * s].reshape(h, s, w, s).mean(axis=(1, 3))


def _zoom(img, s):
    """``img`` magnified ``s`` times about its center (bilinear), same size."""
    h, w = img.shape
    ys = ((h - h / s) / 2 + (np.arange(h) + 0.5) / s - 0.5).clip(0, h - 1)
    xs = ((w - w / s) / 2 + (np.arange(w) + 0.5) / s - 0.5).clip(0, w - 1)
    yi, xi = np.minimum(ys.astype(int), h - 2), np.minimum(xs.astype(int), w - 2)
    fy, fx = (ys - yi)[:, None], (xs - xi)[None]
    a, b = img[yi][:, xi], img[yi][:, xi + 1]
    c, d = img[yi + 1][:, xi], img[yi + 1][:, xi + 1]
    return a * (1 - fy) * (1 - fx) + b * (1 - fy) * fx + c * fy * (1 - fx) + d * fy * fx


def _std(a):
    a = a - a.mean(axis=-1, keepdims=True)
    return a / (a.std(axis=-1, keepdims=True) + 1e-6)


class _Framing:
    """Apparent zoom of a picture relative to a reference: the magnification of the
    reference (with a small shift) whose structure best matches it."""

    def __init__(self, ref_thumb):
        m = 6
        h, w = ref_thumb.shape
        self.crop = (slice(m, h - m), slice(m, w - m))
        rows, self.scales = [], []
        for s in _FRAME_SCALES:
            z = _zoom(ref_thumb, s)
            for dy, dx in _FRAME_SHIFTS:
                rows.append(z[m + dy:h - m + dy, m + dx:w - m + dx].ravel())
                self.scales.append(s)
        self.templates = _std(np.stack(rows))
        self.scales = np.array(self.scales)

    def measure(self, thumbs):
        """(scale, match) over a stack: median best scale and its median correlation."""
        best_s, best_c = [], []
        for t in thumbs:
            c = self.templates @ _std(t[self.crop].ravel()) / self.templates.shape[1]
            i = int(np.argmax(c))
            best_s.append(self.scales[i])
            best_c.append(c[i])
        return float(np.exp(np.median(np.log(best_s)))), float(np.median(best_c))


def _compare(look, ref, framing, sharp_base, limits):
    """Shifts of ``look`` from ``ref``, framing from ``framing``, and the limits crossed."""
    scale, match = framing.measure(look["thumbs"])
    row = {
        "exposure": round(look["luma"] - ref["luma"], 1),
        "saturation": round(look["sat"] - ref["sat"], 1),
        "color_match": round(float(np.minimum(look["hist"], ref["hist"]).sum()), 3),
        "sharpness": round(look["sharp"] / max(sharp_base, 1e-6), 3) if sharp_base else None,
        "framing_scale": round(scale, 2),
        "framing_match": round(match, 2),
    }
    flags = []
    if abs(row["exposure"]) > limits["exposure"]:
        flags.append("exposure")
    if abs(row["saturation"]) > limits["saturation"]:
        flags.append("saturation")
    if row["color_match"] < limits["color_match"]:
        flags.append("color")
    if row["sharpness"] is not None and row["sharpness"] < limits["sharpness"]:
        flags.append("detail")
    if match >= limits["framing_match"] and not 1 / limits["framing"] <= scale <= limits["framing"]:
        flags.append("framing")
    row["flags"] = flags
    return row


async def _analysis_size(stimma, path):
    info = await probe(stimma, path)
    return (_DRIFT_W, max(2, round(info["height"] * _DRIFT_W / info["width"] / 2) * 2)), info


async def drift(stimma, video, *, reference=None, window=4.0, limits=None):
    """Has a long take drifted from where it started? Measures look, detail and framing
    over time against a reference.

    Each generation that starts from the previous one's output adds a little
    error, and it compounds: colors saturate and darken, fine detail smears, and
    the framing creeps in. Each step looks fine next to its neighbor, so
    comparing neighbors (or watching) misses it. This compares every stretch of
    the take with the reference instead.

    ``video``: a path, measured in windows of ``window`` seconds; or a list of
    segments (paths, or dicts with ``path`` and optional ``trim_head``,
    ``trim_tail``, ``overlap`` in frames, as for ``join``), measured one window
    per segment, leaving out each segment's trimmed and overlapping frames.
    ``reference``: the picture whose framing the take should keep, such as the
    start image (a still, or a video's opening); default the first window. Look
    and detail are always compared with the first window: no video reproduces a
    still's exact palette and crispness, so measuring those against the still
    would only measure the first generation.

    Per window: ``exposure`` and ``saturation`` (shift in 0-255 levels),
    ``color_match`` (histogram overlap, 1 = same palette), ``sharpness`` (fine
    detail relative to the first window, 1 = unchanged), ``framing_scale``
    (apparent zoom vs the reference, above 1 = tighter) with ``framing_match``
    (how well the pictures align; below ``DRIFT_LIMITS["framing_match"]`` the
    content differs too much to judge framing), and ``flags`` naming each limit
    crossed. Returns ``{"ok", "summary", "windows", "worst", "limits"}``.

    Measured against the start, a planned change also reads as drift: a move
    to a new place or a planned push-in. Read the flags against the plan, and
    look at the flagged windows next to the reference.
    """
    limits = {**DRIFT_LIMITS, **(limits or {})}
    segments = None if isinstance(video, (str, Path)) else [
        {"path": s} if isinstance(s, (str, Path)) else dict(s) for s in video]
    first = video if segments is None else segments[0]["path"]
    size, info = await _analysis_size(stimma, first)
    work = Path(".seamkit") / uuid.uuid4().hex[:8]
    work.mkdir(parents=True, exist_ok=True)
    try:
        spans = []
        if segments is None:
            frames = await _samples(stimma, video, size, work)
            n = max(1, round(window * _DRIFT_FPS))
            for i in range(0, len(frames), n):
                if len(frames) - i >= max(2, n // 2) or i == 0:
                    spans.append((i / _DRIFT_FPS, min(len(frames), i + n) / _DRIFT_FPS, frames[i:i + n]))
        else:
            t = 0.0
            for k, seg in enumerate(segments):
                seg_info = info if k == 0 else await probe(stimma, seg["path"])
                fps = seg_info["fps"] or 24.0
                head = int(seg.get("trim_head", 0)) + (int(seg.get("overlap", 0)) if k else 0)
                total = round(seg_info["duration"] * fps)
                end = total - int(seg.get("trim_tail", 0))
                frames = await _samples(stimma, seg["path"], size, work, start=head, end=end)
                spans.append((t, t + (end - head) / fps, frames))
                t += (end - head) / fps
        base = _look(spans[0][2])
        thumbs = base["thumbs"]
        if reference is not None:
            still = Path(str(reference)).suffix.lower() in _STILL_SUFFIXES
            end = None if still else round(window * ((await probe(stimma, reference))["fps"] or 24.0))
            thumbs = _look(await _samples(stimma, reference, size, work, end=end))["thumbs"]
        framing = _Framing(np.mean(thumbs, axis=0))
        windows = []
        for k, (t0, t1, frames) in enumerate(spans):
            row = _compare(base if k == 0 else _look(frames), base, framing, base["sharp"], limits)
            windows.append({"start": round(t0, 2), "end": round(t1, 2), **row})
    finally:
        shutil.rmtree(work, ignore_errors=True)
    flagged = [w for w in windows if w["flags"]]
    worst = {
        "exposure": max((w["exposure"] for w in windows), key=abs),
        "saturation": max((w["saturation"] for w in windows), key=abs),
        "color_match": min(w["color_match"] for w in windows),
        "sharpness": min(w["sharpness"] for w in windows),
        "framing_scale": max((w["framing_scale"] for w in windows if w["framing_match"] >= limits["framing_match"]),
                             key=lambda s: abs(math.log(s)), default=None),
    }
    if flagged:
        kinds = sorted({f for w in flagged for f in w["flags"]})
        summary = (f"drift in {', '.join(kinds)} from {flagged[0]['start']:g} s "
                   f"({len(flagged)} of {len(windows)} windows)")
    else:
        summary = f"no drift beyond the limits across {len(windows)} windows"
    return {"ok": not flagged, "summary": summary, "windows": windows, "worst": worst, "limits": limits}


async def anchors(stimma, source, stills, *, limits=None, framing_tolerance=1.12):
    """Do anchor stills agree with the source picture before you render video from them?

    Segments that start from separate stills only join smoothly when the stills
    share the source's shape, framing and look: a bridge between two stills
    framed differently resolves the difference with a cut, not a move. Image
    edits often reframe a little tighter or shift the exposure without being
    asked. Compare each anchor with the source and redo the ones that moved.

    Per still: ``aspect`` (its width/height over the source's), ``framing_scale``
    (apparent zoom vs the source, above 1 = tighter) and ``framing_match``,
    ``exposure``, ``saturation``, ``color_match``, and ``flags``. Framing is
    flagged outside ``framing_tolerance`` either way when the pictures align well
    enough to judge (``framing_match`` 0.5 or more); a still showing a new place
    can't be compared that way and is marked ``comparable: False``, so check its
    framing by eye. Returns ``{"ok", "stills": [...]}``.
    """
    limits = {**DRIFT_LIMITS, **(limits or {}), "framing": framing_tolerance, "framing_match": 0.5}
    size, info = await _analysis_size(stimma, source)
    work = Path(".seamkit") / uuid.uuid4().hex[:8]
    work.mkdir(parents=True, exist_ok=True)
    try:
        ref = _look(await _samples(stimma, source, size, work, end=1))
        framing = _Framing(ref["thumbs"][0])
        out = []
        for path in stills:
            s_info = await probe(stimma, path)
            row = _compare(_look(await _samples(stimma, path, size, work, end=1)), ref, framing, None, limits)
            aspect = (s_info["width"] / s_info["height"]) / (info["width"] / info["height"])
            row = {"path": str(path), "aspect": round(aspect, 3), **row,
                   "comparable": row["framing_match"] >= limits["framing_match"]}
            if abs(aspect - 1) > 0.01:
                row["flags"].insert(0, "aspect")
            out.append(row)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"ok": not any(r["flags"] for r in out), "stills": out}
