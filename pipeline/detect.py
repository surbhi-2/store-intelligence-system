# pipeline/detect.py

import cv2
import json
import numpy as np
import argparse
from datetime import datetime, timezone
from pathlib import Path
from ultralytics import YOLO
from scipy.spatial import ConvexHull

from pipeline.tracker import PersonTracker
from pipeline.emit import emit_event, append_event_to_jsonl, calc_timestamp


def load_store_layout(layout_path: str) -> dict:
    with open(layout_path, "r") as f:
        return json.load(f)


def point_in_polygon(point: tuple, polygon: list) -> bool:
    """
    Check if a point (x, y) is inside a polygon.
    Uses ray casting algorithm.
    polygon is a list of [x, y] pairs.
    """
    x, y = point
    n = len(polygon)
    inside = False
    px, py = polygon[0]
    for i in range(1, n + 1):
        qx, qy = polygon[i % n]
        if ((py > y) != (qy > y)) and (x < (qx - px) * (y - py) / (qy - py + 1e-9) + px):
            inside = not inside
        px, py = qx, qy
    return inside


def get_zone_for_point(x: float, y: float, zones: list, camera_id: str) -> tuple:
    """
    Given a point and camera_id, find which zone it's in.
    Returns (zone_id, sku_zone) or (None, None)
    """
    for zone in zones:
        if zone["camera_id"] != camera_id:
            continue
        if point_in_polygon((x, y), zone["polygon"]):
            return zone["zone_id"], zone.get("sku_zone")
    return None, None


#def detect_staff_by_color(frame: np.ndarray, bbox: list) -> bool:
    """
    Simple staff detection by uniform color.
    Staff at retail stores often wear specific colored uniforms.
    This checks if the dominant color in the torso area matches
    a staff uniform color range.

    This is a heuristic — document in CHOICES.md that a VLM
    would be more accurate but slower.
    """
    if len(bbox) < 4:
        return False

    x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    height = y2 - y1

    # Focus on torso area (middle third of bounding box)
    torso_y1 = y1 + height // 3
    torso_y2 = y1 + (2 * height) // 3

    # Clamp to frame bounds
    h, w = frame.shape[:2]
    x1 = max(0, x1); x2 = min(w, x2)
    torso_y1 = max(0, torso_y1); torso_y2 = min(h, torso_y2)

    if x2 <= x1 or torso_y2 <= torso_y1:
        return False

    torso = frame[torso_y1:torso_y2, x1:x2]
    if torso.size == 0:
        return False

    # Convert to HSV for better color detection
    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    avg_hue = np.mean(hsv[:, :, 0])
    avg_sat = np.mean(hsv[:, :, 1])

    # Black uniform: low saturation, low value
    avg_val = np.mean(hsv[:, :, 2])
    if avg_sat < 50 and avg_val < 80:
        return True

    # Dark navy/blue uniform: hue around 100-130
    if 100 <= avg_hue <= 130 and avg_sat > 80:
        return True

    return False

def detect_staff_by_color(frame, bbox):
    return False

def process_video(
    video_path: str,
    store_layout: dict,
    camera_id: str,
    output_jsonl: str,
    clip_start_time: datetime = None
):
    """
    Main processing function.
    Opens video, runs YOLO+ByteTrack, emits events.
    """
    if clip_start_time is None:
        # Default: use today's date at store opening time
        clip_start_time = datetime.now(tz=timezone.utc).replace(
            hour=10, minute=0, second=0, microsecond=0
        )

    print(f"Loading YOLO model...")
    # YOLOv8m — medium model, good balance of speed and accuracy
    # 'm' is better than 'n' (nano) for detecting people in crowds
    model = YOLO("yolov8m.pt")

    print(f"Opening video: {video_path}")
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"Video: {width}x{height} @ {fps:.1f}fps, {total_frames} frames")

    store_id   = store_layout["store_id"]
    zones      = store_layout["zones"]
    entry_line = store_layout.get("entry_line", {})
    entry_y    = entry_line.get("y_threshold", height // 2)

    tracker    = PersonTracker(reentry_window_seconds=300)
    all_events = []

    # Track zone dwell times
    # track_id -> {zone_id, enter_frame, last_dwell_emit_frame}
    zone_state: dict = {}

    # Track billing queue
    billing_visitors: set = set()

    frame_number = 0
    process_every_n = 2  # Process every 2nd frame for speed (still 12fps)

    print(f"Processing {total_frames} frames...")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_number += 1

        # Skip frames for speed — still accurate enough
        if frame_number % process_every_n != 0:
            continue

        # Calculate real-world timestamp for this frame
        timestamp_str = calc_timestamp(clip_start_time, frame_number, fps)
        frame_time = datetime.fromtimestamp(
            clip_start_time.timestamp() + frame_number / fps,
            tz=timezone.utc
        )

        # Run YOLOv8 with ByteTrack
        # persist=True keeps track IDs consistent across frames
        # classes=[0] means only detect "person" class (class 0 in COCO)
        # conf=0.3 means minimum 30% confidence — we keep low conf events
        #          but flag them, not drop them
        results = model.track(
            frame,
            persist=True,
            classes=[0],
            conf=0.25,
            iou=0.5,
            tracker="bytetrack.yaml",
            verbose=False
        )

        current_track_ids = set()

        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes      = results[0].boxes.xyxy.cpu().numpy()
            track_ids  = results[0].boxes.id.cpu().numpy().astype(int)
            confidences = results[0].boxes.conf.cpu().numpy()

            for bbox, track_id, conf in zip(boxes, track_ids, confidences):
                current_track_ids.add(track_id)

                x1, y1, x2, y2 = bbox
                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2
                foot_y   = y2  # Bottom of bounding box = feet position

                # Detect if this person is staff
                is_staff = detect_staff_by_color(frame, bbox)

                # Get or create visitor session
                visitor_id, is_new, is_reentry = tracker.get_or_create_visitor(
                    track_id, list(bbox), frame_time, is_staff
                )

                session_seq = tracker.get_session_seq(track_id)

                # ── ENTRY / REENTRY detection ──
                # Person appears near the top of frame (y < entry_y) going down
                if camera_id == "CAM_ENTRY_01":
                    if is_new:
                        if is_reentry:
                            event = emit_event(
                            store_id=store_id,
                            camera_id=camera_id,
                            visitor_id=visitor_id,
                            event_type="REENTRY",
                            timestamp=timestamp_str,
                            zone_id=None,
                            dwell_ms=0,
                            is_staff=is_staff,
                            confidence=float(conf),
                            session_seq=session_seq
                            )
                        else:
                            event = emit_event(
                            store_id=store_id,
                            camera_id=camera_id,
                            visitor_id=visitor_id,
                            event_type="ENTRY",
                            timestamp=timestamp_str,
                            zone_id=None,
                            dwell_ms=0,
                            is_staff=is_staff,
                            confidence=float(conf),
                            session_seq=session_seq
                            )
                        all_events.append(event)
                        append_event_to_jsonl(event, output_jsonl)

                # ── ZONE detection ──
            #if camera_id != "CAM_ENTRY_01":
                zone_id, sku_zone = get_zone_for_point(
                    center_x, foot_y, zones, camera_id
                )

                prev_zone = tracker.get_zone(track_id)

                if zone_id != prev_zone:
                    # Person moved to a different zone
                    if prev_zone is not None:
                        # Emit ZONE_EXIT for previous zone
                        dwell_ms = tracker.get_zone_dwell_ms(track_id, frame_time)
                        if dwell_ms < 3000:
                            continue
                        tracker.increment_seq(track_id)
                        exit_event = emit_event(
                            store_id=store_id,
                            camera_id=camera_id,
                            visitor_id=visitor_id,
                            event_type="ZONE_EXIT",
                            timestamp=timestamp_str,
                            zone_id=prev_zone,
                            dwell_ms=dwell_ms,
                            is_staff=is_staff,
                            confidence=float(conf),
                            session_seq=tracker.get_session_seq(track_id)
                        )
                        all_events.append(exit_event)
                        append_event_to_jsonl(exit_event, output_jsonl)

                    if zone_id is not None:
                        # Emit ZONE_ENTER for new zone
                        tracker.set_zone(track_id, zone_id, frame_time)
                        tracker.increment_seq(track_id)

                        # Check if billing zone with queue
                        current_queue_depth = None
                        event_type = "ZONE_ENTER"

                        if zone_id == "BILLING":
                            current_queue_depth = len(billing_visitors)
                            if current_queue_depth > 0:
                                event_type = "BILLING_QUEUE_JOIN"
                            billing_visitors.add(visitor_id)

                        enter_event = emit_event(
                            store_id=store_id,
                            camera_id=camera_id,
                            visitor_id=visitor_id,
                            event_type=event_type,
                            timestamp=timestamp_str,
                            zone_id=zone_id,
                            dwell_ms=0,
                            is_staff=is_staff,
                            confidence=float(conf),
                            sku_zone=sku_zone,
                            queue_depth=current_queue_depth,
                            session_seq=tracker.get_session_seq(track_id)
                        )
                        all_events.append(enter_event)
                        append_event_to_jsonl(enter_event, output_jsonl)
                    else:
                       tracker.set_zone(track_id, None, frame_time)

                # ── ZONE_DWELL — emit every 30 seconds of continuous dwell ──
                if zone_id is not None:
                    dwell_ms = tracker.get_zone_dwell_ms(track_id, frame_time)
                    if dwell_ms >= 30000:
                        last_dwell = zone_state.get(track_id, {}).get("last_dwell_ms", 0)
                        if dwell_ms - last_dwell >= 30000:
                            tracker.increment_seq(track_id)
                            dwell_event = emit_event(
                                store_id=store_id,
                                camera_id=camera_id,
                                visitor_id=visitor_id,
                                event_type="ZONE_DWELL",
                                timestamp=timestamp_str,
                                zone_id=zone_id,
                                dwell_ms=dwell_ms,
                                is_staff=is_staff,
                                confidence=float(conf),
                                sku_zone=sku_zone,
                                session_seq=tracker.get_session_seq(track_id)
                            )
                            all_events.append(dwell_event)
                            append_event_to_jsonl(dwell_event, output_jsonl)
                            if track_id not in zone_state:
                                zone_state[track_id] = {}
                            zone_state[track_id]["last_dwell_ms"] = dwell_ms

        # ── EXIT detection ──
        # Any track we saw last frame but not this frame = potential exit
        
        MAX_MISSING_FRAMES = 150

        for track_id in list(tracker.active_tracks.keys()):

           if track_id in current_track_ids:
              tracker.active_tracks[track_id]["missing_frames"] = 0
              continue

        tracker.active_tracks[track_id]["missing_frames"] += 1

        if tracker.active_tracks[track_id]["missing_frames"] < MAX_MISSING_FRAMES:
          continue

        track_info = tracker.active_tracks[track_id]

        visitor_id = track_info["visitor_id"]
        is_staff = track_info["is_staff"]

        billing_visitors.discard(visitor_id)

        tracker.increment_seq(track_id)

        exit_event = emit_event(
        store_id=store_id,
        camera_id=camera_id,
        visitor_id=visitor_id,
        event_type="EXIT",
        timestamp=timestamp_str,
        zone_id=None,
        dwell_ms=0,
        is_staff=is_staff,
        confidence=0.7,
        session_seq=tracker.get_session_seq(track_id)
        )

        all_events.append(exit_event)
        append_event_to_jsonl(exit_event, output_jsonl)

        tracker.mark_exited(track_id, frame_time)

# ← OUTSIDE FOR LOOP

    if frame_number % 300 == 0:
     tracker.cleanup_old_exits(frame_time)
     progress = (frame_number / total_frames) * 100
     print(
        f"Progress: {progress:.1f}% | "
        f"Active tracks: {len(tracker.active_tracks)} | "
        f"Events: {len(all_events)}"
    )

    cap.release()

    print(f"\nDone. Total events emitted: {len(all_events)}")
    print(f"Events written to: {output_jsonl}")

    return all_events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video",    required=True, help="Path to video file")
    parser.add_argument("--layout",   required=True, help="Path to store_layout.json")
    parser.add_argument("--camera",   required=True, help="Camera ID e.g. CAM_ENTRY_01")
    parser.add_argument("--output",   required=True, help="Output .jsonl file path")
    parser.add_argument("--start-time", default=None, help="Clip start time ISO-8601")
    args = parser.parse_args()

    layout = load_store_layout(args.layout)

    start_time = None
    if args.start_time:
        start_time = datetime.fromisoformat(args.start_time)
    else:
        # Use today's date at store opening (12:00 based on your CSV data)
        start_time = datetime.now(tz=timezone.utc).replace(
            hour=12, minute=0, second=0, microsecond=0
        )

    process_video(
        video_path=args.video,
        store_layout=layout,
        camera_id=args.camera,
        output_jsonl=args.output,
        clip_start_time=start_time
    )