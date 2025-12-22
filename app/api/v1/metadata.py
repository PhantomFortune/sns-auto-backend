"""
Metadata API endpoints
Endpoints for generating YouTube metadata
"""
from fastapi import APIRouter, HTTPException, status
import logging

from app.schemas.metadata import (
    MetadataRequest,
    MetadataResponse,
)
from app.services.metadata_service import MetadataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metadata", tags=["Metadata"])

# Initialize service
metadata_service = MetadataService()


@router.post(
    "/generate",
    response_model=MetadataResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid request"},
        500: {"description": "Server error"},
    },
)
async def generate_metadata(request: MetadataRequest):
    """
    Generate YouTube metadata (titles, description, hashtags) based on the provided information.
    
    - **script_summary**: Script summary (required, max 1000 characters)
    - **video_format**: Video format (required: ショート動画, 通常動画, ライブ)
    - **purposes**: List of purposes (required, multiple selection: 同時接続増加, 登録者増加, 発見性向上, 視聴維持改善)
    - **channel_summary**: Channel summary (optional, max 200 characters)
    - **forbidden_words**: Forbidden words (optional, comma-separated)
    
    Returns YouTube metadata with:
    - Title candidates (3-5 titles)
    - Description text
    - Recommended hashtags (3-10 hashtags)
    - Thumbnail text (main and sub)
    """
    logger.info(f"メタデータ生成リクエスト受信: script_summary={len(request.script_summary)}文字, video_format={request.video_format}, purposes={request.purposes}")
    
    try:
        # Validate script summary
        if not request.script_summary or not request.script_summary.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="脚本要約を入力してください",
            )
        
        if len(request.script_summary) > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="脚本要約は1000文字以内で入力してください",
            )
        
        # Validate video format
        valid_formats = ["ショート動画", "通常動画", "ライブ"]
        if request.video_format not in valid_formats:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"動画形式は{', '.join(valid_formats)}のいずれかを選択してください",
            )
        
        # Validate purposes
        valid_purposes = ["同時接続増加", "登録者増加", "発見性向上", "視聴維持改善"]
        if not request.purposes or len(request.purposes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="目的を1つ以上選択してください",
            )
        
        for purpose in request.purposes:
            if purpose not in valid_purposes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"目的は{', '.join(valid_purposes)}のいずれかを選択してください",
                )
        
        # Validate channel summary
        if request.channel_summary and len(request.channel_summary) > 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="チャンネル概要は200文字以内で入力してください",
            )
        
        # Generate metadata
        logger.info("メタデータ生成を開始します...")
        metadata = metadata_service.generate_metadata(request)
        logger.info(f"メタデータ生成成功: titles={len(metadata.titles)}個, hashtags={len(metadata.hashtags)}個")
        return metadata
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"リクエストデータが不正です: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error generating metadata: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"メタデータの生成に失敗しました: {str(e)}",
        )

