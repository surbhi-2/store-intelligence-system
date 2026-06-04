#!/bin/bash
# scripts/fix_timestamp_mismatch.sh

set -e

echo "🔧 Fixing timestamp mismatch..."
echo ""

# Step 1: Clear database
echo "Step 1: Clearing old database..."
rm -f data/store_intelligence.db data/store_intelligence.db-shm data/store_intelligence.db-wal
echo "✓ Database cleared"

# Step 2: Restart API to create fresh tables
echo ""
echo "Step 2: Restarting API (docker compose)..."
echo "Note: This will take 10 seconds, wait for 'Application startup complete'"
# Assuming docker compose is running in another terminal
# User will need to run this manually or we just note it

# Step 3: Regenerate events with CORRECT start time
echo ""
echo "Step 3: Regenerating events with correct timestamp..."
python3 -m pipeline.detect \
  --video data/store_4.mp4 \
  --layout data/store_layout.json \
  --camera CAM_FLOOR_01 \
  --output data/events/store_4_events_fixed.jsonl \
  --start-time "2026-04-10T12:15:00+00:00"

echo "✓ Events regenerated"

# Step 4: Load events
echo ""
echo "Step 4: Loading events..."
python3 scripts/load_events.py
echo "✓ Events loaded"

# Step 5: Load POS data
echo ""
echo "Step 5: Loading POS data..."
python3 scripts/load_pos.py pos_data.csv
echo "✓ POS data loaded"

# Step 6: Check metrics
echo ""
echo "Step 6: Checking metrics..."
curl -s http://localhost:8000/stores/ST1008/metrics | python3 -m json.tool

echo ""
echo "✅ Done! Conversion rate should now be > 0%"