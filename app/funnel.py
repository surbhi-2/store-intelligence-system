# app/funnel.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import structlog

from app.database import get_db
from app.models import EventDB

logger = structlog.get_logger()
router = APIRouter()


class FunnelStage(BaseModel):
    stage: str
    visitor_count: int
    drop_off_percent: float


class FunnelResponse(BaseModel):
    store_id: str
    stages: List[FunnelStage]
    timestamp: str


@router.get("/stores/{store_id}/funnel", response_model=FunnelResponse)
async def get_conversion_funnel(
    store_id: str,
    db: Session = Depends(get_db)
):
    """
    GET /stores/{store_id}/funnel
    
    Shows the customer journey as a funnel:
    
    ENTRY → ZONE_VISIT → BILLING_QUEUE → PURCHASE
    
    Each stage shows how many visitors reached it.
    Drop-off % shows what % didn't move to the next stage.
    
    The unit is SESSION, not individual events.
    A session is all events for one visitor_id from ENTRY to EXIT.
    
    Re-entries are NOT double-counted as new visitors.
    """
    
    try:
        #now = datetime.utcnow()
        #start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_day = datetime(2026, 1, 1)
        
        logger.info(
            "funnel_query_start",
            store_id=store_id
        )
        
        # ────── STAGE 1: ENTRY ──────
        # Count unique visitors who ENTERed today
        entry_events = db.query(EventDB).filter(
            and_(
                EventDB.store_id == store_id,
                EventDB.timestamp >= start_of_day,
                EventDB.event_type == "ENTRY",
                EventDB.is_staff == False
            )
        ).all()
        
        entry_visitors = set(e.visitor_id for e in entry_events)
        entry_count = len(entry_visitors)
        
        logger.debug(
            "funnel_stage_entry",
            count=entry_count
        )
        
        # ────── STAGE 2: ZONE VISIT ──────
        # Visitors who ENTERed AND visited any product zone
        # (ZONE_ENTER, ZONE_EXIT, ZONE_DWELL events)
        zone_visit_events = db.query(EventDB).filter(
            and_(
                EventDB.store_id == store_id,
                EventDB.timestamp >= start_of_day,
                EventDB.event_type.in_(["ZONE_ENTER", "ZONE_EXIT", "ZONE_DWELL"]),
                EventDB.is_staff == False,
                EventDB.visitor_id.in_(list(entry_visitors)) if entry_visitors else False
            )
        ).all()
        
        zone_visitors = set(e.visitor_id for e in zone_visit_events)
        zone_count = len(zone_visitors)
        zone_dropoff = (
            ((entry_count - zone_count) / entry_count * 100)
            if entry_count > 0
            else 0
        )
        
        logger.debug(
            "funnel_stage_zone",
            count=zone_count,
            dropoff_percent=round(zone_dropoff, 2)
        )
        
        # ────── STAGE 3: BILLING QUEUE ──────
        # Visitors who visited zones AND reached the billing queue
        billing_events = db.query(EventDB).filter(
            and_(
                EventDB.store_id == store_id,
                EventDB.timestamp >= start_of_day,
                EventDB.event_type.in_(["BILLING_QUEUE_JOIN", "ZONE_ENTER"]),
                EventDB.zone_id == "BILLING",
                EventDB.is_staff == False,
                EventDB.visitor_id.in_(list(zone_visitors)) if zone_visitors else False
            )
        ).all()
        
        billing_visitors = set(e.visitor_id for e in billing_events)
        billing_count = len(billing_visitors)
        billing_dropoff = (
            ((zone_count - billing_count) / zone_count * 100)
            if zone_count > 0
            else 0
        )
        
        logger.debug(
            "funnel_stage_billing",
            count=billing_count,
            dropoff_percent=round(billing_dropoff, 2)
        )
        
        # ────── STAGE 4: PURCHASE ──────
        # Visitors in billing queue who completed a transaction
        # (We don't have explicit PURCHASE events, so we infer from /metrics logic:
        # visitor in billing zone within 5 min before a POS transaction)
        from app.models import POSTransactionDB
        
        transactions = db.query(POSTransactionDB).filter(
            and_(
                POSTransactionDB.store_id == store_id,
                POSTransactionDB.timestamp >= start_of_day
            )
        ).all()
        
        purchase_visitors = set()
        for transaction in transactions:
            # Find any billing event from our funnel in 5-min window before transaction
            for event in billing_events:
                time_diff = (transaction.timestamp - event.timestamp).total_seconds() / 60
                if 0 <= time_diff <= 5:
                    purchase_visitors.add(event.visitor_id)
                    break
        
        purchase_count = len(purchase_visitors)
        purchase_dropoff = (
            ((billing_count - purchase_count) / billing_count * 100)
            if billing_count > 0
            else 0
        )
        
        logger.debug(
            "funnel_stage_purchase",
            count=purchase_count,
            dropoff_percent=round(purchase_dropoff, 2)
        )
        
        # ────── FINAL CONVERSION ──────
        # Overall: Entry → Purchase
        overall_conversion = (
            (purchase_count / entry_count * 100)
            if entry_count > 0
            else 0
        )
        
        logger.info(
            "funnel_complete",
            store_id=store_id,
            entry=entry_count,
            zone=zone_count,
            billing=billing_count,
            purchase=purchase_count,
            overall_conversion_percent=round(overall_conversion, 2)
        )
        
        return FunnelResponse(
            store_id=store_id,
            stages=[
                FunnelStage(
                    stage="ENTRY",
                    visitor_count=entry_count,
                    drop_off_percent=0  # First stage, no drop-off
                ),
                FunnelStage(
                    stage="ZONE_VISIT",
                    visitor_count=zone_count,
                    drop_off_percent=round(zone_dropoff, 2)
                ),
                FunnelStage(
                    stage="BILLING_QUEUE",
                    visitor_count=billing_count,
                    drop_off_percent=round(billing_dropoff, 2)
                ),
                FunnelStage(
                    stage="PURCHASE",
                    visitor_count=purchase_count,
                    drop_off_percent=round(purchase_dropoff, 2)
                ),
            ],
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    except Exception as e:
        logger.error(
            "funnel_error",
            store_id=store_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not compute funnel"
        )