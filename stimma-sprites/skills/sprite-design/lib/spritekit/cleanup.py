"""Deterministic frame cleanup: halo removal, flicker fix, palette snap, grid quantize.

Every op takes and returns a list of RGBA PIL frames. ``apply_profile`` runs
a style preset's ops in the right order with sane defaults — the chat flow
applies it silently after extraction.
"""

import numpy as np
from PIL import Image


def _stack(frames: list) -> np.ndarray:
    """(N, H, W, 4) uint8 stack; raises if frames aren't uniform size."""
    arrays = [np.asarray(f.convert("RGBA"), dtype=np.uint8) for f in frames]
    shapes = {a.shape for a in arrays}
    if len(shapes) > 1:
        raise ValueError(f"frames are not uniform size: {sorted(shapes)}")
    return np.stack(arrays)


def _unstack(stack: np.ndarray) -> list:
    return [Image.fromarray(a, "RGBA") for a in stack]


def _erode(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    """4-neighbor binary erosion (edge pixels wrap; sprites have empty borders)."""
    m = mask
    for _ in range(iterations):
        m = (
            m
            & np.roll(m, 1, axis=0) & np.roll(m, -1, axis=0)
            & np.roll(m, 1, axis=1) & np.roll(m, -1, axis=1)
        )
    return m


def sample_background(frame, *, border: int = 2) -> tuple:
    """Median RGB of the frame's border ring — the plain backdrop color."""
    arr = np.asarray(frame.convert("RGBA"), dtype=np.uint8)
    ring = np.concatenate([
        arr[:border, :, :3].reshape(-1, 3),
        arr[-border:, :, :3].reshape(-1, 3),
        arr[:, :border, :3].reshape(-1, 3),
        arr[:, -border:, :3].reshape(-1, 3),
    ])
    return tuple(int(v) for v in np.median(ring, axis=0))


def auto_tolerance(frame, color, *, border: int = 8, factor: float = 2.0,
                   low: float = 6.0, high: float = 24.0) -> float:
    """Derive a keying tolerance from how noisy the backdrop actually is.

    A generated backdrop is nearly flat (measured: 99.9th-percentile border
    deviation ~5/255), so a fixed generous tolerance is not "safe" — it
    silently eats light parts of the character. White sneakers on a pale
    mint backdrop are only ~80 apart, so a tolerance of 28 punched holes in
    them. Scaling the threshold off the observed border noise keeps the key
    tight where the source is clean and loosens it only when it must.
    """
    arr = np.asarray(frame.convert("RGB"), dtype=np.float32)
    ring = np.concatenate([
        arr[:border].reshape(-1, 3), arr[-border:].reshape(-1, 3),
        arr[:, :border].reshape(-1, 3), arr[:, -border:].reshape(-1, 3),
    ])
    spread = float(np.percentile(np.linalg.norm(ring - np.asarray(color, dtype=np.float32), axis=1), 99.9))
    return float(np.clip(spread * factor, low, high))


def chroma_distance(rgb: np.ndarray, color) -> np.ndarray:
    """Distance in chromaticity (colour ratio) space to the key colour.

    Keying on RGB distance cannot see coverage: a shadow cast on the
    backdrop, or the backdrop blended with a dark outline, moves far in RGB
    while remaining exactly the backdrop's *hue*. Both then survive as
    opaque — the magenta puddle under a character's feet, and the coloured
    halo around it. Dividing out brightness fixes that by construction:
    darkening a colour, or mixing it with black, leaves chromaticity
    unchanged, so both read as pure backdrop.
    """
    p = rgb.astype(np.float32)
    total = np.maximum(p.sum(axis=-1, keepdims=True), 1e-6)
    key = np.asarray(color, dtype=np.float32)
    return np.linalg.norm(p / total - key / max(key.sum(), 1e-6), axis=-1)


def key_background(
    frames: list,
    *,
    color: "tuple | None" = None,
    chroma_low: float = 0.10,
    chroma_high: float = 0.22,
    dark_floor: float = 0.12,
    connected: bool = False,
    edge_band: int = 2,
) -> list:
    """Chroma-key a flat generated backdrop to transparency.

    This is the PRIMARY background removal for sprite clips, not a
    fallback: generated moves are shot on a flat plain backdrop (border
    colour std ~1/255), so an exact distance key beats a photo-matting
    model, which invents soft alpha and hair haze that no amount of
    downstream cleanup fully removes. Reserve model matting for footage
    with a genuinely busy background.

Keying is done in CHROMATICITY, not RGB distance: alpha ramps from 0
    at ``chroma_low`` to 1 at ``chroma_high`` (see ``chroma_distance``).
    That is what removes shadows the character casts on the backdrop and
    the blended halo where the backdrop meets a dark outline — both keep
    the backdrop's hue while moving far in RGB, so a distance key leaves
    them behind as puddles and fringes.

    RGB is deliberately left alone — do NOT unmix the backdrop out
    algebraically; on light subjects that pushes colours into the
    complementary hue (white minus a green backdrop reads magenta).
    ``edge_pad`` supplies clean edge colours instead.

    Frames that already carry transparency pass through untouched.

    Args:
        color: Backdrop RGB; sampled from the first frame's border if None.
        chroma_low: Chromaticity distance at or below which a pixel is pure
            backdrop. Character colours typically sit above 0.35.
        chroma_high: Distance at which a pixel is fully opaque.
        dark_floor: Fraction of the backdrop's brightness below which a
            pixel is always foreground, since chromaticity is unreliable
            for near-black pixels.
        connected: Restore backdrop-coloured regions that are sealed inside
            the silhouette, on the theory they are character detail that
            happens to match the backdrop. Defaults to False, because such
            pockets are almost always REAL gaps — between an arm and the
            torso, or between the legs — and filling them grows a blob
            behind the character. Choose a key colour far from the
            character's palette (see prep.pick_key_color) and there is
            nothing for this to protect; enable it only for a subject that
            genuinely shares the backdrop's colour.
        edge_band: How many pixels from the true silhouette edge may keep a
            soft alpha. Everything further inside is forced fully opaque, so
            a light interior (white shoes, socks) can never come out
            see-through just because its colour resembles the backdrop.
            0 disables, letting distance alone drive alpha everywhere.
    """
    stack = _stack(frames)
    if stack[:, :, :, 3].min() < 255:
        return frames  # already keyed or matted
    if color is None:
        color = sample_background(frames[0])
    target = np.array(color, dtype=np.float32)
    key_lum = float(target.mean())
    out = stack.astype(np.float32)
    for arr in out:
        d = chroma_distance(arr[:, :, :3], color)
        alpha = np.clip((d - chroma_low) / max(1e-6, chroma_high - chroma_low), 0.0, 1.0)
        # Chromaticity is meaningless for near-black pixels (dividing by a
        # tiny sum), and the backdrop is never that dark, so anything far
        # below the backdrop's brightness is foreground — this is what keeps
        # dark outlines and black clothing solid.
        alpha[arr[:, :, :3].mean(axis=2) < key_lum * dark_floor] = 1.0
        outside = None
        if connected or edge_band:
            try:
                from scipy import ndimage
            except ImportError:
                ndimage = None
            if ndimage is not None:
                cleared = alpha <= 0.0
                labels, n = ndimage.label(cleared)
                if n:
                    border = np.unique(np.concatenate(
                        [labels[0], labels[-1], labels[:, 0], labels[:, -1]]
                    ))
                    outside = np.isin(labels, border[border != 0])
                    if connected:
                        alpha[cleared & ~outside] = 1.0
                if outside is not None and edge_band:
                    # Soft alpha belongs to the silhouette edge only; deeper
                    # in, partial transparency is a keying mistake. Only
                    # pixels that already read as *some* subject qualify —
                    # a pocket that is pure backdrop (alpha 0) is a real gap
                    # between limbs, and filling it grows a cape.
                    near_edge = ndimage.binary_dilation(outside, iterations=edge_band)
                    alpha[(alpha > 0.0) & ~outside & ~near_edge] = 1.0
        arr[:, :, 3] = alpha * 255.0
    return _unstack(np.clip(np.rint(out), 0, 255).astype(np.uint8))


def thin_gaps(solid: np.ndarray, *, width: int = 2):
    """Background pixels sitting in a narrow channel through the subject.

    The gap between an arm and the torso is exactly this: background, only
    a few pixels wide, open in some frames and pinched shut in others. Any
    smoothing that works by majority — a median filter, a temporal vote —
    will happily fill it, webbing the limb to the body. Morphological
    opening finds those channels so they can be protected: a channel
    narrower than ``2*width`` vanishes under erosion and never comes back.
    """
    try:
        from scipy import ndimage
    except ImportError:
        return np.zeros_like(solid, dtype=bool)
    background = ~solid
    opened = ndimage.binary_dilation(
        ndimage.binary_erosion(background, iterations=width), iterations=width)
    return background & ~opened


def denoise_matte(frames: list, *, size: int = 3) -> list:
    """Median-filter the alpha channel. Colour is untouched.

    A matte computed per frame from a continuous distance wobbles wherever
    the source is noisy: compression noise moves boundary pixels a few
    percent either side of the ramp, which is invisible in a still frame
    and reads as crawling "TV static" along the rim once it animates. A
    small median kills that speckle without moving the silhouette, and
    because it is purely spatial it cannot ghost or smear motion.
    """
    try:
        from scipy import ndimage
    except ImportError:
        return frames
    stack = _stack(frames)
    for arr in stack:
        original = arr[:, :, 3].copy()
        filtered = ndimage.median_filter(original, size=size)
        # A median closes thin structures. Where the subject pinches around
        # a narrow background channel, keep the lower of the two so speckle
        # is still removed but the gap is never bridged.
        protect = thin_gaps(original > 128, width=max(1, size // 2))
        arr[:, :, 3] = np.where(protect, np.minimum(filtered, original), filtered)
    return _unstack(stack)


def stabilize_matte(frames: list, *, window: int = 3, low: int = 8, high: int = 247) -> list:
    """Temporal median of alpha, applied ONLY to pixels that are uncertain.

    Confident pixels (fully transparent or fully opaque) are left exactly
    as they are, so a real moving edge is never smeared; only the
    in-between band — the pixels that flicker because the source is noisy —
    is smoothed across ``window`` frames. Alpha only: temporally averaging
    COLOUR fabricates values no frame contained, which is a different and
    much uglier artefact.
    """
    if window < 3 or len(frames) < window:
        return frames
    stack = _stack(frames)
    alpha = stack[:, :, :, 3].astype(np.float32)
    half = window // 2
    padded = np.concatenate(
        [alpha[-half:], alpha, alpha[:half]], axis=0)     # cycles areloops, so the window wraps
    smoothed = np.median(
        np.stack([padded[i:i + len(alpha)] for i in range(window)]), axis=0)
    uncertain = (alpha > low) & (alpha < high)
    alpha = np.where(uncertain, smoothed, alpha)
    stack[:, :, :, 3] = np.clip(np.rint(alpha), 0, 255).astype(np.uint8)
    return _unstack(stack)


def smooth_silhouette(frames: list, *, window: int = 3, max_shift: int = 2) -> list:
    """Temporal majority vote on the SILHOUETTE, not the soft band.

    Once the matte has been choked, the boundary is effectively binary, so
    smoothing the soft ramp achieves nothing — the ramp was eroded away.
    What still crawls is the binary edge itself: each frame's silhouette
    lands a pixel differently because the source is noisy. This takes a
    majority vote across ``window`` frames, but only lets a pixel flip if
    it sits within ``max_shift`` of the current edge, so genuine motion
    (which moves the edge much further) passes through untouched.
    """
    if window < 3 or len(frames) < window:
        return frames
    try:
        from scipy import ndimage
    except ImportError:
        return frames
    stack = _stack(frames)
    alpha = stack[:, :, :, 3]
    mask = (alpha > 128).astype(np.float32)
    half = window // 2
    padded = np.concatenate([mask[-half:], mask, mask[:half]], axis=0)
    vote = np.mean(np.stack([padded[i:i + len(mask)] for i in range(window)]), axis=0)
    for i in range(len(stack)):
        current = mask[i] > 0.5
        near = (ndimage.binary_dilation(current, iterations=max_shift)
                & ~ndimage.binary_erosion(current, iterations=max_shift))
        # Removing a flickering pixel is always safe; ADDING one can weld a
        # limb to the body, so adds are refused inside narrow gaps.
        add = near & (vote[i] > 0.66) & ~current & ~thin_gaps(current, width=max_shift)
        drop = near & (vote[i] < 0.34) & current
        stack[i, :, :, 3][add] = 255
        stack[i, :, :, 3][drop] = 0
    return _unstack(stack)


def choke_matte(frames: list, *, pixels: int = 1, alpha_floor: int = 128) -> list:
    """Shrink the silhouette to drop the backdrop-blended boundary ring.

    Distance keying cannot see *coverage*. A pixel that is 75% backdrop and
    25% dark outline sits far from the backdrop colour, so it keys as fully
    opaque while still carrying a backdrop tint — the coloured fringe that
    survives every later cleanup step, because ``edge_pad`` treats it as a
    valid colour donor. Eroding the mask by a couple of pixels removes that
    ring outright (the compositing world's "choke"). Measured on a 1280px
    clip: 2px cuts backdrop-cast pixels from 2.85% of the sprite to 0.08%,
    at a cost of ~1% of silhouette width — invisible after downscaling.

    Keep this SMALL. Eroding more than a pixel or two chews through the
    character's dark outline and exposes the lighter material behind it,
    which reads as a white fringe — measured on a real sprite, the edge
    went from 0.4% light pixels at 0px to 33% at 3px while the interior
    stayed at ~6%. 1px is the balance point: the outline survives and
    backdrop leak stays around 0.2%.

    Args:
        pixels: Erosion depth. 0 disables; above 2 starts eating outlines.
        alpha_floor: Alpha at or above this counts as silhouette.
    """
    if pixels <= 0:
        return frames
    try:
        from scipy import ndimage
    except ImportError:
        return frames
    stack = _stack(frames)
    for arr in stack:
        keep = ndimage.binary_erosion(arr[:, :, 3] >= alpha_floor, iterations=pixels)
        arr[:, :, 3] = np.where(keep, arr[:, :, 3], 0)
    return _unstack(stack)


def keyness(rgb: np.ndarray, color) -> np.ndarray:
    """How much of the key colour's *hue* a pixel carries. 1.0 = pure key.

    Compares chroma (colour minus its own brightness) against the key's
    chroma, so it is insensitive to how light or dark the pixel is: a 50%
    blend of the key with a black outline still scores ~0.5, while a
    neutral or opposite-hue pixel scores ~0.
    """
    key = np.asarray(color, dtype=np.float32)
    kc = key - key.mean()
    denom = float((kc ** 2).sum()) or 1.0
    pc = rgb.astype(np.float32) - rgb.astype(np.float32).mean(axis=-1, keepdims=True)
    return (pc * kc).sum(axis=-1) / denom


def despill(frames: list, *, color: "tuple | None" = None,
            threshold: float = 0.35, band: int = 6) -> list:
    """Repair pixels that carry the backdrop's hue near the silhouette.

    A saturated staging colour makes partial-coverage pixels *garish*: a
    magenta backdrop blended with a black outline reads as purple, and no
    amount of eroding fixes thin features like fingers, where eroding would
    destroy the feature instead. So rather than cutting these pixels, repair
    their colour — replace contaminated pixels with the nearest clean
    neighbour's colour, leaving alpha untouched.

    Only pixels within ``band`` of the silhouette edge are candidates, so a
    genuinely warm interior (a red shirt scores ~0.3 against a magenta key)
    is never touched.

    Args:
        color: Backdrop RGB; sampled from the frame border if None.
        threshold: Keyness above which a pixel counts as contaminated.
            Keep it above the keyness of the character's own colours.
        band: Distance from the edge to consider, in pixels. 0 disables.
    """
    if band <= 0:
        return frames
    try:
        from scipy import ndimage
    except ImportError:
        return frames
    if color is None:
        color = sample_background(frames[0])
    stack = _stack(frames)
    for arr in stack:
        alpha = arr[:, :, 3]
        solid = alpha > 32
        if not solid.any():
            continue
        edge_zone = solid & ~ndimage.binary_erosion(solid, iterations=band)
        contaminated = edge_zone & (keyness(arr[:, :, :3], color) > threshold)
        clean = solid & ~contaminated
        if not contaminated.any() or not clean.any():
            continue
        _, (iy, ix) = ndimage.distance_transform_edt(~clean, return_indices=True)
        arr[:, :, :3] = np.where(contaminated[:, :, None], arr[iy, ix, :3], arr[:, :, :3])
    return _unstack(stack)


def edge_pad(frames: list, *, solid_at: int = 255) -> list:
    """Bleed opaque RGB outward into transparent pixels (alpha untouched).

    Standard texture-pipeline step. Partly transparent pixels still hold
    backdrop-tinted colour; any later resample mixes that tint back in as
    a fringe. Replacing every non-solid pixel's colour with its nearest
    solid neighbour's means no pixel anywhere holds backdrop colour, so
    scaling and packing cannot reintroduce it.
    """
    try:
        from scipy import ndimage
    except ImportError:
        return frames
    stack = _stack(frames)
    for arr in stack:
        solid = arr[:, :, 3] >= solid_at
        if not solid.any() or solid.all():
            continue
        _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
        arr[:, :, :3] = arr[iy, ix, :3]
    return _unstack(stack)


def fill_holes(frames: list, *, max_frac: float = 0.0008) -> list:
    """Close small transparent pockets inside the silhouette.

    Keying can punch pinholes through backdrop-coloured highlights. Only
    holes enclosed by the subject and smaller than ``max_frac`` of it are
    filled, so real gaps (between an arm and the body) stay open.
    """
    try:
        from scipy import ndimage
    except ImportError:
        return frames
    stack = _stack(frames)
    for arr in stack:
        alpha = arr[:, :, 3]
        holes = alpha <= 32
        subject = int((alpha > 32).sum())
        if not subject:
            continue
        labels, n = ndimage.label(holes)
        if not n:
            continue
        border = set(np.unique(np.concatenate(
            [labels[0], labels[-1], labels[:, 0], labels[:, -1]]
        )).tolist()) - {0}
        sizes = ndimage.sum(holes, labels, range(1, n + 1))
        fill = [i + 1 for i, s in enumerate(sizes)
                if (i + 1) not in border and s < subject * max_frac]
        if fill:
            alpha[np.isin(labels, fill)] = 255
    return _unstack(stack)


def threshold_alpha(frames: list, *, floor: int = 130, binarize: bool = False) -> list:
    """Cut weak matte alpha; the post-matting step that removes soft haze.

    A matting model marks motion smear and soft halos with low alpha (a
    haze cloud averages ~70-90) while the character body sits at ~255.
    Clearing everything below ``floor`` deletes the cloud in one pass —
    boundary erosion alone would need to chew through it pixel by pixel.
    ``binarize`` additionally snaps surviving alpha to 255 for styles that
    want hard pixel edges.
    """
    stack = _stack(frames)
    for arr in stack:
        alpha = arr[:, :, 3]
        weak = alpha < floor
        alpha[weak] = 0
        if binarize:
            alpha[~weak] = 255
    return _unstack(stack)


def _touches_transparent(alpha: np.ndarray) -> np.ndarray:
    """Pixels with at least one 4-neighbor whose alpha is exactly 0.

    Out-of-frame neighbors don't count, so a sprite cropped at the frame
    edge isn't eroded from that side.
    """
    empty = alpha == 0
    touch = np.zeros_like(empty)
    touch[1:, :] |= empty[:-1, :]
    touch[:-1, :] |= empty[1:, :]
    touch[:, 1:] |= empty[:, :-1]
    touch[:, :-1] |= empty[:, 1:]
    return touch


def remove_halo(
    frames: list,
    *,
    brightness: float = 0.88,
    passes: int = 2,
    bg_tolerance: float = 60.0,
) -> list:
    """Trim fringe inward from transparent edges (the AutoSprite recipe).

    Each pass clears boundary pixels — alpha > 0 with a fully transparent
    4-neighbor — that are near-white (``min(r,g,b) >= brightness``),
    semi-transparent (``alpha < 255``), or within ``bg_tolerance`` of the
    frame's own backdrop color (sampled from the RGB that keying/matting
    leaves under transparent pixels — this is what catches gray-blend
    fringe that isn't bright enough for the brightness clause). Stops
    early when a pass removes nothing.

    Args:
        brightness: Min-channel threshold in [0,1]. Higher removes only
            near-white fringe; lower trims more pale edge detail.
        passes: How many pixels deep the trim can push inward.
        bg_tolerance: RGB distance to the backdrop counted as blend; 0
            disables the clause.
    """
    stack = _stack(frames)
    threshold = round(brightness * 255)
    for arr in stack:
        alpha = arr[:, :, 3]
        near_bg = np.zeros(alpha.shape, dtype=bool)
        if bg_tolerance:
            transparent = alpha == 0
            if transparent.any():
                bg = np.median(arr[:, :, :3][transparent], axis=0)
                # Encoders that zero RGB under transparency would make the
                # backdrop estimate black and eat dark outlines — skip then.
                if bg.mean() > 30:
                    near_bg = (
                        np.linalg.norm(arr[:, :, :3].astype(np.float32) - bg, axis=2)
                        <= bg_tolerance
                    )
        for _ in range(max(1, passes)):
            candidates = (
                (alpha > 0)
                & _touches_transparent(alpha)
                & ((arr[:, :, :3].min(axis=2) >= threshold) | (alpha < 255) | near_bg)
            )
            if not candidates.any():
                break
            alpha[candidates] = 0
    return _unstack(stack)


def clear_matte_regions(
    frames: list,
    *,
    colors: "list | None" = None,
    min_region: "int | None" = None,
    homogeneity: float = 0.55,
    dilate: int = 3,
) -> list:
    """Erase leftover backdrop patches that survived matting or keying.

    Port of AutoSprite's matte scan: candidate pixels are opaque and either
    near one of ``colors`` (±12 per channel) or, by default, flat and
    bright (max−min ≤ 24, min ≥ 150 — a low-saturation backdrop tone).
    Candidates group into connected regions; a region is cleared when it's
    big enough and (in default mode) color-homogeneous — a real matte patch
    is flat, a highlight on the character isn't. Cleared regions grow up to
    ``dilate`` px into their paler fringe. Frames without any transparency
    are left alone (nothing has been keyed yet, so everything would match).
    """
    try:
        from scipy import ndimage
    except ImportError:
        return frames
    stack = _stack(frames)
    if min_region is None:
        min_region = 8 if colors else 16
    palette = np.array(colors, dtype=np.int16) if colors else None
    for arr in stack:
        alpha = arr[:, :, 3]
        if (alpha < 8).sum() == 0:
            continue
        rgb = arr[:, :, :3].astype(np.int16)
        opaque = alpha > 128
        if palette is not None:
            near = np.zeros(opaque.shape, dtype=bool)
            for c in palette:
                near |= (np.abs(rgb - c) <= 12).all(axis=2)
            candidates = opaque & near
        else:
            flat = (rgb.max(axis=2) - rgb.min(axis=2)) <= 24
            bright = rgb.min(axis=2) >= 150
            candidates = opaque & flat & bright
        labels, count = ndimage.label(candidates)
        mask = np.zeros(opaque.shape, dtype=bool)
        for region_label in range(1, count + 1):
            region = labels == region_label
            size = int(region.sum())
            if size < min_region:
                continue
            if palette is None:
                # Top-two colors must dominate the region.
                packed = (
                    rgb[region][:, 0].astype(np.int32) << 16
                ) | (rgb[region][:, 1].astype(np.int32) << 8) | rgb[region][:, 2]
                counts = np.sort(np.unique(packed, return_counts=True)[1])[::-1]
                if counts[:2].sum() / size < homogeneity:
                    continue
            mask |= region
        if not mask.any():
            continue
        pale = ((rgb.max(axis=2) - rgb.min(axis=2)) <= 40) & (rgb.min(axis=2) >= 80)
        for _ in range(dilate):
            grown = (
                np.roll(mask, 1, 0) | np.roll(mask, -1, 0)
                | np.roll(mask, 1, 1) | np.roll(mask, -1, 1)
            ) & ~mask & (alpha >= 8) & pale
            if not grown.any():
                break
            mask |= grown
        arr[mask] = 0
    return _unstack(stack)


def fix_flicker(
    frames: list,
    *,
    tolerance: float = 12.0,
    majority: float = 0.7,
    blend_distance: float = 110.0,
) -> list:
    """Kill stray pixels, shimmer, and transient haze; leave real motion alone.

    Majority vote per pixel: where at least ``majority`` of the frames agree
    with the temporal median (within ``tolerance`` per channel, 0-255
    scale), the disagreeing frames are snapped to that median — with one
    motion guard. When the median is *transparent* (the pixel is background
    most of the time), an opaque outlier is only cleared if its color sits
    within ``blend_distance`` of the median RGB — i.e. it looks like a
    backdrop blend (haze, smear, fringe). A hand or chin passing through at
    a motion extreme is solid character color, far from the backdrop, and
    survives. Opaque-median pixels (body shimmer) snap unconditionally.
    """
    stack = _stack(frames).astype(np.float32)
    if len(stack) < 3:
        return _unstack(stack.astype(np.uint8))
    median = np.median(stack, axis=0)
    deviation = np.abs(stack - median).max(axis=3)  # worst channel, (N, H, W)
    agree_mask = deviation <= tolerance
    agree = agree_mask.sum(axis=0)
    quorum = agree >= max(2, int(np.ceil(majority * len(stack))))
    # Snap value = mean of the frames that actually agree, NEVER the raw
    # channel-wise median: at pixels where frames split between two
    # populations (hair vs backdrop under residual zoom), the independent
    # per-channel median fabricates a color no frame contains — painting it
    # in is exactly the "black schmutz" bug. Agreeing frames are all within
    # tolerance of each other, so their mean is a real, clean value.
    counts = np.maximum(agree, 1)[:, :, None]
    consensus = (stack * agree_mask[:, :, :, None]).sum(axis=0) / counts
    outliers = ~agree_mask & quorum[None, :, :]
    consensus_opaque = consensus[:, :, 3] >= 128
    looks_like_blend = (
        np.linalg.norm(stack[:, :, :, :3] - consensus[None, :, :, :3], axis=3)
        <= blend_distance
    )
    clear = outliers & (consensus_opaque[None, :, :] | looks_like_blend)
    stack[clear] = np.broadcast_to(consensus, stack.shape)[clear]
    return _unstack(np.clip(np.rint(stack), 0, 255).astype(np.uint8))


def prune_components(frames: list, *, keep_ratio: float = 0.01) -> list:
    """Drop small disconnected alpha blobs — the post-flicker debris pass.

    After the temporal vote clears most transient haze, what survives is
    scattered blobs detached from (or barely touching) the character. Per
    frame, keep the largest connected component and anything at least
    ``keep_ratio`` of its size (so a thrown projectile or detached effect
    survives, but a 500-px smear next to a 100k-px body doesn't).
    """
    try:
        from scipy import ndimage
    except ImportError:
        return frames
    stack = _stack(frames)
    for arr in stack:
        mask = arr[:, :, 3] > 0
        labels, count = ndimage.label(mask)
        if count <= 1:
            continue
        sizes = ndimage.sum(mask, labels, range(1, count + 1))
        threshold = sizes.max() * keep_ratio
        drop = np.isin(labels, [i + 1 for i, s in enumerate(sizes) if s < threshold])
        arr[drop] = 0
    return _unstack(stack)


def build_palette(frames: list, *, colors: int = 32) -> np.ndarray:
    """Adaptive palette over all frames' opaque pixels. Shape (K, 3) uint8."""
    stack = _stack(frames)
    opaque = stack[stack[:, :, :, 3] >= 128][:, :3]
    if len(opaque) == 0:
        return np.zeros((1, 3), dtype=np.uint8)
    # PIL's adaptive quantizer wants an image; feed it the opaque pixels as a strip.
    strip = Image.fromarray(opaque.reshape(1, -1, 3), "RGB")
    quantized = strip.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    palette = np.asarray(quantized.getpalette(), dtype=np.uint8).reshape(-1, 3)
    used = sorted(set(quantized.getdata()))
    return palette[used]


def snap_palette(
    frames: list, *, colors: int = 32, palette: "np.ndarray | None" = None
) -> list:
    """Quantize every frame to one animation-wide palette (alpha untouched)."""
    if palette is None:
        palette = build_palette(frames, colors=colors)
    stack = _stack(frames)
    flat = stack[:, :, :, :3].reshape(-1, 3).astype(np.int32)
    # Nearest palette color by squared distance, chunked to bound memory.
    pal = palette.astype(np.int32)
    out = np.empty_like(flat)
    step = 1 << 16
    for i in range(0, len(flat), step):
        chunk = flat[i : i + step]
        dist = ((chunk[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)
        out[i : i + step] = pal[dist.argmin(axis=1)]
    stack[:, :, :, :3] = out.reshape(stack[:, :, :, :3].shape).astype(np.uint8)
    return _unstack(stack)


def quantize_grid(frames: list, *, pixel: int = 4) -> list:
    """Snap to an N-px logical pixel grid (the "pixel art filter").

    Args:
        pixel: Logical pixel size in output pixels; frame dimensions are
            preserved (down- then up-sampled with nearest-neighbor).
    """
    if pixel <= 1:
        return [f.convert("RGBA") for f in frames]
    out = []
    for f in frames:
        f = f.convert("RGBA")
        w, h = f.size
        small = f.resize((max(1, w // pixel), max(1, h // pixel)), Image.Resampling.NEAREST)
        out.append(small.resize((w, h), Image.Resampling.NEAREST))
    return out


def apply_profile(frames: list, profile: "dict | None") -> list:
    """Run a style preset's cleanup chain in the correct order.

    The default chain is tuned for the normal case: a clip generated on a
    flat plain backdrop, chroma-keyed. Defaults-on stages (set ``False``
    to disable): ``key`` (chroma key; no-ops on already-matted frames),
    ``denoise`` (median-filter the matte — kills rim static),
    ``smooth`` (temporal majority vote on the silhouette — the rest of the
    rim static; refuses to fill narrow gaps, so limbs never weld),
    ``choke`` (erode the backdrop-blended boundary ring — the fringe
    fix), ``despill`` (repair edge pixels carrying the backdrop's hue —
    what saves thin features like fingers, which eroding would destroy), ``holes`` (fill pinholes), ``prune`` (drop detached debris),
    ``matte`` (trapped-backdrop pockets, given the sampled colour),
    ``edge_pad`` (bleed clean colour outward so later scaling can't
    fringe).

    Opt-in stages, all off by default: ``flicker`` (temporal majority
    vote — only for residual shimmer; it compares frames, so run it after
    ``stabilize`` or it smears edges), ``alpha`` (weak-matte floor, for
    model-matted input), ``halo`` (edge trim), ``matte`` (leftover
    backdrop-patch scan), ``grid`` (logical pixel size), ``palette``
    (colour count). Each accepts a kwargs dict, or True for defaults.

    Order: key, denoise, smooth, choke, despill, holes, prune, flicker,
    alpha, halo, matte, edge_pad, grid, palette — edge_pad after every alpha change so padding reflects
    final alpha, and colour ops last so they see clean pixels.
    """
    profile = profile or {}

    def opt(name, default=False):
        value = profile.get(name, default)
        if value is False or value is None:
            return None
        return value if isinstance(value, dict) else {}

    # Sample the backdrop ONCE and reuse it for every frame and every op.
    # Identical parameters across frames is itself an anti-flicker measure:
    # per-frame adaptive thresholds make the silhouette breathe.
    backdrop = None
    try:
        if np.asarray(frames[0].convert("RGBA"))[:, :, 3].min() == 255:
            backdrop = sample_background(frames[0])
    except Exception:
        backdrop = None

    kwargs = opt("key", True)
    if kwargs is not None:
        if backdrop is not None:
            kwargs.setdefault("color", backdrop)
        frames = key_background(frames, **kwargs)
    kwargs = opt("denoise", True)
    if kwargs is not None:
        frames = denoise_matte(frames, **kwargs)
    kwargs = opt("smooth", True)
    if kwargs is not None:
        kwargs.setdefault("max_shift", 1)
        frames = smooth_silhouette(frames, **kwargs)
    kwargs = opt("choke", True)
    if kwargs is not None:
        frames = choke_matte(frames, **kwargs)
    kwargs = opt("despill", True)
    if kwargs is not None:
        if backdrop is not None:
            kwargs.setdefault("color", backdrop)
        frames = despill(frames, **kwargs)
    kwargs = opt("holes", True)
    if kwargs is not None:
        frames = fill_holes(frames, **kwargs)
    kwargs = opt("prune", True)
    if kwargs is not None:
        frames = prune_components(frames, **kwargs)
    kwargs = opt("flicker")
    if kwargs is not None:
        frames = fix_flicker(frames, **kwargs)
    kwargs = opt("alpha")
    if kwargs is not None:
        frames = threshold_alpha(frames, **kwargs)
    kwargs = opt("halo")
    if kwargs is not None:
        frames = remove_halo(frames, **kwargs)
    kwargs = opt("matte", True)
    if kwargs is not None:
        # Give the scan the ACTUAL backdrop colour rather than relying on the
        # "flat light grey" heuristic, which only holds for a grey staging
        # colour; ours is chosen per character.
        if backdrop is not None:
            kwargs.setdefault("colors", [backdrop])
        frames = clear_matte_regions(frames, **kwargs)
    kwargs = opt("edge_pad", True)
    if kwargs is not None:
        frames = edge_pad(frames, **kwargs)
    if profile.get("grid"):
        frames = quantize_grid(frames, pixel=int(profile["grid"]))
    if profile.get("palette"):
        frames = snap_palette(frames, colors=int(profile["palette"]))
    return frames
