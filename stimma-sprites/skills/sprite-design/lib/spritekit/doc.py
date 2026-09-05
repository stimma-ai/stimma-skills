"""Read, write, and validate .stimmasprite.json documents.

A sprite document is one character. Each animation entry is one move in one
direction and owns exactly one media artifact: an animated lossless WebP.
Artifacts are referenced by SHA-256 content hash (the app's media hash).

Animation references may also carry ``frame_indices``: one encoded WebP
frame index per logical document frame, pinned by add_animation before any
timing edits. This preserves holds even when WebP merges repeated frames.

Mirrored directions are baked at generation time; ``mirrored_from`` records
provenance only — consumers never flip.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

SCHEMA_VERSION = 1
DOC_SUFFIX = ".stimmasprite.json"

DIRECTIONS = (
    "south", "southwest", "west", "northwest",
    "north", "northeast", "east", "southeast",
)
# Generate one side, bake the other by horizontal flip.
MIRROR_PAIRS = {
    "east": "west", "west": "east",
    "northeast": "northwest", "northwest": "northeast",
    "southeast": "southwest", "southwest": "southeast",
}
LOOP_MODES = ("loop", "once", "pingpong")


def file_hash(path: "str | Path") -> str:
    """SHA-256 hex digest of a file — matches the app's media file_hash."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_ref(path: "str | Path") -> dict:
    """Hash reference for an image file: {"hash": "..."}."""
    return {"hash": file_hash(path)}


def new_doc(title: str, *, style: str = "", description: str = "") -> dict:
    """A fresh sprite document with no animations.

    Set ``base_image`` / ``base_image_nobg`` / ``portrait`` with image_ref()
    once those files exist. ``anchor`` defaults to bottom-center (feet).
    """
    return {
        "type": "sprite",
        "version": SCHEMA_VERSION,
        "title": title,
        "description": description,
        "style": style,
        "base_image": None,
        "base_image_nobg": None,
        "portrait": None,
        "anchor": {"x": 0.5, "y": 1.0},
        "animations": [],
    }


def _default_frame_meta() -> dict:
    return {"duration_ms": None, "rects": {}, "events": []}


def add_animation(
    doc: dict,
    name: str,
    animation_path: "str | Path",
    *,
    frame_count: int,
    direction: "str | None" = None,
    fps: float = 12,
    loop: str = "loop",
    loop_start: "int | None" = None,
    loop_end: "int | None" = None,
    mirrored_from: "str | None" = None,
    source_video: "str | Path | None" = None,
    durations_ms: "list[int | None] | None" = None,
) -> dict:
    """Add (or replace) the animation entry keyed by (name, direction).

    Args:
        animation_path: The move's animated WebP file; hashed into the doc.
        durations_ms: Optional per-frame overrides of the fps-derived timing;
            None entries mean "use fps".
    """
    if loop not in LOOP_MODES:
        raise ValueError(f"loop must be one of {LOOP_MODES}, got {loop!r}")
    if direction is not None and direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
    if durations_ms is not None and len(durations_ms) != frame_count:
        raise ValueError(
            f"durations_ms has {len(durations_ms)} entries for {frame_count} frames"
        )
    frames = [_default_frame_meta() for _ in range(frame_count)]
    if durations_ms is not None:
        for meta, d in zip(frames, durations_ms):
            meta["duration_ms"] = d
    entry = {
        "name": name,
        "direction": direction,
        "mirrored_from": mirrored_from,
        "fps": fps,
        "loop": loop,
        "loop_start": 0 if loop_start is None else loop_start,
        "loop_end": frame_count - 1 if loop_end is None else loop_end,
        "source_video": image_ref(source_video) if source_video else None,
        "animation": {"hash": file_hash(animation_path), "format": "webp"},
        "frame_count": frame_count,
        "frames": frames,
    }
    if not isinstance(animation_path, dict):
        from .encode import load_animation

        _, encoded_durations = load_animation(animation_path)
        entry["animation"]["frame_indices"] = sprite_frame_indices(entry, encoded_durations)
    remove_animation(doc, name, direction)
    doc["animations"].append(entry)
    return entry


def get_animation(doc: dict, name: str, direction: "str | None" = None) -> "dict | None":
    for entry in doc["animations"]:
        if entry["name"] == name and entry["direction"] == direction:
            return entry
    return None


def remove_animation(doc: dict, name: str, direction: "str | None" = None) -> bool:
    entry = get_animation(doc, name, direction)
    if entry is None:
        return False
    doc["animations"].remove(entry)
    return True


def validate(doc: dict) -> list[str]:
    """Structural checks. Returns a list of problems; empty means valid."""
    errors = []
    if doc.get("type") != "sprite":
        errors.append(f"type must be 'sprite', got {doc.get('type')!r}")
    if doc.get("version") != SCHEMA_VERSION:
        errors.append(f"version must be {SCHEMA_VERSION}, got {doc.get('version')!r}")
    if not doc.get("title"):
        errors.append("title is required")
    anchor = doc.get("anchor") or {}
    if not (0 <= anchor.get("x", -1) <= 1 and 0 <= anchor.get("y", -1) <= 1):
        errors.append("anchor.x and anchor.y must be in [0,1]")
    seen = set()
    for i, entry in enumerate(doc.get("animations", [])):
        where = f"animations[{i}] ({entry.get('name')!r})"
        key = (entry.get("name"), entry.get("direction"))
        if key in seen:
            errors.append(f"{where}: duplicate (name, direction) {key}")
        seen.add(key)
        if not entry.get("name"):
            errors.append(f"{where}: name is required")
        if entry.get("direction") not in DIRECTIONS + (None,):
            errors.append(f"{where}: bad direction {entry.get('direction')!r}")
        if entry.get("loop") not in LOOP_MODES:
            errors.append(f"{where}: bad loop {entry.get('loop')!r}")
        if not (entry.get("animation") or {}).get("hash"):
            errors.append(f"{where}: animation.hash is required")
        n = entry.get("frame_count", 0)
        if n < 1:
            errors.append(f"{where}: frame_count must be >= 1")
        if len(entry.get("frames", [])) != n:
            errors.append(f"{where}: frames has {len(entry.get('frames', []))} entries for frame_count {n}")
        if not (0 <= entry.get("loop_start", -1) <= entry.get("loop_end", -1) < n):
            errors.append(f"{where}: need 0 <= loop_start <= loop_end < frame_count")
        # mirrored_from names the source direction; it must be the mirror of
        # this entry's direction and that source entry must exist.
        mf = entry.get("mirrored_from")
        if mf is not None:
            if mf not in DIRECTIONS:
                errors.append(f"{where}: mirrored_from must be a direction, got {mf!r}")
            elif MIRROR_PAIRS.get(entry.get("direction") or "") != mf:
                errors.append(f"{where}: mirrored_from {mf!r} is not the mirror of {entry.get('direction')!r}")
            elif get_animation(doc, entry.get("name", ""), mf) is None:
                errors.append(f"{where}: mirrored_from {mf!r} has no source entry")
    return errors


def save(doc: dict, path: "str | Path") -> Path:
    """Write the document. Path should end in .stimmasprite.json."""
    problems = validate(doc)
    if problems:
        raise ValueError("invalid sprite doc: " + "; ".join(problems))
    path = Path(path)
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


def load(path: "str | Path") -> dict:
    doc = json.loads(Path(path).read_text())
    problems = validate(doc)
    if problems:
        raise ValueError(f"invalid sprite doc {path}: " + "; ".join(problems))
    return doc


@dataclass
class ResolvedAnimation:
    """An animation entry with its frames decoded and timing flattened."""

    entry: dict
    frames: list = field(default_factory=list)  # PIL RGBA images

    @property
    def name(self) -> str:
        return self.entry["name"]

    @property
    def direction(self) -> "str | None":
        return self.entry["direction"]

    @property
    def key(self) -> str:
        d = self.entry["direction"]
        return f"{self.entry['name']}_{d}" if d else self.entry["name"]

    @property
    def durations_ms(self) -> list[int]:
        base = round(1000 / self.entry["fps"])
        return [
            m["duration_ms"] if m.get("duration_ms") else base
            for m in self.entry["frames"]
        ]


def sprite_frame_indices(entry: dict, encoded_durations: list[int]) -> list[int]:
    """Map logical document frames onto WebP frames (which can merge holds).

    New documents pin this mapping before timing edits. For older documents,
    recover it from the original timeline only when its boundaries align.
    """
    count = entry["frame_count"]
    mapping = (entry.get("animation") or {}).get("frame_indices")
    if mapping is not None:
        if (not isinstance(mapping, list) or len(mapping) != count
                or any(type(i) is not int or not 0 <= i < len(encoded_durations) for i in mapping)):
            raise ValueError("animation.frame_indices must map every document frame to an encoded frame")
        return mapping
    if len(encoded_durations) == count:
        return list(range(count))
    if len(encoded_durations) == 1:
        return [0] * count
    base = max(1, round(1000 / float(entry.get("fps") or 12)))
    durations = [int(m.get("duration_ms") or base) for m in entry["frames"]]
    mapping = []
    index = 0
    elapsed = 0
    boundary = encoded_durations[0]
    for duration in durations:
        if duration <= 0 or elapsed + duration > boundary:
            raise ValueError("Encoded frame boundaries do not match the document timeline")
        mapping.append(index)
        elapsed += duration
        if elapsed == boundary and index + 1 < len(encoded_durations):
            index += 1
            boundary += encoded_durations[index]
    if elapsed != sum(encoded_durations):
        raise ValueError("Encoded duration does not match the document timeline")
    return mapping


def resolve_animations(doc: dict, resolver) -> "list[ResolvedAnimation]":
    """Decode every animation's WebP via ``resolver(hash) -> path``.

    In chat, the resolver is usually a dict lookup over files you just wrote,
    or a workspace scan that hashes candidates.
    """
    from .encode import load_animation

    resolved = []
    for entry in doc["animations"]:
        path = resolver(entry["animation"]["hash"])
        frames, durations = load_animation(path)
        frames = [frames[i] for i in sprite_frame_indices(entry, durations)]
        resolved.append(ResolvedAnimation(entry=entry, frames=frames))
    return resolved


def workspace_resolver(directory: "str | Path" = ".", pattern: str = "*.webp"):
    """Resolver that hashes matching files in a directory once, then looks up."""
    table = {}
    for p in Path(directory).glob(pattern):
        table[file_hash(p)] = p
    def resolve(h: str) -> Path:
        if h not in table:
            raise KeyError(f"no file with hash {h[:12]}… in {directory}")
        return table[h]
    return resolve
