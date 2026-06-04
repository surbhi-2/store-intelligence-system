# scripts/load_events.py
"""
Load events from JSONL files and ingest them into the API.
Sends events in batches of 500 (API limit per request).
"""

import json
import requests
import sys
from pathlib import Path
import time

# Files to load — update this with your actual event files
FILES = [
    "data/events/store1_events.jsonl",
    "data/events/store2_events.jsonl",
    "data/events/store3_events.jsonl",
    "data/events/store5_events.jsonl"
]

API_URL = "http://localhost:8000/events/ingest"
BATCH_SIZE = 500  # Max events per request (API limit)


def load_events_from_files(file_paths):
    """
    Load all events from JSONL files.
    Each line in the file is one JSON event.
    
    Returns: list of event dicts
    """
    all_events = []
    
    for file_path in file_paths:
        path = Path(file_path)
        if not path.exists():
            print(f"⚠️  File not found: {file_path}")
            continue
        
        print(f"📂 Loading: {file_path}")
        try:
            with open(path, "r") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        all_events.append(event)
                    except json.JSONDecodeError as e:
                        print(f"  ⚠️  Line {line_num}: Invalid JSON — {str(e)[:50]}")
                        continue
        
        except Exception as e:
            print(f"  ❌ Error reading file: {e}")
            continue
    
    return all_events


def ingest_events_in_batches(events, batch_size=BATCH_SIZE):
    """
    Send events to API in batches.
    
    Why batching?
    - The API endpoint accepts max 500 events per request
    - Sending fewer, larger batches is more efficient than tiny batches
    - But not all events at once to avoid timeout
    
    Args:
        events: list of event dicts
        batch_size: number of events per request (default 500)
    
    Returns:
        dict with {accepted, rejected, duplicates, failed_batches}
    """
    
    total_events = len(events)
    stats = {
        "total_events": total_events,
        "accepted": 0,
        "rejected": 0,
        "duplicates": 0,
        "failed_batches": 0,
        "successful_batches": 0
    }
    
    if total_events == 0:
        print("❌ No events to ingest")
        return stats
    
    print(f"\n📊 Ingesting {total_events} events in batches of {batch_size}...")
    print(f"   Total requests: {(total_events + batch_size - 1) // batch_size}\n")
    
    # Process in batches
    for batch_num in range(0, total_events, batch_size):
        batch = events[batch_num:batch_num + batch_size]
        batch_num_display = (batch_num // batch_size) + 1
        total_batches = (total_events + batch_size - 1) // batch_size
        
        print(f"📤 Batch {batch_num_display}/{total_batches} ({len(batch)} events)...", end=" ")
        
        try:
            # Send this batch to the API
            response = requests.post(
                API_URL,
                json={"events": batch},
                timeout=30  # 30 second timeout per batch
            )
            
            # Check response
            if response.status_code == 200:
                result = response.json()
                stats["accepted"] += result.get("accepted", 0)
                stats["rejected"] += result.get("rejected", 0)
                stats["duplicates"] += result.get("duplicate", 0)
                stats["successful_batches"] += 1
                
                # Print result summary
                print(f"✓ Accepted: {result.get('accepted')}, Rejected: {result.get('rejected')}, Duplicates: {result.get('duplicate')}")
                
                # If there were errors, show them
                if result.get("errors"):
                    print(f"     Errors in batch:")
                    for err in result.get("errors", [])[:3]:  # Show first 3 errors
                        print(f"       - Index {err.get('event_index')}: {err.get('error')}")
            
            else:
                # API returned an error
                print(f"❌ HTTP {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                stats["failed_batches"] += 1
        
        except requests.exceptions.Timeout:
            print(f"❌ Timeout")
            stats["failed_batches"] += 1
        
        except requests.exceptions.ConnectionError:
            print(f"❌ Connection failed")
            print(f"   Is the API running? (docker compose up)")
            stats["failed_batches"] += 1
            break
        
        except Exception as e:
            print(f"❌ Error: {str(e)[:100]}")
            stats["failed_batches"] += 1
        
        # Small delay between batches (be nice to the database)
        time.sleep(0.5)
    
    return stats


def print_summary(stats):
    """Print a nice summary of the ingestion results."""
    print("\n" + "="*60)
    print("📈 INGESTION SUMMARY")
    print("="*60)
    print(f"Total events:        {stats['total_events']}")
    print(f"✓ Accepted:          {stats['accepted']}")
    print(f"✗ Rejected:          {stats['rejected']}")
    print(f"⊗ Duplicates:        {stats['duplicates']}")
    print(f"Successful batches:  {stats['successful_batches']}")
    print(f"Failed batches:      {stats['failed_batches']}")
    print("="*60)
    
    if stats["failed_batches"] > 0:
        print("⚠️  Some batches failed. Check API logs for details.")
    elif stats["rejected"] > 0:
        print("⚠️  Some events were rejected. Check event schema.")
    else:
        print("✅ All events ingested successfully!")


if __name__ == "__main__":
    print("🚀 Store Intelligence — Event Loader\n")
    
    # Check if API is running
    print("🔍 Checking API health...")
    try:
        health = requests.get("http://localhost:8000/health", timeout=5)
        if health.status_code == 200:
            health_data = health.json()
            print(f"   ✓ API is running (status: {health_data.get('status')})")
            print(f"   ✓ Database: {health_data.get('database')}")
        else:
            print(f"   ⚠️  API returned {health.status_code}")
    except requests.exceptions.ConnectionError:
        print("   ❌ API is not running!")
        print("   Run: docker compose up")
        sys.exit(1)
    except Exception as e:
        print(f"   ⚠️  Could not check health: {e}")
    
    print()
    
    # Load events
    events = load_events_from_files(FILES)
    
    if not events:
        print("❌ No events loaded")
        sys.exit(1)
    
    print(f"✅ Loaded {len(events)} events total\n")
    
    # Ingest in batches
    stats = ingest_events_in_batches(events, batch_size=BATCH_SIZE)
    
    # Print summary
    print_summary(stats)
    
    # Exit with error code if any batches failed
    if stats["failed_batches"] > 0:
        sys.exit(1)