"""
X (Twitter) API Service using tweepy
Handles data fetching from X API v2
"""
import tweepy
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import re
import logging
import unicodedata
import asyncio
from cachetools import TTLCache

from app.core.config import settings
from app.schemas.x_analytics import (
    XAnalyticsData,
    EngagementTrendItem,
    HashtagAnalysis,
    HashtagDataItem,
)

logger = logging.getLogger(__name__)

# Japan Standard Time (UTC+9) - all analytics are based on Tokyo time
JST = timezone(timedelta(hours=9))


# Cache for API responses (DISABLED for strict real-time consistency)
# NOTE: We keep the object for future use, but do not read from it anymore.
analytics_cache: TTLCache = TTLCache(maxsize=100, ttl=300)


class XAPIService:
    """Service for interacting with X (Twitter) API"""
    
    def __init__(self):
        self.client: Optional[tweepy.Client] = None
        self.api: Optional[tweepy.API] = None
        self.user_id: Optional[str] = None
        self.followers_count_cache: Optional[int] = None
        self.followers_count_cache_time: Optional[datetime] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize tweepy clients with credentials"""
        try:
            # OAuth 2.0 Bearer Token for read-only access
            self.client = tweepy.Client(
                bearer_token=settings.X_BEARER_TOKEN,
                consumer_key=settings.X_API_KEY,
                consumer_secret=settings.X_API_KEY_SECRET,
                access_token=settings.X_ACCESS_TOKEN,
                access_token_secret=settings.X_ACCESS_TOKEN_SECRET,
                # Disable automatic rate limit waiting to prevent infinite retries
                # We'll handle rate limits explicitly in the API call
                wait_on_rate_limit=False,
            )
            
            # OAuth 1.0a for user context
            auth = tweepy.OAuth1UserHandler(
                settings.X_API_KEY,
                settings.X_API_KEY_SECRET,
                settings.X_ACCESS_TOKEN,
                settings.X_ACCESS_TOKEN_SECRET,
            )
            self.api = tweepy.API(auth, wait_on_rate_limit=False)
            
            logger.info("X API client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize X API client: {e}")
            raise
    
    def _get_user_id(self) -> str:
        """Get the user ID for the configured username"""
        if self.user_id:
            return self.user_id
        
        try:
            user = self.client.get_user(username=settings.X_USERNAME)
            if user.data:
                self.user_id = user.data.id
                return self.user_id
            raise ValueError(f"User {settings.X_USERNAME} not found")
        except Exception as e:
            logger.error(f"Failed to get user ID: {e}")
            raise
    
    def _get_time_range(self, period: str) -> Tuple[datetime, datetime]:
        """
        Calculate time range based on period in **Tokyo time (JST)**.

        NOTE:
        - We anchor to current UTC time and then convert to JST explicitly.
          This avoids any ambiguity from OS/local timezone settings.
        """
        now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
        now_jst = now_utc.astimezone(JST)

        if period == "2hours":
            start_jst = now_jst - timedelta(hours=2)
        elif period == "1day":
            start_jst = now_jst - timedelta(days=1)
        elif period == "1week":
            start_jst = now_jst - timedelta(weeks=1)
        elif period == "1month":
            start_jst = now_jst - timedelta(days=30)
        else:
            start_jst = now_jst - timedelta(days=1)  # Default to 1 day

        return start_jst, now_jst
    
    def _extract_hashtags(self, text: str) -> List[str]:
        """Extract hashtags from tweet text"""
        return re.findall(r'#(\w+)', text)
    
    def _normalize_hashtag(self, tag: str) -> str:
        """Normalize hashtag for consistent comparison"""
        # Unicode NFC normalization for Japanese characters
        normalized = unicodedata.normalize("NFC", tag)
        # Remove variation selectors and invisible characters
        normalized = ''.join(c for c in normalized if not unicodedata.category(c).startswith('M'))
        return normalized.strip()
    
    def _generate_time_labels(self, period: str, count: int, start_time: datetime) -> List[str]:
        """
        Generate time labels for trend data.

        IMPORTANT:
        - Labels are aligned with the same time buckets used in `_calculate_engagement_trend`
        - This guarantees consistency between bucketed values and displayed timestamps
        """
        labels: List[str] = []

        if period == "2hours":
            bucket_minutes = 10   # 10分刻み × 12 = 2時間
            fmt = "%H:%M"
        elif period == "1day":
            bucket_minutes = 60   # 1時間刻み × 24 = 24時間
            fmt = "%H:%M"
        elif period == "1week":
            bucket_minutes = 60 * 24  # 1日刻み × 7
            fmt = "%m/%d"
        else:  # 1month
            bucket_minutes = 60 * 24  # 1日刻み × 30
            fmt = "%m/%d"

        for i in range(count):
            time_point = start_time + timedelta(minutes=bucket_minutes * i)
            labels.append(time_point.strftime(fmt))

        return labels
    
    async def get_analytics(self, period: str) -> XAnalyticsData:
        """
        Fetch analytics data from X API
        
        Args:
            period: Time period - "2hours", "1day", "1week", or "1month"
            
        Returns:
            XAnalyticsData with all metrics
        """
        # Track API calls for debugging
        api_call_count = 0
        
        try:
            # Get user ID (with async wrapper if needed)
            if self.user_id:
                user_id = self.user_id
                logger.debug("Using cached user_id, no API call needed")
            else:
                # Wrap synchronous API call in executor
                loop = asyncio.get_event_loop()
                logger.info("Fetching user ID from X API...")
                user = await loop.run_in_executor(
                    None,
                    lambda: self.client.get_user(username=settings.X_USERNAME)
                )
                api_call_count += 1
                logger.info(f"API call #{api_call_count}: get_user (username lookup)")
                if user.data:
                    self.user_id = user.data.id
                    user_id = self.user_id
                else:
                    raise ValueError(f"User {settings.X_USERNAME} not found")
            
            # Time range in JST (for analytics & labels)
            start_jst, end_jst = self._get_time_range(period)

            # Convert to UTC for X API (RFC3339, Z suffix)
            start_utc = start_jst.astimezone(timezone.utc)
            end_utc = end_jst.astimezone(timezone.utc)

            start_time_str = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_time_str = end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            # Fetch user's tweets with metrics
            # NOTE: wait_on_rate_limit=False to prevent infinite retries
            try:
                # Wrap synchronous API call in executor to prevent blocking
                loop = asyncio.get_event_loop()
                logger.info(f"Fetching tweets from X API for period {period}...")
                
                # Call API without automatic rate limit waiting
                # Rate limits will be handled explicitly by raising TooManyRequests exception
                tweets_response = await loop.run_in_executor(
                    None,
                    lambda: self.client.get_users_tweets(
                        id=user_id,
                        start_time=start_time_str,
                        end_time=end_time_str,
                        max_results=100,
                        tweet_fields=["public_metrics", "created_at", "entities", "referenced_tweets"],
                        expansions=["author_id"],
                    )
                )
                api_call_count += 1
                logger.info(f"API call #{api_call_count}: get_users_tweets (period: {period})")
                    
            except tweepy.TooManyRequests as e:
                # Rate limit hit - extract reset time and re-raise to be handled by caller
                logger.error(f"Rate limit exceeded while fetching tweets for period {period}: {e}")
                
                # Extract reset time from error if available
                reset_time = None
                if hasattr(e, 'response') and e.response is not None:
                    headers = e.response.headers if hasattr(e.response, 'headers') else {}
                    reset_time_str = headers.get('x-rate-limit-reset', headers.get('X-Rate-Limit-Reset'))
                    if reset_time_str:
                        try:
                            reset_time = int(reset_time_str)
                        except (ValueError, TypeError):
                            pass
                
                # Re-raise with reset time information
                raise
            except Exception as e:
                # Other API errors
                logger.error(f"Error fetching tweets from X API for period {period}: {e}")
                raise
            
            # Initialize counters
            total_likes = 0
            total_retweets = 0
            total_replies = 0
            total_impressions = 0
            hashtag_stats: Dict[str, int] = defaultdict(int)
            hashtag_timeline: Dict[str, List[Tuple[datetime, int]]] = defaultdict(list)
            hashtag_display_names: Dict[str, str] = {}  # normalized -> original display name
            
            # Process tweets
            tweets = tweets_response.data or []
            logger.info(f"Processing {len(tweets)} tweets for period {period}")
            
            # Check if we got empty response (possible rate limit or no tweets)
            if not tweets:
                logger.warning(f"No tweets found for period {period}. This might indicate rate limiting or no tweets in the period.")
                # Still return valid structure with zeros, but log the issue
                # The frontend should handle this appropriately
            
            # Track statistics for validation
            tweets_in_period_count = 0
            tweets_before_period_count = 0
            retweets_of_others_count = 0  # Count of retweets of other users' tweets (excluded from retweet_count)
            retweet_details: List[Dict[str, any]] = []  # For detailed logging
            
            for tweet in tweets:
                metrics = tweet.public_metrics or {}

                # Convert tweet timestamp to JST for consistent bucketing
                created_at = tweet.created_at
                if created_at is None:
                    continue
                if created_at.tzinfo is None:
                    # Treat naive datetime as UTC, then convert to JST
                    created_at_utc = created_at.replace(tzinfo=timezone.utc)
                else:
                    created_at_utc = created_at.astimezone(timezone.utc)
                created_at_jst = created_at_utc.astimezone(JST)

                # IMPORTANT: X API's retweet_count is cumulative (total since tweet creation)
                # To get period-specific retweets, we only count retweets for tweets
                # that were created within the period. For tweets created before the period,
                # we cannot accurately calculate period-specific retweets without historical data.
                # 
                # Strategy: Only count retweets for tweets created within the period
                # This ensures we're showing actual retweets that happened during the period
                # (for new tweets) rather than cumulative totals from older tweets.
                
                retweet_count = metrics.get("retweet_count", 0)
                like_count = metrics.get("like_count", 0)
                reply_count = metrics.get("reply_count", 0)
                impression_count = metrics.get("impression_count", 0)
                
                # Check if this tweet is a retweet of another user's tweet
                # If it is, the retweet_count refers to the original tweet's count, not the user's own tweet
                is_retweet_of_other = False
                if hasattr(tweet, 'referenced_tweets') and tweet.referenced_tweets:
                    for ref in tweet.referenced_tweets:
                        if ref.type == "retweeted":
                            is_retweet_of_other = True
                            break
                
                # Only count retweets if tweet was created within the period AND is not a retweet of another user's tweet
                # This prevents counting:
                # 1. Cumulative retweets from older tweets
                # 2. Retweet counts from original tweets when the user retweeted them
                if created_at_jst >= start_jst and not is_retweet_of_other:
                    # Tweet created within period and is original (not a retweet): count all retweets (they all happened in period)
                    tweets_in_period_count += 1
                    total_retweets += retweet_count
                    retweet_details.append({
                        "tweet_id": str(tweet.id),
                        "created_at": created_at_jst.strftime("%Y-%m-%d %H:%M:%S"),
                        "retweets": retweet_count,
                        "likes": like_count,
                        "is_retweet": is_retweet_of_other
                    })
                    logger.debug(
                        f"Tweet {tweet.id}: created within period ({created_at_jst}), "
                        f"counting retweets={retweet_count}, likes={like_count}, is_retweet={is_retweet_of_other}"
                    )
                elif created_at_jst >= start_jst and is_retweet_of_other:
                    # Tweet created within period but is a retweet of another user's tweet
                    # Skip retweet_count as it refers to the original tweet, not the user's own tweet
                    tweets_in_period_count += 1
                    retweets_of_others_count += 1
                    logger.debug(
                        f"Tweet {tweet.id}: created within period ({created_at_jst}) but is retweet of other user's tweet, "
                        f"skipping retweet_count={retweet_count} (refers to original tweet), likes={like_count}"
                    )
                else:
                    # Tweet created before period: cannot accurately calculate period-specific retweets
                    # Skip retweets to avoid inflating the count with cumulative values
                    tweets_before_period_count += 1
                    logger.debug(
                        f"Tweet {tweet.id}: created before period ({created_at_jst} < {start_jst}), "
                        f"skipping retweets (cumulative={retweet_count})"
                    )
                    # Note: We still count likes/replies/impressions as they might be more recent
                    # But retweets are more likely to be cumulative and misleading
                
                # Always count likes, replies, and impressions (they're less likely to be misleading)
                total_likes += like_count
                total_replies += reply_count
                total_impressions += impression_count
                
                # Extract hashtags from entities
                if tweet.entities and "hashtags" in tweet.entities:
                    for ht in tweet.entities["hashtags"]:
                        original_tag = ht["tag"]
                        normalized_tag = self._normalize_hashtag(original_tag)
                        
                        # Store the first occurrence as the display name
                        if normalized_tag not in hashtag_display_names:
                            hashtag_display_names[normalized_tag] = original_tag
                        
                        like_count = metrics.get("like_count", 0)
                        hashtag_stats[normalized_tag] += like_count
                        # Store JST timestamps for hashtag timelines as well
                        hashtag_timeline[normalized_tag].append(
                            (created_at_jst, like_count)
                        )
                        
                        logger.debug(f"Hashtag found: #{original_tag} (normalized: {normalized_tag}) - {like_count} likes")
            
            # Get user info for follower count
            # OPTIMIZATION: Cache followers count for 5 minutes to reduce API calls
            # This reduces API calls from 2 per request to 1 per request (after first call)
            now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
            cache_valid = (
                self.followers_count_cache is not None and
                self.followers_count_cache_time is not None and
                (now_utc - self.followers_count_cache_time).total_seconds() < 300  # 5 minutes cache
            )
            
            if cache_valid:
                followers_count = self.followers_count_cache
                logger.debug(f"Using cached followers count: {followers_count} (no API call needed)")
            else:
                # Fetch fresh followers count
                loop = asyncio.get_event_loop()
                logger.info("Fetching followers count from X API...")
                try:
                    user_response = await loop.run_in_executor(
                        None,
                        lambda: self.client.get_user(
                            id=user_id,
                            user_fields=["public_metrics"],
                        )
                    )
                    api_call_count += 1
                    logger.info(f"API call #{api_call_count}: get_user (followers count)")
                    
                    followers_count = 0
                    if user_response.data:
                        followers_count = user_response.data.public_metrics.get("followers_count", 0)
                    
                    # Cache the result
                    self.followers_count_cache = followers_count
                    self.followers_count_cache_time = now_utc
                    logger.info(f"Fetched and cached followers count: {followers_count}")
                except tweepy.TooManyRequests as e:
                    # If rate limited, use cached value if available, otherwise use 0
                    if self.followers_count_cache is not None:
                        followers_count = self.followers_count_cache
                        logger.warning(f"Rate limited while fetching followers count, using cached value: {followers_count}")
                    else:
                        followers_count = 0
                        logger.warning(f"Rate limited while fetching followers count, no cache available, using 0")
                except Exception as e:
                    # If other error, use cached value if available, otherwise use 0
                    if self.followers_count_cache is not None:
                        followers_count = self.followers_count_cache
                        logger.warning(f"Error fetching followers count ({e}), using cached value: {followers_count}")
                    else:
                        followers_count = 0
                        logger.warning(f"Error fetching followers count ({e}), no cache available, using 0")
            
            # Generate engagement trend
            data_points = 12 if period == "2hours" else (24 if period == "1day" else (7 if period == "1week" else 30))
            # Labels are generated from the same JST start_time and bucket size used for aggregation
            time_labels = self._generate_time_labels(period, data_points, start_jst)

            # Calculate engagement per time bucket (also in JST)
            engagement_trend = self._calculate_engagement_trend(
                tweets, period, time_labels, start_jst
            )
            
            # Build hashtag analysis (top 10 unique hashtags)
            sorted_hashtags = sorted(
                hashtag_stats.items(), key=lambda x: x[1], reverse=True
            )[:10]
            
            logger.info(f"Found {len(hashtag_stats)} unique hashtags, top {len(sorted_hashtags)}: {[hashtag_display_names.get(tag, tag) for tag, _ in sorted_hashtags]}")
            
            hashtag_analysis = []
            seen_display_names = set()  # Prevent duplicate display names
            
            for normalized_tag, likes in sorted_hashtags:
                # Get the original display name
                display_name = hashtag_display_names.get(normalized_tag, normalized_tag)
                
                # Skip if we've already added this display name
                if display_name in seen_display_names:
                    continue
                seen_display_names.add(display_name)
                
                hashtag_data = self._build_hashtag_timeline(
                    normalized_tag,
                    hashtag_timeline[normalized_tag],
                    time_labels,
                    period,
                    start_jst,
                )
                hashtag_analysis.append(
                    HashtagAnalysis(
                        tag=display_name,
                        likes=likes,
                        data=hashtag_data,
                    )
                )
            
            # If no hashtags found, add placeholder message
            if not hashtag_analysis:
                logger.warning("No hashtags found in tweets")
                hashtag_analysis.append(
                    HashtagAnalysis(
                        tag="データなし",
                        likes=0,
                        data=[HashtagDataItem(time=t, likes=0) for t in time_labels],
                    )
                )
            
            # Calculate statistics for validation
            original_tweets_count = tweets_in_period_count - retweets_of_others_count
            avg_retweets_per_tweet = total_retweets / original_tweets_count if original_tweets_count > 0 else 0
            max_retweets = max([d["retweets"] for d in retweet_details], default=0)
            min_retweets = min([d["retweets"] for d in retweet_details], default=0)
            
            # Log detailed summary for debugging and validation
            logger.info(
                f"Analytics summary for {period}: "
                f"total_api_calls={api_call_count}, "
                f"total_tweets_fetched={len(tweets)}, "
                f"tweets_in_period={tweets_in_period_count}, "
                f"original_tweets={original_tweets_count}, "
                f"retweets_of_others={retweets_of_others_count} (excluded from retweet_count), "
                f"tweets_before_period={tweets_before_period_count}, "
                f"likes={total_likes}, "
                f"retweets={total_retweets} (only from {original_tweets_count} original tweets created in period, excluding retweets of others), "
                f"avg_retweets_per_tweet={avg_retweets_per_tweet:.1f}, "
                f"max_retweets={max_retweets}, "
                f"min_retweets={min_retweets}, "
                f"replies={total_replies}, "
                f"impressions={total_impressions}, "
                f"time_range={start_jst.strftime('%Y-%m-%d %H:%M:%S JST')} to {end_jst.strftime('%Y-%m-%d %H:%M:%S JST')}"
            )
            
            # Log top retweeted tweets for validation (if any)
            if retweet_details:
                top_retweeted = sorted(retweet_details, key=lambda x: x["retweets"], reverse=True)[:5]
                logger.info(
                    f"Top 5 retweeted tweets in period: "
                    + ", ".join([f"Tweet {d['tweet_id'][:8]}...: {d['retweets']} RTs ({d['created_at']})" 
                                for d in top_retweeted])
                )
            
            # For 2hours period, if no tweets found, add a helpful message
            message = None
            if period == "2hours" and len(tweets) == 0:
                message = f"過去2時間（{start_jst.strftime('%H:%M')}〜{end_jst.strftime('%H:%M')}）の期間内にツイートが見つかりませんでした。"
            
            result = XAnalyticsData(
                likes_count=total_likes,
                retweets_count=total_retweets,
                replies_count=total_replies,
                impressions_count=total_impressions,
                followers_count=followers_count,
                engagement_trend=engagement_trend,
                hashtag_analysis=hashtag_analysis,
                is_cached=False,
                data_age_minutes=0,
                message=message,
            )
            
            return result
            
        except tweepy.TooManyRequests as e:
            logger.warning(f"Rate limited: {e}")
            raise
        except tweepy.TwitterServerError as e:
            logger.error(f"Twitter server error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching analytics: {e}")
            raise
    
    def _calculate_engagement_trend(
        self,
        tweets: List,
        period: str,
        time_labels: List[str],
        start_time: datetime,
    ) -> List[EngagementTrendItem]:
        """Calculate engagement trend over time buckets"""
        
        # Initialize buckets
        data_points = len(time_labels)
        engagement_buckets = [0] * data_points
        impression_buckets = [0] * data_points
        
        if period == "2hours":
            bucket_minutes = 10
        elif period == "1day":
            bucket_minutes = 60
        elif period == "1week":
            bucket_minutes = 60 * 24
        else:  # 1month
            bucket_minutes = 60 * 24
        
        for tweet in tweets:
            if not tweet.created_at:
                continue

            # Convert tweet timestamp to JST to align with start_time (also JST)
            created_at = tweet.created_at
            if created_at.tzinfo is None:
                created_at_utc = created_at.replace(tzinfo=timezone.utc)
            else:
                created_at_utc = created_at.astimezone(timezone.utc)
            created_at_jst = created_at_utc.astimezone(JST)

            # Calculate which bucket this tweet belongs to (in JST)
            time_diff = (created_at_jst - start_time).total_seconds()
            bucket_index = int(time_diff / (bucket_minutes * 60))
            
            if 0 <= bucket_index < data_points:
                metrics = tweet.public_metrics or {}
                engagement = (
                    metrics.get("like_count", 0) +
                    metrics.get("retweet_count", 0) +
                    metrics.get("reply_count", 0)
                )
                engagement_buckets[bucket_index] += engagement
                impression_buckets[bucket_index] += metrics.get("impression_count", 0)
        
        return [
            EngagementTrendItem(
                time=time_labels[i],
                engagement=engagement_buckets[i],
                impressions=impression_buckets[i],
            )
            for i in range(data_points)
        ]
    
    def _build_hashtag_timeline(
        self,
        tag: str,
        timeline_data: List[Tuple[datetime, int]],
        time_labels: List[str],
        period: str,
        start_time: datetime,
    ) -> List[HashtagDataItem]:
        """Build timeline data for a specific hashtag"""
        
        data_points = len(time_labels)
        likes_buckets = [0] * data_points
        
        if period == "2hours":
            bucket_minutes = 10
        elif period == "1day":
            bucket_minutes = 60
        elif period == "1week":
            bucket_minutes = 60 * 24
        else:  # 1month
            bucket_minutes = 60 * 24
        
        for created_at, likes in timeline_data:
            # created_at is already stored in JST with tzinfo; keep it aware
            time_diff = (created_at - start_time).total_seconds()
            bucket_index = int(time_diff / (bucket_minutes * 60))
            
            if 0 <= bucket_index < data_points:
                likes_buckets[bucket_index] += likes
        
        return [
            HashtagDataItem(time=time_labels[i], likes=likes_buckets[i])
            for i in range(data_points)
        ]


# Singleton instance
x_api_service = XAPIService()

