# pipeline/emit.py

import uuid
import json
from datetime import datetime, timezone
from typing import Optional


def make_visitor_id() -> str:
    """Generate a short readable visitor ID like VIS_c8a2f1"""
    short = str(uuid.uuid4()).replace("-", "")[:6]
    return f"VIS_{short}"


def make_event_id() -> str:
    """Generate a UUID4 event ID"""
    return str(uuid.uuid4())


def calc_timestamp(clip_start_time: datetime, frame_number: int, fps: float) -> str:
    """
    Convert frame number to ISO-8601 UTC timestamp.
    clip_start_time: when the video recording started (real wall clock time)
    frame_number: which frame we're on
    fps: frames per second of the video
    """
    offset_seconds = frame_number / fps
    event_time = clip_start_time.timestamp() + offset_seconds
    dt = datetime.fromtimestamp(event_time, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_event(
    store_id: str,
    camera_id: str,
    visitor_id: str,
    event_type: str,
    timestamp: str,
    zone_id: Optional[str],
    dwell_ms: int,
    is_staff: bool,
    confidence: float,
    queue_depth: Optional[int] = None,
    sku_zone: Optional[str] = None,
    session_seq: int = 0
) -> dict:
    """
    Build a single event dictionary matching the required schema exactly.
    This is called by detect.py every time something happens.
    """
    return {
        "event_id":   make_event_id(),
        "store_id":   store_id,
        "camera_id":  camera_id,
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp":  timestamp,
        "zone_id":    zone_id,
        "dwell_ms":   dwell_ms,
        "is_staff":   is_staff,
        "confidence": round(confidence, 4),
        "metadata": {
            "queue_depth": queue_depth,
            "sku_zone":    sku_zone,
            "session_seq": session_seq
        }
    }


def write_events_to_jsonl(events: list, output_path: str):
    """
    Write list of events to a .jsonl file.
    Each line is one JSON event — this is the standard format
    for streaming event data.
    """
    with open(output_path, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
    print(f"Written {len(events)} events to {output_path}")


def append_event_to_jsonl(event: dict, output_path: str):
    """
    Append a single event to .jsonl file — used for real-time streaming mode.
    """
    with open(output_path, "a") as f:
        f.write(json.dumps(event) + "\n")