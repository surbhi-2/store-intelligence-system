# CHOICES.md

This document explains three key decisions made during the build of the
Store Intelligence system — what options were considered, what AI suggested,
and what I chose and why.

---

## Decision 1 — Detection Model Selection

### Options Considered
- **YOLOv8n** (nano) — fastest, lowest accuracy, misses people in crowds
- **YOLOv8m** (medium) — balanced speed and accuracy
- **YOLOv8x** (extra large) — highest accuracy, too slow for near-real-time
- **RT-DETR** — transformer-based detector, better on occlusion but heavier
- **MediaPipe** — fast but optimized for single person, poor on crowds

### What AI Suggested
Claude suggested RT-DETR for better handling of partial occlusion cases
(people behind displays, crowded billing area). It argued that
transformer-based attention handles occluded scenes better than
anchor-based YOLO.

### What I Chose and Why
YOLOv8m with ByteTrack (built into ultralytics).

I disagreed with the RT-DETR suggestion for this use case. RT-DETR is
heavier and slower, and the challenge footage is 15fps — not a high
frame rate. YOLOv8m runs comfortably at 15fps on CPU. More importantly,
the ultralytics package bundles ByteTrack tracking directly, which means
I get detection + multi-object tracking in one library call. RT-DETR
would require a separate tracking integration.

For the partial occlusion edge case, I handled it at the confidence
level — low confidence detections are flagged (confidence field in
schema) rather than dropped, which is what the scoring criteria
explicitly asks for.

---

## Decision 2 — Event Schema Design

### Options Considered

**Option A** — Minimal schema: just event_type, timestamp, visitor_id.
Simple but can't answer zone-level queries.

**Option B** — Required schema from problem statement with all fields
including metadata.queue_depth, session_seq, confidence.

**Option C** — Extended schema adding raw bounding box coordinates for
later replay/analysis.

### What AI Suggested
AI suggested Option C — storing raw bounding boxes for maximum future
flexibility and potential re-analysis without re-running detection.

### What I Chose and Why
Option B — exactly the required schema, nothing more.

I overrode the AI suggestion to add bounding boxes. Reasons:

First, the scoring harness validates against the defined schema — extra
fields are not rewarded and could cause unexpected validation behavior.

Second, the schema is already well-designed for the business questions
it needs to answer. The session_seq field lets me reconstruct visitor
journeys. The confidence field handles graceful degradation. The
metadata object is flexible enough for queue_depth and sku_zone.

Third, bounding boxes would double the storage size of every event with
no scoring benefit.

The key design insight in the schema is session_seq — an ordinal counter
per visitor session. This makes funnel reconstruction O(n) instead of
requiring expensive timestamp sorting per visitor.

---

## Decision 3 — Storage Engine

### Options Considered
- **PostgreSQL** — production-grade, handles concurrent writes, requires
  its own container and configuration
- **SQLite** — file-based, zero configuration, built into Python,
  single-writer limitation
- **Redis** — fast but not a relational store, can't do funnel queries

### What AI Suggested
AI suggested PostgreSQL to signal production-readiness and because the
challenge mentions "production-aware API."

### What I Chose and Why
SQLite.

The challenge runs on a single reviewer's machine from a git clone.
SQLite requires zero configuration, zero extra containers, and zero
credential management. The SQLAlchemy ORM layer means migrating to
PostgreSQL is literally a one-line change to DATABASE_URL.

I chose the option that eliminates an entire failure surface — DB
container not starting, wrong credentials, healthcheck timing races —
so I could focus time on detection accuracy and API correctness, which
are worth 65 of the 100 points.

In production at 40 live stores sending concurrent events, I would
switch to PostgreSQL and add a connection pool. The write bottleneck in
SQLite would appear first at the /events/ingest endpoint under
simultaneous multi-store load.

## Decision 4 — Tracking Strategy

### Options Considered

* Centroid tracking (custom implementation)
* DeepSORT
* ByteTrack
* OC-SORT

### What AI Suggested

AI suggested DeepSORT because appearance embeddings can help recover identities after short occlusions.

### What I Chose and Why

ByteTrack.

The challenge videos are short retail CCTV clips where people are mostly visible and camera viewpoints are fixed. ByteTrack is already integrated with the Ultralytics ecosystem and requires no additional model downloads or embedding networks.

Compared to DeepSORT, ByteTrack is simpler to deploy, faster on CPU, and has fewer dependencies. It also performs well on retail-style scenes where the main challenge is maintaining identities through temporary missed detections.

For a take-home challenge prioritizing reliability and reproducibility, ByteTrack provided the best trade-off between accuracy, implementation complexity, and runtime performance.
