# app/anomalies.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from pydantic import BaseModel
from typing import List
from datetime import datetime, timedelta
import structlog

from app.database import get_db
from app.models import EventDB, POSTransactionDB

logger = structlog.get_logger()
router = APIRouter()


class Anomaly(BaseModel):
    anomaly_type: str
    severity: str  # INFO, WARN, CRITICAL
    message: str
    suggested_action: str


class AnomaliesResponse(BaseModel):
    store_id: str
    anomalies: List[Anomaly]
    timestamp: str


@router.get("/stores/{store_id}/anomalies", response_model=AnomaliesResponse)
async def get_anomalies(
    store_id: str,
    db: Session = Depends(get_db)
):
    """
    GET /stores/{store_id}/anomalies
    
    Detects three types of operational anomalies:
    1. BILLING_QUEUE_SPIKE — queue too deep, customers waiting
    2. CONVERSION_DROP — today's conversion rate below 7-day average
    3. DEAD_ZONE — a product zone hasn't seen visitors in 30+ minutes
    
    Each anomaly has a severity and suggested action for the store manager.
    """
    
    try:
        latest_event = db.query(EventDB)\
        .filter(EventDB.store_id == store_id)\
        .order_by(EventDB.timestamp.desc())\
        .first()

        if latest_event:
            now = latest_event.timestamp
        else:
            now = datetime.utcnow()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        last_7_days = now - timedelta(days=7)
        
        anomalies = []
        
        logger.info(
            "anomalies_check_start",
            store_id=store_id
        )
        
        # ────── ANOMALY 1: QUEUE SPIKE ──────
        # Get current queue depth from active billing zone visits
        current_billing = db.query(EventDB).filter(
            and_(
                EventDB.store_id == store_id,
                EventDB.zone_id == "BILLING",
                EventDB.timestamp > now - timedelta(minutes=1),
                EventDB.is_staff == False
            )
        ).all()
        
        current_queue = len(set(e.visitor_id for e in current_billing))
        
        # Check if queue is abnormally large
        # Threshold: >5 people waiting = concerning
        if current_queue > 5:
            severity = "CRITICAL" if current_queue > 10 else "WARN"
            anomalies.append(Anomaly(
                anomaly_type="BILLING_QUEUE_SPIKE",
                severity=severity,
                message=f"Queue depth: {current_queue} visitors waiting. Normal: <3",
                suggested_action="Activate additional billing counter or alert staff to expedite checkouts"
            ))
            logger.warning(
                "anomaly_queue_spike",
                store_id=store_id,
                queue_depth=current_queue
            )
        
        # ────── ANOMALY 2: CONVERSION DROP ──────
        # Today's conversion rate vs 7-day moving average
        today_transactions = db.query(func.count(POSTransactionDB.transaction_id)).filter(
            and_(
                POSTransactionDB.store_id == store_id,
                POSTransactionDB.timestamp >= start_of_day
            )
        ).scalar() or 0
        
        today_visitors = len(set(
            e.visitor_id for e in db.query(EventDB).filter(
                and_(
                    EventDB.store_id == store_id,
                    EventDB.timestamp >= start_of_day,
                    EventDB.event_type == "ENTRY",
                    EventDB.is_staff == False
                )
            ).all()
        ))
        
        today_conversion = (today_transactions / today_visitors * 100) if today_visitors > 0 else 0
        
        # 7-day average conversion
        past_7_days_transactions = db.query(func.count(POSTransactionDB.transaction_id)).filter(
            and_(
                POSTransactionDB.store_id == store_id,
                POSTransactionDB.timestamp >= last_7_days
            )
        ).scalar() or 0
        
        past_7_days_visitors = len(set(
            e.visitor_id for e in db.query(EventDB).filter(
                and_(
                    EventDB.store_id == store_id,
                    EventDB.timestamp >= last_7_days,
                    EventDB.event_type == "ENTRY",
                    EventDB.is_staff == False
                )
            ).all()
        ))
        
        avg_7day_conversion = (past_7_days_transactions / past_7_days_visitors * 100) if past_7_days_visitors > 0 else 0
        
        # If today's conversion is more than 20% below 7-day average
        conversion_drop_percent = ((avg_7day_conversion - today_conversion) / max(avg_7day_conversion, 1)) * 100
        
        if today_conversion < (avg_7day_conversion * 0.8):  # 20% drop threshold
            severity = "CRITICAL" if conversion_drop_percent > 50 else "WARN"
            anomalies.append(Anomaly(
                anomaly_type="CONVERSION_DROP",
                severity=severity,
                message=f"Today's conversion {today_conversion:.1f}% vs 7-day avg {avg_7day_conversion:.1f}% (drop: {conversion_drop_percent:.1f}%)",
                suggested_action="Review pricing, stock, or promotional offers. Check if any checkout issues occurred."
            ))
            logger.warning(
                "anomaly_conversion_drop",
                store_id=store_id,
                today=today_conversion,
                avg_7day=avg_7day_conversion,
                drop_percent=conversion_drop_percent
            )
        
        # ────── ANOMALY 3: DEAD ZONE ──────
        # Product zones with no visits in last 30 minutes
        # Might indicate stock-out, display issue, or staff shortage
        zones = ["SKINCARE_TOPROW", "MAKEUP_BOTTOMROW", "MENS_CARE", "ACCESSORIES"]
        
        for zone in zones:
            last_zone_visit = db.query(EventDB).filter(
                and_(
                    EventDB.store_id == store_id,
                    EventDB.zone_id == zone,
                    EventDB.is_staff == False
                )
            ).order_by(EventDB.timestamp.desc()).first()
            
            if last_zone_visit is None:
                # No visits to this zone ever today
                minutes_without_traffic = 1440  # Full day
            else:
                minutes_without_traffic = (now - last_zone_visit.timestamp).total_seconds() / 60
            
            if minutes_without_traffic > 30:
                severity = "INFO" if minutes_without_traffic < 120 else "WARN"
                anomalies.append(Anomaly(
                    anomaly_type="DEAD_ZONE",
                    severity=severity,
                    message=f"Zone '{zone}' has {int(minutes_without_traffic)} minutes without customer visits",
                    suggested_action="Check stock, displays, and signage in this zone. May need restocking or repositioning."
                ))
                logger.info(
                    "anomaly_dead_zone",
                    store_id=store_id,
                    zone=zone,
                    minutes_no_traffic=minutes_without_traffic
                )
        
        logger.info(
            "anomalies_complete",
            store_id=store_id,
            anomaly_count=len(anomalies)
        )
        
        return AnomaliesResponse(
            store_id=store_id,
            anomalies=anomalies,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    except Exception as e:
        logger.error(
            "anomalies_error",
            store_id=store_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not detect anomalies"
        )