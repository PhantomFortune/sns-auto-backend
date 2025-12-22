"""
CeVIO AI API endpoints
Endpoints for CeVIO AI text-to-speech
"""
from fastapi import APIRouter, HTTPException, status
import logging

from app.schemas.cevio import (
    CeVIOSpeakRequest,
    CeVIOSpeakResponse,
    CeVIOStatusResponse,
)
from app.services.cevio_service import cevio_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cevio", tags=["CeVIO AI"])


@router.get(
    "/status",
    response_model=CeVIOStatusResponse,
    responses={
        500: {"description": "Server error"},
    },
)
async def get_cevio_status():
    """
    Get CeVIO AI connection status and available casts.
    This will attempt to connect if not already connected.
    """
    try:
        # Try to ensure connection
        connected = cevio_service.ensure_connected()
        
        return CeVIOStatusResponse(
            connected=connected,
            is_speaking=cevio_service.is_speaking() if connected else False,
            available_casts=cevio_service.get_available_casts(),
        )
    except Exception as e:
        logger.error(f"Error getting CeVIO AI status: {e}", exc_info=True)
        return CeVIOStatusResponse(
            connected=False,
            is_speaking=False,
            available_casts=["フィーちゃん", "ユニちゃん", "夏色花梨"],
        )


@router.get(
    "/test",
    responses={
        200: {"description": "Test result"},
        500: {"description": "Server error"},
    },
)
async def test_cevio_connection():
    """
    Test CeVIO AI connection with detailed diagnostics.
    This endpoint provides detailed information for debugging.
    """
    import platform
    diagnostics = {
        "platform": platform.system(),
        "com_available": cevio_service.com_available,
        "is_connected": cevio_service.is_connected,
        "connection_attempt": None,
        "error_details": None,
    }
    
    try:
        # Try to connect
        connected = cevio_service.ensure_connected()
        diagnostics["connection_attempt"] = "success" if connected else "failed"
        
        if connected:
            # Try to get current cast
            try:
                current_cast = cevio_service.talker.Cast if cevio_service.talker else None
                diagnostics["current_cast"] = current_cast
            except Exception as e:
                diagnostics["current_cast_error"] = str(e)
            
            # Try to check if speaking
            try:
                is_speaking = cevio_service.is_speaking()
                diagnostics["is_speaking"] = is_speaking
            except Exception as e:
                diagnostics["is_speaking_error"] = str(e)
        else:
            diagnostics["error_details"] = "Failed to connect to CeVIO AI. Make sure CeVIO AI Talk Editor is running."
        
        return {
            "success": connected,
            "diagnostics": diagnostics,
            "message": "CeVIO AI接続テスト完了" if connected else "CeVIO AI接続に失敗しました",
        }
    except Exception as e:
        logger.error(f"Error testing CeVIO AI connection: {e}", exc_info=True)
        diagnostics["error_details"] = str(e)
        return {
            "success": False,
            "diagnostics": diagnostics,
            "message": f"テスト中にエラーが発生しました: {str(e)}",
        }


@router.post(
    "/speak",
    response_model=CeVIOSpeakResponse,
    responses={
        400: {"description": "Invalid request"},
        500: {"description": "Server error"},
    },
)
async def speak_text(request: CeVIOSpeakRequest):
    """
    Speak text using CeVIO AI.
    
    - **text**: Text to speak
    - **cast**: Voice cast name (フィーちゃん, ユニちゃん, 夏色花梨)
    """
    try:
        # Validate cast
        valid_casts = ["フィーちゃん", "ユニちゃん", "夏色花梨"]
        if request.cast not in valid_casts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"キャストは{', '.join(valid_casts)}のいずれかを選択してください",
            )
        
        # Validate text
        if not request.text or not request.text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="読み上げるテキストを入力してください",
            )
        
        # Ensure connection before speaking
        if not cevio_service.ensure_connected():
            logger.error("CeVIO AI connection failed. Please check if CeVIO AI Talk Editor is running.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="CeVIO AIに接続できません。CeVIO AIトークエディタが起動しているか確認してください。起動後、バックエンドサーバーを再起動してください。",
            )
        
        # Speak text
        success = cevio_service.speak(request.text, request.cast)
        
        if success:
            return CeVIOSpeakResponse(
                success=True,
                message=f"テキストを読み上げました（キャスト: {request.cast}）",
            )
        else:
            # Connection is established but speaking failed
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="音声読み上げに失敗しました。CeVIO AIのログを確認してください。",
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error speaking with CeVIO AI: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"音声読み上げに失敗しました: {str(e)}",
        )


@router.post(
    "/stop",
    response_model=CeVIOSpeakResponse,
    responses={
        500: {"description": "Server error"},
    },
)
async def stop_speech():
    """
    Stop current CeVIO AI speech.
    """
    try:
        success = cevio_service.stop()
        
        if success:
            return CeVIOSpeakResponse(
                success=True,
                message="音声読み上げを停止しました",
            )
        else:
            return CeVIOSpeakResponse(
                success=False,
                message="音声読み上げの停止に失敗しました",
            )
        
    except Exception as e:
        logger.error(f"Error stopping CeVIO AI speech: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"音声読み上げの停止に失敗しました: {str(e)}",
        )

