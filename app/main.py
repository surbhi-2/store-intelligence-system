# app/main.py

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import structlog
import time
import uuid
import os

from app.database import check_db_connection, create_tables
from app.ingestion import router as ingest_router
from app.metrics import router as metrics_router
from app.funnel import router as funnel_router
from app.anomalies import router as anomalies_router
from app.health import router as health_router

logger = structlog.get_logger()

app = FastAPI(
    title="Store Intelligence API",
    description="Real-time retail analytics from CCTV footage",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Middleware that runs on every HTTP request.
    Logs trace_id, endpoint, latency, status_code for observability.
    """
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    request.state.trace_id = trace_id

    response = await call_next(request)

    latency_ms = round((time.time() - start_time) * 1000, 2)

    logger.info(
        "request_completed",
        trace_id=trace_id,
        method=request.method,
        endpoint=str(request.url.path),
        status_code=response.status_code,
        latency_ms=latency_ms
    )

    response.headers["X-Trace-ID"] = trace_id
    return response


@app.on_event("startup")
async def startup_event():
    """
    Runs once when the API starts.
    Create database tables if they don't exist.
    """
    logger.info(
        "api_starting",
        environment=os.getenv("ENVIRONMENT", "development")
    )
    create_tables()
    logger.info("api_ready")


# Include all routers
# This registers all the endpoints from each module
app.include_router(ingest_router, tags=["events"])
app.include_router(metrics_router, tags=["analytics"])
app.include_router(funnel_router, tags=["analytics"])
app.include_router(anomalies_router, tags=["analytics"])
app.include_router(health_router, tags=["system"])


@app.get("/", tags=["root"])
async def root():
    """
    Root endpoint. Provides navigation to other endpoints.
    """
    return {
        "message": "Store Intelligence API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "ingest": "POST /events/ingest",
            "metrics": "GET /stores/{store_id}/metrics",
            "funnel": "GET /stores/{store_id}/funnel",
            "anomalies": "GET /stores/{store_id}/anomalies",
            "health": "GET /health"
        }
    }


@app.get("/health", tags=["system"])
async def health_check_root(db=None):
    """
    Root health endpoint (same as /health from router).
    """
    from app.health import health_check
    from app.database import get_db
    from sqlalchemy.orm import Session
    
    db = next(get_db())
    return await health_check(db)