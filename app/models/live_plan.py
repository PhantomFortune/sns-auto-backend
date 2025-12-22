"""
Live Plan Database Model
"""
from sqlalchemy import Column, String, Integer, DateTime, JSON, Text
from sqlalchemy.sql import func
from app.database import Base


class LivePlan(Base):
    """Live plan database model"""
    __tablename__ = "live_plans"

    id = Column(String, primary_key=True, index=True)
    type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, index=True)
    duration_hours = Column(Integer, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    purposes = Column(JSON, nullable=False)  # Store purposes as JSON array
    target_audience = Column(String, nullable=False)
    preferred_time_start = Column(String, nullable=True)
    preferred_time_end = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    difficulty = Column(String, nullable=True)
    flow = Column(JSON, nullable=False)  # Store flow items as JSON
    preparations = Column(JSON, nullable=False)  # Store preparations as JSON array
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<LivePlan(id={self.id}, title={self.title}, type={self.type})>"

