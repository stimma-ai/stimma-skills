"""Package approved sprite pixels through the app's canonical export writers."""
import io
import json
import zipfile

from packages.recipes import Build, Input, Param, recipe
from sprite_export import SpriteExportOptions, run_sprite_export
from sprite_source import read_source


@recipe(
    id="sprite-assets", version=1, display_name="Sprite assets",
    description="Registered sprite frames, atlas, animation metadata and optional Godot 4 resource from a prepared sprite source archive. Repeat for actors, terrain, props and backgrounds.",
    inputs=[Input("source", kind="file", description="ZIP produced by spritekit.package_source: source.json plus approved PNG frames")],
    params=[Param("godot", type="boolean", default=False, description="Also emit Godot 4 SpriteFrames (.tres); full-animation loops only"),
            Param("padding", type="integer", default=2, minimum=0, maximum=16),
            Param("pixels_per_unit", type="integer", default=32, minimum=1, maximum=1024)],
    guidance="""Use sprite-design's spritekit.package_source to freeze reviewed frames into one source
archive per actor or coherent static set. All moves of one actor share the exact canvas,
scale and pivot before packaging. This recipe validates and exports; it does not create,
key, align or invent motion. Repeat this recipe in one package for the game's asset families.

Outputs: frames/<animation>/frame_000.png, atlas/<name>.png and .json, and asset.json.
asset.json explicitly lists frame paths in playback order, milliseconds, loop bounds,
facing and top-left normalized pivot. The atlas is a JSON hash with explicit rectangles;
padding is excluded from rectangles. Godot is optional; its .tres and PNG stay together.
Unity first-version handoff is PNG + documented manual import settings, not native JSON
import or a tested editor plugin. Keep original artwork and editable sources as members.

Author the cover yourself using the packaging skill and kit. Show a scene composed from
actual final assets, representative frames at game scale, and the chosen animation scope.
Animation strips are images: use readable crops/contact sheets rather than shrinking a
very wide atlas onto a PDF page. Show alpha against a neutral background. Identify drafts
versus selected work. Include a short game-facing inventory linking actual run paths,
collision/weapon placement notes and which direction may be mirrored. Describe unresolved
visual or import limitations honestly. The recipe supplies data and README, never cover HTML.""",
)
def build(b: Build) -> None:
    source, usage = read_source(b.path("source"))
    targets = [("frames", "frames"), ("atlas-hash", "atlas")]
    if b.params.godot:
        targets.append(("godot", "godot"))
    manifest = None
    for target, folder in targets:
        result = run_sprite_export(source, SpriteExportOptions(format=target, padding=b.params.padding))
        with zipfile.ZipFile(io.BytesIO(result.payload)) as archive:
            for name in archive.namelist():
                if name == "manifest.json":
                    if manifest is None:
                        manifest = json.loads(archive.read(name))
                    continue
                b.derive(f"{folder}/{name}", archive.read(name), source="source")
    manifest.pop("source", None)
    manifest.pop("files", None)
    manifest["target"] = "engine-neutral"
    manifest["sprite_asset"] = 1
    manifest["coordinates"] = "pixels; x right, y down; normalized anchor measured from top-left of the untrimmed frame"
    manifest["sampling"] = "nearest" if source.pixelated else "linear"
    manifest["pixels_per_unit"] = b.params.pixels_per_unit
    manifest["padding"] = b.params.padding
    manifest["atlas"] = f"atlas/{source.base_name}.json"
    manifest["usage"] = usage
    for a in manifest["animations"]:
        a["frames"] = [f"frames/{a['key']}/frame_{i:03d}.png" for i in range(a["frame_count"])]
    manifest["integrations"] = {"unity": "PNG manual import; editor integration untested",
        "godot": f"godot/{source.base_name}.tres" if b.params.godot else None}
    b.derive("asset.json", json.dumps(manifest, indent=2) + "\n", source="source")
    b.file("README.txt", f"""{source.title}
Read asset.json first. Paths are relative to this run folder. PNGs are untrimmed
RGBA; frames of this asset share one canvas. Frame arrays define playback order;
durations_ms defines timing. loop_start/end are inclusive. 'once' holds the last
frame; 'loop' repeats the range after any intro; 'pingpong' reverses within that
range without duplicating endpoints. Stop/transition rules belong to the game.
Anchor is normalized from the top-left. Place a frame at
(position_x - anchor.x * width, position_y - anchor.y * height).
Mirroring is allowed only where the game-facing usage notes say so. Reflect
attachments and collision offsets with the sprite. Alpha is not a collision shape.

Unity 6 manual import (not an automatic JSON importer): use individual PNGs as
Sprite (2D and UI), Single, Full Rect, {b.params.pixels_per_unit} Pixels Per Unit.
Use Point filtering for pixel art, no mipmaps, no compression, Wrap Mode Clamp.
Custom Unity pivot = (anchor.x, 1 - anchor.y). For the sheet use Multiple and
explicit atlas rectangles (Unity y = sheet height - rect.y - rect.h), not automatic
silhouette slicing. Construct clips from the frame order/timing in asset.json.
No Unity Editor import was validated by this recipe.
https://docs.unity3d.com/6000.0/Documentation/Manual/texture-type-sprite.html

Godot 4, when included: copy the godot folder intact anywhere below res:// and
assign the .tres to AnimatedSprite2D.sprite_frames. Use nearest texture filtering
for pixel art. Set centered=false and offset=(-anchor.x*width, -anchor.y*height)
for the exported pivot; SpriteFrames alone does not store a node pivot. Set
flip_h only for mirror-safe artwork. Collision and gameplay remain game-owned.
https://docs.godotengine.org/en/stable/classes/class_spriteframes.html
""")
