"""CPU optical-flow propagation of sampled 09b segmentation masks.

No classifications are invented between keyframes: these are propagated mask
estimates, reset to the real pipeline result at each sampled/key frame.
This is an offline video visualization, not a real-time detector.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from app.services.video_safe_zone import DEFAULT_ZONE, validate_zone, zone_pixels

FLOW_MAX_WIDTH = 576


def _colour_hex(value):
    text = str(value or '#8d8d8d').strip().lstrip('#')
    if len(text) == 3:
        text = ''.join(ch * 2 for ch in text)
    if len(text) != 6:
        return (141, 141, 141)
    try:
        return tuple(int(text[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        return (141, 141, 141)


def _mask_bounds(mask):
    pts = cv2.findNonZero(mask)
    if pts is None:
        return None
    x, y, w, h = cv2.boundingRect(pts)
    return [x, y, x + w, y + h]


def _iou(a, b):
    if a is None or b is None:
        return 0.0
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x1 - x0) * max(0, y1 - y0)
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return intersection / max(1, area_a + area_b - intersection)


def _encode_polygons(mask, scale_x, scale_y):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polygons = []
    for contour in contours:
        if cv2.contourArea(contour) < 12:
            continue
        approx = cv2.approxPolyDP(contour, max(1.6, cv2.arcLength(contour, True) * 0.012), True)
        points = approx.reshape(-1, 2)
        # Limit transfer size while retaining an accurate clickable silhouette.
        if len(points) > 70:
            points = points[::math.ceil(len(points) / 70)]
        if len(points) >= 3:
            polygons.append([[int(round(x * scale_x)), int(round(y * scale_y))] for x, y in points])
    return polygons


@dataclass
class _Tracked:
    number: int
    mask: np.ndarray
    meta: dict


class VideoMaskTracker:
    """Refresh on sampled AI keyframes; flow-warp masks on other video frames."""

    def __init__(self, width: int, height: int, safe_zone=DEFAULT_ZONE):
        self.width, self.height = int(width), int(height)
        self.safe_zone = validate_zone(safe_zone)
        self.zone_rect = zone_pixels(self.safe_zone, self.width, self.height)
        # Each tracked object triggers independently on first crossing.
        # Completed ids never re-arm, including after an AI keyframe refresh.
        self.activated: set[int] = set()
        self.completed: set[int] = set()
        self.outside_frames: dict[int, int] = {}
        self.activations: list[dict] = []
        self.flow_width = min(FLOW_MAX_WIDTH, self.width)
        self.flow_height = max(16, round(self.height * self.flow_width / self.width))
        self.scale_x = self.width / self.flow_width
        self.scale_y = self.height / self.flow_height
        self.tracked: dict[int, _Tracked] = {}
        self.track_info: dict[str, dict] = {}
        self.track_history: dict[str, list] = {}
        self.frame_index = -1
        self.serial = 0
        self.previous_gray = None
        self.optic = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_ULTRAFAST) if hasattr(cv2, 'DISOpticalFlow_create') else None
        self.map_x, self.map_y = np.meshgrid(
            np.arange(self.flow_width, dtype=np.float32),
            np.arange(self.flow_height, dtype=np.float32),
        )

    def _gray(self, bgr):
        scaled = cv2.resize(bgr, (self.flow_width, self.flow_height), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)

    def _new_mask(self, item):
        mask = np.zeros((self.flow_height, self.flow_width), dtype=np.uint8)
        for polygon in item.get('polygons') or []:
            if len(polygon) < 3:
                continue
            coords = np.asarray(polygon, dtype=np.float32).reshape(-1, 2)
            coords[:, 0] /= self.scale_x
            coords[:, 1] /= self.scale_y
            cv2.fillPoly(mask, [np.rint(coords).astype(np.int32)], 255)
        return mask

    def _flow(self, previous_gray, current_gray):
        # Backward flow (current pixel -> its position in previous frame).
        if self.optic is not None:
            return self.optic.calc(current_gray, previous_gray, None)
        return cv2.calcOpticalFlowFarneback(current_gray, previous_gray, None,
                                          0.5, 2, 11, 2, 5, 1.1, 0)

    def update(self, bgr, keyframe=None):
        self.frame_index += 1
        now = self._gray(bgr)
        if self.previous_gray is not None and self.tracked:
            flow = self._flow(self.previous_gray, now)
            map_x = self.map_x + flow[:, :, 0]
            map_y = self.map_y + flow[:, :, 1]
            for number, track in list(self.tracked.items()):
                mask = cv2.remap(track.mask, map_x, map_y, cv2.INTER_NEAREST,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=0)
                if cv2.countNonZero(mask) < 12:
                    del self.tracked[number]
                else:
                    track.mask = mask
        if keyframe is not None:
            self._refresh(keyframe.get('objects') or [])
        self.previous_gray = now

    def _refresh(self, objects):
        candidates = []
        for item in objects:
            mask = self._new_mask(item)
            if cv2.countNonZero(mask) < 12:
                continue
            candidates.append((mask, _mask_bounds(mask), item))
        active = list(self.tracked.values())
        pairs = sorted(((_iou(_mask_bounds(track.mask), bounds), track.number, idx)
                        for track in active for idx, (_, bounds, _) in enumerate(candidates)), reverse=True)
        assignments = {}
        occupied = set()
        for score, number, idx in pairs:
            if score < 0.18:
                continue
            if number in occupied or idx in assignments:
                continue
            # Do not transfer identity between different 09b classes.
            previous = self.track_info.get(str(number), {})
            current = candidates[idx][2]
            if previous.get('class_name') and previous.get('class_name') != current.get('class_name'):
                continue
            assignments[idx] = number
            occupied.add(number)
        fresh = {}
        for idx, (mask, _, item) in enumerate(candidates):
            number = assignments.get(idx)
            if number is None:
                self.serial += 1
                number = self.serial
            meta = {key: item.get(key) for key in (
                'object_id', 'class_name', 'display_name', 'class_confidence',
                'detection_confidence', 'decision', 'mask_colour',
            )}
            meta['track_id'] = number
            fresh[number] = _Tracked(number, mask, meta)
            self.track_info[str(number)] = meta
            self.track_history.setdefault(str(number), []).append([self.frame_index, meta])
        # A keyframe decides which biscuits still exist; old tracks not found
        # here must disappear rather than being shown indefinitely.
        self.tracked = fresh
        for number in list(self.outside_frames):
            if number not in fresh:
                self.outside_frames.pop(number, None)

    def _show_mask_in_zone(self, number: int, mask: np.ndarray) -> np.ndarray | None:
        """Activate on x-only entry; never crop any visible mask to the zone."""
        bounds = _mask_bounds(mask)
        if not bounds or number in self.completed:
            return None
        x0, y0, x1, y1 = self.zone_rect
        center_x = (bounds[0] + bounds[2]) * 0.5
        # The zone controls horizontal entry only. Vertical position does not
        # restrict activation; a whole biscuit mask remains visible at edges.
        inside = x0 <= center_x < x1
        if inside:
            self.outside_frames[number] = 0
            if number not in self.activated:
                self.activated.add(number)
                self.activations.append({"track_id": number, "entry_frame": self.frame_index})
        else:
            if number in self.activated:
                # Two consecutive outside frames finish the event. This
                # prevents minor optical-flow jitter from rearming it.
                self.outside_frames[number] = self.outside_frames.get(number, 0) + 1
                if self.outside_frames[number] >= 2:
                    self.completed.add(number)
            return None
        if number not in self.activated:
            return None
        # Never clip an activated biscuit: its top/bottom/side silhouette
        # must remain intact, including the clickable coordinates.
        return mask if cv2.countNonZero(mask) >= 12 else None

    def paint_and_metadata(self, bgr):
        """Return full clickable silhouettes for activated tracks only."""
        if not self.tracked:
            return bgr, []
        alpha = np.zeros_like(bgr)
        overlay_mask = np.zeros((self.height, self.width), dtype=np.uint8)
        frames = []
        for number, track in sorted(self.tracked.items()):
            full_mask = cv2.resize(track.mask, (self.width, self.height), interpolation=cv2.INTER_NEAREST)
            visible_mask = self._show_mask_in_zone(number, full_mask)
            if visible_mask is None:
                continue
            contours, _ = cv2.findContours(visible_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            rgb = _colour_hex(track.meta.get('mask_colour'))
            bgr_colour = (rgb[2], rgb[1], rgb[0])
            cv2.drawContours(alpha, contours, -1, bgr_colour, cv2.FILLED)
            overlay_mask = cv2.bitwise_or(overlay_mask, visible_mask)
            cv2.drawContours(bgr, contours, -1, (250, 250, 250), 1, cv2.LINE_AA)
            # Metadata follows the whole visible biscuit silhouette.
            flow_mask = cv2.resize(visible_mask, (self.flow_width, self.flow_height),
                                   interpolation=cv2.INTER_NEAREST)
            polygons = _encode_polygons(flow_mask, self.scale_x, self.scale_y)
            bounds = _mask_bounds(visible_mask)
            if polygons and bounds:
                frames.append([number, bounds, polygons])
        if cv2.countNonZero(overlay_mask):
            colour = cv2.addWeighted(bgr, 0.60, alpha, 0.40, 0)
            bgr[overlay_mask > 0] = colour[overlay_mask > 0]
        # Safe Zone is an invisible trigger boundary, not a video overlay.
        return bgr, frames
