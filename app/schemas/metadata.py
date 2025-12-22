"""
Metadata Schemas
Request and response models for metadata generation
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class MetadataRequest(BaseModel):
    """Request model for metadata generation"""
    script_summary: str = Field(..., max_length=1000, description="脚本要約 / スクリプト要約（必須、最大1000文字）")
    video_format: str = Field(..., description="動画形式（必須: ショート動画、通常動画、ライブ）")
    purposes: List[str] = Field(..., min_items=1, description="目的（必須、複数選択可能: 同時接続増加、登録者増加、発見性向上、視聴維持改善）")
    channel_summary: Optional[str] = Field(None, max_length=200, description="チャンネル概要（任意、最大200文字）")
    forbidden_words: Optional[str] = Field(None, description="禁止語（任意、カンマ区切り）")


class MetadataResponse(BaseModel):
    """Response model for metadata generation"""
    titles: List[str] = Field(..., min_items=3, max_items=5, description="タイトル候補（3-5個）")
    description: str = Field(..., description="説明文")
    hashtags: List[str] = Field(..., min_items=3, max_items=10, description="推奨ハッシュタグ（3-10個）")
    thumbnail_text: dict = Field(..., description="サムネイルテキスト（main, sub）")

