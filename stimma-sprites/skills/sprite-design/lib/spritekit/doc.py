"""Read, write, and validate .stimmasprite.json documents.

A sprite document is one character, and it is the *recipe*: everything a
fresh chat needs to redo a move lives in the document or one lineage hop
away from a media id the document holds. Each animation entry is one move in
one direction and owns exactly one media artifact: an animated lossless WebP.

Media references are ``{"media_id": N, "hash": "<sha256>"}``. The id is what
an agent walks lineage from (``stimma.library.get`` / ``media_info``); the
hash is the integrity check and what the app's player resolves through
``/media/by-hash``. Record the id as soon as ``stimma.library.save`` returns
it. The ``production`` block records the inputs the code path used that
lineage never sees: style preset, key colour, cleanup profile, frame budget,
target height, direction scheme, and tool ids.

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
DIRECTION_SCHEMES = ("side", "4-way", "8-way")

# Keys the production block knows. Unknown keys are kept (the schema is
# additive) but these are the ones the resume path reads.
PRODUCTION_KEYS = (
    "style",            # {"preset": "16-bit pixel", "fragment": "..."}
    "key",              # {"rgb": [r, g, b], "phrase": "plain solid ... background", "margin": 0.31}
    "cleanup_profile",  # {"name": "16-bit pixel", "overrides": {...}} — the apply_profile input
    "frame_budget",     # 16 | 25 | 49 ...
    "fps",              # playback fps used for every move
    "height_px",        # finalize(height=...)
    "direction_scheme", # side | 4-way | 8-way
    "anchor_padding",   # {"aspect": [w, h], "margin": 0.08} — pad_to_aspect inputs
    "tools",            # {"text_to_image": "provider:tool", "image_to_video": "provider:tool"}
)


def file_hash(path: "str | Path") -> str:
    """SHA-256 hex digest of a file — matches the app's media file_hash."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_ref(path: "str | Path") -> dict:
    """Hash-only reference for a file that has not been saved to the library yet."""
    return {"hash": file_hash(path)}


def media_ref(path: "str | Path", media_id: "int | None" = None) -> dict:
    """Reference for a file, with the library media id when it is known.

    ``media_id`` comes back from ``stimma.library.save(...)["media_id"]`` (or a
    ToolResult's ``media_id``). Always pass it when you have it: it is what a
    fresh chat walks lineage from.
    """
    ref = {"hash": file_hash(path)}
    if media_id is not None:
        ref["media_id"] = int(media_id)
    return ref


def as_ref(value, media_id: "int | None" = None) -> "dict | None":
    """Normalize a reference argument: a path, a ``{"hash", "media_id"}`` dict,
    or None. A separate ``media_id`` fills in a path's id."""
    if value is None:
        return None
    if isinstance(value, dict):
        ref = dict(value)
        if media_id is not None:
            ref["media_id"] = int(media_id)
        if not ref.get("hash"):
            raise ValueError("a media reference needs a hash")
        return ref
    return media_ref(value, media_id)


def set_media_id(ref: "dict | None", media_id: int) -> "dict | None":
    """Attach a media id to an existing reference (after a later library save)."""
    if ref is None:
        return None
    ref["media_id"] = int(media_id)
    return ref


def new_doc(title: str, *, style: str = "", description: str = "", production: "dict | None" = None) -> dict:
    """A fresh sprite document with no animations.

    Set ``base_image`` / ``base_image_nobg`` / ``portrait`` with media_ref()
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
        "production": dict(production or {}),
        "animations": [],
    }


def set_production(doc: dict, **fields) -> dict:
    """Record production inputs (see PRODUCTION_KEYS). Merges; returns the block."""
    block = doc.setdefault("production", {})
    for key, value in fields.items():
        if value is None:
            block.pop(key, None)
        else:
            block[key] = value
    return block


def _default_frame_meta() -> dict:
    return {"duration_ms": None, "rects": {}, "events": []}


def add_animation(
    doc: dict,
    name: str,
    animation_path: "str | Path | dict",
    *,
    frame_count: int,
    direction: "str | None" = None,
    fps: float = 12,
    loop: str = "loop",
    loop_start: "int | None" = None,
    loop_end: "int | None" = None,
    mirrored_from: "str | None" = None,
    source_video: "str | Path | dict | None" = None,
    anchor: "str | Path | dict | None" = None,
    prompt: "str | None" = None,
    media_id: "int | None" = None,
    durations_ms: "list[int | None] | None" = None,
) -> dict:
    """Add (or replace) the animation entry keyed by (name, direction).

    Args:
        animation_path: The move's animated WebP file (or a ref dict); hashed into the doc.
        media_id: Library media id of that WebP, when it has been saved already.
        source_video: The generated clip the frames came from (path or ref).
        anchor: The padded anchor image the clip was conditioned on (path or ref).
        prompt: The image-to-video prompt actually sent — the resume path re-uses it.
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
    animation = as_ref(animation_path, media_id)
    animation["format"] = "webp"
    entry = {
        "name": name,
        "direction": direction,
        "mirrored_from": mirrored_from,
        "fps": fps,
        "loop": loop,
        "loop_start": 0 if loop_start is None else loop_start,
        "loop_end": frame_count - 1 if loop_end is None else loop_end,
        "source_video": as_ref(source_video),
        "anchor": as_ref(anchor),
        "prompt": prompt,
        "animation": animation,
        "frame_count": frame_count,
        "frames": frames,
    }
    if not isinstance(animation_path, dict):
        from .encode import load_animation

        _, encoded_durations = load_animation(animation_path)
        animation["frame_indices"] = sprite_frame_indices(entry, encoded_durations)
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


def animation_key(entry: dict) -> str:
    d = entry.get("direction")
    return f"{entry['name']}_{d}" if d else entry["name"]


def iter_refs(doc: dict):
    """Yield ``(role, ref)`` for every media reference in the document."""
    for field_name in ("base_image", "base_image_nobg", "portrait"):
        ref = doc.get(field_name)
        if isinstance(ref, dict):
            yield field_name, ref
    for entry in doc.get("animations", []):
        key = animation_key(entry)
        for field_name in ("anchor", "source_video", "animation"):
            ref = entry.get(field_name)
            if isinstance(ref, dict):
                yield f"{key}/{field_name}", ref


def missing_media_ids(doc: dict) -> list[str]:
    """Roles whose reference has no media id yet — save those files to the library first."""
    return [role for role, ref in iter_refs(doc) if ref.get("media_id") is None]


def validate(doc: dict, *, require_media_ids: bool = False) -> list[str]:
    """Structural checks. Returns a list of problems; empty means valid.

    ``require_media_ids`` insists every reference carries a media id — the
    state a document must be in before it is saved to the library, so a fresh
    chat can walk from it.
    """
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
    production = doc.get("production")
    if production is not None and not isinstance(production, dict):
        errors.append("production must be an object")
    elif isinstance(production, dict):
        scheme = production.get("direction_scheme")
        if scheme is not None and scheme not in DIRECTION_SCHEMES:
            errors.append(f"production.direction_scheme must be one of {DIRECTION_SCHEMES}, got {scheme!r}")
    for role, ref in iter_refs(doc):
        if not ref.get("hash"):
            errors.append(f"{role}: reference needs a hash")
        if require_media_ids and ref.get("media_id") is None:
            errors.append(f"{role}: reference needs a media_id (save it to the library first)")
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


def save(doc: dict, path: "str | Path", *, require_media_ids: bool = False) -> Path:
    """Write the document. Path should end in .stimmasprite.json.

    Pass ``require_media_ids=True`` for the copy that goes to the library.
    """
    problems = validate(doc, require_media_ids=require_media_ids)
    if problems:
        raise ValueError("invalid sprite doc: " + "; ".join(problems))
    path = Path(path)
    if not path.name.endswith(DOC_SUFFIX):
        raise ValueError(f"sprite documents must end in {DOC_SUFFIX}: {path.name}")
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


def load(path: "str | Path") -> dict:
    doc = json.loads(Path(path).read_text())
    doc.setdefault("production", {})
    for entry in doc.get("animations", []):
        entry.setdefault("anchor", None)
        entry.setdefault("prompt", None)
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
        return animation_key(self.entry)

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
    or a workspace scan that hashes candidates. For a sprite loaded from the
    library, ``library_resolver(stimma)`` fetches each artifact by media id.
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


async def fetch_refs(stimma, doc: dict, *, roles: "list[str] | None" = None) -> dict:
    """Copy referenced library files into the workspace: ``{role: path}``.

    Uses the media id when present and ``stimma.library.by_hash`` otherwise.
    Pair with ``resolve_animations(doc, lambda h: paths_by_hash[h])``.
    """
    paths = {}
    for role, ref in iter_refs(doc):
        if roles is not None and role not in roles:
            continue
        if ref.get("media_id") is not None:
            info = await stimma.library.get(int(ref["media_id"]))
        else:
            info = await stimma.library.by_hash(ref["hash"])
        paths[role] = Path(info["path"])
    return paths


async def library_resolver(stimma, doc: dict):
    """Resolver over the document's animation artifacts fetched from the library."""
    paths = await fetch_refs(stimma, doc)
    by_hash = {}
    for entry in doc["animations"]:
        key = f"{animation_key(entry)}/animation"
        if key in paths:
            by_hash[entry["animation"]["hash"]] = paths[key]
    def resolve(h: str) -> Path:
        if h not in by_hash:
            raise KeyError(f"no animation with hash {h[:12]}… in the library")
        return by_hash[h]
    return resolve
