# app/pos_loader.py
"""
Load POS transaction data from CSV into the database.
Called once during setup or when new transaction data arrives.
"""

import csv
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
import structlog

from app.database import SessionLocal
from app.models import POSTransactionDB

logger = structlog.get_logger()


def load_pos_from_csv(csv_path: str, db: Session = None):
    """
    Load POS transactions from CSV file into database.
    
    Expected CSV columns (from your Brigade_Bangalore file):
    - store_id or store_name (to map to store_id)
    - transaction_id or order_id
    - timestamp or order_time
    - basket_value, GMV, NMV, or total_amount (revenue field)
    - Other optional fields (customer_id, product_name, etc)
    
    Args:
        csv_path: Path to CSV file
        db: SQLAlchemy session (creates new one if None)
    
    Returns:
        dict: {loaded: count, skipped: count, errors: list}
    """
    
    if db is None:
        db = SessionLocal()
    
    csv_file = Path(csv_path)
    if not csv_file.exists():
        logger.error("pos_file_not_found", path=csv_path)
        return {"loaded": 0, "skipped": 0, "errors": [f"File not found: {csv_path}"]}
    
    logger.info("pos_load_start", file=csv_path)
    
    loaded = 0
    skipped = 0
    errors = []
    
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            if reader.fieldnames is None:
                error_msg = "CSV file is empty or has no headers"
                logger.error("pos_csv_error", error=error_msg)
                return {"loaded": 0, "skipped": 0, "errors": [error_msg]}
            
            # Normalize column names (handle different naming conventions)
            headers = {h.lower().strip(): h for h in reader.fieldnames}
            
            for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
                try:
                    # ── Extract and normalize fields ──
                    
                    # Store ID
                    store_id = None
                    if "store_id" in headers:
                        store_id = row.get(headers["store_id"], "").strip()
                    elif "store_name" in headers:
                        # Map store name to ID (you may need to customize this)
                        store_name = row.get(headers["store_name"], "").strip().upper()
                        store_id = map_store_name_to_id(store_name)
                    
                    if not store_id:
                        raise ValueError("No store_id or store_name found")
                    
                    # Transaction ID
                    transaction_id = None
                    if "transaction_id" in headers:
                        transaction_id = row.get(headers["transaction_id"], "").strip()
                    elif "order_id" in headers:
                        transaction_id = row.get(headers["order_id"], "").strip()
                    
                    if not transaction_id:
                        raise ValueError("No transaction_id or order_id found")
                    
                    # Timestamp
                    timestamp_str = None
                    if "timestamp" in headers:
                        timestamp_str = row.get(headers["timestamp"], "").strip()
                    elif "order_date" in headers and "order_time" in headers:
                        # Combine date and time columns
                        date_str = row.get(headers["order_date"], "").strip()
                        time_str = row.get(headers["order_time"], "").strip()
                        timestamp_str = f"{date_str} {time_str}"
                    
                    if not timestamp_str:
                        raise ValueError("No timestamp found")
                    
                    # Parse timestamp (handle multiple formats)
                    timestamp = parse_timestamp(timestamp_str)
                    if not timestamp:
                        raise ValueError(f"Could not parse timestamp: {timestamp_str}")
                    
                    # Revenue/Basket Value
                    basket_value = 0.0
                    for revenue_col in ["basket_value", "gmv", "nmv", "total_amount", "amount"]:
                        if revenue_col in headers:
                            try:
                                val = float(row.get(headers[revenue_col], "0").replace(",", ""))
                                basket_value = val
                                break
                            except (ValueError, TypeError):
                                continue
                    
                    # ── Check for duplicates ──
                    # Don't re-insert same transaction_id
                    existing = db.query(POSTransactionDB).filter(
                        POSTransactionDB.transaction_id == transaction_id
                    ).first()
                    
                    if existing:
                        skipped += 1
                        logger.debug(
                            "pos_transaction_duplicate",
                            transaction_id=transaction_id,
                            row=row_num
                        )
                        continue
                    
                    # ── Create and insert transaction ──
                    pos_transaction = POSTransactionDB(
                        transaction_id=transaction_id,
                        store_id=store_id,
                        timestamp=timestamp,
                        basket_value=basket_value
                    )
                    
                    db.add(pos_transaction)
                    loaded += 1
                    
                    logger.debug(
                        "pos_transaction_loaded",
                        transaction_id=transaction_id,
                        store_id=store_id,
                        amount=basket_value,
                        timestamp=timestamp.isoformat()
                    )
                
                except Exception as e:
                    skipped += 1
                    error_msg = f"Row {row_num}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(
                        "pos_row_error",
                        row=row_num,
                        error=str(e)[:100]
                    )
        
        # Commit all loaded transactions
        try:
            db.commit()
            logger.info(
                "pos_load_complete",
                loaded=loaded,
                skipped=skipped,
                errors_count=len(errors)
            )
        except Exception as e:
            db.rollback()
            logger.error("pos_load_commit_failed", error=str(e))
            return {
                "loaded": 0,
                "skipped": skipped,
                "errors": [f"Database commit failed: {str(e)}"] + errors
            }
    
    except Exception as e:
        logger.error("pos_load_error", error=str(e))
        return {
            "loaded": loaded,
            "skipped": skipped,
            "errors": [f"File reading error: {str(e)}"] + errors
        }
    
    return {"loaded": loaded, "skipped": skipped, "errors": errors}


def parse_timestamp(timestamp_str: str) -> datetime:
    """
    Parse timestamp in multiple formats.
    Handles: "2026-04-10T12:30:00Z", "10-04-2026 12:30:00", "2026-04-10 12:30:00", etc.
    """
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",      # ISO 8601 with Z
        "%Y-%m-%dT%H:%M:%S",        # ISO 8601 without Z
        "%d-%m-%Y %H:%M:%S",        # DD-MM-YYYY HH:MM:SS
        "%Y-%m-%d %H:%M:%S",        # YYYY-MM-DD HH:MM:SS
        "%m/%d/%Y %H:%M:%S",        # MM/DD/YYYY HH:MM:SS
        "%d/%m/%Y %H:%M:%S",        # DD/MM/YYYY HH:MM:SS
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    
    return None


def map_store_name_to_id(store_name: str) -> str:
    """
    Map store name to store ID.
    Customize this based on your store naming convention.
    """
    mapping = {
        "BRIGADE_BANGALORE": "ST1008",
        "BRIGADE BANGALORE": "ST1008",
        "BANGALORE": "ST1008",
        # Add more stores as needed
    }
    
    store_name_upper = store_name.upper().strip()
    return mapping.get(store_name_upper, store_name_upper)