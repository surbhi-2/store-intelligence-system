#!/bin/bash
# run.sh — process all clips and feed events into the API
# Usage: ./pipeline/run.sh

set -e

LAYOUT="data/store_layout.json"
OUTPUT_DIR="data/events"
mkdir -p $OUTPUT_DIR

echo "=== Store Intelligence Detection Pipeline ==="
echo "Store: Brigade_Bangalore (ST1008)"
echo ""

# Process the video
python3 -m pipeline.detect \
    --video "data/store_4.mp4" \
    --layout "$LAYOUT" \
    --camera "CAM_FLOOR_01" \
    --output "$OUTPUT_DIR/store_4_events.jsonl" \
    --start-time "2026-04-10T12:00:00+00:00"

echo ""
echo "=== Ingesting events into API ==="

# Feed events into the API in batches
python3 -c "
import json, requests, sys

jsonl_file = '$OUTPUT_DIR/store_4_events.jsonl'
api_url = 'http://localhost:8000/events/ingest'

events = []
with open(jsonl_file) as f:
    for line in f:
        line = line.strip()
        if line:
            events.append(json.loads(line))

print(f'Total events to ingest: {len(events)}')

# Send in batches of 500
batch_size = 500
for i in range(0, len(events), batch_size):
    batch = events[i:i+batch_size]
    resp = requests.post(api_url, json={'events': batch})
    print(f'Batch {i//batch_size + 1}: {resp.json()}')

print('Done.')
"