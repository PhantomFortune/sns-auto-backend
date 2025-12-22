"""
Auto Post Generation Service
Generates X (Twitter) post text using OpenAI API.
"""
from typing import Optional
import logging

from openai import OpenAI

from app.schemas.auto_post import AutoPostGenerateRequest, AutoPostGenerateResponse
from app.core.config import settings

logger = logging.getLogger(__name__)


class AutoPostService:
    """Service for generating X post text using OpenAI"""

    def __init__(self) -> None:
        # Initialize OpenAI client only if API key is provided
        self.client = None
        if settings.OPENAI_API_KEY:
            self.client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                timeout=30.0,  # 30 seconds timeout
            )

    def generate_post(self, request: AutoPostGenerateRequest) -> AutoPostGenerateResponse:
        """
        Generate X post text based on request data.

        1. Try OpenAI API (if API key is set)
        2. If it fails or not configured, fall back to rule-based logic
        """
        if self.client:
            try:
                return self._generate_with_openai(request)
            except Exception as e:
                logger.error(f"OpenAIによる投稿文生成に失敗しました: {e}", exc_info=True)

        # Fallback: rule-based generation
        logger.info("OpenAIが無効なため、ルールベースの投稿文生成を使用します")
        return self._generate_rule_based(request)

    def _generate_with_openai(self, request: AutoPostGenerateRequest) -> AutoPostGenerateResponse:
        """Use OpenAI (ChatGPT) to generate X post text in Japanese"""
        
        # Build comprehensive system prompt
        system_prompt = (
            "あなたは日本語でX（旧Twitter）の投稿文を作成する専門家です。\n"
            "役割は、与えられた要件を基に、自然で魅力的な投稿文を280文字以内で作成することです。\n\n"
            "必ず次の方針を厳密に守ってください：\n\n"
            "【基本ルール】\n"
            "1. 文字数は必ず280文字以内に収めること（厳守）\n"
            "2. 日本語で自然な文章を作成すること\n"
            "3. Xに適した文体・表現を使用すること（短文、改行を適切に使用）\n"
            "4. ハッシュタグは必要に応じて自然に含めること（無理に含める必要はない）\n"
            "5. 絵文字や感嘆符の使用は指定されたスタイルに従うこと\n\n"
            "【投稿タイプ別の特徴】\n"
            "- 朝の挨拶: 明るく前向きなトーン、一日の始まりを感じさせる内容\n"
            "- 夜の挨拶: 落ち着いたトーン、一日の振り返りや感謝の気持ち\n"
            "- 放送・ストリーミング案内: 具体的な日時・内容、参加を促す表現\n"
            "- サービス・商品告知: 明確な情報伝達、興味を引く表現\n"
            "- 雑談・日常投稿: 親しみやすいトーン、共感を呼ぶ内容\n"
            "- その他: 指定された目的に応じた適切な内容\n\n"
            "【目的別のアプローチ】\n"
            "- 親近感を高めたい: 個人的なエピソード、共感できる内容、親しみやすい表現\n"
            "- 視聴・参加を誘導したい: 具体的な日時・場所・方法、参加のメリット、期待感を高める表現\n"
            "- 情報を簡潔に伝えたい: 要点を明確に、箇条書きや改行を活用、重要な情報を最初に\n"
            "- ブランディング: 一貫性のあるトーン、特徴的な表現、価値観の伝達\n\n"
            "【トーン別の表現】\n"
            "- カジュアル: 親しみやすい表現、略語や口語的表現も可、絵文字を多用\n"
            "- 丁寧: 敬語を使用、丁寧な表現、適度な改行で読みやすく\n"
            "- 活発: 感嘆符を多用、短い文でテンポよく、エネルギー感を表現\n"
            "- 落ち着いた: 長めの文、落ち着いた表現、余韻を残す\n"
            "- 専門的: 専門用語を適切に使用、情報を正確に伝達、信頼感のある表現\n\n"
            "【投稿主タイプ別の特徴】\n"
            "- VTuber: キャラクター性を活かした表現、ファンとの距離感を意識\n"
            "- 個人: 個人的な視点、親しみやすい表現\n"
            "- 企業公式: 公式らしい丁寧な表現、信頼感のある内容\n"
            "- インフルエンサー: 影響力のある表現、トレンドを意識\n"
            "- その他: 指定されたタイプに応じた適切な表現\n\n"
            "【絵文字・感嘆符の使用】\n"
            "- 豊富に: 絵文字を多用（文末、文中に適切に配置）、感嘆符も積極的に使用\n"
            "- 多様化: 様々な種類の絵文字を使用、バリエーションを意識\n"
            "- 適度に: 必要に応じて使用、過度にならないよう配慮\n"
            "- 控えめに: 最小限の使用、または使用しない\n"
            "- 多用する: 絵文字・感嘆符を積極的に使用\n"
            "- バランス良く: 適度に使用、読みやすさを重視\n"
            "- 使わない: 絵文字・感嘆符は使用しない\n\n"
            "【画像の役割を考慮】\n"
            "- 雰囲気伝達用: 画像で伝わる雰囲気を文章で補完、画像と文章の調和を意識\n"
            "- 内容補足: 画像の内容を文章で説明・補足、画像を見なくても理解できる内容も含める\n"
            "- 情報（日時等）を含む: 画像に含まれる情報を文章でも明記、重複を避けつつ要点を伝達\n"
            "- 特に関係なし: 画像に依存せず、文章だけで完結する内容\n\n"
            "【行動喚起（CTA）の組み込み】\n"
            "- なし: CTAは含めない\n"
            "- 見てほしい: 「ぜひご覧ください」「チェックしてください」などの表現\n"
            "- 参加してほしい: 「ぜひご参加ください」「一緒に楽しみましょう」などの表現\n"
            "- 詳細を確認してほしい: 「詳細はこちら」「続きはリンクから」などの表現\n"
            "- 自由入力: 指定されたカスタムCTAを自然に組み込む\n\n"
            "【必須情報の組み込み】\n"
            "- 必須情報が指定されている場合、自然に文章に組み込むこと\n"
            "- 無理に挿入せず、文脈に合う形で組み込むこと\n"
            "- 重要な情報は目立つ位置（文頭または文末）に配置すること\n\n"
            "【出力形式】\n"
            "- 投稿文のみを出力すること（説明やコメントは不要）\n"
            "- 改行は適切に使用し、読みやすさを重視すること\n"
            "- 280文字以内に必ず収めること\n"
        )

        # Build detailed user prompt
        user_prompt_parts = [
            f"投稿タイプ: {request.post_type}",
            f"目的: {request.purpose}",
            f"絵文字・感嘆符スタイル: {request.emoji_style}",
            f"絵文字・感嘆符使用度: {request.emoji_usage}",
            f"トーン: {request.tone}",
            f"投稿主タイプ: {request.poster_type}",
        ]
        
        if request.required_info:
            user_prompt_parts.append(f"必須情報（必ず組み込む）: {request.required_info}")
        
        if request.image_role:
            user_prompt_parts.append(f"画像の役割: {request.image_role}")
        
        if request.cta == "自由入力" and request.cta_custom:
            user_prompt_parts.append(f"行動喚起（CTA）: {request.cta_custom}")
        elif request.cta != "なし":
            user_prompt_parts.append(f"行動喚起（CTA）: {request.cta}")
        
        user_prompt = "\n".join(user_prompt_parts)
        user_prompt += "\n\n上記の要件に基づいて、X（旧Twitter）に投稿する文章を280文字以内で作成してください。"

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.8,  # 創造性を高める
                max_tokens=500,
                timeout=30.0,
            )

            generated_text = response.choices[0].message.content.strip()
            
            # 280文字以内に収める（念のため）
            if len(generated_text) > 280:
                generated_text = generated_text[:280]
            
            return AutoPostGenerateResponse(
                text=generated_text,
                character_count=len(generated_text),
            )
        except Exception as e:
            logger.error(f"OpenAI API呼び出しエラー: {e}", exc_info=True)
            raise

    def _generate_rule_based(self, request: AutoPostGenerateRequest) -> AutoPostGenerateResponse:
        """Fallback: Generate post text using rule-based logic"""
        logger.info("ルールベースの投稿文生成を使用します")
        
        # Simple rule-based generation
        emoji_map = {
            "豊富に": "✨🎉",
            "多様化": "✨😊🎯",
            "適度に": "😊",
            "控えめに": "",
        }
        
        emoji_usage_map = {
            "多用する": "✨🎉💫",
            "バランス良く": "✨",
            "控えめに": "",
            "使わない": "",
        }
        
        # Combine emoji styles
        emoji = emoji_map.get(request.emoji_style, "")
        emoji_usage = emoji_usage_map.get(request.emoji_usage, "")
        combined_emoji = f"{emoji} {emoji_usage}".strip()
        
        tone_suffix_map = {
            "カジュアル": "！",
            "丁寧": "。ぜひよろしくお願いします。",
            "活発": "！一緒に楽しみましょう！",
            "落ち着いた": "。ゆったりとお楽しみください。",
            "専門的": "。詳細は下記をご確認ください。",
        }
        
        purpose_lead = {
            "親近感を高めたい": "みなさんともっと近づきたいから、",
            "視聴・参加を誘導したい": "ぜひ見に来てほしいので、",
            "情報を簡潔に伝えたい": "ポイントをシンプルにまとめました。",
            "ブランディング": "世界観を感じてもらえるように整えました。",
        }
        
        poster_prefix = (
            "お知らせ"
            if request.poster_type == "その他"
            else f"{request.poster_type}からのお知らせ"
        )
        
        post_type_lead = request.post_type
        purpose_text = purpose_lead.get(request.purpose, "")
        info = f"\n{request.required_info}" if request.required_info else ""
        
        cta_text = ""
        if request.cta == "自由入力" and request.cta_custom:
            cta_text = f"\n{request.cta_custom}"
        elif request.cta != "なし":
            cta_text = f"\n{request.cta}"
        
        tone_suffix = tone_suffix_map.get(request.tone, "")
        
        opening = f"{poster_prefix}です。{post_type_lead}{combined_emoji}"
        body = f"{opening}\n{purpose_text}{tone_suffix}{info}{cta_text}"
        
        # Ensure 280 characters or less
        if len(body) > 280:
            body = body[:280]
        
        return AutoPostGenerateResponse(
            text=body,
            character_count=len(body),
        )

