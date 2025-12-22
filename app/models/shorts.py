"""
Shorts Script Database Model
"""
from sqlalchemy import Column, String, Integer, DateTime, JSON, Text
from sqlalchemy.sql import func
from app.database import Base


class ShortsScript(Base):
    """Shorts script database model"""
    __tablename__ = "shorts_scripts"

    id = Column(String, primary_key=True, index=True)
    theme = Column(String, nullable=False, index=True)
    duration = Column(Integer, nullable=False)
    script_format = Column(String, nullable=False)
    tone = Column(String, nullable=False)
    sections = Column(JSON, nullable=False)  # Store sections as JSON
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<ShortsScript(id={self.id}, theme={self.theme}, duration={self.duration})>"

