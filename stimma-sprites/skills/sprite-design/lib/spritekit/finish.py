"""Turn cleaned full-resolution frames into finished sprite frames.

Two things happen here that the rest of the pipeline must not skip:

* **Shared crop.** Every frame is cropped to the *union* bounding box of
  the whole animation, never per-frame — a per-frame crop would silently
  re-register the character and destroy the animation.
* **Premultiplied downscale.** Game sprites are small (a 256px-tall frame
  is generous). Downscaling is also the single most effective artifact
  filter available: it averages away the pixel-level noise left by video
  compression. It must be done with premultiplied alpha, or transparent
  pixels drag their colour into the edge as a fringe.
"""

import numpy as np
from PIL import Image


def union_box(frames: list, *, pad: int = 2, alpha_floor: int = 32) -> tuple:
    """Bounding box covering the subject across every frame."""
    left = top = None
    right = bottom = None
    for f in frames:
        a = np.asarray(f.convert("RGBA"))[:, :, 3]
        ys, xs = np.where(a > alpha_floor)
        if not len(ys):
            continue
        left = xs.min() if left is None else min(left, xs.min())
        top = ys.min() if top is None else min(top, ys.min())
        right = xs.max() if right is None else max(right, xs.max())
        bottom = ys.max() if bottom is None else max(bottom, ys.max())
    if left is None:
        return (0, 0, frames[0].width, frames[0].height)
    w, h = frames[0].size
    return (
        int(max(0, left - pad)), int(max(0, top - pad)),
        int(min(w, right + 1 + pad)), int(min(h, bottom + 1 + pad)),
    )


def resize_premultiplied(image, size) -> Image.Image:
    """Resize RGBA without letting transparent pixels tint the edges."""
    # Pillow's RGBA resampler already converts to premultiplied RGBa and
    # back. Manually premultiplying first would apply alpha weighting twice.
    # BOX avoids ringing from negative-lobed filters at silhouette edges.
    return image.convert("RGBA").resize(size, Image.Resampling.BOX)


def finalize(
    frames: list,
    *,
    height: "int | None" = 256,
    binarize: "int | None" = None,
    pad: int = 2,
    box: "tuple | None" = None,
    square: bool = True,
) -> "tuple[list, dict]":
    """Crop to the shared box and scale to sprite size.

    Args:
        height: Target frame height in pixels; None keeps full resolution.
        binarize: Alpha at or above this becomes 255, below becomes 0.
            Defaults to None — KEEP THE SOFT ALPHA. Hard alpha turns a
            silhouette edge's smooth sub-pixel coverage into 0/255 pops as
            the character moves, which reads as edge flicker (measured on a
            real idle: 144 hard pops at the heel with binarize=128, zero
            without). Only binarize when a target genuinely cannot carry an
            alpha channel.
        square: Pad each frame to a square of ``height``, the frame model
            sprite sheets assume (square cells, columns = sqrt(frames)).
        pad: Transparent margin kept around the union box.
        box: Override the computed crop (share one box across directions
            of the same character so their sprites stay aligned).

    Returns:
        (sprite frames, info) where info carries "box" and "size".
    """
    if not frames:
        raise ValueError("no frames to finalize")
    box = box or union_box(frames, pad=pad)
    left, top, right, bottom = box
    out = []
    for f in frames:
        cropped = f.convert("RGBA").crop((left, top, right, bottom))
        if height and cropped.height != height:
            scale = height / cropped.height
            cropped = resize_premultiplied(
                cropped, (max(1, round(cropped.width * scale)), height)
            )
        if binarize is not None:
            arr = np.asarray(cropped, dtype=np.uint8).copy()
            arr[:, :, 3] = np.where(arr[:, :, 3] >= binarize, 255, 0)
            cropped = Image.fromarray(arr, "RGBA")
        out.append(cropped)
    if square and height:
        side = height
        squared = []
        for f in out:
            if f.width > side:      # very wide pose: fit to width instead
                scale = side / f.width
                f = resize_premultiplied(f, (side, max(1, round(f.height * scale))))
            canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            canvas.paste(f, ((side - f.width) // 2, side - f.height))  # feet on the floor
            squared.append(canvas)
        out = squared
    return out, {"box": box, "size": out[0].size, "square": bool(square and height)}


def frame_distance(a, b) -> float:
    """Dissimilarity of two frames: alpha mismatch + colour difference.

    Roughly 0 for identical frames; the mean value between neighbouring
    frames of a normal cycle is the yardstick everything else is judged
    against.
    """
    aa = np.asarray(a.convert("RGBA")).astype(np.int16)
    bb = np.asarray(b.convert("RGBA")).astype(np.int16)
    ma, mb = aa[:, :, 3] > 0, bb[:, :, 3] > 0
    union = int((ma | mb).sum())
    mismatch = float((ma ^ mb).sum()) / max(1, union)
    both = ma & mb
    colour = (float(np.abs(aa[:, :, :3][both] - bb[:, :, :3][both]).mean()) / 255.0
              if both.any() else 1.0)
    return mismatch + colour


def find_loop(frames: list, *, min_fraction: float = 0.34) -> dict:
    """Find the best cut point for a seamless loop, and say how good it is.

    A generated clip only loops if the model was told to end where it
    started — with first+last-frame conditioning, ideally. Without that it
    drifts, and the jump back to frame 0 reads as a flicker (typically
    worst at whichever part moved most, e.g. a heel). This measures the
    problem instead of guessing: ``baseline`` is the mean distance between
    neighbouring frames, ``score`` the distance across the proposed seam.

    Returns:
        {"length", "score", "baseline", "ratio", "clean"} — ``ratio`` is
        score/baseline (1.0 is a seamless loop) and ``clean`` is True when
        the seam is within ~2x a normal frame step. When it is not clean,
        regenerate with the anchor as both first and last frame, or play
        the move as ``pingpong``, which loops by construction.
    """
    n = len(frames)
    if n < 3:
        return {"length": n, "score": 0.0, "baseline": 0.0, "ratio": 1.0, "clean": True}
    baseline = float(np.mean([frame_distance(frames[i], frames[i + 1]) for i in range(n - 1)]))
    start = max(2, int(n * min_fraction))
    candidates = [(k, frame_distance(frames[0], frames[k])) for k in range(start, n)]
    length, score = min(candidates, key=lambda t: t[1])
    ratio = score / baseline if baseline > 0 else 1.0
    return {"length": length, "score": score, "baseline": baseline,
            "ratio": ratio, "clean": ratio <= 2.0}


def trim_to_loop(frames: list, *, durations_ms: "list | None" = None,
                 min_fraction: float = 0.34) -> "tuple[list, dict]":
    """Cut the clip at its best loop point. Returns (frames, find_loop info).

    Trimming can only pick the least-bad seam; it cannot make a
    non-cyclic clip cyclic. Check ``info["clean"]`` and act on it.
    """
    info = find_loop(frames, min_fraction=min_fraction)
    k = info["length"]
    if durations_ms is not None:
        info["durations_ms"] = list(durations_ms[:k])
    return frames[:k], info


def pingpong(frames: list, *, durations_ms: "list | None" = None) -> "tuple[list, list | None]":
    """Forward then back, minus the duplicated endpoints — loops by design.

    Every transition is an ordinary neighbouring-frame step, so the seam
    that made a heel flicker simply stops existing. Right for breathing,
    idling, hovering and other symmetric motion; wrong for a walk or run
    cycle, which would appear to moonwalk.
    """
    if len(frames) < 3:
        return list(frames), (list(durations_ms) if durations_ms else None)
    out = list(frames) + list(frames[-2:0:-1])
    dur = None
    if durations_ms is not None:
        dur = list(durations_ms) + list(durations_ms[-2:0:-1])
    return out, dur
