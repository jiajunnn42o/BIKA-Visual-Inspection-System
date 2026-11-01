"""Cheap, conservative visual warning for blank/virtual-webcam placeholder frames.
Not a camera API or a proof that Camo is disconnected. Large uniform grey
placeholder frames should never be submitted to the snack classifier.
"""
from __future__ import annotations
import cv2
import numpy as np


def is_placeholder(frame):
    """Detect sustained mostly-neutral mid-grey virtual-webcam backgrounds."""
    if frame is None or frame.size == 0:
        return False
    small = cv2.resize(frame, (120, 68), interpolation=cv2.INTER_AREA)
    high = small.max(axis=2).astype(np.int16)
    low = small.min(axis=2).astype(np.int16)
    mean = small.mean(axis=2)
    neutral_gray = (high - low <= 14) & (mean >= 58) & (mean <= 192)
    return float(neutral_gray.mean()) >= 0.80


class FeedVisualGuard:
    def __init__(self, delay=2.2):
        self.delay = float(delay)
        self.placeholder_since = 0.0
        self.placeholder_active = False

    def update(self, frame, now):
        flagged = is_placeholder(frame)
        if flagged:
            if not self.placeholder_since:
                self.placeholder_since = float(now)
        else:
            self.placeholder_since = 0.0
        self.placeholder_active = bool(flagged and self.placeholder_since and
                                       now - self.placeholder_since >= self.delay)
        return self.placeholder_active

    def seconds(self, now):
        return round(max(0.0, float(now)-self.placeholder_since), 2) if self.placeholder_since else 0.0

    def reset(self):
        self.placeholder_since = 0.0
        self.placeholder_active = False
