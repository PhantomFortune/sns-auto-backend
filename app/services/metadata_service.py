"""
Metadata Generation Service
Generates YouTube metadata (titles, description, hashtags) using OpenAI API.
"""
from typing import List, Optional
import json
import logging

from openai import OpenAI

from app.schemas.metadata import (
    MetadataRequest,
    MetadataResponse,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class MetadataService:
    """Service for generating YouTube metadata"""

    def __init__(self) -> None:
        # Initialize OpenAI client only if API key is provided
        self.client = None
        if settings.OPENAI_API_KEY:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate_metadata(self, request: MetadataRequest) -> MetadataResponse:
        """
        Generate YouTube metadata based on request data.

        1. Try OpenAI API (if API key is set)
        2. If it fails or not configured, fall back to rule-based logic
        """
        if self.client:
            try:
                return self._generate_with_openai(request)
            except Exception as e:
                logger.error(f"OpenAIによるメタデータ生成に失敗しました: {e}", exc_info=True)

        # Fallback: rule-based generation
        logger.info("OpenAIが無効なため、ルールベースのメタデータ生成を使用します")
        return self._generate_rule_based(request)

    # ---------- OpenAI-based generation ----------

    def _generate_with_openai(self, request: MetadataRequest) -> MetadataResponse:
        """Use OpenAI (ChatGPT) to generate YouTube metadata in Japanese"""
        
        # Prepare detailed system prompt
        system_prompt = (
            "あなたは日本語で回答するYouTube動画メタデータ生成の専門家です。\n"
            "役割は、与えられた脚本要約と動画情報を基に、実用的で効果的なYouTubeメタデータ（タイトル、説明文、ハッシュタグ）を作成することです。\n\n"
            "必ず次の方針を厳密に守ってください：\n"
            "1. タイトルは、YouTubeの検索アルゴリズムと視聴者の興味を引くように作成すること\n"
            "   - 検索されやすいキーワードを含める\n"
            "   - 視聴者の興味を引く具体的な表現を使用\n"
            "   - 動画形式（ショート動画、通常動画、ライブ）に適した長さと形式にする\n"
            "   - ショート動画: 簡潔でインパクトのあるタイトル（30-50文字程度）\n"
            "   - 通常動画: 詳細で検索されやすいタイトル（50-70文字程度）\n"
            "   - ライブ: リアルタイム性を強調するタイトル（40-60文字程度）\n"
            "   - 禁止語は絶対に使用しないこと\n"
            "2. 説明文は、YouTubeの検索最適化と視聴者の理解を促進する内容にすること\n"
            "   - 最初の2-3行で動画の核心を伝える（検索結果のプレビューに表示される）\n"
            "   - 脚本要約の内容を自然に反映させる\n"
            "   - 目的（同時接続増加、登録者増加等）を達成するための要素を含める\n"
            "   - チャンネル概要がある場合は、それも自然に組み込む\n"
            "   - 視聴者への呼びかけ（チャンネル登録、高評価、コメント等）を含める\n"
            "   - 禁止語は絶対に使用しないこと\n"
            "   - 5000文字以内で作成すること\n"
            "3. ハッシュタグは、検索性と発見性を高める適切なものを選択すること\n"
            "   - 動画形式に応じたハッシュタグ（#Shorts、#ライブ配信等）\n"
            "   - 目的に応じたハッシュタグ（#登録者、#同時接続等）\n"
            "   - 脚本要約から抽出したキーワードに基づくハッシュタグ\n"
            "   - 一般的なVTuber関連ハッシュタグ（#VTuber、#ライブ配信等）\n"
            "   - 検索されやすいが競合が少ないハッシュタグを優先\n"
            "   - 禁止語を含むハッシュタグは使用しないこと\n"
            "   - 3-10個のハッシュタグを提供\n"
            "4. サムネイルテキストは、視覚的にインパクトがあり、一目で内容が伝わるものにすること\n"
            "   - main: メインのメッセージ（10文字以内、簡潔で印象的）\n"
            "   - sub: サブメッセージ（目的やキーワードを含む、10文字以内）\n"
            "5. すべての出力は自然な日本語で書き、かつ実用性を重視すること\n"
            "   - YouTubeのコミュニティガイドラインに準拠\n"
            "   - 過度な誇張表現は避ける\n"
            "   - 視聴者に誠実で親しみやすい印象を与える\n\n"
            "出力フォーマットは必ず次のJSONオブジェクト【のみ】とし、余計な文章・説明・コメントは一切出力しないこと：\n"
            "{\n"
            '  \"titles\": [\"タイトル1\", \"タイトル2\", \"タイトル3\"],\n'
            '  \"description\": \"説明文（改行を含む複数行のテキスト）\",\n'
            '  \"hashtags\": [\"#ハッシュタグ1\", \"#ハッシュタグ2\", ...],\n'
            '  \"thumbnail_text\": {\n'
            '    \"main\": \"メインテキスト\",\n'
            '    \"sub\": \"サブテキスト\"\n'
            '  }\n'
            "}"
        )

        # Build detailed user prompt
        user_prompt_parts = [
            "以下の情報を基に、YouTube動画のメタデータを生成してください：",
            "",
            f"【脚本要約】",
            request.script_summary,
            "",
            f"【動画形式】",
            request.video_format,
            "",
            f"【目的】",
            ", ".join(request.purposes),
        ]
        
        if request.channel_summary:
            user_prompt_parts.extend([
                "",
                f"【チャンネル概要】",
                request.channel_summary,
            ])
        
        if request.forbidden_words:
            forbidden_list = [word.strip() for word in request.forbidden_words.split(",") if word.strip()]
            user_prompt_parts.extend([
                "",
                f"【禁止語】",
                ", ".join(forbidden_list),
                "",
                "重要: 上記の禁止語は、タイトル、説明文、ハッシュタグのいずれにも絶対に使用しないでください。",
            ])

        user_prompt_parts.extend([
            "",
            "上記の情報を基に、以下の要件でメタデータを作成してください：",
            "",
            "1. タイトル候補を3-5個作成してください：",
            f"   - 動画形式「{request.video_format}」に適した長さと形式にする",
            "   - 検索されやすいキーワードを含める",
            "   - 視聴者の興味を引く具体的な表現を使用",
            "   - 各タイトルは異なるアプローチ（検索重視、興味喚起重視、簡潔性重視等）を取る",
            "",
            "2. 説明文を作成してください：",
            "   - 最初の2-3行で動画の核心を伝える（検索結果のプレビューに表示される）",
            "   - 脚本要約の内容を自然に反映させる",
            f"   - 目的「{', '.join(request.purposes)}」を達成するための要素を含める",
            "   - 視聴者への呼びかけ（チャンネル登録、高評価、コメント等）を含める",
            "   - 5000文字以内で作成",
            "",
            "3. ハッシュタグを3-10個作成してください：",
            f"   - 動画形式「{request.video_format}」に応じたハッシュタグを含める",
            f"   - 目的「{', '.join(request.purposes)}」に応じたハッシュタグを含める",
            "   - 脚本要約から抽出したキーワードに基づくハッシュタグを含める",
            "   - 一般的なVTuber関連ハッシュタグを含める",
            "   - 検索されやすいが競合が少ないハッシュタグを優先",
            "",
            "4. サムネイルテキストを作成してください：",
            "   - main: メインのメッセージ（10文字以内、簡潔で印象的）",
            "   - sub: サブメッセージ（目的やキーワードを含む、10文字以内）",
        ])

        user_content = "\n".join(user_prompt_parts)

        if not self.client:
            raise ValueError("OpenAI client is not initialized")

        response_text = None
        try:
            model_name = settings.OPENAI_MODEL or "gpt-4o-mini"
            logger.info(f"Calling OpenAI model '{model_name}' for metadata generation")
            logger.debug(f"System prompt length: {len(system_prompt)} characters")
            logger.debug(f"User prompt length: {len(user_content)} characters")
            
            response = self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.7,
                max_tokens=2000,
            )

            logger.info(f"OpenAI API呼び出し成功: {len(response.choices)} choices received")
            
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("OpenAI APIから空のレスポンスが返されました")

            response_text = response.choices[0].message.content.strip()
            logger.debug(f"OpenAI response length: {len(response_text)} characters")
            
            # Parse JSON response
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            logger.debug(f"Parsing JSON response...")
            metadata_data = json.loads(response_text)
            logger.info("JSON解析成功")

            # Validate and filter forbidden words if provided
            forbidden_list = []
            if request.forbidden_words:
                forbidden_list = [word.strip().lower() for word in request.forbidden_words.split(",") if word.strip()]

            # Filter titles
            titles = metadata_data.get("titles", [])
            if forbidden_list:
                titles = [
                    title for title in titles
                    if not any(forbidden in title.lower() for forbidden in forbidden_list)
                ]
            # Ensure at least 3 titles
            if len(titles) < 3:
                titles = titles[:3] if len(titles) >= 3 else titles + ["タイトル候補"] * (3 - len(titles))

            # Filter description
            description = metadata_data.get("description", "")
            if forbidden_list:
                for forbidden in forbidden_list:
                    description = description.replace(forbidden, "").replace(forbidden.capitalize(), "")

            # Filter hashtags
            hashtags = metadata_data.get("hashtags", [])
            if forbidden_list:
                hashtags = [
                    tag for tag in hashtags
                    if not any(forbidden in tag.lower() for forbidden in forbidden_list)
                ]
            # Ensure at least 3 hashtags
            if len(hashtags) < 3:
                hashtags = hashtags[:10] if len(hashtags) >= 3 else hashtags + ["#VTuber"] * (3 - len(hashtags))

            # Build response
            return MetadataResponse(
                titles=titles[:5],  # Max 5 titles
                description=description,
                hashtags=hashtags[:10],  # Max 10 hashtags
                thumbnail_text=metadata_data.get("thumbnail_text", {
                    "main": request.script_summary[:10] if len(request.script_summary) > 10 else request.script_summary,
                    "sub": request.purposes[0] if request.purposes else "",
                }),
            )

        except json.JSONDecodeError as e:
            logger.error(f"OpenAIレスポンスのJSON解析に失敗しました: {e}")
            logger.error(f"レスポンステキスト（最初の500文字）: {response_text[:500] if response_text else 'None'}")
            raise ValueError(f"メタデータの生成に失敗しました。レスポンスの解析に失敗しました: {str(e)}")
        except ValueError as e:
            logger.error(f"値エラー: {e}")
            raise
        except Exception as e:
            logger.error(f"OpenAI API呼び出しエラー: {type(e).__name__}: {e}", exc_info=True)
            raise ValueError(f"メタデータの生成に失敗しました: {str(e)}")

    # ---------- Rule-based fallback generation ----------

    def _generate_rule_based(self, request: MetadataRequest) -> MetadataResponse:
        """Generate metadata using rule-based logic (fallback)"""
        # Extract keywords from script summary
        keywords = self._extract_keywords(request.script_summary)
        
        # Format labels
        format_label = {
            "ショート動画": "Shorts",
            "通常動画": "動画",
            "ライブ": "ライブ配信",
        }.get(request.video_format, request.video_format)
        
        purpose_label = "、".join(request.purposes)
        
        # Generate titles
        titles = [
            f"【{format_label}】{request.script_summary[:30]}{'…' if len(request.script_summary) > 30 else ''}",
            f"{request.script_summary[:25]}{'…' if len(request.script_summary) > 25 else ''}｜{request.purposes[0]}を目指す{format_label}",
            f"{keywords[0] if keywords else 'VTuber'}{'・' + keywords[1] if len(keywords) > 1 else ''}｜{format_label}",
        ]
        
        # Generate description
        description_parts = [
            request.script_summary[:100] + ("…" if len(request.script_summary) > 100 else ""),
            "",
            "▼この動画について",
            f"・形式：{format_label}",
            f"・目的：{purpose_label}",
        ]
        
        if request.channel_summary:
            description_parts.append(f"・チャンネル概要：{request.channel_summary}")
        
        description_parts.extend([
            "",
            "▼視聴者へのお願い",
            "チャンネル登録＆高評価で応援お願いします！",
            "コメントもお気軽にどうぞ ✨",
        ])
        
        description = "\n".join(filter(None, description_parts))
        
        # Generate hashtags
        format_hashtags = {
            "ショート動画": ["#Shorts", "#ショート動画"],
            "通常動画": ["#動画", "#YouTube"],
            "ライブ": ["#ライブ配信", "#配信"],
        }
        
        purpose_hashtags = {
            "同時接続増加": ["#同時接続", "#ライブ"],
            "登録者増加": ["#登録者", "#チャンネル登録"],
            "発見性向上": ["#SEO", "#発見"],
            "視聴維持改善": ["#視聴維持", "#エンゲージメント"],
        }
        
        hashtag_keywords = [
            f"#{keyword.replace(' ', '').replace('　', '')}"
            for keyword in keywords[:3]
            if len(keyword) > 1
        ]
        
        selected_purpose_hashtags = []
        for purpose in request.purposes:
            selected_purpose_hashtags.extend(purpose_hashtags.get(purpose, []))
        
        all_hashtags = [
            "#VTuber",
            "#ライブ配信",
        ]
        all_hashtags.extend(format_hashtags.get(request.video_format, []))
        all_hashtags.extend(selected_purpose_hashtags)
        all_hashtags.extend(hashtag_keywords)
        
        hashtags = list(set(all_hashtags))[:10]
        
        # Generate thumbnail text
        thumbnail_text = {
            "main": request.script_summary[:10] if len(request.script_summary) > 10 else request.script_summary,
            "sub": request.purposes[0] if request.purposes else "",
        }
        
        return MetadataResponse(
            titles=titles,
            description=description,
            hashtags=hashtags,
            thumbnail_text=thumbnail_text,
        )

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        return list(set(
            word.strip()
            for word in text.replace("、", ",").replace("。", ",").split(",")
            if len(word.strip()) > 1
        ))[:4]

