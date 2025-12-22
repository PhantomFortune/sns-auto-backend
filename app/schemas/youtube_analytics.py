"""
Pydantic schemas for YouTube Analytics
Matching the frontend TypeScript interfaces
"""
from pydantic import BaseModel
from typing import List, Optional


class DailyDataItem(BaseModel):
    """Daily data point for trend charts"""
    date: str
    views: int
    estimatedMinutesWatched: float
    netSubscribers: int
    averageViewDuration: float  # seconds
    postClickQualityScore: Optional[float] = None  # Post-Click Quality Score (0-100)


class YouTubeAnalyticsData(BaseModel):
    """
    Main YouTube analytics data response
    Matches frontend YouTubeAnalyticsData interface
    """
    views: int
    estimatedMinutesWatched: float  # minutes
    averageViewDuration: float  # seconds
    impressions: int  # Deprecated: Always 0, not available via API. Use viewerRetentionRate instead.
    subscribersGained: int
    subscribersLost: int
    shares: int
    impressionClickThroughRate: Optional[float] = None  # Deprecated: Always None, not available via API
    viewerRetentionRate: Optional[float] = None  # percentage: (averageViewDuration / averageVideoDuration) * 100
    topVideoViews: Optional[int] = None
    topVideoSubscribersGained: Optional[int] = None
    averageVideoDuration: Optional[float] = None  # seconds
    previousPeriodViews: Optional[int] = None
    previousPeriodEstimatedMinutesWatched: Optional[float] = None
    previousPeriodAverageViewDuration: Optional[float] = None
    previousPeriodImpressions: Optional[int] = None  # Deprecated: Always 0
    previousPeriodViewerRetentionRate: Optional[float] = None  # percentage
    previousPeriodNetSubscribers: Optional[int] = None
    previousPeriodShares: Optional[int] = None
    dailyData: Optional[List[DailyDataItem]] = []


class YouTubeAnalyticsRequest(BaseModel):
    """Request body for YouTube improvement suggestions"""
    views: int
    estimatedMinutesWatched: float
    averageViewDuration: float  # seconds
    subscribersGained: int
    subscribersLost: int
    viewerRetentionRate: Optional[float] = None
    averageVideoDuration: Optional[float] = None  # seconds
    previousPeriodViews: Optional[int] = None
    previousPeriodEstimatedMinutesWatched: Optional[float] = None
    previousPeriodAverageViewDuration: Optional[float] = None
    previousPeriodViewerRetentionRate: Optional[float] = None
    previousPeriodNetSubscribers: Optional[int] = None
    dailyData: Optional[List[DailyDataItem]] = []


class ErrorResponse(BaseModel):
    """Error response with optional retry information"""
    detail: str
    api_timeout: Optional[bool] = False
    retry_after_seconds: Optional[int] = None

