"""Freeze approved frames for the deterministic sprite-assets package recipe."""
from pathlib import Path


def package_source(animations, path, *, name, title=None, anchor=(0.5, 1.0),
                   pixelated=True, usage=None):
    """Write a source ZIP from a list of animation dicts.

    Each dict: name, frames (PIL images), optional direction, fps (12), loop
    ('loop'), durations_ms, loop_start/end, mirrored_from. A still is one frame
    with loop='once'. All moves must already share one registered canvas.
    usage is game-facing metadata: e.g. kind, mirror_safe, collision_box,
    attachments, tile_size, repeat axes, notes. Coordinates are top-left pixels.
    """
    from sprite_export import ExportAnimation, SpriteSource
    from sprite_source import write_source

    resolved = []
    for a in animations:
        frames = list(a["frames"])
        fps = a.get("fps", 12)
        resolved.append(ExportAnimation(name=a["name"], direction=a.get("direction"),
            fps=fps, loop=a.get("loop", "loop"), loop_start=a.get("loop_start", 0),
            loop_end=a.get("loop_end", len(frames) - 1), frames=frames,
            durations_ms=a.get("durations_ms", [round(1000 / fps)] * len(frames)),
            mirrored_from=a.get("mirrored_from")))
    return write_source(SpriteSource(title=title or name, base_name=name, anchor=anchor,
                                     animations=resolved, pixelated=pixelated), Path(path), usage=usage)
