import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
import structlog

logger = structlog.get_logger()

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = os.getenv(
    "DATA_DIR",
    str(BASE_DIR / "data")
)

os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR}/store_intelligence.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


def create_tables():
    from app import models 
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("database_tables_created")
    except Exception as e:
        logger.error("database_setup_failed", error=str(e))
        raise

