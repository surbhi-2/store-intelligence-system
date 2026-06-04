# scripts/load_pos.py
"""
Load POS transaction data from CSV.
Run this once to populate the database with transaction history.

Usage:
  python3 scripts/load_pos.py [csv_file]

Example:
  python3 scripts/load_pos.py "Brigade_Bangalore_10_April_26__1_bc6219c.csv"
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pos_loader import load_pos_from_csv
from app.database import SessionLocal
import requests


def main():
    if len(sys.argv) < 2:
        print("❌ Usage: python3 scripts/load_pos.py <csv_file>")
        print("\nExample:")
        print("  python3 scripts/load_pos.py data/Brigade_Bangalore_10_April_26__1_bc6219c.csv")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    
    print("🚀 Store Intelligence — POS Loader\n")
    
    # Check if API is running
    print("🔍 Checking API health...")
    try:
        health = requests.get("http://localhost:8000/health", timeout=5)
        if health.status_code == 200:
            print(f"   ✓ API is running")
        else:
            print(f"   ⚠️  API returned {health.status_code}")
    except requests.exceptions.ConnectionError:
        print("   ❌ API is not running!")
        print("   Run: docker compose up")
        sys.exit(1)
    
    # Load POS data
    print(f"\n📂 Loading POS data from: {csv_file}")
    
    db = SessionLocal()
    result = load_pos_from_csv(csv_file, db)
    db.close()
    
    # Print results
    print("\n" + "="*60)
    print("📊 POS LOAD SUMMARY")
    print("="*60)
    print(f"✓ Loaded:      {result['loaded']}")
    print(f"⊗ Skipped:     {result['skipped']}")
    print(f"✗ Errors:      {len(result['errors'])}")
    print("="*60)
    
    if result['errors']:
        print("\n⚠️  Errors encountered:")
        for error in result['errors'][:5]:  # Show first 5 errors
            print(f"   - {error}")
        if len(result['errors']) > 5:
            print(f"   ... and {len(result['errors']) - 5} more")
    
    if result['loaded'] > 0:
        print(f"\n✅ Successfully loaded {result['loaded']} transactions")
    else:
        print("\n❌ No transactions were loaded")
        sys.exit(1)


if __name__ == "__main__":
    main()