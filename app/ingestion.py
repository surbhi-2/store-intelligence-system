# app/ingestion.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
import structlog

from app.database import get_db
from app.models import EventSchema, EventIngestRequest, EventIngestResponse, EventDB

logger = structlog.get_logger()
router = APIRouter()


@router.post("/events/ingest", response_model=EventIngestResponse)
async def ingest_events(
    request: EventIngestRequest,
    db: Session = Depends(get_db)
):
    """
    POST /events/ingest
    
    Accepts up to 500 events from the detection pipeline.
    Validates each one, deduplicates by event_id, stores valid ones.
    Returns detailed response: how many accepted, rejected, duplicates.
    
    This endpoint is idempotent — calling it twice with the same events
    returns the same result. Duplicate event_ids are silently ignored on
    the second call (database unique constraint prevents duplicates).
    """
    
    accepted_count = 0
    rejected_count = 0
    duplicate_count = 0
    errors = []
    
    # Log incoming request
    logger.info(
        "ingest_request_received",
        event_count=len(request.events),
        store_ids=list(set(e.store_id for e in request.events))
    )
    
    # Process each event one by one
    for idx, event in enumerate(request.events):
        try:
            # Step 1: Validate the event schema
            # Pydantic automatically validates: timestamp is ISO-8601,
            # event_type is one of the 8 allowed values, confidence is 0-1, etc.
            # If validation fails, this raises ValidationError caught below.
            validated = EventSchema(**event.dict() if hasattr(event, 'dict') else event)
            
            # Step 2: Check if this event_id already exists (idempotency)
            existing = db.query(EventDB).filter(
                EventDB.event_id == validated.event_id
            ).first()
            
            if existing:
                # This event was already ingested before — skip it
                duplicate_count += 1
                logger.debug(
                    "event_duplicate",
                    event_id=validated.event_id,
                    store_id=validated.store_id
                )
                continue
            
            # Step 3: Convert Pydantic model to SQLAlchemy model for database
            db_event = EventDB(
                event_id=validated.event_id,
                store_id=validated.store_id,
                camera_id=validated.camera_id,
                visitor_id=validated.visitor_id,
                event_type=validated.event_type,
                timestamp=validated.timestamp,
                zone_id=validated.zone_id,
                dwell_ms=validated.dwell_ms,
                is_staff=validated.is_staff,
                confidence=validated.confidence,
                queue_depth=validated.metadata.queue_depth,
                sku_zone=validated.metadata.sku_zone,
                session_seq=validated.metadata.session_seq,
            )
            
            # Step 4: Try to insert into database
            db.add(db_event)
            db.flush()  # Flush but don't commit yet — commit all at once later
            accepted_count += 1
            
            logger.debug(
                "event_accepted",
                event_id=validated.event_id,
                event_type=validated.event_type,
                store_id=validated.store_id,
                visitor_id=validated.visitor_id
            )
            
        except ValidationError as ve:
            # Schema validation failed — event doesn't match the required format
            rejected_count += 1
            error_detail = {
                "event_index": idx,
                "error": "schema_validation_failed",
                "details": str(ve)
            }
            errors.append(error_detail)
            logger.warning(
                "event_validation_failed",
                index=idx,
                error=str(ve)[:100]  # Log first 100 chars of error
            )
        
        except IntegrityError as ie:
            # Database constraint violation — likely duplicate event_id
            # (although we check for this above, race conditions could cause this)
            db.rollback()
            duplicate_count += 1
            error_detail = {
                "event_index": idx,
                "error": "database_integrity_error",
                "details": "Possible duplicate event_id"
            }
            errors.append(error_detail)
            logger.warning(
                "event_integrity_error",
                index=idx,
                error=str(ie)[:100]
            )
        
        except Exception as e:
            # Unexpected error
            rejected_count += 1
            error_detail = {
                "event_index": idx,
                "error": "unexpected_error",
                "details": str(e)[:100]
            }
            errors.append(error_detail)
            logger.error(
                "event_processing_error",
                index=idx,
                error=str(e)[:100]
            )
    
    # Step 5: Commit all accepted events to database at once
    try:
        db.commit()
        logger.info(
            "events_committed",
            accepted=accepted_count,
            rejected=rejected_count,
            duplicates=duplicate_count
        )
    except Exception as e:
        db.rollback()
        logger.error(
            "commit_failed",
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "database_commit_failed",
                "message": "Could not save events to database"
            }
        )
    
    # Return summary of what happened
    return EventIngestResponse(
        accepted=accepted_count,
        rejected=rejected_count,
        duplicate=duplicate_count,
        total=len(request.events),
        errors=errors
    )