"""SpriteKit — sprite documents, frame cleanup, and engine exports for run_code.

Pipeline: extract frames from an i2v clip -> stabilize -> cleanup ->
encode one animated lossless WebP per move -> record it in a
.stimmasprite.json document -> export engine formats at the end.

Submodules stay importable for the full API (``from spritekit import
cleanup``); the names below cover the standard flow.
"""

from . import align, cleanup, doc, encode, export, extract, finish, pack, prep
from .align import edge_contact, measure_drift, measure_zoom, stabilize
from .cleanup import (
    apply_profile, auto_tolerance, choke_matte, chroma_distance, denoise_matte,
    despill, keyness, smooth_silhouette, thin_gaps, stabilize_matte, clear_matte_regions, edge_pad, fill_holes, key_background,
    prune_components, remove_halo, sample_background, threshold_alpha,
)
from .prep import KEY_COLORS, compose_on, pad_to_aspect, pick_key_color
from .doc import (
    DIRECTIONS,
    MIRROR_PAIRS,
    PRODUCTION_KEYS,
    ResolvedAnimation,
    add_animation,
    animation_key,
    as_ref,
    fetch_refs,
    file_hash,
    image_ref,
    iter_refs,
    library_resolver,
    load,
    media_ref,
    missing_media_ids,
    new_doc,
    resolve_animations,
    save,
    set_media_id,
    set_production,
    validate,
    workspace_resolver,
)
from .encode import load_animation, mirror_frames, save_animation, save_gif
from .export import TARGETS, export_sprite
from .finish import (finalize, find_loop, frame_distance, pingpong,
                     resize_premultiplied, trim_to_loop, union_box)
from .extract import (FRAME_BUDGETS, dedup_frames, extract_frames, load_frames,
                      probe_fps, sample_frames, save_frames)

__all__ = [
    "align", "cleanup", "doc", "encode", "export", "extract", "finish", "pack", "prep",
    "edge_contact", "measure_drift", "measure_zoom", "stabilize", "apply_profile", "key_background",
    "remove_halo", "clear_matte_regions", "threshold_alpha", "prune_components",
    "auto_tolerance", "choke_matte", "chroma_distance", "denoise_matte",
    "despill", "keyness", "smooth_silhouette", "thin_gaps", "stabilize_matte", "edge_pad", "fill_holes", "finalize", "resize_premultiplied", "union_box",
    "find_loop", "trim_to_loop", "pingpong", "frame_distance",
    "sample_background", "pad_to_aspect", "pick_key_color", "compose_on", "KEY_COLORS", "save_frames", "load_frames",
    "DIRECTIONS", "MIRROR_PAIRS", "PRODUCTION_KEYS", "ResolvedAnimation",
    "add_animation", "animation_key", "as_ref", "fetch_refs", "file_hash", "image_ref",
    "iter_refs", "library_resolver", "load", "media_ref", "missing_media_ids", "new_doc",
    "resolve_animations", "save", "set_media_id", "set_production", "validate",
    "workspace_resolver",
    "load_animation", "mirror_frames", "save_animation", "save_gif",
    "TARGETS", "export_sprite",
    "dedup_frames", "extract_frames", "probe_fps", "sample_frames", "FRAME_BUDGETS",
]
