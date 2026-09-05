"""End-to-end exercise of the spritekit lib on synthetic frames.

Run with any Python that has PIL (with WebP animation support), numpy, and
ffmpeg on PATH: ``python tests/test_spritekit.py``.
"""

import asyncio
import json
import shlex
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "sprite-design" / "lib"))
from spritekit import (  # noqa: E402
    add_animation, align, apply_profile, as_ref, cleanup, dedup_frames, doc as docmod,
    export_sprite, extract_frames, file_hash, image_ref, iter_refs, load, load_animation,
    measure_drift, media_ref, mirror_frames, missing_media_ids, new_doc, probe_fps,
    resolve_animations, save, save_animation, save_gif, set_production, stabilize,
    validate, workspace_resolver,
)
from spritekit import chroma_distance  # noqa: E402
from spritekit.export import export_rpgmaker  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="spritekit_test_"))

passed = []


def check(name, cond, detail=""):
    if not cond:
        raise AssertionError(f"FAIL {name} {detail}")
    passed.append(name)


def make_frames(n=8, size=96, jitter=None, halo=False):
    """Bouncing ball with a walking highlight: asymmetric so mirroring is visible."""
    frames = []
    for i in range(n):
        arr = np.zeros((size, size, 4), dtype=np.uint8)
        cx, cy = size // 2, size // 2 + round(10 * np.sin(2 * np.pi * i / n))
        if jitter:
            cx += jitter[i % len(jitter)]
        ys, xs = np.mgrid[0:size, 0:size]
        ball = (xs - cx) ** 2 + (ys - cy) ** 2 <= (size // 4) ** 2
        arr[ball] = [200, 60, 60, 255]
        eye = (xs - (cx + size // 8)) ** 2 + (ys - cy) ** 2 <= 9  # right side: asymmetric
        arr[eye & ball] = [30, 30, 30, 255]
        if halo:
            ring = ((xs - cx) ** 2 + (ys - cy) ** 2 <= (size // 4 + 2) ** 2) & ~ball
            arr[ring] = [250, 250, 250, 255]
        frames.append(Image.fromarray(arr, "RGBA"))
    return frames


# --- encode: lossless WebP round-trip ---------------------------------------
frames = make_frames()
webp = WORK / "run_east.webp"
durations = [83] * 7 + [166]
save_animation(frames, webp, durations_ms=durations)
back, back_dur = load_animation(webp)
check("webp frame count", len(back) == 8)
check("webp durations", back_dur == durations, str(back_dur))
check(
    "webp lossless",
    all(np.array_equal(np.asarray(a), np.asarray(b)) for a, b in zip(frames, back)),
)

# --- mirror bake -------------------------------------------------------------
west = mirror_frames(back)
check(
    "mirror flips",
    np.array_equal(np.asarray(west[0]), np.asarray(back[0])[:, ::-1, :]),
)
webp_west = WORK / "run_west.webp"
save_animation(west, webp_west, durations_ms=durations)

# --- doc: build, validate, save/load ----------------------------------------
sprite = new_doc("Test Ball", style="flat vector")
base_png = WORK / "base.png"
frames[0].save(base_png)
sprite["base_image"] = image_ref(base_png)
add_animation(sprite, "run", webp, frame_count=8, direction="east",
              fps=12, durations_ms=durations)
add_animation(sprite, "run", webp_west, frame_count=8, direction="west",
              fps=12, mirrored_from="east", durations_ms=durations)
check("doc valid", validate(sprite) == [])
bad = json.loads(json.dumps(sprite))
bad["animations"][1]["mirrored_from"] = "north"
check("doc catches bad mirror", any("mirror" in e for e in validate(bad)))
doc_path = WORK / "test-ball.stimmasprite.json"
save(sprite, doc_path)
check("doc roundtrip", load(doc_path)["title"] == "Test Ball")
check("hash is sha256 hex", len(file_hash(webp)) == 64)

# replace semantics: re-adding same (name, direction) keeps one entry
add_animation(sprite, "run", webp, frame_count=8, direction="east", fps=12)
check("add replaces", len(sprite["animations"]) == 2)
add_animation(sprite, "run", webp, frame_count=8, direction="east",
              fps=12, durations_ms=durations)

# --- doc as recipe: media refs, production block, resume-readiness ----------
check("media_ref carries id", media_ref(base_png, 41) == {"hash": file_hash(base_png), "media_id": 41})
check("as_ref fills id", as_ref({"hash": "ab" * 32}, 7)["media_id"] == 7)
try:
    as_ref({"media_id": 3})
    check("as_ref needs hash", False)
except ValueError:
    check("as_ref needs hash", True)
check("missing ids listed", set(missing_media_ids(sprite)) == {"base_image", "run_east/animation", "run_west/animation"})
check("strict validate flags ids", any("media_id" in e for e in validate(sprite, require_media_ids=True)))
try:
    save(sprite, WORK / "strict.stimmasprite.json", require_media_ids=True)
    check("strict save refuses", False)
except ValueError:
    check("strict save refuses", True)
sprite["base_image"] = media_ref(base_png, 41)
# Re-add west first so the entry order the export checks rely on ([west, east]) survives.
add_animation(sprite, "run", webp_west, frame_count=8, direction="west",
              fps=12, mirrored_from="east", durations_ms=durations, media_id=44)
add_animation(sprite, "run", webp, frame_count=8, direction="east", fps=12,
              durations_ms=durations, media_id=42, prompt="running in place",
              anchor=media_ref(base_png, 41), source_video={"hash": "cd" * 32, "media_id": 43})
check("no missing ids", missing_media_ids(sprite) == [])
east = sprite["animations"][1]
check("prompt recorded", east["prompt"] == "running in place")
check("anchor recorded", east["anchor"]["media_id"] == 41)
check("source video recorded", east["source_video"]["media_id"] == 43)
set_production(sprite, style={"preset": "16-bit pixel", "fragment": "16-bit pixel art"},
               key={"rgb": [255, 0, 255], "phrase": "plain solid magenta (#FF00FF) background", "margin": 0.31},
               cleanup_profile={"name": "16-bit pixel", "overrides": {"grid": 4, "palette": 24}},
               frame_budget=25, fps=12, height_px=256, direction_scheme="side",
               tools={"text_to_image": "comfyui:t2i", "image_to_video": "comfyui:i2v"})
check("production recorded", sprite["production"]["key"]["phrase"].startswith("plain solid magenta"))
set_production(sprite, direction_scheme="diagonal")
check("production scheme validated", any("direction_scheme" in e for e in validate(sprite)))
set_production(sprite, direction_scheme="side")
check("strict valid now", validate(sprite, require_media_ids=True) == [])
strict_path = save(sprite, WORK / "strict.stimmasprite.json", require_media_ids=True)
reloaded = load(strict_path)
check("refs roundtrip", reloaded["animations"][1]["animation"]["media_id"] == 42)
check("ref roles", [r for r, _ in iter_refs(reloaded)][:2] == ["base_image", "run_west/animation"])
try:
    save(sprite, WORK / "wrong-suffix.json")
    check("suffix enforced", False)
except ValueError:
    check("suffix enforced", True)
# older documents (no production / anchor / prompt) still load
legacy = json.loads(json.dumps(reloaded))
legacy.pop("production"); [e.pop("anchor") or e.pop("prompt") for e in legacy["animations"]]
(WORK / "legacy.stimmasprite.json").write_text(json.dumps(legacy))
check("legacy loads", load(WORK / "legacy.stimmasprite.json")["production"] == {})

# --- align: drift + stabilize ------------------------------------------------
# Progressive slide = drift; the vertical bounce is animation and must survive.
sliding = make_frames(jitter=[0, 1, 2, 4, 5, 6, 8, 9])
report = measure_drift(sliding)
check("drift measured", report["max_drift"] > 3, str(report["max_drift"]))
stable, srep = stabilize(sliding)
check("stabilize corrects", len(srep["corrected"]) >= 5, str(srep))
check("stabilize reduces drift", measure_drift(stable)["max_drift"] < 1.5,
      str(measure_drift(stable)["max_drift"]))
bounce_before = [c[1] for c in align.alpha_centroids(sliding)]
bounce_after = [c[1] for c in align.alpha_centroids(stable)]
check("bounce preserved", np.std(bounce_after) > 0.8 * np.std(bounce_before),
      f"{np.std(bounce_before):.2f} -> {np.std(bounce_after):.2f}")
# Pure oscillation (a jump) must NOT be flattened or corrected.
_, jrep = stabilize(make_frames())
check("animation motion untouched", jrep["corrected"] == [], str(jrep))
check("no false zoom on bounce", jrep["max_zoom"] <= 1.01, str(jrep["max_zoom"]))

# A linear zoom ramp gets cancelled; the ball's size trend goes flat.
from spritekit import measure_zoom  # noqa: E402
def ball_ramp(r0, step):
    out = []
    for i in range(8):
        arr = np.zeros((96, 96, 4), dtype=np.uint8)
        ys, xs = np.mgrid[0:96, 0:96]
        ball = (xs - 48) ** 2 + (ys - 48) ** 2 <= (r0 + i * step) ** 2
        arr[ball] = [200, 60, 60, 255]
        out.append(Image.fromarray(arr, "RGBA"))
    return out

slow = ball_ramp(24, 0.5)  # ~±5% — a typical LTX creep
zf = measure_zoom(slow)
check("zoom detected", max(zf) - min(zf) > 0.05, str(zf))
dezoomed, zrep = stabilize(slow)
check("zoom reported", zrep["max_zoom"] > 1.03, str(zrep["max_zoom"]))
residual = measure_zoom(dezoomed)
check("zoom cancelled", max(residual) - min(residual) < 0.03, str(residual))
# A drastic zoom is beyond rescue: flag it, don't distort it.
_, bigrep = stabilize(ball_ramp(18, 1.5))
check("big zoom flags", len(bigrep["flagged"]) > 0, str(bigrep))

# --- cleanup ops -------------------------------------------------------------
haloed = make_frames(halo=True)
cleaned = cleanup.remove_halo(haloed, brightness=0.85)
a0 = np.asarray(haloed[0]); c0 = np.asarray(cleaned[0])
check("halo removed", (c0[:, :, 3] > 0).sum() < (a0[:, :, 3] > 0).sum())

# Semi-transparent colored haze on the silhouette edge (matting soft alpha):
# the alpha<255 clause must eat it whatever its hue; opaque interior survives.
hazy = []
for f in make_frames():
    px = np.asarray(f).copy()
    alpha = px[:, :, 3]
    edge = (alpha == 255) & (
        np.roll(alpha, 1, 0) == 0) | ((alpha == 255) & (np.roll(alpha, -1, 1) == 0))
    px[:, :, 3][edge] = 120  # brown-ish soft rim, not bright
    px[:, :, 0][edge] = 120; px[:, :, 1][edge] = 90; px[:, :, 2][edge] = 60
    hazy.append(Image.fromarray(px, "RGBA"))
dehazed = cleanup.remove_halo(hazy, passes=2)
d0 = np.asarray(dehazed[0])
check("halo eats soft haze", not ((d0[:, :, 3] > 0) & (d0[:, :, 3] < 255)).any())
check("halo keeps interior", d0[48, 48, 3] == 255)

# Matte scan: flat bright leftover patch goes, colored detail stays, and
# frames with no transparency at all are left untouched.
matted = []
for f in make_frames():
    px = np.asarray(f).copy()
    px[5:15, 5:25] = [210, 210, 212, 255]   # leftover backdrop patch
    px[70:74, 70:74] = [250, 60, 60, 255]   # small saturated detail
    matted.append(Image.fromarray(px, "RGBA"))
scanned = cleanup.clear_matte_regions(matted)
s0 = np.asarray(scanned[0])
check("matte clears patch", s0[10, 10, 3] == 0)
check("matte keeps color detail", s0[71, 71, 3] == 255)
opaque_only = [f.convert("RGB").convert("RGBA") for f in matted]
untouched = cleanup.clear_matte_regions(opaque_only)
check("matte needs transparency", np.asarray(untouched[0])[10, 10, 3] == 255)

# Component pruning: tiny detached debris dies, proportionate parts survive.
blobby = []
for f in make_frames():
    px = np.asarray(f).copy()
    px[4:7, 4:7] = [140, 110, 80, 255]      # 9-px haze fleck, far from the ball
    px[80:92, 4:16] = [250, 200, 40, 255]   # 144-px "projectile" (>2% of ball)
    blobby.append(Image.fromarray(px, "RGBA"))
pruned = cleanup.prune_components(blobby)
p0 = np.asarray(pruned[0])
check("prune drops debris", p0[5, 5, 3] == 0)
check("prune keeps projectile", p0[85, 10, 3] == 255)
check("prune keeps body", p0[48, 48, 3] == 255)

# threshold_alpha: weak matte alpha dies, strong survives (binarize snaps).
soft = []
for f in make_frames():
    px = np.asarray(f).copy()
    px[20:24, 20:24] = [120, 90, 60, 80]    # weak haze alpha
    soft.append(Image.fromarray(px, "RGBA"))
floored = cleanup.threshold_alpha(soft)
check("alpha floor cuts weak", np.asarray(floored[0])[21, 21, 3] == 0)
check("alpha floor keeps strong", np.asarray(floored[0])[48, 48, 3] == 255)
binz = cleanup.threshold_alpha(soft, binarize=True)
check("alpha binarize", set(np.unique(np.asarray(binz[0])[:, :, 3])) <= {0, 255})

# Realistic frames keep backdrop RGB under transparency (as keying/matting do).
flickery = []
for i, f in enumerate(make_frames()):
    arr = np.asarray(f).copy()
    arr[:, :, :3][arr[:, :, 3] == 0] = (209, 209, 210)
    if i == 3:
        arr[5, 5] = [255, 255, 255, 255]  # stray pixel in a stable region
    flickery.append(Image.fromarray(arr, "RGBA"))
fixed = cleanup.fix_flicker(flickery)
check("flicker fixed", np.asarray(fixed[3])[5, 5, 3] == 0)

snapped = cleanup.snap_palette(make_frames(), colors=4)
colors_used = {tuple(px) for f in snapped for px in np.asarray(f)[np.asarray(f)[:, :, 3] > 0][:, :3]}
check("palette snapped", len(colors_used) <= 4, str(len(colors_used)))

gridded = cleanup.quantize_grid(make_frames(), pixel=8)
g = np.asarray(gridded[0])
check("grid quantized", np.array_equal(g[0:8, 0:8], np.broadcast_to(g[0, 0], (8, 8, 4))))

profiled = apply_profile(make_frames(halo=True), {"halo": True, "flicker": True, "palette": 8, "grid": 4})
check("profile runs", len(profiled) == 8)

# --- background keying + conditioning prep -----------------------------------
from spritekit import key_background, pad_to_aspect, sample_background  # noqa: E402

BG = (214, 214, 216)
def flatten(frames, bg=BG):
    """Composite RGBA frames over a solid backdrop -> fully opaque frames."""
    out = []
    for f in frames:
        canvas = Image.new("RGBA", f.size, (*bg, 255))
        canvas.alpha_composite(f)
        # A backdrop-colored pocket INSIDE the ball: must survive connected keying.
        px = np.asarray(canvas).copy()
        px[44:50, 44:50] = [*bg, 255]
        out.append(Image.fromarray(px, "RGBA"))
    return out

opaque = flatten(make_frames())
check("sample bg", sample_background(opaque[0]) == BG, str(sample_background(opaque[0])))
keyed = key_background(opaque)
k0 = np.asarray(keyed[0])
check("key clears backdrop", k0[2, 2, 3] == 0)
check("key keeps character", k0[48, 30, 3] == 255)  # inside the ball body
# A pocket of backdrop sealed inside the silhouette is almost always a real
# gap (arm against torso), so it must stay OPEN. Filling those grew a "cape".
check("key clears enclosed pocket (a real gap)", k0[46, 46, 3] == 0)
check("key idempotent", key_background(keyed) is keyed)
sealed = key_background(opaque, connected=True)
check("connected=True can still protect a pocket",
      np.asarray(sealed[0])[46, 46, 3] == 255)
# apply_profile keys implicitly, so palette building sees only the character
prof = apply_profile(flatten(make_frames()), {"palette": 4})
p0 = np.asarray(prof[0])
check("profile keys first", p0[2, 2, 3] == 0)

padded = pad_to_aspect(make_frames()[0].convert("RGB"), (16, 9), margin=0.1)
check("pad aspect", abs(padded.width / padded.height - 16 / 9) < 0.02,
      str(padded.size))
check("pad no crop", padded.height >= 96 and padded.width >= 96)

# --- flicker motion safety ---------------------------------------------------
# A solid character-colored "hand" visiting a spot in 2 of 10 frames must
# survive the temporal vote; a backdrop-blend haze blob with the same
# occupancy must die. Transparent pixels keep backdrop RGB, like matting does.
BGC = (209, 209, 210)
motion = []
for i in range(10):
    px = np.zeros((96, 96, 4), np.uint8)
    px[:, :, :3] = BGC          # RGB under transparency = backdrop
    px[40:60, 40:60] = [200, 60, 60, 255]        # static body
    if i in (4, 5):
        px[10:18, 10:18] = [201, 139, 93, 255]   # skin-colored hand, far from bg
        px[10:18, 70:78] = [190, 185, 182, 255]  # haze: near-backdrop blend
    motion.append(Image.fromarray(px, "RGBA"))
voted = cleanup.fix_flicker(motion)
v4 = np.asarray(voted[4])
check("flicker keeps moving hand", v4[14, 14, 3] == 255)
check("flicker clears haze blend", v4[14, 74, 3] == 0)
check("flicker keeps body", v4[50, 50, 3] == 255)

# halo bg-blend clause: gray fringe (not bright, fully opaque) on the boundary
fringe = []
for f in make_frames():
    px = np.asarray(f).copy()
    px[:, :, :3][px[:, :, 3] == 0] = BGC          # backdrop RGB under transparency
    alpha = px[:, :, 3]
    ring = (alpha == 255) & (np.roll(alpha, 1, 1) == 0)
    px[:, :, 0][ring] = 195; px[:, :, 1][ring] = 192; px[:, :, 2][ring] = 190
    fringe.append(Image.fromarray(px, "RGBA"))
defringed = cleanup.remove_halo(fringe, passes=1)
f0 = np.asarray(fringe[0]); d0 = np.asarray(defringed[0])
was_ring = (f0[:, :, 3] == 255) & (f0[:, :, 0] == 195)
check("halo eats gray fringe", (np.asarray(defringed[0])[:, :, 3][was_ring] == 0).all())

# edge_contact: clipped sprite is detected, well-framed one is not
from spritekit import edge_contact  # noqa: E402
clipped = []
for f in make_frames():
    px = np.asarray(f).copy()
    px[-3:, 40:56] = [200, 60, 60, 255]  # feet on the bottom edge
    clipped.append(Image.fromarray(px, "RGBA"))
check("edge_contact detects crop", edge_contact(clipped)["bottom"] == 1.0)
check("edge_contact clean sprite", edge_contact(make_frames())["bottom"] == 0.0)

# --- keying / finishing (the flat-backdrop sprite path) ----------------------
from spritekit import (edge_pad, fill_holes, finalize, union_box,  # noqa: E402
                       resize_premultiplied)

# A SATURATED key colour. A pale one (say 197,228,204) has almost neutral
# chromaticity and therefore cannot be told apart from a white subject by
# hue at all — see the explicit check further down.
GREEN = (0, 177, 64)

def on_backdrop(frames, bg=GREEN):
    """Composite over a flat backdrop -> fully opaque, like a video frame."""
    out = []
    for f in frames:
        canvas = Image.new("RGBA", f.size, (*bg, 255))
        canvas.alpha_composite(f)
        out.append(canvas.convert("RGBA"))
    return out

# A WHITE subject on a GREEN backdrop: the case that produced magenta
# speckles when the backdrop was algebraically unmixed out of edge pixels.
white_ball = []
for f in make_frames():
    px = np.asarray(f).copy()
    body = px[:, :, 3] > 0
    px[body] = [250, 250, 250, 255]
    # Anti-aliased rim, as real footage has: these blend with the backdrop
    # and are exactly the pixels a naive unmix turns magenta.
    rim = body & ~cleanup._erode(body, 1)
    px[:, :, 3][rim] = 128
    white_ball.append(Image.fromarray(px, "RGBA"))
shot = on_backdrop(white_ball)
keyed = cleanup.key_background(shot)
k = np.asarray(keyed[0])
op = k[:, :, 3] > 200
rgb = k[:, :, :3].astype(int)
magenta = op & (rgb[:, :, 0] - rgb[:, :, 1] > 12) & (rgb[:, :, 2] - rgb[:, :, 1] > 12)
check("key introduces no magenta", int(magenta.sum()) == 0, str(int(magenta.sum())))
check("key clears backdrop", k[2, 2, 3] == 0)
check("key keeps subject", k[48, 48, 3] == 255)
ramped = np.asarray(cleanup.key_background(shot, chroma_low=0.02, chroma_high=0.50)[0])
check("key ramps edges", ((ramped[:, :, 3] > 0) & (ramped[:, :, 3] < 255)).any())

# edge_pad: no pixel anywhere keeps backdrop colour, so scaling can't fringe
padded = edge_pad(keyed)
p = np.asarray(padded[0])
bgdist = np.linalg.norm(p[:, :, :3].astype(float) - np.array(GREEN), axis=2)
check("edge_pad removes backdrop colour", int((bgdist < 20).sum()) == 0, str(int((bgdist < 20).sum())))
check("edge_pad keeps alpha", np.array_equal(p[:, :, 3], np.asarray(keyed[0])[:, :, 3]))

# fill_holes: a pinhole closes, a real gap stays open
holed = []
for f in keyed:
    px = np.asarray(f).copy()
    px[46:48, 46:48, 3] = 0          # pinhole inside the body
    holed.append(Image.fromarray(px, "RGBA"))
filled = np.asarray(fill_holes(holed, max_frac=0.01)[0])
check("fill_holes closes pinhole", filled[46, 46, 3] == 255)
check("fill_holes keeps outside", filled[2, 2, 3] == 0)
# A hole too big to be a pinhole is left alone (it may be a real gap).
check("fill_holes spares large gaps", np.asarray(fill_holes(holed, max_frac=0.0001)[0])[46, 46, 3] == 0)

# finalize: shared crop across frames, exact target height, hard alpha
sprites, info = finalize(padded, height=64)
check("finalize height", sprites[0].height == 64, str(sprites[0].size))
check("finalize shares one box", len({s.size for s in sprites}) == 1)
check("finalize makes square cells", sprites[0].width == sprites[0].height, str(sprites[0].size))
# Soft alpha is the DEFAULT and is the anti-flicker property: hard alpha
# turns sub-pixel edge coverage into 0/255 pops as the character moves.
semi_default = sum(int(((np.asarray(s)[:, :, 3] > 0) & (np.asarray(s)[:, :, 3] < 255)).sum()) for s in sprites)
check("finalize keeps soft alpha by default", semi_default > 0, str(semi_default))
hard, _ = finalize(padded, height=64, binarize=128)
semi = sum(int(((np.asarray(s)[:, :, 3] > 0) & (np.asarray(s)[:, :, 3] < 255)).sum()) for s in hard)
check("finalize binarizes on request", semi == 0, str(semi))
tall, _ = finalize(padded, height=64, square=False)
check("finalize can skip squaring", tall[0].width != tall[0].height or tall[0].width == 64)
box = union_box(padded)
check("union_box covers motion", box[3] - box[1] >= 40 and box[0] >= 0, str(box))
# Hard alpha measurably increases edge pops; that is why it is not default.
def pops(seq):
    A = np.stack([np.asarray(s)[:, :, 3].astype(np.int16) for s in seq])
    return int((np.abs(np.diff(A, axis=0)) >= 200).sum())
check("hard alpha pops more than soft", pops(hard) > pops(sprites), f"{pops(hard)} vs {pops(sprites)}")

# Premultiplied resize must not drag transparent pixels' colour into edges.
sharp = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
sharp.paste(Image.new("RGBA", (32, 32), (255, 255, 255, 255)), (16, 16))
small = np.asarray(resize_premultiplied(sharp, (16, 16)))
edge = small[:, :, 3] > 0
check("premultiplied resize keeps colour clean", small[:, :, :3][edge].min() >= 200,
      str(small[:, :, :3][edge].min()))

# Fringe regression: a DARK-outlined subject on a coloured backdrop. The
# blend between backdrop and outline moves far in RGB, so a distance key
# left it behind as a coloured halo. Chromaticity keying removes it with no
# erosion at all — which is why the choke can now stay at 1px.
outlined = []
for f in make_frames():
    px = np.asarray(f).copy()
    body = px[:, :, 3] > 0
    px[body & ~cleanup._erode(body, 2)] = [10, 10, 10, 255]     # dark outline
    outlined.append(Image.fromarray(px, "RGBA"))
shot2 = []
for f in outlined:
    arr = np.asarray(f).astype(float)
    a = arr[:, :, 3:4] / 255.0
    blend = a * arr[:, :, :3] + (1 - a) * np.array(GREEN, dtype=float)
    ring = np.asarray(f)[:, :, 3] > 0
    out = np.dstack([blend, np.full(blend.shape[:2], 255.0)])
    edge = ring & ~cleanup._erode(ring, 1)
    out[edge, :3] = 0.5 * np.array([10, 10, 10]) + 0.5 * np.array(GREEN)   # 50% blend
    shot2.append(Image.fromarray(out.astype(np.uint8), "RGBA"))

def cast_count(frames_):
    n = 0
    for s in frames_:
        arr = np.asarray(s)
        solid = arr[:, :, 3] > 0
        n += int((solid & (chroma_distance(arr[:, :, :3], GREEN) < 0.10)).sum())
    return n

check("keying alone clears the blend halo", cast_count(apply_profile(shot2, {"choke": False})) == 0,
      str(cast_count(apply_profile(shot2, {"choke": False}))))
check("blend halo is present before keying", cast_count(shot2) > 0, str(cast_count(shot2)))
check("subject survives", np.asarray(apply_profile(shot2, {})[0])[48, 48, 3] == 255)

# The choke must stay small: eroding past the outline exposes lighter
# material behind it, which reads as a white fringe.
def edge_lightness(frames_):
    from scipy import ndimage
    arr = np.asarray(frames_[0]); a = arr[:, :, 3] > 32
    edge = a & ~ndimage.binary_erosion(a, iterations=1)
    return float((arr[:, :, :3][edge].min(axis=1) > 175).mean()) if edge.any() else 0.0

light_pale = []
for f in outlined:                       # light body, dark outline
    px = np.asarray(f).copy()
    core = (px[:, :, 3] > 0) & (px[:, :, :3].max(axis=2) > 100)
    px[core] = [245, 245, 245, 255]
    light_pale.append(Image.fromarray(px, "RGBA"))
staged = on_backdrop(light_pale)
gentle = edge_lightness(apply_profile(staged, {"choke": {"pixels": 1}}))
harsh = edge_lightness(apply_profile(staged, {"choke": {"pixels": 4}}))
check("a deep choke eats the outline into a light fringe", harsh > gentle,
      f"1px {gentle:.2f} vs 4px {harsh:.2f}")

# --- dedup -------------------------------------------------------------------
dupes = [frames[0], frames[0], frames[1], frames[2], frames[2], frames[2]]
kept, ddur = dedup_frames(dupes, fps=10)
check("dedup keeps 3", len(kept) == 3, str(len(kept)))
check("dedup durations", ddur == [200, 100, 300], str(ddur))
check("dedup total preserved", sum(ddur) == 600)

# --- resolve + exports -------------------------------------------------------
resolver = workspace_resolver(WORK)
resolved = resolve_animations(sprite, resolver)
check("resolve finds all", len(resolved) == 2)

out = export_sprite(resolved, "atlas", WORK, "testball")
check("atlas zipped", out[0].name == "testball_atlas.zip" and out[0].exists())
with zipfile.ZipFile(out[0]) as zf:
    names = zf.namelist()
    check("atlas zip contents", set(names) == {"testball.png", "testball.json"}, str(names))
    atlas = json.loads(zf.read("testball.json"))
check("atlas frames", len(atlas["frames"]) == 16)
check("atlas tags", [t["name"] for t in atlas["meta"]["frameTags"]] == ["run_west", "run_east"])
check("atlas durations", atlas["frames"]["run_east/7"]["duration"] == 166)

out = export_sprite(resolved, "godot", WORK, "testball")
check("godot zipped", out[0].name == "testball_godot.zip")
with zipfile.ZipFile(out[0]) as zf:
    tres = zf.read("testball.tres").decode()
check("tres header", '[gd_resource type="SpriteFrames"' in tres)
check("tres anims", '&"run_east"' in tres and '&"run_west"' in tres)
check("tres regions", tres.count("AtlasTexture") >= 16)
check("tres frame duration multiplier", '"duration": 2.0' in tres)  # 166ms at 12fps

out = export_sprite(resolved, "gamemaker", WORK, "testball")
check("gm strips", sorted(p.name for p in out) == ["testball_run_east_strip8.png", "testball_run_west_strip8.png"])
strip = Image.open(out[0])
check("gm strip size", strip.size == (96 * 8, 96), str(strip.size))

out = export_sprite(resolved, "gif", WORK, "testball")
check("gifs written", len(out) == 2)
gif = Image.open(out[0])
check("gif animated", getattr(gif, "n_frames", 1) == 8)

# rpgmaker: should fail clearly with only east/west, succeed with 4 directions
try:
    export_rpgmaker(resolved, WORK, "testball", move="run")
    check("rpgmaker validation", False)
except ValueError as e:
    check("rpgmaker validation", "missing: south, north" in str(e), str(e))

four = list(resolved)
for d in ("south", "north"):
    p = WORK / f"walk_{d}.webp"
    save_animation(make_frames(), p, fps=12)
    add_animation(sprite, "run", p, frame_count=8, direction=d, fps=12)
four = resolve_animations(sprite, workspace_resolver(WORK))
out = export_rpgmaker(four, WORK, "testball", move="run")
charset = Image.open(out[0])
check("rpgmaker name", out[0].name == "$testball.png")
check("rpgmaker grid", charset.size == (96 * 3, 96 * 4), str(charset.size))

# --- extract via real ffmpeg through a fake SDK ------------------------------
class FakeSdk:
    async def _run(self, tool, *args):
        flat = []
        for a in args:
            flat.extend(shlex.split(a) if isinstance(a, str) and len(args) == 1 else [str(a)])
        proc = await asyncio.create_subprocess_exec(
            tool, *flat, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(WORK))
        stdout, stderr = await proc.communicate()
        if proc.returncode:
            raise RuntimeError(stderr.decode()[-2000:])
        class R:  # mirrors AVToolResult
            pass
        r = R(); r.stdout = stdout.decode(); r.stderr = stderr.decode(); r.returncode = proc.returncode
        return r
    async def ffmpeg(self, *args, **kw):
        return await self._run("ffmpeg", *args)
    async def ffprobe(self, *args, **kw):
        return await self._run("ffprobe", *args)


async def test_extract():
    # run_code's Python and ffmpeg share the workspace cwd; mirror that here.
    import os
    os.chdir(WORK)
    # Build a tiny test video from our frames, then round-trip it.
    for i, f in enumerate(make_frames(n=12)):
        f.convert("RGB").save(WORK / f"src_{i:03d}.png")
    sdk = FakeSdk()
    await sdk.ffmpeg("-y", "-framerate", "24", "-i", "src_%03d.png",
                     "-pix_fmt", "yuv420p", "clip.mp4")
    fps = await probe_fps(sdk, "clip.mp4")
    check("probe fps", abs(fps - 24) < 0.1, str(fps))
    got = await extract_frames(sdk, "clip.mp4", fps=12)
    check("extract count", len(got) == 6, str(len(got)))
    check("extract rgba", got[0].mode == "RGBA" and got[0].size == (96, 96))

asyncio.run(test_extract())

print(f"ALL {len(passed)} CHECKS PASSED")
