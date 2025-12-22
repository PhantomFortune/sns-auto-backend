"""
Live Plan Schemas
Request and response models for live streaming plan generation
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class LivePlanRequest(BaseModel):
    """Request model for live plan generation"""
    type: str = Field(..., description="ライブ形式（雑談、ゲーム、コラボ、トーク企画、歌枠、ASMR、Q&A、特別イベント）")
    title: str = Field(..., description="ライブタイトル")
    duration_hours: int = Field(..., ge=0, le=8, description="予定時間（時間）")
    duration_minutes: int = Field(..., ge=0, le=59, description="予定時間（分）")
    purposes: List[str] = Field(..., min_items=1, description="目的（同時接続増加、チャンネル登録者増加、視聴維持改善、交流強化、収益化）")
    target_audience: str = Field(..., description="ターゲット層")
    preferred_time_start: Optional[str] = Field(None, description="優先時間帯（開始）hh:mm形式")
    preferred_time_end: Optional[str] = Field(None, description="優先時間帯（終了）hh:mm形式")
    notes: Optional[str] = Field(None, max_length=500, description="追加メモ")
    difficulty: Optional[str] = Field(None, description="希望難易度（low, medium, high）")


class FlowItem(BaseModel):
    """配信の流れの各セクション"""
    time_range: str = Field(..., description="時間範囲（例: 0-10分）")
    title: str = Field(..., description="セクションタイトル")
    content: str = Field(..., description="セクション内容")


class LivePlanResponse(BaseModel):
    """Response model for live plan generation"""
    id: str = Field(..., description="企画案ID")
    type: str = Field(..., description="ライブ形式")
    title: str = Field(..., description="ライブタイトル")
    duration_hours: int = Field(..., description="予定時間（時間）")
    duration_minutes: int = Field(..., description="予定時間（分）")
    purposes: List[str] = Field(..., description="目的")
    target_audience: str = Field(..., description="ターゲット層")
    preferred_time_start: Optional[str] = Field(None, description="優先時間帯（開始）")
    preferred_time_end: Optional[str] = Field(None, description="優先時間帯（終了）")
    notes: Optional[str] = Field(None, description="追加メモ")
    difficulty: Optional[str] = Field(None, description="希望難易度")
    flow: List[FlowItem] = Field(..., description="配信の流れ")
    preparations: List[str] = Field(..., description="準備物リスト")
    generated_at: str = Field(..., description="生成日時")


class LivePlanListResponse(BaseModel):
    """Response model for live plan list"""
    plans: List[LivePlanResponse] = Field(..., description="ライブ企画案のリスト")

