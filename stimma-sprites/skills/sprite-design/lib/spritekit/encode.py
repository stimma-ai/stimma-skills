"""Per-move artifact encoding: frames <-> animated lossless WebP, plus GIF.

One move = one animated WebP with lossless pixels. WebP may merge identical
consecutive frames into a hold; add_animation pins a logical-to-encoded frame
mapping in the document so later timing edits preserve every logical frame.
Embedded durations drive native playback; document timing stays authoritative.
"""

from pathlib import Path

from PIL import Image, ImageSequence


def _durations(count: int, durations_ms: "list[int] | None", fps: float) -> list[int]:
    if durations_ms is None:
        return [round(1000 / fps)] * count
    if len(durations_ms) != count:
        raise ValueError(f"{len(durations_ms)} durations for {count} frames")
    return list(durations_ms)


def save_animation(
    frames: list,
    path: "str | Path",
    *,
    durations_ms: "list[int] | None" = None,
    fps: float = 12,
    loop: int = 0,
) -> Path:
    """Write frames as one animated lossless WebP.

    Args:
        frames: PIL images, uniform size; converted to RGBA.
        loop: 0 = loop forever (WebP convention).
    """
    if not frames:
        raise ValueError("no frames to encode")
    frames = [f.convert("RGBA") for f in frames]
    sizes = {f.size for f in frames}
    if len(sizes) > 1:
        raise ValueError(f"frames are not uniform size: {sorted(sizes)}")
    path = Path(path)
    frames[0].save(
        path,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        lossless=True,
        quality=100,
        method=4,
        duration=_durations(len(frames), durations_ms, fps),
        loop=loop,
    )
    return path


def load_animation(path: "str | Path") -> "tuple[list, list[int]]":
    """Decode an animated image into (RGBA frames, per-frame durations_ms)."""
    frames, durations = [], []
    with Image.open(path) as im:
        for frame in ImageSequence.Iterator(im):
            frames.append(frame.convert("RGBA"))
            durations.append(int(frame.info.get("duration", 0)) or 100)
    return frames, durations


def mirror_frames(frames: list) -> list:
    """Horizontally flipped copies — used to bake mirrored directions."""
    return [f.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for f in frames]


def save_gif(
    frames: list,
    path: "str | Path",
    *,
    durations_ms: "list[int] | None" = None,
    fps: float = 12,
) -> Path:
    """Write a share/preview GIF with 1-bit transparency."""
    if not frames:
        raise ValueError("no frames to encode")
    durations = _durations(len(frames), durations_ms, fps)
    converted = []
    for f in frames:
        f = f.convert("RGBA")
        alpha = f.getchannel("A")
        p = f.convert("RGB").quantize(colors=255, method=Image.Quantize.FASTOCTREE)
        # Reserve index 255 for transparency; GIF alpha is on/off at 128.
        mask = alpha.point(lambda a: 255 if a < 128 else 0)
        p.paste(255, mask=mask)
        converted.append(p)
    path = Path(path)
    converted[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=converted[1:],
        duration=durations,
        loop=0,
        transparency=255,
        disposal=2,
    )
    return path
