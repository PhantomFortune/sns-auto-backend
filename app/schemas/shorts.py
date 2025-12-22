"""
Pydantic schemas for Shorts Script API
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class ShortsSection(BaseModel):
    """Shorts script section schema"""
    timeRange: str = Field(..., description="Time range (e.g., '0-6秒')")
    title: str = Field(..., description="Section title")
    content: str = Field(..., description="Section content")


class ShortsScriptRequest(BaseModel):
    """Request schema for generating Shorts script"""
    theme: str = Field(..., description="Theme/topic for the Shorts", min_length=1)
    duration: int = Field(..., description="Duration in seconds", ge=5, le=60)
    scriptFormat: str = Field(..., description="Script format type")
    tone: str = Field(..., description="Tone of the script")
    detailLevel: Optional[str] = Field(default="standard", description="Detail level: 'concise', 'standard', or 'detailed'")


class ShortsScriptResponse(BaseModel):
    """Response schema for Shorts script"""
    id: str
    theme: str
    duration: int
    scriptFormat: str
    tone: str
    sections: List[ShortsSection]
    generatedAt: str

    class Config:
        from_attributes = True


class ShortsScriptListResponse(BaseModel):
    """Response schema for list of Shorts scripts"""
    scripts: List[ShortsScriptResponse]

