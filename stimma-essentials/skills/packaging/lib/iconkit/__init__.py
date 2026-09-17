"""Platform app-icon rules, composition policy and rendered platform studies.

Shipped inside the Packaging skill so that OS-specific knowledge (sizes, safe
areas, containers, how a Dock or a taskbar draws an icon) lives with the skill
that uses it, and can be updated by publishing the pack. ``spec`` holds the
tables and container writers, ``icon_artwork`` the fit policy, and the
remaining modules render the previews the app-icons recipe ships.
"""

from iconkit.springboard import render_iphone  # noqa: F401
from iconkit.surfaces import (  # noqa: F401
    render_app_store_row,
    render_notification,
    render_settings_row,
    render_spotlight_row,
)
