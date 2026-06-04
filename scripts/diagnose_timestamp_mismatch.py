# scripts/diagnose_timestamp_mismatch.py
"""
Diagnose timestamp mismatches between events and POS data.
This is the #1 reason for 0% conversion rate!
"""

import sqlite3
import pandas as pd
from datetime import datetime
import json

def diagnose():
    print("\n" + "="*70)
    print("🔍 TIMESTAMP MISMATCH DIAGNOSTIC")
    print("="*70)
    
    # Load POS CSV
    try:
        pos_df = pd.read_csv('/mnt/user-data/uploads/pos_data.csv')
        pos_df['datetime'] = pd.to_datetime(
            pos_df['order_date'] + ' ' + pos_df['order_time'],
            format='%d-%m-%Y %H:%M:%S'
        )
        pos_min = pos_df['datetime'].min()
        pos_max = pos_df['datetime'].max()
        print(f"\n📊 POS DATA (from CSV)")
        print(f"   Min: {pos_min}")
        print(f"   Max: {pos_max}")
        print(f"   Total transactions: {len(pos_df)}")
    except Exception as e:
        print(f"\n❌ Could not load POS CSV: {e}")
        pos_min = pos_max = None
    
    # Check database
    try:
        conn = sqlite3.connect('data/store_intelligence.db')
        cursor = conn.cursor()
        
        # Event timestamps
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM event")
        evt_min_str, evt_max_str, evt_count = cursor.fetchone()
        evt_min = datetime.fromisoformat(evt_min_str) if evt_min_str else None
        evt_max = datetime.fromisoformat(evt_max_str) if evt_max_str else None
        
        print(f"\n📹 EVENT DATA (from database)")
        print(f"   Min: {evt_min}")
        print(f"   Max: {evt_max}")
        print(f"   Total events: {evt_count}")
        
        # POS timestamps in database
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM pos_transaction")
        pos_min_str, pos_max_str, pos_count = cursor.fetchone()
        pos_min_db = datetime.fromisoformat(pos_min_str) if pos_min_str else None
        pos_max_db = datetime.fromisoformat(pos_max_str) if pos_max_str else None
        
        print(f"\n💳 POS DATA (from database)")
        print(f"   Min: {pos_min_db}")
        print(f"   Max: {pos_max_db}")
        print(f"   Total transactions: {pos_count}")
        
        # Check overlap
        print(f"\n⏱️  TIME WINDOW ANALYSIS")
        if evt_max and pos_min_db:
            gap_seconds = (pos_min_db - evt_max).total_seconds()
            print(f"   Events end at: {evt_max}")
            print(f"   POS starts at: {pos_min_db}")
            print(f"   Gap: {gap_seconds:.0f} seconds ({gap_seconds/60:.1f} minutes)")
            
            if gap_seconds > 300:  # 5 minute correlation window
                print(f"\n   ❌ PROBLEM: Gap is {gap_seconds/60:.0f} min > 5 min correlation window")
                print(f"      → Visitors leave before transactions occur")
                print(f"      → Conversion rate will be 0%")
            else:
                print(f"\n   ✓ Overlap is good (< 5 min gap)")
        
        # Billing zone events
        cursor.execute("SELECT COUNT(*) FROM event WHERE zone_id='BILLING'")
        billing_count = cursor.fetchone()[0]
        print(f"\n   Billing zone visits: {billing_count}")
        
        if billing_count > 0 and pos_min_db:
            cursor.execute(
                "SELECT MAX(timestamp) FROM event WHERE zone_id='BILLING'"
            )
            billing_max_str = cursor.fetchone()[0]
            billing_max = datetime.fromisoformat(billing_max_str)
            
            gap_to_pos = (pos_min_db - billing_max).total_seconds()
            print(f"   Last billing event: {billing_max}")
            print(f"   First POS transaction: {pos_min_db}")
            print(f"   Gap: {gap_to_pos/60:.1f} minutes")
            
            if gap_to_pos > 300:
                print(f"   ❌ NO CORRELATION POSSIBLE")
        
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Could not query database: {e}")
    
    print("\n" + "="*70)
    print("🔧 SOLUTION")
    print("="*70)
    print("""
Regenerate events with correct start_time that MATCHES POS data:

POS data spans: 2026-04-10 12:15:05 to 21:39:55

So run detection with:

  python3 -m pipeline.detect \\
    --video data/store_4.mp4 \\
    --layout data/store_layout.json \\
    --camera CAM_FLOOR_01 \\
    --output data/events/store_4_events.jsonl \\
    --start-time "2026-04-10T12:15:00+00:00"
    
Then reload events and check metrics again.
    """)
    print("="*70 + "\n")

if __name__ == "__main__":
    diagnose()
    