"""Engine export writers. Bake-at-export: read the doc, pack, emit.

Every writer takes a list of ResolvedAnimations (see doc.resolve_animations)
and writes into ``out_dir``, returning the created paths. Writers with
layout requirements validate up front and raise ValueError with a clear
message instead of emitting something subtly wrong.
"""

import json
import zipfile
from pathlib import Path

from PIL import Image

from .encode import save_gif
from .pack import pack_animations

TARGETS = ("atlas", "godot", "rpgmaker", "gamemaker", "gif")


def export_atlas(
    animations: list, out_dir: "str | Path", base_name: str, *, padding: int = 0
) -> list[Path]:
    """Sheet PNG + TexturePacker-style JSON atlas (Phaser/Unity lingua franca).

    Frame keys are ``<name>[_<direction>]/<index>``; animations also land in
    meta.frameTags (Aseprite convention) with from/to frame spans.
    """
    out_dir = Path(out_dir)
    sheet, rects = pack_animations(animations, padding=padding)
    sheet_path = out_dir / f"{base_name}.png"
    sheet.save(sheet_path)

    frames: dict = {}
    tags = []
    index = 0
    for anim in animations:
        start = index
        for i, rect in enumerate(rects[anim.key]):
            frames[f"{anim.key}/{i}"] = {
                "frame": rect,
                "rotated": False,
                "trimmed": False,
                "spriteSourceSize": {"x": 0, "y": 0, "w": rect["w"], "h": rect["h"]},
                "sourceSize": {"w": rect["w"], "h": rect["h"]},
                "duration": anim.durations_ms[i],
            }
            index += 1
        tags.append(
            {
                "name": anim.key,
                "from": start,
                "to": index - 1,
                "direction": "pingpong" if anim.entry["loop"] == "pingpong" else "forward",
            }
        )
    atlas = {
        "frames": frames,
        "meta": {
            "app": "stimma",
            "image": sheet_path.name,
            "format": "RGBA8888",
            "size": {"w": sheet.width, "h": sheet.height},
            "scale": "1",
            "frameTags": tags,
        },
    }
    json_path = out_dir / f"{base_name}.json"
    json_path.write_text(json.dumps(atlas, indent=2) + "\n")
    return [sheet_path, json_path]


def export_godot(
    animations: list, out_dir: "str | Path", base_name: str, *, padding: int = 0
) -> list[Path]:
    """Sheet PNG + SpriteFrames .tres with AtlasTexture regions, fps, loop."""
    out_dir = Path(out_dir)
    sheet, rects = pack_animations(animations, padding=padding)
    sheet_path = out_dir / f"{base_name}.png"
    sheet.save(sheet_path)

    total_subs = sum(len(rects[a.key]) for a in animations)
    lines = [
        f'[gd_resource type="SpriteFrames" load_steps={total_subs + 2} format=3]',
        "",
        f'[ext_resource type="Texture2D" path="{sheet_path.name}" id="1"]',
        "",
    ]
    sub_id = 0
    anim_blocks = []
    for anim in animations:
        entries = []
        base_ms = round(1000 / anim.entry["fps"])
        for rect, duration in zip(rects[anim.key], anim.durations_ms):
            sub_id += 1
            lines += [
                f'[sub_resource type="AtlasTexture" id="AtlasTexture_{sub_id}"]',
                'atlas = ExtResource("1")',
                f'region = Rect2({rect["x"]}, {rect["y"]}, {rect["w"]}, {rect["h"]})',
                "",
            ]
            # Godot durations are speed-relative multipliers.
            entries.append(
                '{\n"duration": %s,\n"texture": SubResource("AtlasTexture_%d")\n}'
                % (round(duration / base_ms, 4), sub_id)
            )
        loop = "true" if anim.entry["loop"] == "loop" else "false"
        anim_blocks.append(
            '{\n"frames": [%s],\n"loop": %s,\n"name": &"%s",\n"speed": %s\n}'
            % (", ".join(entries), loop, anim.key, anim.entry["fps"])
        )
    lines += ["[resource]", "animations = [%s]" % ", ".join(anim_blocks), ""]
    tres_path = out_dir / f"{base_name}.tres"
    tres_path.write_text("\n".join(lines))
    return [sheet_path, tres_path]


def export_rpgmaker(
    animations: list, out_dir: "str | Path", base_name: str, *, move: str = "walk"
) -> list[Path]:
    """``$<name>.png`` single-character sheet: 3 columns x 4 direction rows.

    Needs the ``move`` animation in south, west, east, and north. Each row
    takes 3 frames sampled evenly from the cycle (RPG Maker plays 0-1-2-1).
    Raises ValueError naming any missing direction — a side-scroller set
    cannot produce a charset and should say so, not fake it.
    """
    out_dir = Path(out_dir)
    row_order = ("south", "west", "east", "north")  # RPG Maker: down/left/right/up
    by_direction = {
        a.direction: a for a in animations if a.name == move and a.direction in row_order
    }
    missing = [d for d in row_order if d not in by_direction]
    if missing:
        raise ValueError(
            f"RPG Maker charset needs {move!r} facing {', '.join(row_order)}; "
            f"missing: {', '.join(missing)}"
        )
    cell_w = max(f.width for a in by_direction.values() for f in a.frames)
    cell_h = max(f.height for a in by_direction.values() for f in a.frames)
    sheet = Image.new("RGBA", (cell_w * 3, cell_h * 4), (0, 0, 0, 0))
    for row, direction in enumerate(row_order):
        frames = by_direction[direction].frames
        picks = [frames[min(round(i * (len(frames) - 1) / 2), len(frames) - 1)] for i in range(3)]
        for col, frame in enumerate(picks):
            frame = frame.convert("RGBA")
            x = col * cell_w + (cell_w - frame.width) // 2
            y = row * cell_h + (cell_h - frame.height)
            sheet.paste(frame, (x, y))
    path = out_dir / f"${base_name}.png"
    sheet.save(path)
    return [path]


def export_gamemaker(animations: list, out_dir: "str | Path", base_name: str) -> list[Path]:
    """One horizontal strip per animation, named ``<base>_<key>_stripN.png``."""
    out_dir = Path(out_dir)
    paths = []
    for anim in animations:
        cell_w = max(f.width for f in anim.frames)
        cell_h = max(f.height for f in anim.frames)
        strip = Image.new("RGBA", (cell_w * len(anim.frames), cell_h), (0, 0, 0, 0))
        for i, frame in enumerate(anim.frames):
            frame = frame.convert("RGBA")
            strip.paste(
                frame,
                (i * cell_w + (cell_w - frame.width) // 2, cell_h - frame.height),
            )
        path = out_dir / f"{base_name}_{anim.key}_strip{len(anim.frames)}.png"
        strip.save(path)
        paths.append(path)
    return paths


def export_gifs(animations: list, out_dir: "str | Path", base_name: str) -> list[Path]:
    """One preview GIF per animation."""
    out_dir = Path(out_dir)
    paths = []
    for anim in animations:
        path = out_dir / f"{base_name}_{anim.key}.gif"
        save_gif(anim.frames, path, durations_ms=anim.durations_ms)
        paths.append(path)
    return paths


def bundle_zip(paths: list, zip_path: "str | Path") -> Path:
    """Zip export files flat (engine-relative names like the .tres expect)."""
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            zf.write(p, Path(p).name)
    return zip_path


def export_sprite(
    animations: list,
    target: str,
    out_dir: "str | Path",
    base_name: str,
    *,
    zip_multi: bool = True,
    **kwargs,
) -> list[Path]:
    """Dispatch to a writer by target name; zip multi-file outputs.

    Args:
        target: One of TARGETS ("atlas" covers Phaser/Unity/generic).
        zip_multi: When a target emits several files whose relative names
            must be preserved, also produce ``<base_name>_<target>.zip``.

    Returns:
        The paths handed to the user (the zip when one was made).
    """
    out_dir = Path(out_dir)
    writers = {
        "atlas": export_atlas,
        "godot": export_godot,
        "rpgmaker": export_rpgmaker,
        "gamemaker": export_gamemaker,
        "gif": export_gifs,
    }
    if target not in writers:
        raise ValueError(f"unknown target {target!r}; expected one of {TARGETS}")
    paths = writers[target](animations, out_dir, base_name, **kwargs)
    if zip_multi and len(paths) > 1 and target in ("atlas", "godot"):
        return [bundle_zip(paths, out_dir / f"{base_name}_{target}.zip")]
    return paths
