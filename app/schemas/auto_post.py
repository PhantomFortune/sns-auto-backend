"""
Auto Post Generation Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional


class AutoPostGenerateRequest(BaseModel):
    """Request schema for auto post text generation"""
    post_type: str = Field(..., description="投稿タイプ（朝の挨拶、夜の挨拶など）")
    purpose: str = Field(..., description="目的（親近感を高めたい、視聴・参加を誘導したいなど）")
    emoji_style: str = Field(..., description="絵文字・感嘆符のスタイル（豊富に、多様化、適度に、控えめに）")
    emoji_usage: str = Field(..., description="絵文字・感嘆符の使用度（多用する、バランス良く、控えめに、使わない）")
    tone: str = Field(..., description="トーン（カジュアル、丁寧、活発、落ち着いた、専門的）")
    poster_type: str = Field(..., description="投稿主タイプ（VTuber、個人、企業公式、インフルエンサー、その他）")
    required_info: Optional[str] = Field(None, description="必須情報（例：本日21時より配信、URL不要など）")
    image_role: Optional[str] = Field(None, description="画像の役割（雰囲気伝達用、内容補足、情報（日時等）を含む、特に関係なし）")
    cta: str = Field(..., description="行動喚起（なし、見てほしい、参加してほしい、詳細を確認してほしい、自由入力）")
    cta_custom: Optional[str] = Field(None, description="CTA自由入力内容")


class AutoPostGenerateResponse(BaseModel):
    """Response schema for auto post text generation"""
    text: str = Field(..., description="生成された投稿文（280文字以内）")
    character_count: int = Field(..., description="文字数")

