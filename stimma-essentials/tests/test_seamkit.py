"""Seamkit on synthetic clips: a loop bridge with an exposure offset and pinned endpoints."""
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "video-production" / "lib"))
import seamkit  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")

W, H, FPS = 320, 192, 24


class FakeStimma:
    """The two SDK calls seamkit uses, run in the current directory like run_code does."""

    async def _run(self, tool, args):
        proc = await asyncio.to_thread(subprocess.run, [tool, *map(str, args)], capture_output=True, text=True)
        if proc.returncode:
            raise RuntimeError(proc.stderr)
        return SimpleNamespace(stdout=proc.stdout, stderr=proc.stderr)

    async def ffmpeg(self, *args, **_):
        return await self._run("ffmpeg", args)

    async def ffprobe(self, *args, **_):
        return await self._run("ffprobe", args)


PERIOD = 60


def scene(t):
    """A textured scene that moves smoothly and repeats every PERIOD frames."""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    p = 2 * np.pi * t / PERIOD
    base = 110 + 60 * np.sin(x / 23.0 + p) * np.cos(y / 31.0 - p)
    return np.stack([base, base * 0.9 + 12, base * 0.8 + 25], -1)


def write_clip(path, frames, tone=440.0, gain=0.2):
    raw = path.with_suffix(".rgb")
    np.clip(np.rint(np.stack(frames)), 0, 255).astype(np.uint8).tofile(raw)
    n = round(len(frames) / FPS * 48000)
    pcm = path.with_suffix(".f32")
    wave = (gain * np.sin(2 * np.pi * tone * np.arange(n) / 48000)).astype(np.float32)
    np.stack([wave, wave], 1).tofile(pcm)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                    "-framerate", str(FPS), "-i", raw, "-f", "f32le", "-ar", "48000", "-ac", "2", "-i", pcm,
                    "-c:v", "libx264", "-crf", "4", "-pix_fmt", "yuv444p", "-colorspace", "bt709",
                    "-color_range", "tv", "-c:a", "aac", "-shortest", path], check=True)


@pytest.fixture
def loop_clips(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Source covers t=0..47 of a 60-frame cycle. The bridge was pinned to the
    # source's last frame and its first, so it runs t=47..60 and both its end
    # frames repeat source frames.
    src = [scene(t) for t in range(48)]
    bridge_t = range(47, 61)
    bridge = [scene(t) * 0.97 - 2 for t in bridge_t]  # its own exposure: gain + offset
    write_clip(Path("source.mp4"), src)
    write_clip(Path("bridge.mp4"), bridge, tone=440.0, gain=0.1)  # 6 dB quieter
    return Path("source.mp4"), Path("bridge.mp4")


async def test_loop_bridge_is_trimmed_matched_and_verified(loop_clips):
    src, bridge = loop_clips
    stimma = FakeStimma()
    report = await seamkit.join(stimma, [{"path": src, "lock": True}, bridge], "loop.mp4", loop=True)

    bridge_seg = report["segments"][1]
    assert bridge_seg["trim_head"] == 1 and bridge_seg["trim_tail"] == 1, bridge_seg
    assert report["frames"] == 48 + 12

    for seam in report["seams"]:
        assert max(abs(d) for d in seam["before"]["median_delta_rgb"]) > 3
        assert max(abs(d) for d in seam["after"]["median_delta_rgb"]) < 1.5, seam
        assert seam["fit"]["kind"] in ("gain", "gain+offset"), seam["fit"]

    gains = report["audio_gains_db"]["1"] if "1" in report["audio_gains_db"] else report["audio_gains_db"][1]
    assert 5 < gains["head_db"] <= 6

    info = await seamkit.probe(stimma, "loop.mp4")
    assert info["has_audio"] and info["color_space"] == "bt709"


async def test_check_reports_without_writing(loop_clips):
    src, _ = loop_clips
    report = await seamkit.check(FakeStimma(), src, loop=True)
    assert "out" not in report and len(report["seams"]) == 1
    # The source alone does not loop: its wrap is a visible jump.
    assert report["seams"][0]["before"]["motion_step_ratio"] > 3


async def test_cut_is_left_alone(loop_clips):
    src, bridge = loop_clips
    report = await seamkit.join(FakeStimma(), [src, {"path": bridge, "cut": True}], None)
    assert report["segments"][1]["trim_head"] == 0
    assert report["seams"][0]["fit"] is None


async def test_overlapping_continuation_is_crossfaded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # The continuation was pinned to the first clip's last 6 frames (t=18..23),
    # so its head repeats them, at its own exposure.
    write_clip(Path("a.mp4"), [scene(t) for t in range(24)])
    write_clip(Path("b.mp4"), [scene(t) * 1.04 + 1 for t in range(18, 42)])
    report = await seamkit.join(FakeStimma(), ["a.mp4", {"path": "b.mp4", "overlap": 6}], "long.mp4")
    assert report["frames"] == 24 + 24 - 6
    seam = report["seams"][0]
    assert abs(seam["fit"]["gain_rgb"][1] - 1 / 1.04) < 0.01, seam
    assert max(abs(d) for d in seam["after"]["median_delta_rgb"]) < 1.5, seam
    assert seam["after"]["motion_step_ratio"] < 2, seam
    assert seam["moment"]["same"], seam["moment"]


async def test_loop_bridge_with_clip_pins_at_both_ends(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # The bridge pins the source's last 6 frames at its start and the source's
    # first 6 at its end, so it covers t=42..65 (65 == 5 in the 60-frame cycle).
    write_clip(Path("source.mp4"), [scene(t) for t in range(48)])
    write_clip(Path("bridge.mp4"), [scene(t) * 0.96 + 3 for t in range(42, 66)])
    report = await seamkit.join(
        FakeStimma(), [{"path": "source.mp4", "lock": True, "overlap": 6}, {"path": "bridge.mp4", "overlap": 6}],
        "loop.mp4", loop=True)
    assert report["frames"] == PERIOD
    for seam in report["seams"]:
        assert max(abs(d) for d in seam["after"]["median_delta_rgb"]) < 1.5, seam
        assert seam["after"]["motion_step_ratio"] < 2, seam
        assert seam["moment"]["same"], seam["moment"]


async def test_motion_finds_a_slow_start(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Motion builds from a standstill over the first second, then runs steady.
    speed = np.minimum(1.0, np.arange(96) / 24) ** 2
    write_clip(Path("ramp.mp4"), [scene(t) for t in np.cumsum(speed)])
    report = await seamkit.motion(FakeStimma(), "ramp.mp4")
    assert 0.4 <= report["settles_at"] <= 1.0, report
    assert report["fades_at"] == report["duration"], report
    assert report["per_second"][0] < 0.6 and report["per_second"][-1] > 0.8, report


async def test_state_preserving_join_measures_rich_host_report_without_repair(loop_clips):
    from unittest.mock import AsyncMock
    src, bridge = loop_clips
    stimma = FakeStimma()
    original = [{"media_id": 1}, {"media_id": 2, "trim_head": 1}]
    parts = [
        {"path": str(src), "trim_head": 0, "trim_tail": 0, "lock": True, "frames": 48, "has_audio": True},
        {"path": str(bridge), "trim_head": 1, "trim_tail": 1, "lock": True, "frames": 12, "has_audio": True},
    ]
    stimma.join_video = AsyncMock(return_value={"out": "joined.mp4", "frames": 60, "segments": parts, "companions": 2})
    report = await seamkit.join(stimma, original, "joined.mp4", preserve_state=True)
    stimma.join_video.assert_awaited_once_with(original, out="joined.mp4")
    assert len(report["seams"]) == 1
    assert report["segments"] == parts
    assert report["companions"] == 2


def _steps(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    g = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)
    return np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))


async def test_slow_approach_to_a_seam_keeps_the_pace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Two generated segments meet on a pinned still: the first slows to a near
    # stop over its last half second, the second starts from one.
    ease = np.linspace(1.0, 0.08, 12)
    a_t = np.concatenate([np.arange(36, dtype=float), 35 + np.cumsum(ease)])
    b_t = a_t[-1] + np.concatenate([[0.0], np.cumsum(ease[::-1]), ease.sum() + 1 + np.arange(35)])
    write_clip(Path("a.mp4"), [scene(t) for t in a_t])
    write_clip(Path("b.mp4"), [scene(t) for t in b_t])
    plain = await seamkit.join(FakeStimma(), ["a.mp4", "b.mp4"], "plain.mp4", pace=False)
    report = await seamkit.join(FakeStimma(), ["a.mp4", "b.mp4"], "paced.mp4")
    assert report["seams"][0]["slow_frames_left_out"] >= 4, report["seams"][0]
    assert report["frames"] < plain["frames"] - 4

    def slowest(path, at):
        s = _steps(path)
        typical = np.median(s)
        window = s[max(0, at - 10):at + 10]
        return np.convolve(window, np.ones(5) / 5, mode="valid").min() / typical

    assert slowest("plain.mp4", plain["seams"][0]["at_frame"]) < 0.5
    assert slowest("paced.mp4", report["seams"][0]["at_frame"]) > 0.6
    info = await seamkit.probe(FakeStimma(), "paced.mp4")
    assert abs(info["duration"] - report["frames"] / FPS) < 0.1


async def test_repeated_frames_are_replaced_by_interpolated_ones(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Every fourth frame repeats the one before; the next frame catches up.
    t = np.arange(48, dtype=float)
    shown = [scene(x - 1 if i % 4 == 3 else x) for i, x in enumerate(t)]
    write_clip(Path("a.mp4"), [scene(x) for x in range(-24, 0)])
    write_clip(Path("b.mp4"), shown)
    report = await seamkit.join(FakeStimma(), ["a.mp4", {"path": "b.mp4", "cut": True}], "out.mp4")
    assert any("repeated" in a for a in report["segments"][1]["actions"]), report["segments"][1]
    s = _steps("out.mp4")[24:-1]  # a repeat in the very last frame has nothing after it
    assert s.min() > 0.4 * np.median(s)


def _speechlike(n, seed=7):
    """Noise bursts with pauses: no two stretches alike, so any slip shows as a lag."""
    rng = np.random.default_rng(seed)
    env = np.repeat(rng.random(n // 2400 + 1) > 0.4, 2400)[:n].astype(np.float32)
    return (0.3 * rng.standard_normal(n) * env).astype(np.float32)


def _write_with_sound(path, frames, sound):
    raw, pcm = path.with_suffix(".rgb"), path.with_suffix(".f32")
    np.clip(np.rint(np.stack(frames)), 0, 255).astype(np.uint8).tofile(raw)
    np.stack([sound, sound], 1).astype(np.float32).tofile(pcm)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                    "-framerate", str(FPS), "-i", raw, "-f", "f32le", "-ar", "48000", "-ac", "2", "-i", pcm,
                    "-c:v", "libx264", "-crf", "4", "-pix_fmt", "yuv444p", "-colorspace", "bt709",
                    "-color_range", "tv", "-c:a", "pcm_s16le", "-shortest", path.with_suffix(".mov")], check=True)
    path.with_suffix(".mov").rename(path)


def _sound(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "48000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def _lag_ms(a, b, max_ms=200):
    """Lag of b against a, by cross-correlation of the first seconds."""
    n = min(len(a), len(b), 48000 * 6)
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    m = 48 * max_ms
    lags = range(-m, m + 1, 12)
    scores = [float(np.dot(a[max(0, -k):n - max(0, k)], b[max(0, k):n - max(0, -k)])) for k in lags]
    return list(lags)[int(np.argmax(scores))] / 48


async def test_pinned_sound_track_keeps_picture_and_speech_in_sync(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Three still-to-still segments of one take, each 49 frames sharing a frame
    # with the next, each slowing into and out of its end stills (what pacing
    # trims), each pinned to its slice of one continuous track.
    seg_n, step = 49, 48
    total = 1 + 3 * step
    track = _speechlike(round(total / FPS * 48000))
    _write_with_sound(Path("speech.mov"), [scene(0)] * total, track)
    ease = np.concatenate([np.linspace(0.1, 1, 12), np.ones(seg_n - 25), np.linspace(1, 0.1, 12)])
    paths = []
    for k in range(3):
        t = k * 20.0 + np.concatenate([[0.0], np.cumsum(ease)]) * 20.0 / ease.sum()
        a = round(k * step / FPS * 48000)
        part = track[a:a + round(seg_n / FPS * 48000)]
        p = Path(f"seg{k}.mov")
        _write_with_sound(p, [scene(x) for x in t], part)
        paths.append(p)
    segments = [{"path": str(paths[0])}] + [{"path": str(p), "trim_head": 1} for p in paths[1:]]

    paced = await seamkit.join(FakeStimma(), segments, "paced.mp4")
    report = await seamkit.join(FakeStimma(), segments, "take.mp4", audio="speech.mov")

    # Pacing alone leaves frames out, so its picture runs short of the speech.
    assert paced["frames"] < total
    # With the track, every frame keeps its place and the sound is the track itself.
    assert report["frames"] == total
    assert all(s["slow_frames_left_out"] == 0 for s in report["seams"])
    assert report["sound"]["note"] is None
    out = _sound("take.mp4")
    assert abs(_lag_ms(track, out)) < 2
    tail = slice(len(out) - 48000 * 2, len(out) - 4800)
    assert np.corrcoef(track[tail], out[tail])[0, 1] > 0.95
    info = await seamkit.probe(FakeStimma(), "take.mp4")
    assert abs(info["duration"] - total / FPS) < 0.06


async def test_sound_track_must_be_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="path of a sound track"):
        await seamkit.join(FakeStimma(), ["a.mp4"], "out.mp4", audio="automatic")


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "seams"


def _sides(name):
    """Frames either side of a real seam, stored as one strip: ``<name>-<frames before>.jpg``."""
    from PIL import Image
    path = next(FIXTURES.glob(f"{name}-*.jpg"))
    split = int(path.stem.rsplit("-", 1)[1])
    strip = np.asarray(Image.open(path).convert("RGB"))
    tiles = [strip[:, x:x + 160] for x in range(0, strip.shape[1], 160)]
    return tiles[:split], tiles[split:]


def test_two_clips_from_one_still_show_different_moments():
    # A sip clip's tail joined straight onto a talking clip from the same still:
    # the mug and head jump, though framing, light and the opening still match.
    moment = seamkit._moment(*_sides("different-moments"))
    assert not moment["same"], moment


@pytest.mark.parametrize("name", ["same-moment-kitchen", "same-moment-walk", "same-moment-walk-pinned"])
def test_still_to_still_joins_show_the_same_moment(name):
    # Reviewed joins between still-to-still segments, including a fast walk.
    moment = seamkit._moment(*_sides(name))
    assert moment["same"], moment


async def test_join_flags_a_seam_between_different_moments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_clip(Path("a.mp4"), [scene(t) for t in range(24)])
    write_clip(Path("b.mp4"), [scene(t) for t in range(30, 54)])  # half a cycle later
    report = await seamkit.join(FakeStimma(), ["a.mp4", "b.mp4"], "joined.mp4")
    seam = report["seams"][0]
    assert not seam["moment"]["same"], seam
    assert any("different moments" in w and "Bridge it" in w for w in report["warnings"])
    # Blending still smooths the numbers after the join; the flag doesn't depend on them.

    clean = await seamkit.join(FakeStimma(), ["a.mp4", {"path": "b.mp4", "cut": True}], None)
    assert clean["seams"][0]["moment"] is None and not clean["warnings"]
