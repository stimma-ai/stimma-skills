"""Video -> frames. Runs ffmpeg/ffprobe through the run_code SDK handle.

These functions take the ``stimma`` SDK object as their first argument
because ffmpeg is only reachable through ``stimma.ffmpeg`` inside run_code:

    from spritekit import extract
    fps = await extract.probe_fps(stimma, "run.mp4")
    frames = await extract.extract_frames(stimma, "run.mp4", fps=12)
"""

import json
import os
from pathlib import Path

import numpy as np
from PIL import Image


async def probe_fps(sdk, video_path: "str | Path") -> float:
    """The video's average frame rate."""
    result = await sdk.ffprobe(
        "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate,r_frame_rate",
        "-of", "json", str(video_path),
    )
    stream = json.loads(result.stdout)["streams"][0]
    rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    num, _, den = rate.partition("/")
    den = float(den or 1)
    return float(num) / den if den else 0.0


async def extract_frames(
    sdk,
    video_path: "str | Path",
    *,
    fps: "float | None" = None,
    max_frames: "int | None" = None,
    out_dir: str = "_sprite_frames",
) -> list:
    """Decode a video to a list of RGBA frames.

    Args:
        fps: Resample to this rate; None keeps every source frame.
        out_dir: Workspace-relative scratch directory for the PNGs.
    """
    video_path = Path(video_path)
    scratch = Path(out_dir) / video_path.stem
    os.makedirs(scratch, exist_ok=True)
    for old in scratch.glob("frame_*.png"):
        old.unlink()
    args = ["-y", "-i", str(video_path)]
    if fps:
        args += ["-vf", f"fps={fps}"]
    else:
        args += ["-vsync", "0"]
    if max_frames:
        args += ["-frames:v", str(max_frames)]
    args += [str(scratch / "frame_%05d.png")]
    await sdk.ffmpeg(*args)
    frames = []
    for p in sorted(scratch.glob("frame_*.png")):
        with Image.open(p) as im:
            frames.append(im.convert("RGBA"))
    if not frames:
        raise RuntimeError(f"no frames extracted from {video_path}")
    return frames


def save_frames(frames: list, directory: "str | Path") -> list:
    """Write frames as numbered PNGs; returns the paths in frame order.

    Round-trip half for per-frame background removal: save, feed the paths
    to the remove-background tool, then load_frames() the results.
    """
    directory = Path(directory)
    os.makedirs(directory, exist_ok=True)
    paths = []
    for i, frame in enumerate(frames):
        p = directory / f"frame_{i:05d}.png"
        frame.convert("RGBA").save(p)
        paths.append(p)
    return paths


def load_frames(paths_or_dir) -> list:
    """Load RGBA frames from a list of paths (kept in order) or a directory."""
    if isinstance(paths_or_dir, (str, Path)):
        paths = sorted(Path(paths_or_dir).glob("*.png"))
    else:
        paths = [Path(p) for p in paths_or_dir]
    frames = []
    for p in paths:
        with Image.open(p) as im:
            frames.append(im.convert("RGBA"))
    return frames


def dedup_frames(
    frames: list,
    *,
    fps: float = 12,
    max_diff: float = 1.0,
) -> "tuple[list, list[int]]":
    """Collapse near-identical consecutive frames into longer durations.

    Args:
        max_diff: Mean absolute per-channel difference (0-255 scale) at or
            below which two frames count as the same.

    Returns:
        (kept frames, per-frame durations_ms) — durations absorb the dropped
        duplicates so total animation length is unchanged.
    """
    if not frames:
        return [], []
    base = round(1000 / fps)
    kept = [frames[0]]
    durations = [base]
    prev = np.asarray(frames[0], dtype=np.int16)
    for frame in frames[1:]:
        arr = np.asarray(frame, dtype=np.int16)
        if arr.shape == prev.shape and np.abs(arr - prev).mean() <= max_diff:
            durations[-1] += base
        else:
            kept.append(frame)
            durations.append(base)
            prev = arr
    return kept, durations


# Perfect squares, so a sheet packs as a square grid (columns = sqrt(n)).
FRAME_BUDGETS = (4, 16, 25, 49, 64)


async def sample_frames(
    sdk,
    video_path: "str | Path",
    *,
    count: int = 25,
    out_dir: str = "_sprite_frames",
) -> list:
    """Take a FIXED budget of frames spread evenly across the whole clip.

    Decide the frame count first, then sample to it — do not extract at the
    source frame rate and thin afterwards. The budget is the animation's
    frame count, so playback fps is ``count / clip_duration`` (or whatever
    8-12 fps you choose), and a square budget packs as a square sheet.

    Sampling evenly also keeps every frame equally spaced in time, which a
    dedup pass cannot promise.
    """
    duration = 0.0
    try:
        result = await sdk.ffprobe(
            "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(video_path),
        )
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        duration = 0.0
    rate = (count / duration) if duration > 0 else 12.0
    frames = await extract_frames(sdk, video_path, fps=rate, out_dir=out_dir)
    if len(frames) == count:
        return frames
    # ffmpeg rounds; resample the decoded list to exactly the budget.
    idx = np.linspace(0, len(frames) - 1, count).round().astype(int)
    return [frames[i] for i in idx]
