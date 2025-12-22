"""
Improvement Suggestion Service
Generates improvement suggestions based on analytics data.

Primary: uses OpenAI API (ChatGPT) to generate suggestions in Japanese.
Fallback: rule-based logic if OpenAI API is not configured or fails.
"""
from typing import List
from datetime import datetime
import json
import logging

from openai import OpenAI

from app.schemas.x_analytics import (
    XAnalyticsRequest,
    ImprovementSuggestion,
    HashtagAnalysis,
)
from app.schemas.youtube_analytics import (
    YouTubeAnalyticsRequest,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class ImprovementService:
    """Service for generating improvement suggestions based on analytics"""

    def __init__(self) -> None:
        # Initialize OpenAI client only if API key is provided
        self.client = None
        if settings.OPENAI_API_KEY:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate_suggestions(self, data: XAnalyticsRequest) -> ImprovementSuggestion:
        """
        Generate improvement suggestions based on analytics data.

        1. Try OpenAI API (if API key is set)
        2. If it fails or not configured, fall back to rule-based logic
        """
        if self.client:
            try:
                return self._generate_with_openai(data)
            except Exception as e:
                logger.error(f"OpenAIによる改善提案生成に失敗しました: {e}", exc_info=True)

        # Fallback: rule-based suggestions
        logger.info("OpenAIが無効なため、ルールベースの改善提案を使用します")
        return self._generate_rule_based(data)

    # ---------- OpenAI-based generation ----------

    def _generate_with_openai(self, data: XAnalyticsRequest) -> ImprovementSuggestion:
        """Use OpenAI (ChatGPT) to generate improvement suggestions in Japanese"""
        # Prepare compact numeric payload for the model
        analytics_payload = {
            "likes_count": data.likes_count,
            "retweets_count": data.retweets_count,
            "replies_count": data.replies_count,
            "impressions_count": data.impressions_count,
            "followers_count": data.followers_count,
            "period": data.period,
            "hashtags": [
                {
                    "tag": h.tag,
                    "likes": h.likes,
                }
                for h in data.hashtag_analysis
            ],
        }

        system_prompt = (
            "あなたは日本語で回答するSNS（X/Twitter）アナリティクスのプロコンサルタントです。\n"
            "役割は、与えられた定量データだけに基づいて、VTuberアカウントの運用改善提案を行うことです。\n"
            "必ず次の方針を厳密に守ってください：\n"
            "1. 数値データ（いいね数、リツイート数、返信数、インプレッション数、フォロワー数、フォロワー増減、ハッシュタグ別パフォーマンス）\n"
            "   から論理的に導ける範囲内でのみ結論を出すこと。推測や根拠のない断定はしないこと。\n"
            "2. 改善提案は、実際の運用でそのまま試せるレベルの具体性（頻度・時間帯・投稿フォーマットなど）を持たせること。\n"
            "3. 科学的・統計的な観点（エンゲージメント率、相対比較、期間内の増減など）を明示し、\n"
            "   「なぜその提案が有効と考えられるのか」を短くてもよいので数値と結びつけて説明すること。\n"
            "4. データに表れていない事実（ユーザー属性やプラットフォーム外の要因など）は断定しない。\n"
            "5. すべての出力は自然なビジネス日本語で書き、かつ過度な誇張表現は避けること。\n\n"
            "出力フォーマットは必ず次のJSONオブジェクト【のみ】とし、余計な文章・説明・コメントは一切出力しないこと：\n"
            "{\n"
            '  \"summary\": \"...\",                     // 全体のサマリー（1〜3文、日本語）\n'
            '  \"key_insights\": [\"...\", \"...\"],      // 数値に根拠を持つ主要インサイト 2〜4 個、日本語\n'
            '  \"recommendations\": [\"...\", \"...\"],   // 実行可能で具体的な改善アクション 3〜5 個、日本語\n'
            '  \"best_posting_time\": \"..\",             // 推奨投稿時間帯（例: \"20:00-22:00\"）\n'
            '  \"hashtag_recommendations\": [\"#..\", \"#..\"] // データと整合的な推奨ハッシュタグ 3〜5 個\n'
            "}"
        )

        user_content = (
            "以下は、VTuberアカウントのX分析データです。これを基に、"
            "フォロワー増加とエンゲージメント向上のための改善提案を作成してください。\n\n"
            f"{json.dumps(analytics_payload, ensure_ascii=False)}"
        )

        if not self.client:
            raise ValueError("OpenAI client is not initialized")

        model_name = settings.OPENAI_MODEL or "gpt-4o-mini"

        logger.info(f"Calling OpenAI model '{model_name}' for improvement suggestions")

        completion = self.client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
        )

        content = completion.choices[0].message.content

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"OpenAIレスポンスのJSONパースに失敗しました: {e}. content={content}")
            raise

        # Validate and map to Pydantic model
        suggestion = ImprovementSuggestion(
            summary=parsed.get("summary", ""),
            key_insights=parsed.get("key_insights", [])[:4],
            recommendations=parsed.get("recommendations", [])[:5],
            best_posting_time=parsed.get("best_posting_time", ""),
            hashtag_recommendations=parsed.get("hashtag_recommendations", [])[:5],
        )

        return suggestion

    # ---------- Rule-based fallback (existing logic) ----------

    def _generate_rule_based(self, data: XAnalyticsRequest) -> ImprovementSuggestion:
        """Existing rule-based logic used as a fallback"""
        # Calculate engagement metrics
        total_engagement = data.likes_count + data.retweets_count + data.replies_count
        engagement_rate = (
            (total_engagement / data.impressions_count * 100)
            if data.impressions_count > 0
            else 0
        )

        # Analyze hashtag performance
        top_hashtags = sorted(
            data.hashtag_analysis, key=lambda x: x.likes, reverse=True
        )[:3]
        top_hashtag_names = [f"#{h.tag}" for h in top_hashtags] if top_hashtags else ["#VTuber"]

        # Generate period-specific label
        period_labels = {
            "2hours": "過去2時間",
            "1day": "過去1日",
            "1week": "過去1週間",
        }
        period_label = period_labels.get(data.period, "分析期間")

        # Generate summary
        summary = self._generate_summary(data, total_engagement, engagement_rate, period_label)

        # Generate key insights
        key_insights = self._generate_key_insights(
            data, engagement_rate, top_hashtags
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            data, engagement_rate, top_hashtags
        )

        # Determine best posting time
        best_posting_time = self._determine_best_posting_time(data)

        # Generate hashtag recommendations
        hashtag_recommendations = self._generate_hashtag_recommendations(top_hashtag_names)

        return ImprovementSuggestion(
            summary=summary,
            key_insights=key_insights,
            recommendations=recommendations,
            best_posting_time=best_posting_time,
            hashtag_recommendations=hashtag_recommendations,
        )
    
    def _generate_summary(
        self,
        data: XAnalyticsRequest,
        total_engagement: int,
        engagement_rate: float,
        period_label: str,
    ) -> str:
        """Generate summary text"""
        return (
            f"{period_label}中、インプレッション数{data.impressions_count:,}、"
            f"エンゲージメント数{total_engagement:,}を記録しました。"
            f"エンゲージメント率は{engagement_rate:.2f}%です。"
        )
    
    def _generate_key_insights(
        self,
        data: XAnalyticsRequest,
        engagement_rate: float,
        top_hashtags: List[HashtagAnalysis],
    ) -> List[str]:
        """Generate key insights based on data analysis"""
        insights = []
        
        # Engagement rate insight
        if engagement_rate >= 3.0:
            insights.append("エンゲージメント率は業界平均（1-3%）を上回る優秀な数値です")
        elif engagement_rate >= 1.0:
            insights.append("エンゲージメント率は業界平均の範囲内です")
        else:
            insights.append("エンゲージメント率の向上余地があります")
        
        # Likes vs Retweets ratio
        if data.likes_count > 0:
            rt_ratio = data.retweets_count / data.likes_count
            if rt_ratio > 0.3:
                insights.append("リツイート率が高く、シェアされやすいコンテンツを作成できています")
            else:
                insights.append("いいねは多いですが、リツイートを促進する余地があります")
        
        # Reply engagement
        if data.replies_count > 0 and data.likes_count > 0:
            reply_ratio = data.replies_count / data.likes_count
            if reply_ratio > 0.1:
                insights.append("フォロワーとの対話が活発で、コミュニティ形成が進んでいます")
        
        # Top hashtag insight
        if top_hashtags:
            top_tag = top_hashtags[0]
            insights.append(
                f"#{top_tag.tag}を使用した投稿が最も高いパフォーマンス（{top_tag.likes}いいね）を記録しています"
            )
        
        return insights[:4]  # Return max 4 insights
    
    def _generate_recommendations(
        self,
        data: XAnalyticsRequest,
        engagement_rate: float,
        top_hashtags: List[HashtagAnalysis],
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Low engagement recommendations
        if engagement_rate < 2.0:
            recommendations.append(
                "画像や動画付きツイートの割合を増やすことで、エンゲージメント率の向上が期待できます"
            )
        
        # Retweet improvement
        if data.likes_count > 0 and (data.retweets_count / data.likes_count) < 0.2:
            recommendations.append(
                "リツイートを促進するため、共感を呼ぶコンテンツや有益な情報の共有を心がけてください"
            )
        
        # Reply/interaction improvement
        if data.replies_count < data.likes_count * 0.05:
            recommendations.append(
                "フォロワーとの対話を増やすため、質問形式の投稿を週2-3回取り入れてください"
            )
        
        # Content consistency
        recommendations.append(
            "投稿の一貫性を保つため、毎日決まった時間に投稿するスケジュールを作成してください"
        )
        
        # Hashtag strategy
        if top_hashtags:
            recommendations.append(
                f"パフォーマンスの高い#{top_hashtags[0].tag}と関連性の高いハッシュタグを組み合わせて使用してください"
            )
        
        return recommendations[:4]  # Return max 4 recommendations
    
    def _determine_best_posting_time(self, data: XAnalyticsRequest) -> str:
        """Determine best posting time based on engagement patterns"""
        # For VTuber/streamer accounts, evening hours are typically best
        # This would be more accurate with actual timestamp analysis
        
        current_hour = datetime.now().hour
        
        # Japanese audience typical peak times
        if current_hour >= 20 or current_hour < 2:
            return "20:00-24:00"
        elif current_hour >= 12 and current_hour < 14:
            return "12:00-14:00"
        else:
            return "20:00-22:00"
    
    def _generate_hashtag_recommendations(
        self, top_hashtag_names: List[str]
    ) -> List[str]:
        """Generate hashtag recommendations"""
        base_recommendations = []
        
        # Add top performing hashtags
        base_recommendations.extend(top_hashtag_names[:2])
        
        # Add VTuber-specific recommendations
        vtuber_hashtags = [
            "#新人VTuber",
            "#Vtuber好きと繋がりたい",
            "#VTuber",
            "#配信者",
            "#ゲーム配信",
            "#歌ってみた",
        ]
        
        for tag in vtuber_hashtags:
            if tag not in base_recommendations:
                base_recommendations.append(tag)
            if len(base_recommendations) >= 5:
                break
        
        return base_recommendations[:5]

    # ---------- YouTube Analytics Improvement Suggestions ----------

    def generate_youtube_suggestions(self, data: YouTubeAnalyticsRequest) -> ImprovementSuggestion:
        """
        Generate improvement suggestions based on YouTube analytics data.

        1. Try OpenAI API (if API key is set)
        2. If it fails or not configured, fall back to rule-based logic
        """
        if settings.OPENAI_API_KEY:
            try:
                return self._generate_youtube_with_openai(data)
            except Exception as e:
                logger.error(f"OpenAIによるYouTube改善提案生成に失敗しました: {e}", exc_info=True)

        # Fallback: rule-based suggestions
        logger.info("OpenAIが無効なため、ルールベースのYouTube改善提案を使用します")
        return self._generate_youtube_rule_based(data)

    def _generate_youtube_with_openai(self, data: YouTubeAnalyticsRequest) -> ImprovementSuggestion:
        """Use OpenAI (ChatGPT) to generate YouTube improvement suggestions in Japanese"""
        # Calculate derived metrics
        net_subscribers = data.subscribersGained - data.subscribersLost
        previous_net_subscribers = data.previousPeriodNetSubscribers or 0
        
        # Calculate percentage changes
        views_change = 0
        if data.previousPeriodViews and data.previousPeriodViews > 0:
            views_change = ((data.views - data.previousPeriodViews) / data.previousPeriodViews) * 100
        
        retention_change = 0
        if data.previousPeriodViewerRetentionRate and data.previousPeriodViewerRetentionRate > 0:
            retention_change = ((data.viewerRetentionRate or 0) - data.previousPeriodViewerRetentionRate) / data.previousPeriodViewerRetentionRate * 100
        
        # Prepare analytics payload
        analytics_payload = {
            "views": data.views,
            "estimatedMinutesWatched": round(data.estimatedMinutesWatched, 2),
            "averageViewDuration": round(data.averageViewDuration, 2),
            "subscribersGained": data.subscribersGained,
            "subscribersLost": data.subscribersLost,
            "netSubscribers": net_subscribers,
            "viewerRetentionRate": round(data.viewerRetentionRate, 2) if data.viewerRetentionRate else None,
            "averageVideoDuration": round(data.averageVideoDuration, 2) if data.averageVideoDuration else None,
            "previousPeriodViews": data.previousPeriodViews,
            "previousPeriodEstimatedMinutesWatched": round(data.previousPeriodEstimatedMinutesWatched, 2) if data.previousPeriodEstimatedMinutesWatched else None,
            "previousPeriodAverageViewDuration": round(data.previousPeriodAverageViewDuration, 2) if data.previousPeriodAverageViewDuration else None,
            "previousPeriodViewerRetentionRate": round(data.previousPeriodViewerRetentionRate, 2) if data.previousPeriodViewerRetentionRate else None,
            "previousPeriodNetSubscribers": previous_net_subscribers,
            "viewsChangePercent": round(views_change, 2),
            "retentionChangePercent": round(retention_change, 2),
            "dailyDataCount": len(data.dailyData) if data.dailyData else 0,
        }

        system_prompt = (
            "あなたは日本語で回答するYouTubeアナリティクスのプロコンサルタントです。\n"
            "役割は、与えられた定量データだけに基づいて、VTuberチャンネルの運用改善提案を行うことです。\n"
            "必ず次の方針を厳密に守ってください：\n"
            "1. 数値データ（再生回数、総再生時間、平均視聴時間、視聴継続率、登録者増減、前期間比較など）\n"
            "   から論理的に導ける範囲内でのみ結論を出すこと。推測や根拠のない断定はしないこと。\n"
            "2. 改善提案は、実際の運用でそのまま試せるレベルの具体性（動画の長さ・頻度・時間帯・サムネイル・タイトル・構成など）を持たせること。\n"
            "3. 科学的・統計的な観点（視聴継続率、前期間比較、再生時間あたりの再生回数など）を明示し、\n"
            "   「なぜその提案が有効と考えられるのか」を短くてもよいので数値と結びつけて説明すること。\n"
            "4. データに表れていない事実（視聴者の属性やプラットフォーム外の要因など）は断定しない。\n"
            "5. すべての出力は自然なビジネス日本語で書き、かつ過度な誇張表現は避けること。\n"
            "6. 実用性、誠実性、具体性を保証すること。\n\n"
            "出力フォーマットは必ず次のJSONオブジェクト【のみ】とし、余計な文章・説明・コメントは一切出力しないこと：\n"
            "{\n"
            '  \"summary\": \"...\",                     // 全体のサマリー（2〜4文、日本語）\n'
            '  \"key_insights\": [\"...\", \"...\"],      // 数値に根拠を持つ主要インサイト 3〜5 個、日本語\n'
            '  \"recommendations\": [\"...\", \"...\"],   // 実行可能で具体的な改善アクション 4〜6 個、日本語\n'
            '  \"best_posting_time\": \"..\",             // 推奨投稿時間帯（例: \"20:00-22:00\"、YouTubeには適用しない場合は空文字列）\n'
            '  \"hashtag_recommendations\": [\"#..\", \"#..\"] // データと整合的な推奨ハッシュタグ 3〜5 個（YouTubeには適用しない場合は空配列）\n'
            "}"
        )

        user_content = (
            "以下は、VTuberチャンネルのYouTube分析データです。これを基に、"
            "再生回数・視聴継続率・登録者増加の向上のための改善提案を作成してください。\n\n"
            f"{json.dumps(analytics_payload, ensure_ascii=False, indent=2)}"
        )

        if not self.client:
            raise ValueError("OpenAI client is not initialized")

        model_name = settings.OPENAI_MODEL or "gpt-4o-mini"

        logger.info(f"Calling OpenAI model '{model_name}' for YouTube improvement suggestions")

        completion = self.client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
        )

        content = completion.choices[0].message.content

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"OpenAIレスポンスのJSONパースに失敗しました: {e}. content={content}")
            raise

        # Validate and map to Pydantic model
        suggestion = ImprovementSuggestion(
            summary=parsed.get("summary", ""),
            key_insights=parsed.get("key_insights", [])[:5],
            recommendations=parsed.get("recommendations", [])[:6],
            best_posting_time=parsed.get("best_posting_time", ""),
            hashtag_recommendations=parsed.get("hashtag_recommendations", [])[:5],
        )

        return suggestion

    def _generate_youtube_rule_based(self, data: YouTubeAnalyticsRequest) -> ImprovementSuggestion:
        """Rule-based YouTube improvement suggestions as fallback"""
        net_subscribers = data.subscribersGained - data.subscribersLost
        previous_net_subscribers = data.previousPeriodNetSubscribers or 0
        
        # Calculate metrics
        views_change = 0
        if data.previousPeriodViews and data.previousPeriodViews > 0:
            views_change = ((data.views - data.previousPeriodViews) / data.previousPeriodViews) * 100
        
        avg_watch_time_per_view = (data.estimatedMinutesWatched * 60) / data.views if data.views > 0 else 0
        
        # Generate summary
        summary = (
            f"過去1週間で再生回数{data.views:,}回、総再生時間{data.estimatedMinutesWatched:.1f}分を記録しました。"
        )
        if data.viewerRetentionRate:
            summary += f"視聴継続率は{data.viewerRetentionRate:.1f}%です。"
        if net_subscribers != 0:
            summary += f"純増登録者数は{net_subscribers:+,}人です。"
        
        # Generate key insights
        insights = []
        if views_change > 0:
            insights.append(f"再生回数が前期間比{views_change:.1f}%増加しています")
        elif views_change < 0:
            insights.append(f"再生回数が前期間比{abs(views_change):.1f}%減少しています")
        
        if data.viewerRetentionRate:
            if data.viewerRetentionRate >= 50:
                insights.append(f"視聴継続率{data.viewerRetentionRate:.1f}%は良好な数値です")
            elif data.viewerRetentionRate >= 30:
                insights.append(f"視聴継続率{data.viewerRetentionRate:.1f}%は平均的な数値です")
            else:
                insights.append(f"視聴継続率{data.viewerRetentionRate:.1f}%の向上余地があります")
        
        if data.averageVideoDuration and avg_watch_time_per_view > 0:
            watch_ratio = (avg_watch_time_per_view / data.averageVideoDuration) * 100
            if watch_ratio >= 60:
                insights.append(f"平均視聴時間は動画長の{watch_ratio:.1f}%で、視聴者の関心が高いです")
            else:
                insights.append(f"平均視聴時間は動画長の{watch_ratio:.1f}%で、冒頭の引き付けを強化する余地があります")
        
        if net_subscribers > previous_net_subscribers:
            insights.append(f"登録者数が{net_subscribers - previous_net_subscribers:+,}人増加しています")
        
        # Generate recommendations
        recommendations = []
        
        if data.viewerRetentionRate and data.viewerRetentionRate < 40:
            recommendations.append(
                "視聴継続率を向上させるため、動画の冒頭30秒で視聴者の興味を引く構成（質問、驚き、予告など）を取り入れてください"
            )
        
        if avg_watch_time_per_view > 0 and data.averageVideoDuration:
            watch_ratio = (avg_watch_time_per_view / data.averageVideoDuration) * 100
            if watch_ratio < 50:
                recommendations.append(
                    f"平均視聴時間が動画長の{watch_ratio:.1f}%と低いため、動画を短くする（{int(data.averageVideoDuration * 0.7 / 60)}分程度）か、内容をより濃密にしてください"
                )
        
        if data.views > 0:
            views_per_subscriber = data.views / (data.subscribersGained + 1) if data.subscribersGained > 0 else 0
            if views_per_subscriber < 0.5:
                recommendations.append(
                    "登録者あたりの再生回数が低いため、通知を有効にするよう促すメッセージを動画内や説明欄に追加してください"
                )
        
        recommendations.append(
            "サムネイルとタイトルの組み合わせを最適化するため、A/Bテストを実施し、クリック率の高いパターンを特定してください"
        )
        
        recommendations.append(
            "視聴者のコメントやフィードバックを分析し、人気の高いコンテンツの要素（テーマ、形式、時間帯など）を他の動画にも取り入れてください"
        )
        
        if data.subscribersGained < 10:
            recommendations.append(
                "登録者獲得を促進するため、動画内で登録ボタンを押すよう明確に呼びかけるCTA（Call to Action）を追加してください"
            )
        
        return ImprovementSuggestion(
            summary=summary,
            key_insights=insights[:5],
            recommendations=recommendations[:6],
            best_posting_time="",  # YouTubeには投稿時間の概念がないため空文字列
            hashtag_recommendations=[],  # YouTubeにはハッシュタグの概念がないため空配列
        )


# Singleton instance
improvement_service = ImprovementService()

