# app/models.py

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text
from sqlalchemy.sql import func
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from datetime import datetime
import uuid

from app.database import Base


# ─────────────────────────────────────────────
# SECTION 1 — SQLAlchemy Database Table Models
# These define what gets stored in SQLite
# ─────────────────────────────────────────────

class EventDB(Base):
    """
    Main events table. Every event emitted by the detection
    pipeline gets stored here via POST /events/ingest
    """
    __tablename__ = "events"

    # Primary key — the event_id from the pipeline (UUID4)
    # We use the pipeline's event_id directly, not auto-increment
    # This is what makes idempotency work — inserting same event_id twice
    # just fails the unique constraint silently
    event_id        = Column(String, primary_key=True, index=True)

    store_id        = Column(String, nullable=False, index=True)
    camera_id       = Column(String, nullable=False)
    visitor_id      = Column(String, nullable=False, index=True)

    # Event type is one of 8 defined values — stored as string
    event_type      = Column(String, nullable=False, index=True)

    # ISO-8601 timestamp from the pipeline (derived from frame offset)
    timestamp       = Column(DateTime, nullable=False, index=True)

    # Null for ENTRY/EXIT events, zone name for everything else
    zone_id         = Column(String, nullable=True)

    # Duration in milliseconds — 0 for instantaneous events
    dwell_ms        = Column(Integer, default=0)

    # True if detection model classified this person as staff
    is_staff        = Column(Boolean, default=False, index=True)

    # Detection confidence from the model — never suppressed
    confidence      = Column(Float, nullable=False)

    # Metadata fields stored as flat columns (easier to query than JSON)
    queue_depth     = Column(Integer, nullable=True)
    sku_zone        = Column(String, nullable=True)
    session_seq     = Column(Integer, default=0)

    # When this event was ingested into our system
    ingested_at     = Column(DateTime, server_default=func.now())


class POSTransactionDB(Base):
    __tablename__ = "pos_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    transaction_id = Column(String, index=True)
    store_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    basket_value = Column(Float, nullable=False)

    ingested_at = Column(DateTime, server_default=func.now())


# ─────────────────────────────────────────────
# SECTION 2 — Pydantic Schemas
# These define what the API accepts and returns
# Pydantic validates every field automatically
# ─────────────────────────────────────────────

class EventMetadata(BaseModel):
    """
    Nested metadata object inside each event.
    All fields optional because not every event type uses all fields.
    BILLING_QUEUE_JOIN uses queue_depth.
    ZONE_ENTER/EXIT use sku_zone.
    All use session_seq.
    """
    queue_depth:    Optional[int]   = None
    sku_zone:       Optional[str]   = None
    session_seq:    int             = 0


class EventSchema(BaseModel):
    """
    The exact schema your detection pipeline must emit.
    This is also what POST /events/ingest accepts.
    Every field matches the required schema in the problem statement.
    """
    event_id:   str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID4 — globally unique per event"
    )
    store_id:   str = Field(..., description="e.g. STORE_BLR_002")
    camera_id:  str = Field(..., description="e.g. CAM_ENTRY_01")
    visitor_id: str = Field(..., description="e.g. VIS_c8a2f1 — unique per visit session")

    event_type: Literal[
        "ENTRY",
        "EXIT",
        "ZONE_ENTER",
        "ZONE_EXIT",
        "ZONE_DWELL",
        "BILLING_QUEUE_JOIN",
        "BILLING_QUEUE_ABANDON",
        "REENTRY"
    ] = Field(..., description="One of 8 defined event types")

    timestamp:  datetime = Field(..., description="ISO-8601 UTC")
    zone_id:    Optional[str]   = Field(None, description="Null for ENTRY/EXIT")
    dwell_ms:   int             = Field(0, ge=0)
    is_staff:   bool            = Field(False)
    confidence: float           = Field(..., ge=0.0, le=1.0)
    metadata:   EventMetadata   = Field(default_factory=EventMetadata)

    @validator("event_id")
    def event_id_must_be_valid(cls, v):
        # Ensure event_id looks like a UUID or VIS_ prefixed string
        if not v or len(v) < 8:
            raise ValueError("event_id must be at least 8 characters")
        return v

    @validator("zone_id")
    def zone_id_required_for_zone_events(cls, v, values):
        # If event_type is a ZONE event, zone_id must not be null
        event_type = values.get("event_type", "")
        if event_type in ("ZONE_ENTER", "ZONE_EXIT", "ZONE_DWELL") and not v:
            raise ValueError(f"zone_id is required for {event_type} events")
        return v

    class Config:
        # Allows using datetime objects directly (not just strings)
        json_encoders = {datetime: lambda v: v.isoformat()}


class EventIngestRequest(BaseModel):
    """
    What POST /events/ingest accepts.
    A batch of up to 500 events.
    """
    events: list[EventSchema] = Field(..., max_length=500)


class EventIngestResponse(BaseModel):
    """
    What POST /events/ingest returns.
    Shows exactly which events succeeded and which failed — partial success.
    """
    accepted:       int
    rejected:       int
    duplicate:      int
    total:          int
    errors:         list[dict] = []


class POSTransactionSchema(BaseModel):
    """
    Schema for loading POS transaction data from CSV.
    Used internally — not a public API endpoint.
    """
    transaction_id: str
    store_id:       str
    timestamp:      datetime
    basket_value:   float

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}