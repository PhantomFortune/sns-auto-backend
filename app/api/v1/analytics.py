"""
Analytics API Routes
Endpoints for X (Twitter) and YouTube analytics
"""
from fastapi import APIRouter, Query, HTTPException, status
from typing import Literal
import logging
import tweepy
from datetime import datetime

from app.schemas.x_analytics import (
    XAnalyticsData,
    XAnalyticsRequest,
    ImprovementSuggestion,
    ErrorResponse,
)
from app.schemas.youtube_analytics import (
    YouTubeAnalyticsData,
    YouTubeAnalyticsRequest,
    ErrorResponse as YouTubeErrorResponse,
)
from app.services.x_api_service import x_api_service
from app.services.youtube_api_service import youtube_api_service
from googleapiclient.errors import HttpError
from app.services.improvement_service import improvement_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/x/analyze",
    response_model=XAnalyticsData,
    responses={
        429: {"model": ErrorResponse, "description": "Rate limited"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def analyze_x_data(
    period: Literal["2hours", "1day", "1week", "1month"] = Query(
        default="1day",
        description="Analysis period: 2hours, 1day, 1week, or 1month",
    )
):
    """
    Analyze X (Twitter) data for the specified period.
    
    - **period**: Time period to analyze
        - `2hours`: Last 2 hours
        - `1day`: Last 24 hours  
        - `1week`: Last 7 days
        - `1month`: Last 30 days
    
    Returns analytics data including:
    - Engagement metrics (likes, retweets, replies)
    - Impressions and profile views
    - Follower count and changes
    - Engagement trend over time
    - Hashtag performance analysis
    """
    try:
        analytics_data = await x_api_service.get_analytics(period)
        return analytics_data
        
    except tweepy.TooManyRequests as e:
        # Extract rate limit information from error
        reset_time = None
        limit = None
        remaining = None
        
        if hasattr(e, 'response') and e.response is not None:
            headers = e.response.headers if hasattr(e.response, 'headers') else {}
            reset_time_str = headers.get('x-rate-limit-reset', headers.get('X-Rate-Limit-Reset'))
            limit_str = headers.get('x-rate-limit-limit', headers.get('X-Rate-Limit-Limit'))
            remaining_str = headers.get('x-rate-limit-remaining', headers.get('X-Rate-Limit-Remaining'))
            
            if reset_time_str:
                try:
                    reset_time = int(reset_time_str)
                    current_time = int(datetime.now().timestamp())
                    retry_after = max(reset_time - current_time, 60)  # At least 60 seconds
                except (ValueError, TypeError):
                    retry_after = 60
            else:
                retry_after = 60
            
            if limit_str:
                try:
                    limit = int(limit_str)
                except (ValueError, TypeError):
                    pass
            
            if remaining_str:
                try:
                    remaining = int(remaining_str)
                except (ValueError, TypeError):
                    pass
        
        # Log detailed rate limit information
        logger.error(f"X API Rate Limit Exceeded:")
        logger.error(f"  Error: {e}")
        logger.error(f"  Rate Limit: {limit if limit is not None else 'unknown'}")
        logger.error(f"  Remaining: {remaining if remaining is not None else 'unknown'}")
        logger.error(f"  Reset Time: {reset_time if reset_time else 'unknown'}")
        logger.error(f"  Retry After: {retry_after} seconds")
        
        raise HTTPException(
            status_code=429,
            detail={
                "message": "X APIのレート制限に達しました",
                "api_timeout": True,
                "retry_after_seconds": retry_after,
                "rate_limit": limit,
                "remaining": remaining,
            },
        )
    except tweepy.TwitterServerError as e:
        logger.error(f"Twitter server error: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "message": "X APIサーバーエラーが発生しました",
                "api_timeout": True,
                "retry_after_seconds": 30,
            },
        )
    except tweepy.Unauthorized as e:
        logger.error(f"Unauthorized: {e}")
        raise HTTPException(
            status_code=401,
            detail="X API認証に失敗しました。APIキーを確認してください。",
        )
    except tweepy.Forbidden as e:
        logger.error(f"Forbidden: {e}")
        raise HTTPException(
            status_code=403,
            detail="X APIへのアクセスが拒否されました。アカウント権限を確認してください。",
        )
    except Exception as e:
        logger.error(f"Unexpected error in analyze_x_data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"データ取得に失敗しました: {str(e)}",
        )


@router.post(
    "/x/improvements",
    response_model=ImprovementSuggestion,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def generate_improvements(request: XAnalyticsRequest):
    """
    Generate AI improvement suggestions based on analytics data.
    
    Analyzes the provided metrics and returns:
    - Summary of current performance
    - Key insights from the data
    - Actionable recommendations
    - Best posting time suggestions
    - Hashtag recommendations
    """
    try:
        suggestions = improvement_service.generate_suggestions(request)
        return suggestions
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"リクエストデータが不正です: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error generating improvements: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"改善提案の生成に失敗しました: {str(e)}",
        )


@router.get("/x/status")
async def check_api_status():
    """
    Check X API connection status.
    
    Returns the connection status and rate limit information.
    """
    try:
        # Simple check - try to get authenticated user
        user = x_api_service.client.get_me()
        
        return {
            "status": "connected",
            "username": user.data.username if user.data else None,
            "message": "X API接続成功",
        }
    except tweepy.Unauthorized:
        return {
            "status": "unauthorized",
            "message": "認証に失敗しました",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }


@router.get(
    "/youtube/analyze",
    response_model=YouTubeAnalyticsData,
    responses={
        500: {"model": YouTubeErrorResponse, "description": "Server error"},
    },
)
async def analyze_youtube_data(
    period: Literal["1week", "1month"] = Query(
        default="1week",
        description="Analysis period: 1week or 1month (YouTube Analytics API cannot fetch data for the past 3 days)",
    )
):
    """
    Analyze YouTube data for the specified period.
    
    - **period**: Time period to analyze
        - `1week`: Last 7 days
        - `1month`: Last 30 days
    
    Note: YouTube Analytics API cannot fetch data for the past 3 days.
    
    Returns analytics data including:
    - Views, watch time, average view duration
    - Viewer retention rate
    - Subscriber gains/losses
    - Daily trend data
    - Video-specific metrics
    """
    try:
        analytics_data = await youtube_api_service.get_analytics(period)
        return YouTubeAnalyticsData(**analytics_data)
    except ValueError as e:
        # Handle authentication errors specifically
        logger.error(f"YouTube Analytics authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except HttpError as e:
        logger.error(f"YouTube API error: {e}")
        error_content = ""
        try:
            if hasattr(e, 'content') and e.content:
                error_content = e.content.decode('utf-8') if isinstance(e.content, bytes) else str(e.content)
        except Exception:
            error_content = str(e)
        
        raise HTTPException(
            status_code=e.resp.status if hasattr(e, 'resp') else status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"YouTube APIエラー: {error_content}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in analyze_youtube_data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"YouTubeデータ取得に失敗しました: {str(e)}"
        )


@router.post(
    "/youtube/improvements",
    response_model=ImprovementSuggestion,
    responses={
        400: {"model": YouTubeErrorResponse, "description": "Invalid request"},
        500: {"model": YouTubeErrorResponse, "description": "Server error"},
    },
)
async def generate_youtube_improvements(request: YouTubeAnalyticsRequest):
    """
    Generate AI improvement suggestions based on YouTube analytics data.
    
    Analyzes the provided metrics and returns:
    - Summary of current performance
    - Key insights from the data
    - Actionable recommendations
    - Best practices for video optimization
    """
    try:
        suggestions = improvement_service.generate_youtube_suggestions(request)
        return suggestions
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"リクエストデータが不正です: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error generating YouTube improvements: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"改善提案の生成に失敗しました: {str(e)}",
        )

