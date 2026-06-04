# pipeline/tracker.py

import numpy as np
from datetime import datetime, timezone
from typing import Optional
from pipeline.emit import make_visitor_id



class PersonTracker:
    """
    Manages visitor sessions and Re-ID across frames.

    The core problem: YOLOv8+ByteTrack gives each person a track_id
    that resets when they leave the frame. We need a stable visitor_id
    that persists for the whole visit and detects re-entry.

    Our Re-ID approach: bounding box size + position similarity.
    When a new track appears, compare it to recently-exited tracks.
    If size and entry position are similar within a time window,
    it's likely the same person returning = REENTRY.
    """

    def __init__(self, reentry_window_seconds: int = 300):
        # Active tracks: track_id -> visitor info
        self.active_tracks: dict = {}

        # Recently exited visitors for re-entry detection
        # visitor_id -> {exit_time, bbox_size, exit_position}
        self.exited_visitors: dict = {}

        # How long to remember exited visitors for re-entry detection (5 min)
        self.reentry_window = reentry_window_seconds

        # Staff track IDs identified this session
        self.staff_track_ids: set = set()

    def get_or_create_visitor(
        self,
        track_id: int,
        bbox: list,
        frame_timestamp: datetime,
        is_staff: bool = False
    ) -> tuple:
        """
        Given a YOLOv8 track_id and bounding box, return:
        (visitor_id, is_new_entry, is_reentry)

        is_new_entry = True if this is the first time we see this track
        is_reentry = True if we matched this to a previously exited visitor
        """
        # Already tracking this person
        if track_id in self.active_tracks:
            self.active_tracks[track_id]["last_seen"] = frame_timestamp
            #self.active_tracks[track_id]["session_seq"] += 1
            return (
                self.active_tracks[track_id]["visitor_id"],
                False,
                False
            )

        # New track — check if it's a re-entry
        matched_visitor_id = self._check_reentry(bbox, frame_timestamp)

        if matched_visitor_id:
            # Re-entry detected
            visitor_id = matched_visitor_id
            is_reentry = True
            # Remove from exited list
            del self.exited_visitors[visitor_id]
        else:
            # Brand new visitor
            visitor_id = make_visitor_id()
            is_reentry = False

        # Register this track
        self.active_tracks[track_id] = {
            "visitor_id":   visitor_id,
            "track_id":     track_id,
            "first_seen":   frame_timestamp,
            "last_seen":    frame_timestamp,
            "bbox":         bbox,
            "is_staff":     is_staff,
            "session_seq":  1,
            "current_zone": None,
            "zone_enter_time": None,
            "missing_frames": 0
        }

        if is_staff:
            self.staff_track_ids.add(track_id)

        return (visitor_id, True, is_reentry)

    def get_session_seq(self, track_id: int) -> int:
        if track_id in self.active_tracks:
            return self.active_tracks[track_id]["session_seq"]
        return 0

    def increment_seq(self, track_id: int):
        if track_id in self.active_tracks:
            self.active_tracks[track_id]["session_seq"] += 1

    def set_zone(self, track_id: int, zone_id: str, timestamp: datetime):
        if track_id in self.active_tracks:
            self.active_tracks[track_id]["current_zone"] = zone_id
            self.active_tracks[track_id]["zone_enter_time"] = timestamp

    def get_zone(self, track_id: int) -> Optional[str]:
        if track_id in self.active_tracks:
            return self.active_tracks[track_id].get("current_zone")
        return None

    def get_zone_dwell_ms(self, track_id: int, current_time: datetime) -> int:
        if track_id in self.active_tracks:
            enter_time = self.active_tracks[track_id].get("zone_enter_time")
            if enter_time:
                return int((current_time - enter_time).total_seconds() * 1000)
        return 0

    def mark_exited(self, track_id: int, frame_timestamp: datetime):
        """Called when a person crosses the exit threshold"""
        if track_id not in self.active_tracks:
            return

        track = self.active_tracks[track_id]
        visitor_id = track["visitor_id"]
        bbox = track["bbox"]

        # Remember this visitor for potential re-entry detection
        self.exited_visitors[visitor_id] = {
            "exit_time":      frame_timestamp,
            "bbox_width":     bbox[2] - bbox[0] if len(bbox) >= 4 else 100,
            "bbox_height":    bbox[3] - bbox[1] if len(bbox) >= 4 else 200,
            "exit_x":         (bbox[0] + bbox[2]) / 2 if len(bbox) >= 4 else 0,
        }

        del self.active_tracks[track_id]

    def cleanup_old_exits(self, current_time: datetime):
        """Remove exited visitors outside the re-entry window"""
        to_remove = []
        for vid, info in self.exited_visitors.items():
            elapsed = (current_time - info["exit_time"]).total_seconds()
            if elapsed > self.reentry_window:
                to_remove.append(vid)
        for vid in to_remove:
            del self.exited_visitors[vid]

    def _check_reentry(self, bbox: list, current_time: datetime) -> Optional[str]:
        """
        Compare new track's bounding box to recently exited visitors.
        If size is similar (within 30%) and recent (within reentry_window),
        it's likely the same person returning.
        """
        if not self.exited_visitors or len(bbox) < 4:
            return None

        new_width  = bbox[2] - bbox[0]
        new_height = bbox[3] - bbox[1]
        new_x      = (bbox[0] + bbox[2]) / 2

        best_match = None
        best_score = float("inf")

        for visitor_id, info in self.exited_visitors.items():
            # Check time window
            elapsed = (current_time - info["exit_time"]).total_seconds()
            if elapsed > self.reentry_window:
                continue

            # Compare bounding box size (person's physical size stays same)
            old_width  = info["bbox_width"]
            old_height = info["bbox_height"]

            width_diff  = abs(new_width - old_width) / max(old_width, 1)
            height_diff = abs(new_height - old_height) / max(old_height, 1)

            # Similar size = within 35% difference
            if width_diff < 0.15 and height_diff < 0.15:
                score = width_diff + height_diff
                if score < best_score:
                    best_score = score
                    best_match = visitor_id

        return best_match


# Add this import at top of tracker.py
#from typing import Optional