"""
Live Plan API endpoints
Endpoints for generating live streaming plans
"""
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from typing import List
import logging

from app.database import get_db
from app.models.live_plan import LivePlan
from app.schemas.live_plan import (
    LivePlanRequest,
    LivePlanResponse,
    LivePlanListResponse,
    FlowItem,
)
from app.services.live_plan_service import LivePlanService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/live-plan", tags=["Live Plan"])

# Initialize service
live_plan_service = LivePlanService()


@router.post(
    "/generate",
    response_model=LivePlanResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid request"},
        500: {"description": "Server error"},
    },
)
async def generate_live_plan(
    request: LivePlanRequest,
    db: Session = Depends(get_db)
):
    """
    Generate a live streaming plan based on the provided information.
    
    - **type**: Live format (雑談, ゲーム, コラボ, トーク企画, 歌枠, ASMR, Q&A, 特別イベント)
    - **title**: Live title
    - **duration_hours**: Planned duration (hours)
    - **duration_minutes**: Planned duration (minutes)
    - **purposes**: List of purposes (同時接続増加, チャンネル登録者増加, 視聴維持改善, 交流強化, 収益化)
    - **target_audience**: Target audience
    - **preferred_time_start**: Preferred start time (optional, hh:mm format)
    - **preferred_time_end**: Preferred end time (optional, hh:mm format)
    - **notes**: Additional notes (optional, max 500 characters)
    - **difficulty**: Difficulty level (optional: low, medium, high)
    
    Returns a detailed live plan with:
    - Flow sections with time ranges and content
    - Preparation items list
    """
    try:
        # Validate total duration
        total_minutes = request.duration_hours * 60 + request.duration_minutes
        if total_minutes < 10 or total_minutes > 480:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="予定ライブ時間は10分以上480分以下で入力してください",
            )
        
        # Generate plan
        plan_response = live_plan_service.generate_plan(request)
        
        # Save to database
        db_plan = LivePlan(
            id=plan_response.id,
            type=plan_response.type,
            title=plan_response.title,
            duration_hours=plan_response.duration_hours,
            duration_minutes=plan_response.duration_minutes,
            purposes=plan_response.purposes,
            target_audience=plan_response.target_audience,
            preferred_time_start=plan_response.preferred_time_start,
            preferred_time_end=plan_response.preferred_time_end,
            notes=plan_response.notes,
            difficulty=plan_response.difficulty,
            flow=[
                {
                    "time_range": item.time_range,
                    "title": item.title,
                    "content": item.content
                }
                for item in plan_response.flow
            ],
            preparations=plan_response.preparations,
        )
        
        db.add(db_plan)
        db.commit()
        db.refresh(db_plan)
        
        return plan_response
        
    except HTTPException:
        raise
    except ValueError as e:
        db.rollback()
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"リクエストデータが不正です: {str(e)}",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error generating live plan: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ライブ企画案の生成に失敗しました: {str(e)}",
        )


@router.get("/", response_model=LivePlanListResponse)
async def get_live_plans(
    db: Session = Depends(get_db)
):
    """
    Get all live plans (history)
    """
    try:
        plans = db.query(LivePlan).order_by(LivePlan.created_at.desc()).all()
        
        plan_responses = []
        for plan in plans:
            flow_items = [
                FlowItem(
                    time_range=item.get("time_range", ""),
                    title=item.get("title", ""),
                    content=item.get("content", "")
                )
                for item in plan.flow
            ]
            
            plan_responses.append(LivePlanResponse(
                id=plan.id,
                type=plan.type,
                title=plan.title,
                duration_hours=plan.duration_hours,
                duration_minutes=plan.duration_minutes,
                purposes=plan.purposes,
                target_audience=plan.target_audience,
                preferred_time_start=plan.preferred_time_start,
                preferred_time_end=plan.preferred_time_end,
                notes=plan.notes,
                difficulty=plan.difficulty,
                flow=flow_items,
                preparations=plan.preparations,
                generated_at=plan.generated_at.strftime("%Y-%m-%d %H:%M:%S") if plan.generated_at else ""
            ))
        
        return LivePlanListResponse(plans=plan_responses)
        
    except Exception as e:
        logger.error(f"Error fetching live plans: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ライブ企画案の取得に失敗しました: {str(e)}",
        )


@router.get("/{plan_id}", response_model=LivePlanResponse)
async def get_live_plan(
    plan_id: str,
    db: Session = Depends(get_db)
):
    """
    Get a specific live plan by ID
    """
    try:
        plan = db.query(LivePlan).filter(LivePlan.id == plan_id).first()
        
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ライブ企画案が見つかりません"
            )
        
        flow_items = [
            FlowItem(
                time_range=item.get("time_range", ""),
                title=item.get("title", ""),
                content=item.get("content", "")
            )
            for item in plan.flow
        ]
        
        return LivePlanResponse(
            id=plan.id,
            type=plan.type,
            title=plan.title,
            duration_hours=plan.duration_hours,
            duration_minutes=plan.duration_minutes,
            purposes=plan.purposes,
            target_audience=plan.target_audience,
            preferred_time_start=plan.preferred_time_start,
            preferred_time_end=plan.preferred_time_end,
            notes=plan.notes,
            difficulty=plan.difficulty,
            flow=flow_items,
            preparations=plan.preparations,
            generated_at=plan.generated_at.strftime("%Y-%m-%d %H:%M:%S") if plan.generated_at else ""
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching live plan: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ライブ企画案の取得に失敗しました: {str(e)}",
        )


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_live_plan(
    plan_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete a live plan by ID
    """
    try:
        plan = db.query(LivePlan).filter(LivePlan.id == plan_id).first()
        
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ライブ企画案が見つかりません"
            )
        
        db.delete(plan)
        db.commit()
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting live plan: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ライブ企画案の削除に失敗しました: {str(e)}",
        )

