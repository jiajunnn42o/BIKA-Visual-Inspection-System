from __future__ import annotations

class LineCounter:
    """One count per confirmed stable ID, when centroid crosses the inspection line.

    This is NOT yet global physical re-identification if object becomes a new ID.
    """
    def __init__(self, direction='ltr', position=.75):
        self.direction = direction
        self.position = position
        self.seen_before = set()
        self.crossed = set()
        self.counted = set()

    def coordinate(self, box, width, height):
        cx = (box[0] + box[2]) / 2
        cy = (box[1] + box[3]) / 2
        if self.direction == 'ltr': return cx / width
        if self.direction == 'rtl': return 1 - cx / width
        if self.direction == 'ttb': return cy / height
        if self.direction == 'btt': return 1 - cy / height
        raise ValueError(self.direction)

    def update(self, stable_id, coord, confirmed, label, confidence, tracks, min_prob):
        if coord < self.position:
            self.seen_before.add(stable_id)
        if coord >= self.position and stable_id in self.seen_before:
            self.crossed.add(stable_id)
        if (stable_id in self.crossed and stable_id not in self.counted
                and confirmed and label is not None and confidence >= min_prob):
            if tracks.emit_once(stable_id):
                self.counted.add(stable_id)
                return True
        return False

