"""
Pydantic schemas for X (Twitter) analytics
Matching the frontend TypeScript interfaces
"""
from pydantic import BaseModel
from typing import List, Optional


class EngagementTrendItem(BaseModel):
    """Single data point in engagement trend"""
    time: str
    engagement: int
    impressions: int


class HashtagDataItem(BaseModel):
    """Single data point for hashtag analysis"""
    time: str
    likes: int


class HashtagAnalysis(BaseModel):
    """Hashtag analysis with likes and trend data"""
    tag: str
    likes: int
    data: List[HashtagDataItem]


class XAnalyticsData(BaseModel):
    """
    Main analytics data response
    Matches frontend XAnalyticsData interface
    """
    likes_count: int
    retweets_count: int
    replies_count: int
    impressions_count: int
    followers_count: int
    engagement_trend: List[EngagementTrendItem]
    hashtag_analysis: List[HashtagAnalysis]
    is_cached: Optional[bool] = False
    data_age_minutes: Optional[int] = 0
    api_timeout: Optional[bool] = False
    retry_after_seconds: Optional[int] = None
    message: Optional[str] = None


class XAnalyticsRequest(BaseModel):
    """Request body for improvement suggestions"""
    likes_count: int
    retweets_count: int
    replies_count: int
    impressions_count: int
    followers_count: int
    hashtag_analysis: List[HashtagAnalysis]
    period: str


class ImprovementSuggestion(BaseModel):
    """
    AI-generated improvement suggestions
    Matches frontend ImprovementSuggestion interface
    """
    summary: str
    key_insights: List[str]
    recommendations: List[str]
    best_posting_time: str
    hashtag_recommendations: List[str]


class ErrorResponse(BaseModel):
    """Error response with optional retry information"""
    detail: str
    api_timeout: Optional[bool] = False
    retry_after_seconds: Optional[int] = None

