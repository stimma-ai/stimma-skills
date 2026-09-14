"""Editable build example for run_file after the master artwork is prepared.

Set the values below from the request and recipe guidance. Run with SAVE=False
while inspecting the draft and authoring cover.html. Set SAVE=True only after
reviewing the authored preview. The cover remains your HTML, separate from this
file; use one of the app-icons HTML references as its starting point.
"""
import json
from pathlib import Path

APP_NAME = ""  # The person's app name.
MASTER = "master.png"  # Prepared square artwork, at least 1024 px.
BACKGROUND = ""  # The requested background color.
PLATFORMS = ["ios"]  # Choose from the recipe's platform options.
ANDROID_FOREGROUND = None  # Optional path to a prepared transparent layer.
COVER = "cover.html"
SAVE = False

pkg = stimma.packages.new(f"{APP_NAME} — app icons")
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
    print(json.dumps(await pkg.manifest(), indent=2))
    print("Draft folder:", await pkg.preview())
