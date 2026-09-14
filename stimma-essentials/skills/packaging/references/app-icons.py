"""Editable build example for run_file after the master artwork is prepared.

Set the values below from the request and recipe guidance. Use the actual
source or tool-result path for MASTER; the file is already in the workspace. Run with SAVE=False
while inspecting the draft and authoring cover.html. Set SAVE=True only after
reviewing the authored preview with view_image on the printed draft folder.
The rendered page inside that folder is index.html. The cover remains your HTML, separate from this
file; use one of the app-icons HTML references as its starting point.
"""
import json
from pathlib import Path

APP_NAME = ""  # The person's app name.
MASTER = ""  # Actual workspace path returned by the tool, or supplied source path.
BACKGROUND = ""  # The requested background color.
PLATFORMS = ["ios"]  # Choose from the recipe's platform options.
ANDROID_FOREGROUND = None  # Optional path to a prepared transparent layer.
COVER = "cover.html"
SAVE = False

pkg = stimma.packages.new(APP_NAME)
inputs = {"master": await pkg.add_member(MASTER, role="master")}
if ANDROID_FOREGROUND:
    inputs["android_foreground"] = await pkg.add_member(ANDROID_FOREGROUND, role="android_foreground")
await pkg.run("app-icons", inputs, {
    "app_name": APP_NAME, "background": BACKGROUND, "platforms": PLATFORMS,
})

if Path(COVER).is_file():
    pkg.set_cover(COVER)  # Synchronous. Validates the authored refs now.

if SAVE:
    media_id = await pkg.save()  # Refuses a missing authored cover.
    stimma.show(media_id=media_id, role="final")
else:
    manifest = await pkg.manifest()
    print(json.dumps({
        "members": [{"id": m["id"], "path": m["path"]} for m in manifest["members"]],
        "runs": [{"id": r["id"], "root": r["root"], "files": [f["path"] for f in r["files"]]} for r in manifest["runs"]],
        "cover_image": manifest.get("cover_image"),
    }, indent=2))
    print("Draft folder:", await pkg.preview())
