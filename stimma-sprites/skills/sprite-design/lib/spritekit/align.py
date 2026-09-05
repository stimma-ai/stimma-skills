"""Registration: measure per-frame drift and nudge frames back into place.

In-place motion prompts keep the character roughly centered, but i2v output
still slides by a few pixels over the clip. Drift is the *systematic* trend
of the alpha centroid across frames — a linear fit over frame index — so
legitimate oscillating motion (bounce, jump, arm swing) is never touched.
Small trends get corrected by integer translation; large ones mean the
generation failed and the move should be regenerated, not rescued.
"""

import numpy as np
from PIL import Image


def alpha_centroids(frames: list) -> "list[tuple[float, float] | None]":
    """Alpha-weighted centroid (x, y) per frame; None for empty frames."""
    centroids = []
    for f in frames:
        a = np.asarray(f.convert("RGBA"), dtype=np.float32)[:, :, 3]
        total = a.sum()
        if total == 0:
            centroids.append(None)
            continue
        ys, xs = np.mgrid[0 : a.shape[0], 0 : a.shape[1]]
        centroids.append((float((xs * a).sum() / total), float((ys * a).sum() / total)))
    return centroids


def alpha_bboxes(frames: list) -> "list[tuple[int, int, int, int] | None]":
    """Alpha bounding box (left, top, right, bottom) per frame."""
    return [f.convert("RGBA").getbbox() for f in frames]


def _axis_trend(t: np.ndarray, values: np.ndarray, r2_threshold: float) -> np.ndarray:
    """Linear-fit component of one axis, or zeros when the fit doesn't hold.

    A slide is a line (R² near 1); animation motion (bounce, swing) is not,
    even though one sampled cycle has a nonzero linear component. Only an
    axis whose movement is actually explained by the line counts as drift.
    """
    centered = values - values.mean()
    fitted = np.polyval(np.polyfit(t, centered, 1), t) if len(t) >= 2 else np.zeros_like(centered)
    total_var = float((centered**2).mean())
    if total_var < 0.25:  # sub-half-pixel wiggle: nothing to correct
        return np.zeros_like(centered)
    r2 = 1.0 - float(((centered - fitted) ** 2).mean()) / total_var
    return fitted if r2 >= r2_threshold else np.zeros_like(centered)


def edge_contact(frames: list, *, band: int = 2, alpha_floor: int = 32) -> dict:
    """Fraction of frames whose subject touches each canvas edge.

    A character brushing the top or bottom in most frames means the
    conditioning framing cropped it — regenerate with a padded conditioning
    image instead of processing a clipped clip.

    Returns:
        {"top": f, "bottom": f, "left": f, "right": f} with f in [0, 1].
    """
    counts = {"top": 0, "bottom": 0, "left": 0, "right": 0}
    for f in frames:
        a = np.asarray(f.convert("RGBA"))[:, :, 3]
        if (a[:band, :] >= alpha_floor).any():
            counts["top"] += 1
        if (a[-band:, :] >= alpha_floor).any():
            counts["bottom"] += 1
        if (a[:, :band] >= alpha_floor).any():
            counts["left"] += 1
        if (a[:, -band:] >= alpha_floor).any():
            counts["right"] += 1
    n = max(1, len(frames))
    return {k: v / n for k, v in counts.items()}


def measure_drift(frames: list, *, r2_threshold: float = 0.7) -> dict:
    """Split centroid movement into systematic drift and animation motion.

    Returns:
        {"offsets": [(dx, dy) | None], "trend": [(dx, dy) | None],
         "max_drift": float} — offsets are deviations from the mean
        centroid; trend is the per-axis slide component (zero on axes whose
        motion the linear fit can't explain); max_drift is the largest
        trend magnitude in pixels.
    """
    centroids = alpha_centroids(frames)
    idx = [i for i, c in enumerate(centroids) if c is not None]
    if not idx:
        return {"offsets": [None] * len(frames), "trend": [None] * len(frames), "max_drift": 0.0}
    t = np.array(idx, dtype=np.float64)
    xs = np.array([centroids[i][0] for i in idx])
    ys = np.array([centroids[i][1] for i in idx])
    fx = _axis_trend(t, xs, r2_threshold)
    fy = _axis_trend(t, ys, r2_threshold)
    offsets: list = [None] * len(frames)
    trend: list = [None] * len(frames)
    for j, i in enumerate(idx):
        offsets[i] = (float(xs[j] - xs.mean()), float(ys[j] - ys.mean()))
        trend[i] = (float(fx[j]), float(fy[j]))
    max_drift = max(float(np.hypot(*trend[i])) for i in idx)
    return {"offsets": offsets, "trend": trend, "max_drift": max_drift}


def measure_zoom(frames: list, *, r2_threshold: float = 0.7) -> "list[float]":
    """Per-frame scale factors of any systematic zoom, 1.0 = no zoom.

    Subject size is sqrt of the alpha-covered area; a slow zoom (an LTX
    habit) is a linear ramp in that measure, while breathing, crouching, or
    limb swings oscillate and fail the same R² gate used for translation
    drift. Returns all-1.0 when no linear zoom is detectable.
    """
    sizes = []
    for f in frames:
        a = np.asarray(f.convert("RGBA"))[:, :, 3]
        covered = float((a > 0).sum())
        sizes.append(np.sqrt(covered) if covered else None)
    idx = [i for i, s in enumerate(sizes) if s]
    factors = [1.0] * len(frames)
    if len(idx) < 3:
        return factors
    t = np.array(idx, dtype=np.float64)
    values = np.array([sizes[i] for i in idx])
    fitted = _axis_trend(t, values, r2_threshold)
    mean = values.mean()
    for j, i in enumerate(idx):
        factors[i] = float((mean + fitted[j]) / mean)
    return factors


def stabilize(
    frames: list,
    *,
    max_auto_shift: float = 8.0,
    flag_threshold: float = 16.0,
    correct_zoom: bool = True,
    max_zoom: float = 1.15,
) -> "tuple[list, dict]":
    """Cancel systematic slide and zoom; report frames that are too far gone.

    Args:
        max_auto_shift: Trend offsets up to this many pixels are corrected.
        flag_threshold: Beyond this, the frame index lands in
            report["flagged"] — recommend regenerating the move.
        correct_zoom: Rescale frames to cancel a linear zoom trend (about
            the canvas center; the translation pass then fixes what's left).
        max_zoom: Zoom factors beyond this are flagged, not corrected.

    Returns:
        (stabilized frames, report) with report keys "corrected", "flagged",
        "max_drift", "max_zoom".
    """
    zoom_factors = measure_zoom(frames) if correct_zoom else [1.0] * len(frames)
    max_zoom_seen = max(abs(z - 1.0) for z in zoom_factors) + 1.0
    zoom_flagged = max_zoom_seen > max_zoom
    if not zoom_flagged and any(abs(z - 1.0) > 0.005 for z in zoom_factors):
        rescaled = []
        for frame, z in zip(frames, zoom_factors):
            frame = frame.convert("RGBA")
            if abs(z - 1.0) <= 0.005:
                rescaled.append(frame)
                continue
            from .finish import resize_premultiplied

            w, h = frame.size
            nw, nh = max(1, round(w / z)), max(1, round(h / z))
            # Premultiplied, or the resample drags transparent pixels'
            # colour into the silhouette as a fringe.
            resized = resize_premultiplied(frame, (nw, nh))
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.paste(resized, ((w - nw) // 2, (h - nh) // 2))
            rescaled.append(canvas)
        frames = rescaled
    drift = measure_drift(frames)
    out, corrected, flagged = [], [], []
    for i, frame in enumerate(frames):
        frame = frame.convert("RGBA")
        t = drift["trend"][i]
        if t is None:
            out.append(frame)
            continue
        magnitude = float(np.hypot(t[0], t[1]))
        if magnitude > flag_threshold:
            flagged.append(i)
        dx, dy = -round(t[0]), -round(t[1])
        if (dx or dy) and magnitude <= max_auto_shift:
            shifted = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            shifted.paste(frame, (dx, dy))
            out.append(shifted)
            corrected.append(i)
        else:
            out.append(frame)
    if zoom_flagged:
        flagged = sorted(set(flagged) | {i for i, z in enumerate(zoom_factors) if abs(z - 1.0) > 0.05})
    return out, {
        "corrected": corrected,
        "flagged": flagged,
        "max_drift": drift["max_drift"],
        "max_zoom": round(max_zoom_seen, 4),
    }
