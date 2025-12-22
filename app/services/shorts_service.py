"""
Shorts Script Generation Service using OpenAI
"""
import json
import uuid
from datetime import datetime
from typing import List, Dict
from openai import OpenAI
from app.core.config import settings
from app.schemas.shorts import ShortsSection, ShortsScriptResponse


class ShortsGenerationService:
    """Service for generating Shorts scripts using OpenAI"""
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
    
    def generate_script(
        self,
        theme: str,
        duration: int,
        script_format: str,
        tone: str,
        detail_level: str = "standard"
    ) -> ShortsScriptResponse:
        """
        Generate a Shorts script using OpenAI API
        
        Args:
            theme: Theme/topic for the Shorts
            duration: Duration in seconds (5-60)
            script_format: Script format type
            tone: Tone of the script
            
        Returns:
            ShortsScriptResponse with generated script
        """
        if not self.client:
            raise ValueError("OpenAI API key is not configured")
        
        # Calculate time distribution
        opening_duration = min(7, max(3, int(duration * 0.2)))
        closing_duration = min(6, max(3, int(duration * 0.15)))
        main_duration = max(10, duration - opening_duration - closing_duration)
        
        # Get detail level guidance
        detail_guidance = self._get_detail_guidance(detail_level)
        
        # Construct advanced professional prompt
        system_prompt = f"""あなたはYouTube Shortsの台本作成の専門家です。
視聴者の注意を引き、エンゲージメントを最大化する高品質な台本を作成してください。

要件:
1. オープニング（最初の3-7秒）で視聴者の注意を即座に引く
2. メインコンテンツで価値ある情報やエンターテインメントを提供
3. クロージングで視聴者に行動を促す（高評価、チャンネル登録、コメントなど）
4. 指定されたトーンと形式に厳密に従う
5. 自然で話しやすい日本語を使用
6. 各セクションの時間配分を正確に守る
7. {detail_guidance}

出力形式:
JSON形式で、以下の構造で返してください:
{{
  "sections": [
    {{
      "timeRange": "0-6秒",
      "title": "オープニング",
      "content": "実際の台本テキスト（話し言葉で、自然な日本語）"
    }},
    {{
      "timeRange": "6-26秒",
      "title": "メインコンテンツ",
      "content": "実際の台本テキスト"
    }},
    {{
      "timeRange": "26-30秒",
      "title": "クロージング",
      "content": "実際の台本テキスト"
    }}
  ]
}}

重要:
- contentフィールドには、実際に話す台本テキストのみを含める
- カギ括弧「」は使用しない（話し言葉として自然に）
- 各セクションの時間配分を正確に守る
- 視聴者に直接語りかける形式で書く
- {detail_guidance}"""
        
        # Calculate target word count based on detail level
        target_words = self._get_target_word_count(duration, detail_level)
        
        user_prompt = f"""以下の条件でYouTube Shortsの台本を作成してください:

テーマ・トピック: {theme}
動画時間: {duration}秒
スクリプト形式: {script_format}
トーン: {tone}
詳細度: {detail_level}

時間配分:
- オープニング: 0-{opening_duration}秒
- メインコンテンツ: {opening_duration}-{opening_duration + main_duration}秒
- クロージング: {opening_duration + main_duration}-{duration}秒

文字数目標: 合計で約{target_words}文字程度の台本を作成してください。
（オープニング: 約{int(target_words * 0.2)}文字、メイン: 約{int(target_words * 0.65)}文字、クロージング: 約{int(target_words * 0.15)}文字）

スクリプト形式の詳細:
{self._get_format_guidance(script_format)}

トーンの詳細:
{self._get_tone_guidance(tone)}

詳細度の指示:
{detail_guidance}

上記の条件に基づいて、視聴者の注意を引き、エンゲージメントを最大化する台本を作成してください。
文字数目標を意識しながら、{detail_guidance.lower()}台本を作成してください。
JSON形式で返答してください。"""
        
        try:
            # Adjust max_tokens based on detail level
            max_tokens = self._get_max_tokens(detail_level)
            
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.8,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Validate and format sections
            sections = []
            for section_data in result.get("sections", []):
                sections.append(ShortsSection(
                    timeRange=section_data.get("timeRange", ""),
                    title=section_data.get("title", ""),
                    content=section_data.get("content", "")
                ))
            
            # Ensure we have exactly 3 sections
            if len(sections) != 3:
                sections = self._create_fallback_sections(theme, duration, script_format, tone, opening_duration, main_duration, closing_duration)
            
            # Create response
            script_id = str(uuid.uuid4())
            return ShortsScriptResponse(
                id=script_id,
                theme=theme,
                duration=duration,
                scriptFormat=script_format,
                tone=tone,
                sections=sections,
                generatedAt=datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            )
            
        except Exception as e:
            # Fallback to template-based generation if OpenAI fails
            return self._generate_fallback_script(theme, duration, script_format, tone, opening_duration, main_duration, closing_duration)
    
    def _get_format_guidance(self, script_format: str) -> str:
        """Get guidance text for script format"""
        guidance = {
            "解説・教育": "視聴者に知識やスキルを教える形式。3つのポイント（基礎、実践、応用）を含める。",
            "物語・ストーリー": "ストーリーテリング形式。起承転結があり、視聴者を引き込む展開。",
            "リスト・ランキング": "TOP3などのランキング形式。各項目を簡潔に紹介し、理由を説明。",
            "How-to": "手順を説明する形式。3ステップ（準備、実践、仕上げ）で構成。",
            "レビュー・紹介": "商品やコンテンツのレビュー形式。メリット、デメリット、総合評価を含める。",
            "エンターテインメント・雑談": "エンターテインメント性の高い形式。エピソードや体験談を面白く語る。"
        }
        return guidance.get(script_format, "視聴者に価値を提供する形式。")
    
    def _get_tone_guidance(self, tone: str) -> str:
        """Get guidance text for tone"""
        guidance = {
            "明るい（賑やか・フレンドリー）": "明るく元気なトーン。視聴者に親しみやすく、楽しい雰囲気。",
            "自信のある（プロフェッショナル）": "自信に満ちたプロフェッショナルなトーン。専門的で信頼できる。",
            "フォーマル（丁寧・かたい印象）": "丁寧でフォーマルなトーン。敬語を使用し、堅実な印象。",
            "カジュアル（親しみやすい）": "カジュアルで親しみやすいトーン。友達に話すような自然な口調。",
            "ユーモラス（軽い・ユーモアを含む）": "ユーモアを含む軽いトーン。笑いを誘う要素を含める。",
            "シリアス（落ち着いた・真剣な雰囲気）": "真剣で落ち着いたトーン。深い内容を扱う際に適している。"
        }
        return guidance.get(tone, "視聴者に適切に伝わるトーン。")
    
    def _get_detail_guidance(self, detail_level: str) -> str:
        """Get guidance text for detail level"""
        guidance = {
            "concise": "簡潔に要点をまとめた台本を作成してください。各セクションは短めに、核心的な内容のみを含めてください。",
            "standard": "標準的な詳細度で台本を作成してください。各セクションに適度な説明と具体例を含めてください。",
            "detailed": "詳細で充実した台本を作成してください。各セクションに具体的な説明、例、補足情報を含め、視聴者が理解しやすいよう丁寧に説明してください。文字数を多めに使用して、より豊富な内容を提供してください。"
        }
        return guidance.get(detail_level, guidance["standard"])
    
    def _get_target_word_count(self, duration: int, detail_level: str) -> int:
        """Calculate target word count based on duration and detail level"""
        # Base: approximately 4-5 characters per second (Japanese)
        base_chars = duration * 4
        
        multipliers = {
            "concise": 0.7,  # 30% shorter
            "standard": 1.0,  # Standard
            "detailed": 1.5   # 50% longer
        }
        
        multiplier = multipliers.get(detail_level, 1.0)
        return int(base_chars * multiplier)
    
    def _get_max_tokens(self, detail_level: str) -> int:
        """Get max_tokens based on detail level"""
        tokens = {
            "concise": 1500,
            "standard": 2500,
            "detailed": 4000
        }
        return tokens.get(detail_level, 2500)
    
    def _create_fallback_sections(
        self,
        theme: str,
        duration: int,
        script_format: str,
        tone: str,
        opening_duration: int,
        main_duration: int,
        closing_duration: int
    ) -> List[ShortsSection]:
        """Create fallback sections if OpenAI response is invalid"""
        return self._generate_fallback_script(theme, duration, script_format, tone, opening_duration, main_duration, closing_duration).sections
    
    def _generate_fallback_script(
        self,
        theme: str,
        duration: int,
        script_format: str,
        tone: str,
        opening_duration: int,
        main_duration: int,
        closing_duration: int
    ) -> ShortsScriptResponse:
        """Generate script using template-based fallback"""
        # Simple template-based generation
        opener = f"{theme}について、わかりやすくお伝えします！"
        main = f"{theme}のポイントを3つご紹介します。まず、基礎知識。次に、実践方法。最後に、応用テクニックです。"
        closer = "参考になったら高評価お願いします！質問はコメント欄へ！"
        
        sections = [
            ShortsSection(
                timeRange=f"0-{opening_duration}秒",
                title="オープニング",
                content=opener
            ),
            ShortsSection(
                timeRange=f"{opening_duration}-{opening_duration + main_duration}秒",
                title="メインコンテンツ",
                content=main
            ),
            ShortsSection(
                timeRange=f"{opening_duration + main_duration}-{duration}秒",
                title="クロージング",
                content=closer
            )
        ]
        
        return ShortsScriptResponse(
            id=str(uuid.uuid4()),
            theme=theme,
            duration=duration,
            scriptFormat=script_format,
            tone=tone,
            sections=sections,
            generatedAt=datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        )

