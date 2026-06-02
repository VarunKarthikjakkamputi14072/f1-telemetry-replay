"""Clip recorder for the telemetry replay.

Captures the live pygame frame buffer while recording and exports a shareable
clip (MP4 preferred, GIF fallback). Frames are sampled down to a target FPS and
optionally scaled to keep memory and file size reasonable, and recording is
hard-capped so a forgotten session can't exhaust memory.
"""

import os
import time

import pygame

try:
    import imageio.v2 as imageio
except Exception:  # pragma: no cover - optional dependency
    try:
        import imageio
    except Exception:
        imageio = None


class ClipRecorder:
    """Buffers rendered frames and writes them to an MP4/GIF clip."""

    def __init__(self, out_dir, source_fps=60, target_fps=30,
                 max_seconds=30, scale=0.6, prefix="clip"):
        self.out_dir = out_dir
        self.target_fps = target_fps
        self.scale = scale
        self.prefix = prefix
        self.max_frames = target_fps * max_seconds
        self._frame_skip = max(1, round(source_fps / target_fps))

        self.recording = False
        self.frames = []
        self._tick = 0

    @property
    def available(self):
        """True when the imageio backend is importable."""
        return imageio is not None

    def toggle(self):
        """Start if idle, stop (and save) if recording. Returns saved path or None."""
        if self.recording:
            return self.stop()
        self.start()
        return None

    def start(self):
        self.frames = []
        self._tick = 0
        self.recording = True

    def capture(self, surface):
        """Buffer one sampled frame. Returns True when the cap is reached."""
        if not self.recording:
            return False
        self._tick += 1
        if self._tick % self._frame_skip != 0:
            return False

        if self.scale != 1.0:
            w, h = surface.get_size()
            surface = pygame.transform.smoothscale(
                surface, (int(w * self.scale), int(h * self.scale)))

        # pygame gives (W, H, 3); imageio expects (H, W, 3).
        arr = pygame.surfarray.array3d(surface).transpose(1, 0, 2)
        self.frames.append(arr)
        return len(self.frames) >= self.max_frames

    def stop(self):
        """Stop recording and write the clip. Returns the saved path or None."""
        self.recording = False
        if not self.frames:
            return None
        path = self._save()
        self.frames = []
        return path

    def _save(self):
        if imageio is None:
            return None
        os.makedirs(self.out_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        base = os.path.join(self.out_dir, f"{self.prefix}_{ts}")

        # Prefer MP4 (small, shareable); fall back to GIF if ffmpeg is missing.
        try:
            path = base + ".mp4"
            imageio.mimwrite(
                path, self.frames, fps=self.target_fps,
                quality=8, macro_block_size=None)
            return path
        except Exception:
            try:
                path = base + ".gif"
                imageio.mimwrite(path, self.frames, fps=self.target_fps)
                return path
            except Exception:
                return None

    @property
    def seconds(self):
        """Current recorded length in seconds."""
        return len(self.frames) / self.target_fps
