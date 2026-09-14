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
| iOS | `previews/device-studio.png`, `previews/device-lifestyle.png`; details: `previews/ios-store-light.png`, `previews/ios-notification-light.png` |
| Android | `previews/platform-android-studio.png`, `previews/platform-android.png`; details: `previews/android-store-light.png`, `previews/android-notification-light.png` |
| macOS | `previews/platform-macos.png` |
| Windows | `previews/platform-windows-start.png`, `previews/platform-windows-taskbar.png` |
| Linux | `previews/platform-linux.png` (Ubuntu), `previews/platform-linux-kde.png` (KDE Plasma) |

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

## Adjust one platform without changing the master

Use the recipe's `<platform>_scale` parameter (ios, android, macos, windows,
linux or web). `1.0` is the current default fit; `0.9` makes the artwork 10%
smaller and adds padding. Change only the requested platform and rerun. These
values affect the delivered files and all their previews together. Enlargement
that exceeds the canvas or Android safe zone is refused, not silently clipped.
The platform canvas, macOS outer margin and format dimensions stay fixed.
Keep the shared SVG unchanged so it can serve other runs in a brand kit.

## Author the cover

Use `references/app-icons-mixed.html` for multiple platforms, or
`references/app-icons.html` for iOS alone. The mixed reference assumes all five
mobile/desktop targets: remove unrequested sections and retain every requested
one. If iOS is absent, use `templates/delivery.html` plus the section patterns
in this reference; do not inspect the generated auto cover for its internals.
Include additional runs and members according to the package's scope.
Replace `APP_NAME`, `RUN_ID`, `RUN_ROOT`, `MACOS_PNG_REF` and `LINUX_PNG_REF`
using the supplied name and actual manifest. Do not leave placeholder prose.

The following is a starting composition. The person's requested colors, logo
placement, emphasis and grouping take precedence. Author custom CSS and print
overrides as needed; kit layouts are optional conveniences, not the only layouts.

By default, group each OS in its own sibling `<stimma-section page>` labelled
**Platform Study · OS**. Use `layout="pair"` for iOS, Android and Linux, `layout="stack"` for Windows,
and `layout="single"` for macOS. Place the scene media directly inside;
do not nest another section or add image margins. The same content becomes a
responsive HTML section and one landscape PDF page per OS. Keep the opening
icon overview and “At actual size” row together before these page groups, on
the opening page. Give contents its own page section. On each mobile OS page, put store and notification examples in
`<details slot="details"><summary>Details</summary>…</details>`, initially closed.
Inside, use one `stimma-appearance` with light and dark `stimma-grid` children
marked `when="light"` / `when="dark"`, as in the references. The switch follows
system appearance until chosen and fades between variants. The PDF omits the
entire disclosure so the two phone scenes occupy the full OS slide. Do not add
separate detail pages, an “In iOS” section, Settings or Spotlight.

Show scenes wide and give each
platform a short label. Windows needs both Start and taskbar. Linux needs
Ubuntu and KDE Plasma side by side, with those captions. Show studio
and lifestyle scenes for both iOS and Android; do not bring back the old flat
phone home-screen section.
The store and notification examples use neutral sample text, without invented
ratings, categories or app features. Do not add such claims in captions.

Keep the cover factual: platform names, actual sizes, useful folder descriptions.
Avoid promotional claims and invented app features or notifications. Actual-size
rows use `stimma-sizes` with the delivered PNGs. End with `stimma-files` for each
run, or the whole package when that makes the contents clearer. The kit adds the
required hairline and “Made with Stimma” footer. Do not add branding elsewhere.

Attach the authored HTML with `pkg.set_cover`, fix all reported ref problems,
inspect the resulting cover, then save and show the package as the final result.
A folder of images or an auto cover is not the completed agent-authored package.
