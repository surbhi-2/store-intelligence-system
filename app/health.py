# app/health.py

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime, timedelta
import structlog

from app.database import get_db, check_db_connection
from app.models import EventDB

logger = structlog.get_logger()
router = APIRouter()


class StoreLastEvent(BaseModel):
    store_id: str
    last_event_timestamp: Optional[str]
    minutes_since_event: Optional[float]
    is_stale: bool


class HealthResponse(BaseModel):
    status: str  # "ok" or "degraded"
    database: str  # "connected" or "unavailable"
    api_version: str
    uptime_seconds: float
    events_ingested_total: int
    stores_active: int
    stale_feeds: Dict[str, StoreLastEvent]


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check(db: Session = Depends(get_db)):
    """
    GET /health
    
    System health check. Consulted by monitoring systems and on-call engineers.
    
    Returns:
    - Overall system status (ok or degraded)
    - Database connectivity
    - Total events ingested (sanity check)
    - Last event timestamp per store (to detect dead feeds)
    - STALE_FEED warning if no events in 10+ minutes
    
    This endpoint must be fast and accurate — it's called frequently.
    """
    
    import time
    start_time = time.time()
    
    try:
        # Step 1: Database connectivity
        db_ok = check_db_connection()
        
        if not db_ok:
            logger.error("health_check_db_unavailable")
            return HealthResponse(
                status="degraded",
                database="unavailable",
                api_version="1.0.0",
                uptime_seconds=0,
                events_ingested_total=0,
                stores_active=0,
                stale_feeds={}
            )
        
        # Step 2: Basic event count (sanity check)
        total_events = db.query(func.count(EventDB.event_id)).scalar() or 0
        
        # Step 3: Active stores (stores with at least 1 event today)
        now = datetime.utcnow()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        stores_today = db.query(func.distinct(EventDB.store_id)).filter(
            EventDB.timestamp >= start_of_day
        ).all()
        active_store_count = len(stores_today) if stores_today else 0
        
        # Step 4: Last event per store — detect stale feeds
        stale_feeds = {}
        stale_threshold_minutes = 10
        
        for store_row in stores_today:
            store_id = store_row[0]
            
            last_event = db.query(EventDB).filter(
                EventDB.store_id == store_id
            ).order_by(EventDB.timestamp.desc()).first()
            
            if last_event:
                minutes_elapsed = (now - last_event.timestamp).total_seconds() / 60
                is_stale = minutes_elapsed > stale_threshold_minutes
                
                stale_feeds[store_id] = StoreLastEvent(
                    store_id=store_id,
                    last_event_timestamp=last_event.timestamp.isoformat() + "Z",
                    minutes_since_event=round(minutes_elapsed, 2),
                    is_stale=is_stale
                )
                
                if is_stale:
                    logger.warning(
                        "stale_feed_detected",
                        store_id=store_id,
                        minutes_since_last_event=minutes_elapsed
                    )
        
        # Determine overall status
        has_stale_feeds = any(s.is_stale for s in stale_feeds.values())
        overall_status = "degraded" if has_stale_feeds else "ok"
        
        latency_ms = (time.time() - start_time) * 1000
        
        logger.info(
            "health_check_complete",
            status=overall_status,
            database="connected",
            total_events=total_events,
            active_stores=active_store_count,
            stale_feed_count=sum(1 for s in stale_feeds.values() if s.is_stale),
            latency_ms=round(latency_ms, 2)
        )
        
        return HealthResponse(
            status=overall_status,
            database="connected",
            api_version="1.0.0",
            uptime_seconds=time.time() - START_TIME,
            events_ingested_total=total_events,
            stores_active=active_store_count,
            stale_feeds=stale_feeds
        )
    
    except Exception as e:
        logger.error(
            "health_check_error",
            error=str(e)
        )
        return HealthResponse(
            status="degraded",
            database="unavailable",
            api_version="1.0.0",
            uptime_seconds=0,
            events_ingested_total=0,
            stores_active=0,
            stale_feeds={}
        )