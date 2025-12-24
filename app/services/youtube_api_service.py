"""
YouTube Analytics API Service
Handles data fetching from YouTube Analytics API and YouTube Data API v3
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import logging
import json
import os
import asyncio

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from app.core.config import settings

logger = logging.getLogger(__name__)

# Japan Standard Time (UTC+9) - all analytics are based on Tokyo time
JST = timezone(timedelta(hours=9))

# YouTube API scopes
# Note: The refresh token was created with: youtube, youtube.readonly, youtube.force-ssl
# The youtube.readonly scope should provide access to Analytics API as well
# If Analytics API access fails, we'll need to create a new token with yt-analytics.readonly
SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/yt-analytics.readonly'
]
# Fallback scopes if the token doesn't have yt-analytics.readonly
FALLBACK_SCOPES = [
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube.force-ssl'
]


class YouTubeAPIService:
    """Service for interacting with YouTube Analytics API and YouTube Data API v3"""
    
    def __init__(self):
        self.analytics_service = None
        self.data_service = None
        self.credentials = None
        self._initialize_services()
    
    def _initialize_services(self):
        """Initialize YouTube API services"""
        try:
            # Try to use API key first (for public data)
            if settings.YOUTUBE_API_KEY:
                self.data_service = build('youtube', 'v3', developerKey=settings.YOUTUBE_API_KEY)
                logger.info("YouTube Data API v3 initialized with API key")
            
            # Try to initialize Analytics API with OAuth2
            # Check if client_secret.json exists in backend directory or if env var is set
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            client_secret_file = os.path.join(backend_dir, 'client_secret.json')
            
            if settings.YOUTUBE_CLIENT_SECRET_JSON or os.path.exists(client_secret_file):
                logger.info(f"Initializing OAuth2 for YouTube Analytics API...")
                logger.info(f"client_secret.json exists: {os.path.exists(client_secret_file)}")
                logger.info(f"YOUTUBE_CLIENT_SECRET_JSON set: {bool(settings.YOUTUBE_CLIENT_SECRET_JSON)}")
                self._initialize_oauth2()
            else:
                logger.warning(f"client_secret.json not found at {client_secret_file} and YOUTUBE_CLIENT_SECRET_JSON not set")
                logger.warning("YouTube Analytics API will not be available without OAuth2 credentials")
            
            if not self.data_service:
                logger.warning("YouTube API services not initialized. API key or OAuth2 credentials required.")
        except Exception as e:
            logger.error(f"Failed to initialize YouTube API services: {e}")
            raise
    
    def _initialize_oauth2(self):
        """Initialize OAuth2 credentials for YouTube Analytics API"""
        try:
            # Parse client_secret.json
            client_config = None
            # Use absolute path to ensure we find the file regardless of current working directory
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            client_secret_file = os.path.join(backend_dir, 'client_secret.json')
            
            logger.info(f"Looking for client_secret.json at: {client_secret_file}")
            logger.info(f"client_secret.json exists: {os.path.exists(client_secret_file)}")
            
            # Try as file path first
            if settings.YOUTUBE_CLIENT_SECRET_JSON and os.path.exists(settings.YOUTUBE_CLIENT_SECRET_JSON):
                with open(settings.YOUTUBE_CLIENT_SECRET_JSON, 'r') as f:
                    client_config = json.load(f)
                # Also save to backend directory for OAuth flow
                with open(client_secret_file, 'w') as f:
                    json.dump(client_config, f)
                logger.info(f"Loaded client_secret.json from {settings.YOUTUBE_CLIENT_SECRET_JSON}")
            elif settings.YOUTUBE_CLIENT_SECRET_JSON:
                # Try as JSON string
                try:
                    client_config = json.loads(settings.YOUTUBE_CLIENT_SECRET_JSON)
                    # Save to file for OAuth flow
                    with open(client_secret_file, 'w') as f:
                        json.dump(client_config, f)
                    logger.info("Saved client_secret.json from environment variable")
                except json.JSONDecodeError:
                    logger.warning("YOUTUBE_CLIENT_SECRET_JSON is not valid JSON")
                    return
            elif os.path.exists(client_secret_file):
                # Try to load from backend directory
                with open(client_secret_file, 'r') as f:
                    client_config = json.load(f)
                logger.info("Loaded client_secret.json from backend directory")
            
            if not client_config:
                logger.warning("YOUTUBE_CLIENT_SECRET_JSON not provided or invalid")
                return
            
            # Check for existing token
            # Use absolute path to ensure we find the file regardless of current working directory
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            token_file = os.path.join(backend_dir, 'youtube_token.json')
            creds = None
            
            logger.info(f"Looking for token file at: {token_file}")
            logger.info(f"Token file exists: {os.path.exists(token_file)}")
            logger.info(f"Current working directory: {os.getcwd()}")
            
            # Try to load token from environment variable first
            if settings.YOUTUBE_TOKEN_JSON:
                try:
                    if os.path.exists(settings.YOUTUBE_TOKEN_JSON):
                        # Load from file path - don't specify SCOPES to use token's original scopes
                        creds = Credentials.from_authorized_user_file(settings.YOUTUBE_TOKEN_JSON)
                        logger.info(f"Loaded OAuth2 token from {settings.YOUTUBE_TOKEN_JSON}")
                    else:
                        # Try as JSON string
                        token_data = json.loads(settings.YOUTUBE_TOKEN_JSON)
                        creds = Credentials.from_authorized_user_info(token_data)
                        logger.info("Loaded OAuth2 token from environment variable")
                except Exception as e:
                    logger.warning(f"Failed to load token from environment variable: {e}")
            
            # Try to load from file if not loaded from environment
            if not creds and os.path.exists(token_file):
                try:
                    # Don't specify SCOPES to use token's original scopes
                    # The token file contains the scopes it was created with
                    creds = Credentials.from_authorized_user_file(token_file)
                    logger.info(f"Loaded existing OAuth2 token from file: {token_file}")
                except Exception as e:
                    logger.warning(f"Failed to load existing token from {token_file}: {e}")
                    import traceback
                    logger.warning(traceback.format_exc())
            elif not creds:
                logger.warning(f"Token file not found at: {token_file}")
                logger.warning(f"Current working directory: {os.getcwd()}")
            
            # If there are no (valid) credentials available, try to create from refresh token
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        logger.info("OAuth2 token refreshed successfully")
                    except Exception as e:
                        logger.warning(f"Failed to refresh token: {e}")
                        creds = None
                
                # Try to create credentials from refresh token in environment variable
                if not creds and settings.YOUTUBE_REFRESH_TOKEN and client_config:
                    try:
                        # Extract client_id and client_secret from client_config
                        if 'installed' in client_config:
                            installed = client_config['installed']
                            client_id = installed.get('client_id')
                            client_secret = installed.get('client_secret')
                        elif 'web' in client_config:
                            web = client_config['web']
                            client_id = web.get('client_id')
                            client_secret = web.get('client_secret')
                        else:
                            client_id = client_config.get('client_id')
                            client_secret = client_config.get('client_secret')
                        
                        if client_id and client_secret:
                            # Try with required scopes first
                            try:
                                creds = Credentials(
                                    token=None,
                                    refresh_token=settings.YOUTUBE_REFRESH_TOKEN,
                                    token_uri='https://oauth2.googleapis.com/token',
                                    client_id=client_id,
                                    client_secret=client_secret,
                                    scopes=SCOPES
                                )
                                creds.refresh(Request())
                                logger.info("OAuth2 token created from refresh token with required scopes")
                            except Exception as e:
                                # If that fails, try with fallback scopes (what the token was created with)
                                logger.warning(f"Failed with required scopes, trying fallback scopes: {e}")
                                try:
                                    creds = Credentials(
                                        token=None,
                                        refresh_token=settings.YOUTUBE_REFRESH_TOKEN,
                                        token_uri='https://oauth2.googleapis.com/token',
                                        client_id=client_id,
                                        client_secret=client_secret,
                                        scopes=FALLBACK_SCOPES
                                    )
                                    creds.refresh(Request())
                                    logger.info("OAuth2 token created from refresh token with fallback scopes")
                                    logger.warning("Note: Token may not have yt-analytics.readonly scope. Analytics API access may be limited.")
                                except Exception as e2:
                                    logger.warning(f"Failed to refresh token from refresh_token: {e2}")
                                    creds = None
                    except Exception as e:
                        logger.warning(f"Failed to create credentials from refresh token: {e}")
                
                if not creds:
                    # Need to get new credentials - this requires user interaction
                    logger.warning("OAuth2 authentication required. YouTube Analytics API will not be available until authenticated.")
                    logger.warning("To authenticate, run: python authenticate_youtube.py")
                    logger.warning("Or set YOUTUBE_TOKEN_JSON or YOUTUBE_REFRESH_TOKEN environment variable")
                    # Don't return - we'll try to authenticate interactively if possible
                    # For now, we'll continue without Analytics API
                    return
            
            # Save the credentials for the next run
            if creds:
                try:
                    # Ensure token_file is absolute path
                    if not os.path.isabs(token_file):
                        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                        token_file = os.path.join(backend_dir, token_file)
                    
                    with open(token_file, 'w') as token:
                        token.write(creds.to_json())
                    logger.info(f"Saved OAuth2 token to {token_file}")
                except Exception as e:
                    logger.warning(f"Failed to save token to file {token_file}: {e}")
                    import traceback
                    logger.warning(traceback.format_exc())
                
                self.credentials = creds
                self.analytics_service = build('youtubeAnalytics', 'v2', credentials=creds)
                logger.info("YouTube Analytics API initialized with OAuth2")
            else:
                logger.error("OAuth2 credentials not available. YouTube Analytics API will not be available.")
                logger.error("Please provide one of the following:")
                logger.error("  1. YOUTUBE_TOKEN_JSON environment variable (path to youtube_token.json or JSON string)")
                logger.error("  2. YOUTUBE_REFRESH_TOKEN environment variable (with YOUTUBE_CLIENT_SECRET_JSON)")
                logger.error("  3. Place youtube_token.json file in the backend directory")
        except Exception as e:
            logger.warning(f"Failed to initialize OAuth2 for YouTube Analytics API: {e}")
            logger.warning("Continuing with API key only (limited functionality)")
    
    def _get_time_range(self, period: str) -> Tuple[datetime, datetime]:
        """
        Calculate time range based on period in **Tokyo time (JST)**.
        For YouTube Analytics API, we need to ensure start_date < end_date.
        Note: endDate is exclusive in YouTube Analytics API, so we need to use tomorrow's date
        to include today's data.
        
        Note: YouTube Analytics API cannot fetch data for the past 3 days.
        Supported periods: "1week" (7 days) and "1month" (30 days).
        """
        now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
        now_jst = now_utc.astimezone(JST)
        
        if period == "1week":
            # For 1 week: from 7 days ago 00:00 to today (inclusive)
            # This means: from (today - 7 days) 00:00 to today 23:59:59 (inclusive)
            # Since endDate is exclusive in YouTube Analytics API, we use tomorrow's date
            # Example: If today is 2025-12-07 01:18, we want data from 2025-11-30 00:00 to 2025-12-07 23:59:59
            # So start_date = 2025-11-30, end_date = 2025-12-08 (exclusive, so includes 2025-12-07)
            # Calculate exactly 7 days ago from now
            start_jst = (now_jst - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
            # Use tomorrow's date as end_date to include all of today's data
            # This ensures we get data up to and including today
            end_jst = (now_jst + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Log detailed information for debugging
            logger.info(f"1week period calculation:")
            logger.info(f"  Current time (JST): {now_jst.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"  Start date (JST): {start_jst.strftime('%Y-%m-%d %H:%M:%S')} (7 days ago)")
            logger.info(f"  End date (JST): {end_jst.strftime('%Y-%m-%d %H:%M:%S')} (tomorrow, exclusive)")
            logger.info(f"  Expected date range: {start_jst.strftime('%Y-%m-%d')} to {end_jst.strftime('%Y-%m-%d')} (exclusive)")
        elif period == "1month":
            # For 1 month: from 30 days ago 00:00 to today (inclusive)
            # Since endDate is exclusive in YouTube Analytics API, we use tomorrow's date
            # Example: If today is 2025-12-07, we want data from 2025-11-07 00:00 to 2025-12-07 23:59:59
            # So start_date = 2025-11-07, end_date = 2025-12-08 (exclusive, so includes 2025-12-07)
            start_jst = (now_jst - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_jst = (now_jst + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Log detailed information for debugging
            logger.info(f"1month period calculation:")
            logger.info(f"  Current time (JST): {now_jst.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"  Start date (JST): {start_jst.strftime('%Y-%m-%d %H:%M:%S')} (30 days ago)")
            logger.info(f"  End date (JST): {end_jst.strftime('%Y-%m-%d %H:%M:%S')} (tomorrow, exclusive)")
            logger.info(f"  Expected date range: {start_jst.strftime('%Y-%m-%d')} to {end_jst.strftime('%Y-%m-%d')} (exclusive)")
        else:
            # Default to 1week if invalid period is provided
            logger.warning(f"Invalid period '{period}' provided. Defaulting to '1week'.")
            start_jst = (now_jst - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_jst = (now_jst + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Ensure start_date is strictly before end_date for API
        # YouTube Analytics API requires start_date < end_date
        if start_jst.date() >= end_jst.date():
            # For other periods, adjust start to be at least 1 day before
            start_jst = (end_jst - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        logger.debug(f"Time range for {period}: {start_jst.strftime('%Y-%m-%d %H:%M:%S JST')} to {end_jst.strftime('%Y-%m-%d %H:%M:%S JST')}")
        
        return start_jst, end_jst
    
    def _format_date_for_api(self, dt: datetime) -> str:
        """Format datetime to YYYY-MM-DD for YouTube Analytics API"""
        return dt.strftime("%Y-%m-%d")
    
    async def get_analytics(self, period: str) -> Dict:
        """
        Fetch analytics data from YouTube Analytics API
        
        Args:
            period: Time period - "1week" or "1month" (YouTube Analytics API cannot fetch data for the past 3 days)
            
        Returns:
            Dictionary with all analytics metrics
        """
        try:
            channel_id = settings.YOUTUBE_CHANNEL_ID
            # Get current time in JST for fallback logic
            now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
            now_jst = now_utc.astimezone(JST)
            
            start_jst, end_jst = self._get_time_range(period)
            start_date = self._format_date_for_api(start_jst)
            end_date = self._format_date_for_api(end_jst)
            
            logger.info(f"YouTube Analytics: Fetching data for period '{period}' from {start_date} to {end_date} (JST: {start_jst.strftime('%Y-%m-%d %H:%M:%S')} to {end_jst.strftime('%Y-%m-%d %H:%M:%S')})")
            
            # Calculate previous period for comparison
            # Note: For previous period, we also need to account for exclusive endDate
            if period == "1week":
                # Previous week: 2 weeks ago to 1 week ago (inclusive)
                prev_start_jst = (start_jst - timedelta(weeks=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                prev_end_jst = start_jst  # This is 1 week ago 00:00, which is exclusive, so it includes 2 weeks ago
            elif period == "1month":
                # Previous month: 2 months ago to 1 month ago (inclusive)
                prev_start_jst = (start_jst - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
                prev_end_jst = start_jst  # This is 1 month ago 00:00, which is exclusive, so it includes 2 months ago
            else:
                # Default to 1week logic
                prev_start_jst = (start_jst - timedelta(weeks=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                prev_end_jst = start_jst
            
            prev_start_date = self._format_date_for_api(prev_start_jst)
            prev_end_date = self._format_date_for_api(prev_end_jst)
            
            result = {}
            
            # Fetch current period data
            if self.analytics_service:
                # Use Analytics API (requires OAuth2)
                try:
                    current_data = await self._fetch_analytics_data(
                        channel_id, start_date, end_date
                    )
                    previous_data = await self._fetch_analytics_data(
                        channel_id, prev_start_date, prev_end_date
                    )
                    
                    result.update(current_data)
                    result['previousPeriodViews'] = previous_data.get('views', 0)
                    result['previousPeriodEstimatedMinutesWatched'] = previous_data.get('estimatedMinutesWatched', 0)
                    result['previousPeriodAverageViewDuration'] = previous_data.get('averageViewDuration', 0)
                    result['previousPeriodNetSubscribers'] = previous_data.get('netSubscribers', 0)
                    result['previousPeriodShares'] = previous_data.get('shares', 0)
                except Exception as e:
                    logger.error(f"Failed to fetch from Analytics API, falling back to Data API: {e}")
                    # Fallback to Data API if Analytics API fails
                    current_data = await self._fetch_data_api_metrics(channel_id, start_date, end_date)
                    previous_data = await self._fetch_data_api_metrics(channel_id, prev_start_date, prev_end_date)
                    
                    result.update(current_data)
                    result['previousPeriodViews'] = previous_data.get('views', 0)
                    result['previousPeriodEstimatedMinutesWatched'] = previous_data.get('estimatedMinutesWatched', 0)
                    result['previousPeriodAverageViewDuration'] = previous_data.get('averageViewDuration', 0)
                    result['previousPeriodNetSubscribers'] = previous_data.get('netSubscribers', 0)
                    result['previousPeriodShares'] = previous_data.get('shares', 0)
            else:
                # Fallback: Use Data API v3 (limited metrics, requires API key)
                logger.error("YouTube Analytics API not initialized. OAuth2 authentication required.")
                logger.error("Please set one of the following:")
                logger.error("  1. YOUTUBE_TOKEN_JSON environment variable (path to youtube_token.json or JSON string)")
                logger.error("  2. YOUTUBE_REFRESH_TOKEN environment variable (with YOUTUBE_CLIENT_SECRET_JSON)")
                logger.error("  3. Place youtube_token.json file in the backend directory")
                # Data API v3 cannot provide period-specific data - raise an error instead of returning misleading data
                error_msg = (
                    "YouTube Analytics API requires OAuth2 authentication. "
                    "Please set YOUTUBE_TOKEN_JSON or YOUTUBE_REFRESH_TOKEN environment variable, "
                    "or place youtube_token.json file in the backend directory. "
                    "Data API v3 only provides cumulative channel statistics, not period-specific metrics."
                )
                raise ValueError(error_msg)
            
            # Ensure netSubscribers is calculated
            if 'netSubscribers' not in result:
                result['netSubscribers'] = result.get('subscribersGained', 0) - result.get('subscribersLost', 0)
            
            # Fetch video list for average video duration and top video metrics
            video_metrics = await self._fetch_video_metrics(channel_id, start_date, end_date)
            if video_metrics:
                result['averageVideoDuration'] = video_metrics.get('averageVideoDuration')
                result['topVideoViews'] = video_metrics.get('topVideoViews')
                result['topVideoSubscribersGained'] = video_metrics.get('topVideoSubscribersGained')
            
            # Calculate viewer retention rate (視聴継続率)
            # Viewer retention rate = (averageViewDuration / averageVideoDuration) * 100
            if result.get('averageVideoDuration') and result.get('averageVideoDuration') > 0:
                viewer_retention_rate = (result.get('averageViewDuration', 0) / result.get('averageVideoDuration')) * 100
                result['viewerRetentionRate'] = round(viewer_retention_rate, 2)
            else:
                result['viewerRetentionRate'] = None
            
            # Calculate previous period viewer retention rate
            # We need to fetch previous period video metrics for accurate calculation
            prev_video_metrics = await self._fetch_video_metrics(channel_id, prev_start_date, prev_end_date)
            if prev_video_metrics and prev_video_metrics.get('averageVideoDuration') and prev_video_metrics.get('averageVideoDuration') > 0:
                prev_avg_duration = result.get('previousPeriodAverageViewDuration', 0)
                prev_video_duration = prev_video_metrics.get('averageVideoDuration')
                if prev_video_duration > 0:
                    prev_viewer_retention = (prev_avg_duration / prev_video_duration) * 100
                    result['previousPeriodViewerRetentionRate'] = round(prev_viewer_retention, 2)
                else:
                    result['previousPeriodViewerRetentionRate'] = None
            else:
                result['previousPeriodViewerRetentionRate'] = None
            
            # For backward compatibility, set impressions to 0 (not available via API)
            result['impressions'] = 0
            result['impressionClickThroughRate'] = None
            
            # Fetch daily data for charts
            daily_data = await self._fetch_daily_data(channel_id, start_date, end_date, period)
            
            # Calculate Post-Click Quality Score (PCQ) for each day
            if daily_data and result.get('averageVideoDuration'):
                daily_data = self._calculate_pcq(daily_data, result.get('averageVideoDuration'))
            
            result['dailyData'] = daily_data
            
            logger.info(f"YouTube analytics data fetched successfully for period {period}")
            return result
            
        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching YouTube analytics: {e}")
            raise
    
    async def _fetch_analytics_data(self, channel_id: str, start_date: str, end_date: str) -> Dict:
        """Fetch data from YouTube Analytics API"""
        if not self.analytics_service:
            raise Exception("YouTube Analytics API not initialized. OAuth2 authentication required.")
        
        try:
            # Query for main metrics
            # Note: When dimensions='day' is used, row[0] is the date, metrics start from row[1]
            # Also note: 'impressions' is not a valid metric in YouTube Analytics API v2 when used with dimensions
            logger.info(f"Fetching YouTube Analytics data for channel {channel_id} from {start_date} to {end_date}")
            
            # Wrap synchronous execute() call in executor to prevent blocking
            loop = asyncio.get_event_loop()
            query = await loop.run_in_executor(
                None,
                lambda: self.analytics_service.reports().query(
                    ids=f'channel=={channel_id}',
                    startDate=start_date,
                    endDate=end_date,
                    metrics='views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost,shares',
                    dimensions='day'
                ).execute()
            )
            
            logger.info(f"YouTube Analytics API query executed successfully")
            
            # Aggregate data
            rows = query.get('rows', [])
            logger.info(f"Received {len(rows)} rows from YouTube Analytics API")
            if not rows:
                logger.warning(f"No data returned from YouTube Analytics API for period {start_date} to {end_date}")
                # Return zeros but don't raise error - might be legitimate (no data in period)
                return {
                    'views': 0,
                    'estimatedMinutesWatched': 0,
                    'averageViewDuration': 0,
                    'subscribersGained': 0,
                    'subscribersLost': 0,
                    'shares': 0,
                    'netSubscribers': 0,
                }
            
            total_views = 0
            total_minutes = 0
            total_gained = 0
            total_lost = 0
            total_shares = 0
            total_avg_duration = 0
            count = 0
            
            # When dimensions='day' is used:
            # row[0] = date (dimension) - SKIP THIS
            # row[1] = views
            # row[2] = estimatedMinutesWatched
            # row[3] = averageViewDuration
            # row[4] = subscribersGained
            # row[5] = subscribersLost
            # row[6] = shares
            for row in rows:
                if len(row) < 7:
                    logger.warning(f"Invalid row format: {row}, expected at least 7 columns (date + 6 metrics)")
                    continue
                # Skip row[0] which is the date dimension
                total_views += int(row[1] or 0)
                total_minutes += float(row[2] or 0)
                total_avg_duration += float(row[3] or 0)  # averageViewDuration is in seconds
                total_gained += int(row[4] or 0)
                total_lost += int(row[5] or 0)
                total_shares += int(row[6] or 0)
                count += 1
            
            avg_duration = total_avg_duration / count if count > 0 else 0
            
            # Note: 'impressions' metric is NOT available in YouTube Analytics API v2
            # Instead, we calculate viewer retention rate (視聴継続率)
            # Viewer retention rate = (averageViewDuration / averageVideoDuration) * 100
            # This will be calculated later when we have averageVideoDuration from video metrics
            
            logger.info(f"Fetched YouTube Analytics data: views={total_views}, minutes={total_minutes:.2f}, "
                       f"avg_duration={avg_duration:.2f}s, gained={total_gained}, lost={total_lost}, "
                       f"shares={total_shares}, rows_processed={count}")
            
            # Log detailed information for debugging shares metric
            if rows and len(rows) > 0:
                shares_by_date = []
                for row in rows[:5]:  # Log first 5 rows
                    if len(row) >= 7:
                        shares_by_date.append({
                            'date': row[0],
                            'shares': row[6] if len(row) > 6 else 0
                        })
                logger.debug(f"Shares breakdown (first 5 rows): {shares_by_date}")
                logger.info(f"Total shares from {count} rows: {total_shares}")
            else:
                logger.warning("No rows returned from API - shares will be 0")
            
            return {
                'views': total_views,
                'estimatedMinutesWatched': total_minutes,
                'averageViewDuration': avg_duration,  # seconds
                'subscribersGained': total_gained,
                'subscribersLost': total_lost,
                'shares': total_shares,
                'netSubscribers': total_gained - total_lost,
            }
        except HttpError as e:
            logger.error(f"YouTube Analytics API HttpError: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching analytics data: {e}", exc_info=True)
            raise
    
    async def _fetch_data_api_metrics(self, channel_id: str, start_date: str, end_date: str) -> Dict:
        """Fallback: Fetch limited metrics from YouTube Data API v3"""
        if not self.data_service:
            return {
                'views': 0,
                'estimatedMinutesWatched': 0,
                'averageViewDuration': 0,
                'impressions': 0,
                'subscribersGained': 0,
                'subscribersLost': 0,
                'shares': 0,
                'netSubscribers': 0,
            }
        
        try:
            # Wrap synchronous execute() call in executor to prevent blocking
            loop = asyncio.get_event_loop()
            channel_response = await loop.run_in_executor(
                None,
                lambda: self.data_service.channels().list(
                    part='statistics',
                    id=channel_id
                ).execute()
            )
            
            # Note: Data API v3 doesn't provide period-specific analytics
            # This is a limitation - Analytics API with OAuth2 is required for accurate period data
            stats = channel_response.get('items', [{}])[0].get('statistics', {})
            
            return {
                'views': int(stats.get('viewCount', 0)),
                'estimatedMinutesWatched': 0,  # Not available in Data API
                'averageViewDuration': 0,  # Not available in Data API
                'impressions': 0,  # Not available in Data API
                'subscribersGained': 0,  # Not available in Data API
                'subscribersLost': 0,  # Not available in Data API
                'shares': 0,  # Not available in Data API
                'netSubscribers': 0,
            }
        except Exception as e:
            logger.error(f"Error fetching Data API metrics: {e}")
            return {
                'views': 0,
                'estimatedMinutesWatched': 0,
                'averageViewDuration': 0,
                'impressions': 0,
                'subscribersGained': 0,
                'subscribersLost': 0,
                'shares': 0,
                'netSubscribers': 0,
            }
    
    async def _fetch_video_metrics(self, channel_id: str, start_date: str, end_date: str) -> Optional[Dict]:
        """Fetch video list and calculate average video duration and top video metrics"""
        if not self.data_service:
            return None
        
        try:
            # Get uploads playlist ID
            loop = asyncio.get_event_loop()
            channel_response = await loop.run_in_executor(
                None,
                lambda: self.data_service.channels().list(
                    part='contentDetails',
                    id=channel_id
                ).execute()
            )
            
            uploads_playlist_id = channel_response.get('items', [{}])[0].get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads')
            if not uploads_playlist_id:
                return None
            
            # Get videos from uploads playlist
            videos = []
            next_page_token = None
            
            while True:
                playlist_response = await loop.run_in_executor(
                    None,
                    lambda: self.data_service.playlistItems().list(
                        part='contentDetails,snippet',
                        playlistId=uploads_playlist_id,
                        maxResults=50,
                        pageToken=next_page_token
                    ).execute()
                )
                
                video_ids = [item['contentDetails']['videoId'] for item in playlist_response.get('items', [])]
                if not video_ids:
                    break
                
                # Get video details
                videos_response = await loop.run_in_executor(
                    None,
                    lambda: self.data_service.videos().list(
                        part='contentDetails,statistics,snippet',
                        id=','.join(video_ids)
                    ).execute()
                )
                
                for video in videos_response.get('items', []):
                    video_date = datetime.fromisoformat(video['snippet']['publishedAt'].replace('Z', '+00:00'))
                    video_date_jst = video_date.astimezone(JST)
                    video_date_str = self._format_date_for_api(video_date_jst)
                    
                    if start_date <= video_date_str <= end_date:
                        duration_str = video['contentDetails']['duration']
                        duration_seconds = self._parse_duration(duration_str)
                        
                        videos.append({
                            'videoId': video['id'],
                            'title': video['snippet']['title'],
                            'duration': duration_seconds,
                            'views': int(video['statistics'].get('viewCount', 0)),
                            'subscribersGained': 0,  # Not available in Data API v3
                        })
                
                next_page_token = playlist_response.get('nextPageToken')
                if not next_page_token:
                    break
            
            if not videos:
                return None
            
            # Calculate average video duration
            total_duration = sum(v['duration'] for v in videos)
            avg_duration = total_duration / len(videos) if videos else 0
            
            # Find top video by views
            top_video = max(videos, key=lambda v: v['views'], default=None)
            
            return {
                'averageVideoDuration': avg_duration,
                'topVideoViews': top_video['views'] if top_video else 0,
                'topVideoSubscribersGained': 0,  # Not available in Data API v3
            }
        except Exception as e:
            logger.error(f"Error fetching video metrics: {e}")
            return None
    
    def _parse_duration(self, duration_str: str) -> float:
        """Parse ISO 8601 duration string to seconds"""
        import re
        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)
        if not match:
            return 0
        
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        
        return hours * 3600 + minutes * 60 + seconds
    
    async def _fetch_daily_data(self, channel_id: str, start_date: str, end_date: str, period: str) -> List[Dict]:
        """Fetch daily data for trend charts"""
        try:
            if self.analytics_service:
                # Use Analytics API - include shares for PCQ calculation
                loop = asyncio.get_event_loop()
                query = await loop.run_in_executor(
                    None,
                    lambda: self.analytics_service.reports().query(
                        ids=f'channel=={channel_id}',
                        startDate=start_date,
                        endDate=end_date,
                        metrics='views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost,shares',
                        dimensions='day'
                    ).execute()
                )
                
                daily_data = []
                rows = query.get('rows', [])
                if not rows:
                    logger.warning(f"No daily data returned from YouTube Analytics API for period {start_date} to {end_date}")
                    return []
                
                dates_found = []
                for row in rows:
                    if len(row) < 7:
                        logger.warning(f"Invalid row format in daily data: {row}")
                        continue
                    date_str = str(row[0]) if row[0] else ""
                    dates_found.append(date_str)
                    daily_data.append({
                        'date': date_str,
                        'views': int(row[1] or 0),
                        'estimatedMinutesWatched': float(row[2] or 0),
                        'netSubscribers': int(row[4] or 0) - int(row[5] or 0),
                        'averageViewDuration': float(row[3] or 0),  # seconds
                        'subscribersGained': int(row[4] or 0),
                        'shares': int(row[6] or 0),
                    })
                
                # Sort by date in ascending order (oldest to newest)
                # This ensures the data is displayed correctly in chronological order
                daily_data.sort(key=lambda x: x['date'])
                
                if dates_found:
                    min_date = min(dates_found)
                    max_date = max(dates_found)
                    logger.info(f"Fetched {len(daily_data)} daily data points")
                    logger.info(f"  Requested date range: {start_date} to {end_date} (end_date is exclusive)")
                    logger.info(f"  Actual date range returned: {min_date} to {max_date}")
                    logger.info(f"  All dates returned: {sorted(set(dates_found))}")
                    
                    # Warn if the latest date is not today or yesterday
                    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
                    now_jst_local = now_utc.astimezone(JST)
                    today_str = now_jst_local.strftime('%Y-%m-%d')
                    yesterday_str = (now_jst_local - timedelta(days=1)).strftime('%Y-%m-%d')
                    if max_date < yesterday_str:
                        logger.warning(f"WARNING: Latest date in response ({max_date}) is older than yesterday ({yesterday_str}). "
                                     f"This may indicate data aggregation delay in YouTube Analytics API.")
                    elif max_date < today_str:
                        logger.info(f"Latest date in response ({max_date}) is yesterday. Today's data may not be fully aggregated yet.")
                else:
                    logger.info(f"Fetched {len(daily_data)} daily data points (sorted by date)")
                return daily_data
            else:
                # Fallback: Generate empty daily data
                logger.warning("Daily data not available without Analytics API")
                return []
        except HttpError as e:
            logger.error(f"YouTube Analytics API HttpError in daily data: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching daily data: {e}", exc_info=True)
            return []
    
    def _calculate_pcq(self, daily_data: List[Dict], average_video_duration: Optional[float]) -> List[Dict]:
        """
        Calculate Post-Click Quality Score (PCQ) for each day
        
        PCQ = 0.6 × normalized(averageViewPercentage)
            + 0.2 × normalized(subscribersGained)
            + 0.2 × normalized(shares)
        
        Args:
            daily_data: List of daily data points
            average_video_duration: Average video duration in seconds for the period
            
        Returns:
            List of daily data with postClickQualityScore added
        """
        if not daily_data or not average_video_duration or average_video_duration <= 0:
            # If no data or no video duration, set PCQ to None for all days
            for day in daily_data:
                day['postClickQualityScore'] = None
            return daily_data
        
        # Calculate averageViewPercentage for each day
        view_percentages = []
        subscribers_gained_list = []
        shares_list = []
        
        for day in daily_data:
            avg_view_duration = day.get('averageViewDuration', 0)
            view_percentage = (avg_view_duration / average_video_duration) * 100 if average_video_duration > 0 else 0
            view_percentages.append(view_percentage)
            subscribers_gained_list.append(day.get('subscribersGained', 0))
            shares_list.append(day.get('shares', 0))
        
        # Normalize each metric to 0-100 scale
        # Find min and max for normalization
        min_view_pct = min(view_percentages) if view_percentages else 0
        max_view_pct = max(view_percentages) if view_percentages else 100
        min_subscribers = min(subscribers_gained_list) if subscribers_gained_list else 0
        max_subscribers = max(subscribers_gained_list) if subscribers_gained_list else 1
        min_shares = min(shares_list) if shares_list else 0
        max_shares = max(shares_list) if shares_list else 1
        
        # Calculate normalized values and PCQ for each day
        for i, day in enumerate(daily_data):
            # Normalize averageViewPercentage (0-100)
            if max_view_pct > min_view_pct:
                normalized_view_pct = ((view_percentages[i] - min_view_pct) / (max_view_pct - min_view_pct)) * 100
            else:
                normalized_view_pct = 100 if view_percentages[i] > 0 else 0
            
            # Normalize subscribersGained (0-100)
            if max_subscribers > min_subscribers:
                normalized_subscribers = ((subscribers_gained_list[i] - min_subscribers) / (max_subscribers - min_subscribers)) * 100
            else:
                normalized_subscribers = 100 if subscribers_gained_list[i] > 0 else 0
            
            # Normalize shares (0-100)
            if max_shares > min_shares:
                normalized_shares = ((shares_list[i] - min_shares) / (max_shares - min_shares)) * 100
            else:
                normalized_shares = 100 if shares_list[i] > 0 else 0
            
            # Calculate PCQ
            pcq = (0.6 * normalized_view_pct) + (0.2 * normalized_subscribers) + (0.2 * normalized_shares)
            day['postClickQualityScore'] = round(pcq, 2)
        
        return daily_data


# Singleton instance
youtube_api_service = YouTubeAPIService()

