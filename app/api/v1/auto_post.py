"""
Auto Post Generation API
"""
from fastapi import APIRouter, HTTPException
from typing import Dict

from app.schemas.auto_post import AutoPostGenerateRequest, AutoPostGenerateResponse
from app.services.auto_post_service import AutoPostService

router = APIRouter(prefix="/auto-post", tags=["auto-post"])

# Initialize service
auto_post_service = AutoPostService()


@router.post("/generate", response_model=AutoPostGenerateResponse)
async def generate_post(request: AutoPostGenerateRequest) -> AutoPostGenerateResponse:
    """
    Generate X post text based on provided parameters.
    
    This endpoint uses OpenAI API to generate natural, engaging post text
    that fits X (Twitter) format (280 characters or less).
    """
    try:
        result = auto_post_service.generate_post(request)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"投稿文の生成に失敗しました: {str(e)}"
        )

