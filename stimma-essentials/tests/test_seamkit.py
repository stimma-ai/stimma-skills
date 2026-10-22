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


async def test_motion_finds_a_slow_start(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Motion builds from a standstill over the first second, then runs steady.
    speed = np.minimum(1.0, np.arange(96) / 24) ** 2
    write_clip(Path("ramp.mp4"), [scene(t) for t in np.cumsum(speed)])
    report = await seamkit.motion(FakeStimma(), "ramp.mp4")
    assert 0.4 <= report["settles_at"] <= 1.0, report
    assert report["fades_at"] == report["duration"], report
    assert report["per_second"][0] < 0.6 and report["per_second"][-1] > 0.8, report
