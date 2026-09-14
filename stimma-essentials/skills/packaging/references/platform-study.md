# Platform Study — app icons

Use this reference after discovering the installed `app-icons` recipe and reading
its current guidance. A Platform Study lets the recipient judge the delivered
icon beside familiar apps. It is a section of an authored package cover; a
package can include several icon runs and other work.

## Prepare the source, then let the recipe do its job

Use the given app name and requested background. An existing raster icon does
not need vectorization. Check the recipe requirements before preparing the
source. Only use Subject Isolation when the background actually needs removing
or replacing; packaging is the task, isolation may be one preparation step.

The recipe's default `artwork_fit="auto"` measures transparent margins or a
uniform source background and fits the visible mark to each platform. Do not
add more transparent padding or hand-resize each output. For intentionally
composed full-bleed artwork with deliberate internal spacing, use
`artwork_fit="canvas"`. Preserve the actual mark's color, opacity and shape.

An Android foreground must remain legible in the guaranteed circular safe zone.
Supply `android_foreground` only when it needs different artwork from the master.
The recipe creates the 108dp layer and fits the foreground inside the safe zone;
do not pre-pad it to 108dp yourself.

After the run, inspect the exact platform outputs and the rendered contexts in
the workspace folder from `await pkg.preview()`. Judge optical size beside the
native neighbors, particularly small Windows icons and the iPhone home screen.
If the mark is still undersized or intentional negative space was cropped,
correct the source or fit choice and rerun. Never compensate by enlarging only
the image shown in the cover. The recipient must receive the corrected files.

## The recipe supplies the context images

Read `await pkg.manifest()` for run ids, roots and filenames. The following are
relative to each run's root, not to the package root:

| Target | Preview files |
| --- | --- |
| iOS | `previews/device-studio.png`, `previews/device-lifestyle.png` |
| Android | `previews/platform-android.png` |
| macOS | `previews/platform-macos.png` |
| Windows | `previews/platform-windows-start.png`, `previews/platform-windows-taskbar.png` |
| Linux | `previews/platform-linux.png` |

Only requested platforms are rendered. Web exports have no supplied context
scene; show their actual files and useful sizes if requested. Do not invent a
scene filename. Every study uses the delivered platform image, with the system's
mask or canvas placement applied by the renderer. The Galaxy view has a populated
home screen; the desktop views are localized Dock, Start and taskbar contexts.

These images are already finished files. Do not call an image model, upscale,
search for a demo checkout, locate SDK templates with shell commands, rebuild OS
chrome, or manually place the app icon in a phone. Read references and templates
from the Packaging skill directory exposed when the skill is activated. Use
normal file tools and the path returned by `pkg.preview()` to inspect outputs.
If a listed preview is absent, check selected platforms and installed guidance;
do not fabricate a path or silently omit the target.

## Author the cover

Use `references/app-icons-mixed.html` for multiple platforms, or
`references/app-icons.html` for iOS alone. The mixed reference assumes all five
mobile/desktop targets: remove unrequested sections and retain every requested
one. Include additional runs and members according to the package's scope.
Replace `APP_NAME`, `RUN_ID`, `RUN_ROOT`, `MACOS_PNG_REF` and `LINUX_PNG_REF`
using the supplied name and actual manifest. Do not leave placeholder prose.

Call the context section **Platform Study**. Show scenes wide and give each
platform a short label. Windows needs both Start and taskbar. Show iOS studio
and lifestyle scenes; do not bring back the old flat phone home-screen section.
Localized iOS context rows can use `stimma-appearance` if useful; its light/dark
switch already fades and works without scripts. Do not add another switch.

Keep the cover factual: platform names, actual sizes, useful folder descriptions.
Avoid promotional claims and invented app features or notifications. Actual-size
rows use `stimma-sizes` with the delivered PNGs. End with `stimma-files` for each
run, or the whole package when that makes the contents clearer. The kit adds the
required hairline and “Made with Stimma” footer. Do not add branding elsewhere.

Attach the authored HTML with `pkg.set_cover`, fix all reported ref problems,
inspect the resulting cover, then save and show the package as the final result.
A folder of images or an auto cover is not the completed agent-authored package.
