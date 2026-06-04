# Store Intelligence System Design

## Overview

The system converts CCTV footage into business intelligence metrics through an event-driven pipeline.

The architecture contains three layers:

1. Video Analytics Layer
2. Event Processing Layer
3. Analytics API Layer

---

## Layer 1 — Video Analytics

Input:

* CCTV video
* Store layout configuration

Processing:

1. YOLOv8 detects people.
2. ByteTrack assigns stable track IDs.
3. Track IDs are converted into visitor sessions.
4. Foot positions are mapped to store zones.
5. Events are emitted.

Generated events:

* ENTRY
* EXIT
* REENTRY
* ZONE_ENTER
* ZONE_EXIT
* ZONE_DWELL
* BILLING_QUEUE_JOIN

Output:

JSONL event stream.

---

## Layer 2 — Event Processing

The ingestion API validates incoming events.

Responsibilities:

* Schema validation
* Duplicate detection
* Event persistence
* Health monitoring

Storage:

SQLite database using SQLAlchemy ORM.

---

## Layer 3 — Analytics

Analytics are computed directly from stored events.

Metrics API:

* Unique visitors
* Revenue
* Transactions
* Dwell time
* Queue depth
* Abandonment rate

Funnel API:

ENTRY → ZONE_VISIT → BILLING_QUEUE → PURCHASE

Anomaly API:

* Dead zones
* Low traffic areas
* Billing bottlenecks

---

## Event Flow

Video
↓
YOLOv8 Detection
↓
ByteTrack Tracking
↓
Zone Mapping
↓
Event Generation
↓
JSONL
↓
Ingestion API
↓
SQLite
↓
Analytics APIs
↓
Dashboard

---

## Scalability

Current:

* Single-node deployment
* SQLite backend
* Local event files

Future:

* PostgreSQL
* Kafka event stream
* Multi-store ingestion
* Real-time dashboard updates

---

## Tradeoffs

Strengths:

* Simple deployment
* Fast setup
* Minimal infrastructure
* Reproducible evaluation

Limitations:

* SQLite write bottleneck
* Heuristic staff detection
* Single-camera visitor identity
* Offline processing rather than live streaming
