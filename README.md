# Store Intelligence System

## Overview

Store Intelligence converts CCTV footage into actionable retail analytics.

The system detects customers, tracks movement across store zones, generates structured visitor events, correlates those events with POS transactions, and exposes business metrics through REST APIs and a dashboard.

Key analytics include:

* Visitor count
* Zone dwell time
* Billing queue depth
* Conversion funnel
* Revenue analytics
* Dead-zone detection

---

## Architecture

The solution contains four layers:

1. Video Analytics Layer
2. Event Generation Layer
3. Analytics API Layer
4. Dashboard Layer

![Architecture](store_intelligence_architecture.png)

## Tech Stack

### Computer Vision

* YOLOv8m
* ByteTrack
* OpenCV

### Backend

* FastAPI
* SQLAlchemy
* SQLite

### Analytics

* Python
* Pandas

### Dashboard

* Streamlit

---

## Project Structure

app/
pipeline/
scripts/
data/
docs/

---

## Setup

### Clone Repository

git clone <repo>

### Install Dependencies

pip install -r requirements.txt

### Start API

docker compose up

### Open Swagger

http://localhost:8000/docs

---

## Processing Videos

python -m pipeline.detect 
--video data/videos/store1.mp4 
--layout data/store_layout.json 
--camera CAM_FLOOR_01 
--output data/events/store1_events.jsonl

---

## Load Events

python scripts/load_events.py

---

## Load POS Transactions

python scripts/load_pos.py data/pos_data.csv

---

## Dashboard

streamlit run dashboard.py

---

## API Endpoints

GET /health

GET /stores/{store_id}/metrics

GET /stores/{store_id}/funnel

GET /stores/{store_id}/anomalies

POST /events/ingest

---

## Assumptions

* One visitor corresponds to one tracked identity.
* Store zones are manually configured.
* Billing-zone presence is used as a proxy for purchase intent.
* Staff detection uses a heuristic approach.

---

## Future Improvements

* Multi-camera re-identification
* PostgreSQL backend
* Kafka event streaming
* Real-time video ingestion
* DeepSORT-based tracking
* LLM-powered anomaly explanations
