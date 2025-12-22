"""
Shorts Script API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import uuid

from app.database import get_db
from app.models.shorts import ShortsScript
from app.schemas.shorts import (
    ShortsScriptRequest,
    ShortsScriptResponse,
    ShortsScriptListResponse,
    ShortsSection
)
from app.services.shorts_service import ShortsGenerationService

router = APIRouter(prefix="/shorts", tags=["shorts"])


@router.post("/generate", response_model=ShortsScriptResponse, status_code=status.HTTP_201_CREATED)
async def generate_shorts_script(
    request: ShortsScriptRequest,
    db: Session = Depends(get_db)
):
    """
    Generate a new Shorts script using OpenAI
    """
    try:
        # Generate script using OpenAI
        service = ShortsGenerationService()
        script_response = service.generate_script(
            theme=request.theme,
            duration=request.duration,
            script_format=request.scriptFormat,
            tone=request.tone,
            detail_level=request.detailLevel or "standard"
        )
        
        # Save to database
        db_script = ShortsScript(
            id=script_response.id,
            theme=script_response.theme,
            duration=script_response.duration,
            script_format=script_response.scriptFormat,
            tone=script_response.tone,
            sections=[
                {
                    "timeRange": section.timeRange,
                    "title": section.title,
                    "content": section.content
                }
                for section in script_response.sections
            ]
        )
        
        db.add(db_script)
        db.commit()
        db.refresh(db_script)
        
        return script_response
        
    except ValueError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        import traceback
        error_detail = str(e)
        print(f"Error generating script: {error_detail}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate script: {error_detail}"
        )


@router.get("/", response_model=ShortsScriptListResponse)
async def get_shorts_scripts(
    db: Session = Depends(get_db)
):
    """
    Get all Shorts scripts (history)
    """
    try:
        scripts = db.query(ShortsScript).order_by(ShortsScript.created_at.desc()).all()
        
        script_responses = []
        for script in scripts:
            sections = [
                ShortsSection(
                    timeRange=section.get("timeRange", ""),
                    title=section.get("title", ""),
                    content=section.get("content", "")
                )
                for section in script.sections
            ]
            
            script_responses.append(ShortsScriptResponse(
                id=script.id,
                theme=script.theme,
                duration=script.duration,
                scriptFormat=script.script_format,
                tone=script.tone,
                sections=sections,
                generatedAt=script.generated_at.strftime("%Y/%m/%d %H:%M:%S") if script.generated_at else ""
            ))
        
        return ShortsScriptListResponse(scripts=script_responses)
        
    except Exception as e:
        import traceback
        error_detail = str(e)
        print(f"Error fetching scripts: {error_detail}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch scripts: {error_detail}"
        )


@router.delete("/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shorts_script(
    script_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete a Shorts script by ID
    """
    try:
        script = db.query(ShortsScript).filter(ShortsScript.id == script_id).first()
        
        if not script:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Script not found"
            )
        
        db.delete(script)
        db.commit()
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete script: {str(e)}"
        )

