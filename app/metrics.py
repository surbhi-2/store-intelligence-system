from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime, timedelta
import structlog

from app.database import get_db
from app.models import EventDB, POSTransactionDB
from app.pos_correlation import POSCorrelator

logger = structlog.get_logger()
router = APIRouter()


class MetricsResponse(BaseModel):
    """
    Response model for GET /stores/{id}/metrics
    Shows today's performance for a single store.
    
    All metrics are REAL-TIME (not cached):
    - Computed fresh on each request
    - Reflects latest events and transactions
    - Correlates visitor sessions with POS data
    """
    store_id: str
    unique_visitors: int
    converted_visitors: int
    conversion_rate: float
    transactions: int
    total_revenue: float
    avg_revenue_per_visitor: float
    avg_dwell_per_zone: Dict[str, float]
    current_billing_queue_depth: int
    abandonment_rate: float
    timestamp: str

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


@router.get("/stores/{store_id}/metrics", response_model=MetricsResponse)
async def get_store_metrics(
    store_id: str,
    db: Session = Depends(get_db)
):
    """
    GET /stores/{store_id}/metrics
    
    Real-time analytics for a store TODAY.
    Uses POS correlation to calculate accurate conversion rate and revenue.
    
    The "north star" metric:
    Conversion Rate = (Customers who bought) / (Total unique customers)
    
    Time window: Today (midnight UTC to now)
    """
    
    try:
        # ────── DEFINE TIME WINDOW ──────
        # Use all available data
        start_of_day = datetime(2026, 1, 1)
        now = datetime(2030, 1, 1)
        #now = datetime.utcnow()
        #start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        logger.info(
            "metrics_query_start",
            store_id=store_id,
            time_window=f"{start_of_day.isoformat()} to {now.isoformat()}"
        )
        
        # ────── LOAD ALL EVENTS ──────
        all_events = db.query(EventDB).filter(
            and_(
                EventDB.store_id == store_id,
                EventDB.timestamp >= start_of_day,
                EventDB.is_staff == False  # Exclude staff
            )
        ).all()
        
        if not all_events:
            logger.warning("metrics_no_events", store_id=store_id)
            # Return zeros for empty store
            return MetricsResponse(
                store_id=store_id,
                unique_visitors=0,
                converted_visitors=0,
                conversion_rate=0.0,
                transactions=0,
                total_revenue=0.0,
                avg_revenue_per_visitor=0.0,
                avg_dwell_per_zone={},
                current_billing_queue_depth=0,
                abandonment_rate=0.0,
                timestamp=datetime.utcnow().isoformat() + "Z"
            )
        
        # ────── POS CORRELATION ──────
        # This is the KEY step — correlate visitors with actual transactions
        try:
            correlator = POSCorrelator(
                db=db,
                store_id=store_id,
                start_time=start_of_day,
                end_time=now
            )
            
            summary = correlator.get_summary()
            
            logger.debug(
                "pos_correlation_complete",
                store_id=store_id,
                converted=summary['converted_visitors'],
                revenue=summary['total_revenue']
            )
        
        except Exception as e:
            logger.error(
                "pos_correlation_failed",
                store_id=store_id,
                error=str(e)
            )
            # If correlation fails, return error response
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="POS correlation failed"
            )
        
        # ────── VISITOR COUNTS ──────
        # Count unique visitors (same person = one visitor)
        unique_visitor_ids = set(e.visitor_id for e in all_events)
        unique_visitors = len(unique_visitor_ids)
        
        # ────── DWELL TIME PER ZONE ──────
        # Average time spent in each product zone
        # Calculated from ZONE_DWELL events (emitted every 30 seconds)
        dwell_events = [e for e in all_events if e.event_type == "ZONE_DWELL"]
        
        avg_dwell_per_zone = {}
        if dwell_events:
            zones = set(e.zone_id for e in dwell_events if e.zone_id)
            
            for zone in zones:
                zone_dwell_ms = [e.dwell_ms for e in dwell_events if e.zone_id == zone]
                if zone_dwell_ms:
                    avg_ms = sum(zone_dwell_ms) / len(zone_dwell_ms)
                    avg_dwell_per_zone[zone] = round(avg_ms / 1000, 2)  # Convert ms to seconds
        
        # ────── BILLING QUEUE ──────
        # Current queue depth = visitors in billing zone right now
        # (not exited yet, and event happened within last 30 seconds)
        billing_events = [
            e for e in all_events
            if e.zone_id == "BILLING" and e.event_type in ("ZONE_ENTER", "ZONE_DWELL", "BILLING_QUEUE_JOIN")
        ]
        
        # Only count recent billing events (within last 30 seconds)
        recent_cutoff = now - timedelta(seconds=30)
        recent_billing = [e for e in billing_events if e.timestamp > recent_cutoff]
        
        current_queue_depth = len(set(e.visitor_id for e in recent_billing))
        
        # ────── LOG RESULTS ──────
        logger.info(
            "metrics_computed",
            store_id=store_id,
            unique_visitors=unique_visitors,
            converted_visitors=summary['converted_visitors'],
            conversion_rate=summary['conversion_rate'],
            total_revenue=summary['total_revenue'],
            transactions=summary['total_transactions'],
            abandonment_rate=summary['abandonment_rate']
        )
        
        # ────── BUILD RESPONSE ──────
        return MetricsResponse(
            store_id=store_id,
            unique_visitors=unique_visitors,
            converted_visitors=summary['converted_visitors'],
            conversion_rate=summary['conversion_rate'],
            transactions=summary['total_transactions'],
            total_revenue=summary['total_revenue'],
            avg_revenue_per_visitor=summary['avg_revenue_per_visitor'],
            avg_dwell_per_zone=avg_dwell_per_zone,
            current_billing_queue_depth=current_queue_depth,
            abandonment_rate=summary['abandonment_rate'],
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    except HTTPException:
        # Re-raise HTTP exceptions (like 500 errors)
        raise
    
    except Exception as e:
        # Catch unexpected errors
        logger.error(
            "metrics_error",
            store_id=store_id,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "metrics_computation_failed",
                "message": str(e)[:100]
            }
        )