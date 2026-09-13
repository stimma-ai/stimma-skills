"""Sheet packing — export-time only. The document never stores a packed sheet.

Frames pack into a uniform-cell grid: dumb, deterministic, and what every
engine importer expects. Trim and padding are parameters here, not document
state.
"""

import math

from PIL import Image


def union_bbox(frames: list) -> "tuple[int, int, int, int]":
    """Bounding box covering every frame's non-transparent pixels.

    Cropping all frames to the union (never per-frame) preserves
    registration — the character stays put relative to the cell.
    """
    left = top = None
    right = bottom = None
    for f in frames:
        box = f.convert("RGBA").getbbox()
        if box is None:
            continue
        left = box[0] if left is None else min(left, box[0])
        top = box[1] if top is None else min(top, box[1])
        right = box[2] if right is None else max(right, box[2])
        bottom = box[3] if bottom is None else max(bottom, box[3])
    if left is None:
        return (0, 0, frames[0].width, frames[0].height)
    return (left, top, right, bottom)


def trim_frames(frames: list, *, padding: int = 0) -> "tuple[list, tuple[int, int]]":
    """Crop all frames to their union bbox plus padding.

    Returns:
        (trimmed frames, (offset_x, offset_y)) — the offset of the crop in
        the original canvas, needed to keep the anchor meaningful.
    """
    left, top, right, bottom = union_bbox(frames)
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(frames[0].width, right + padding)
    bottom = min(frames[0].height, bottom + padding)
    return (
        [f.convert("RGBA").crop((left, top, right, bottom)) for f in frames],
        (left, top),
    )


def pack_sheet(
    frames: list,
    *,
    columns: "int | None" = None,
    padding: int = 0,
) -> "tuple[Image.Image, list[dict]]":
    """Pack uniform-size frames into a grid sheet.

    Args:
        columns: Grid width in cells; default is near-square.
        padding: Transparent pixels between cells (bleed guard).

    Returns:
        (sheet, rects) where rects[i] = {"x", "y", "w", "h"} of frame i.
    """
    if not frames:
        raise ValueError("no frames to pack")
    frames = [f.convert("RGBA") for f in frames]
    sizes = {f.size for f in frames}
    if len(sizes) > 1:
        raise ValueError(f"frames are not uniform size: {sorted(sizes)}")
    cell_w, cell_h = frames[0].size
    count = len(frames)
    cols = columns or math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    sheet = Image.new(
        "RGBA",
        (cols * cell_w + (cols - 1) * padding, rows * cell_h + (rows - 1) * padding),
        (0, 0, 0, 0),
    )
    rects = []
    for i, frame in enumerate(frames):
        x = (i % cols) * (cell_w + padding)
        y = (i // cols) * (cell_h + padding)
        sheet.paste(frame, (x, y))
        rects.append({"x": x, "y": y, "w": cell_w, "h": cell_h})
    return sheet, rects


def pack_animations(
    animations: "list",
    *,
    padding: int = 0,
) -> "tuple[Image.Image, dict[str, list[dict]]]":
    """Pack several ResolvedAnimations onto one sheet, one row per animation.

    Cells are uniform across the whole sheet (max frame dimensions) so
    engines that assume a regular grid stay happy.

    Returns:
        (sheet, {animation.key: [rects]}).
    """
    if not animations:
        raise ValueError("no animations to pack")
    cell_w = max(f.width for a in animations for f in a.frames)
    cell_h = max(f.height for a in animations for f in a.frames)
    cols = max(len(a.frames) for a in animations)
    rows = len(animations)
    sheet = Image.new(
        "RGBA",
        (cols * cell_w + (cols - 1) * padding, rows * cell_h + (rows - 1) * padding),
        (0, 0, 0, 0),
    )
    rects: dict = {}
    for row, anim in enumerate(animations):
        rects[anim.key] = []
        for col, frame in enumerate(anim.frames):
            frame = frame.convert("RGBA")
            x = col * (cell_w + padding) + (cell_w - frame.width) // 2
            y = row * (cell_h + padding) + (cell_h - frame.height)
            sheet.paste(frame, (x, y))
            rects[anim.key].append(
                {"x": x, "y": y, "w": frame.width, "h": frame.height}
            )
    return sheet, rects
