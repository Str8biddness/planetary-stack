from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, JSON, Boolean # type: ignore
from sqlalchemy.ext.declarative import declarative_base # type: ignore
from sqlalchemy.orm import sessionmaker # type: ignore
from datetime import datetime
import os
from pathlib import Path

# Database setup
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "synthesus.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    label = Column(String)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_admin = Column(Boolean, default=False)

class UsageMetric(Base):
    __tablename__ = "usage_metrics"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    total_requests = Column(Integer)
    avg_latency_ms = Column(Float)
    domain_breakdown = Column(JSON)  # Stores { "chat": 100, "rag": 50, ... }
    recommendation_stats = Column(JSON) # Stores { "PROCEED": 80, "HALT": 5, ... }

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Pre-populate with master key if not exists
    db = SessionLocal()
    master_key_str = os.environ.get("SYNTHESUS_API_KEY", "sk-synth-prod-key")
    if not db.query(APIKey).filter(APIKey.key == master_key_str).first():
        master_key = APIKey(
            key=master_key_str,
            label="Master Admin Key",
            is_admin=True,
            status="active"
        ) # type: ignore
        db.add(master_key)
    
    # Add a test dev key
    if not db.query(APIKey).filter(APIKey.key == "sk-test-dev-123").first():
        dev_key = APIKey(
            key="sk-test-dev-123",
            label="Simulation Dev Key",
            is_admin=False,
            status="active"
        ) # type: ignore
        db.add(dev_key)
        
    db.commit()
    db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
