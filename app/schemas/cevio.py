"""
CeVIO AI Schemas
Request and response models for CeVIO AI text-to-speech
"""
from pydantic import BaseModel, Field
from typing import Optional


class CeVIOSpeakRequest(BaseModel):
    """Request model for CeVIO AI text-to-speech"""
    text: str = Field(..., description="Text to speak")
    cast: str = Field(
        default="フィーちゃん",
        description="Voice cast name (フィーちゃん, ユニちゃん, 夏色花梨)"
    )


class CeVIOSpeakResponse(BaseModel):
    """Response model for CeVIO AI text-to-speech"""
    success: bool = Field(..., description="Whether the speech was successful")
    message: str = Field(..., description="Response message")


class CeVIOStatusResponse(BaseModel):
    """Response model for CeVIO AI status"""
    connected: bool = Field(..., description="Whether CeVIO AI is connected")
    is_speaking: bool = Field(..., description="Whether currently speaking")
    available_casts: list[str] = Field(..., description="List of available voice casts")

