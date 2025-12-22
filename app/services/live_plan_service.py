"""
Live Plan Generation Service
Generates live streaming plans using OpenAI API.
"""
from typing import List, Optional
from datetime import datetime
import json
import logging
import uuid

from openai import OpenAI

from app.schemas.live_plan import (
    LivePlanRequest,
    LivePlanResponse,
    FlowItem,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class LivePlanService:
    """Service for generating live streaming plans"""

    def __init__(self) -> None:
        # Initialize OpenAI client only if API key is provided
        self.client = None
        if settings.OPENAI_API_KEY:
            self.client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                timeout=30.0,  # 30 seconds timeout
            )

    def generate_plan(self, request: LivePlanRequest) -> LivePlanResponse:
        """
        Generate live streaming plan based on request data.

        1. Try OpenAI API (if API key is set)
        2. If it fails or not configured, fall back to rule-based logic
        """
        if self.client:
            try:
                return self._generate_with_openai(request)
            except Exception as e:
                logger.error(f"OpenAIによるライブ企画案生成に失敗しました: {e}", exc_info=True)

        # Fallback: rule-based generation
        logger.info("OpenAIが無効なため、ルールベースの企画案生成を使用します")
        return self._generate_rule_based(request)

    # ---------- OpenAI-based generation ----------

    def _generate_with_openai(self, request: LivePlanRequest) -> LivePlanResponse:
        """Use OpenAI (ChatGPT) to generate live streaming plan in Japanese"""
        total_minutes = request.duration_hours * 60 + request.duration_minutes
        
        # Prepare detailed prompt
        system_prompt = (
            "あなたは日本語で回答するVTuberライブ配信企画のプロデューサーです。\n"
            "役割は、与えられた情報を基に、実用的で具体的なライブ配信企画案を作成することです。\n\n"
            "必ず次の方針を厳密に守ってください：\n"
            "1. 企画案は実際の配信でそのまま使えるレベルの具体性を持たせること\n"
            "   - 各セクションで「何を話すか」「何をするか」を明確に記述\n"
            "   - 視聴者への呼びかけや具体的なアクションを含める\n"
            "   - 時間配分を考慮した現実的な内容にする\n"
            "2. 配信の流れ（flow）は、時間配分を明確にし、各セクションの内容を具体的に記述すること\n"
            "   - オープニング: 挨拶、本日のテーマ紹介、目的の説明（5-10分）\n"
            "   - メインコンテンツ: ライブ形式に応じた具体的な活動（配信時間の60-70%）\n"
            "   - 視聴者交流: コメント返し、質問タイム、参加型企画（適宜）\n"
            "   - エンディング: まとめ、次回告知、チャンネル登録・高評価のお願い（5-10分）\n"
            "3. 準備物は、そのライブ形式に必要な具体的なアイテムを列挙すること\n"
            "   - 必須アイテム（配信環境、告知用素材、BGM等）\n"
            "   - ライブ形式特有のアイテム（ゲームソフト、音源、ASMR道具等）\n"
            "   - 難易度に応じた追加アイテム（高難易度の場合は特別な装飾や機材等）\n"
            "4. ターゲット層と目的を意識した内容構成にすること\n"
            "   - ターゲット層に合わせたトーンや話題選び\n"
            "   - 目的（同時接続増加、登録者増加等）を達成するための具体的な施策\n"
            "5. 難易度に応じた適切な企画規模と準備物を提案すること\n"
            "   - 低難易度: シンプルで準備が簡単、少人数でも実施可能\n"
            "   - 中難易度: 標準的な企画、適度な準備が必要\n"
            "   - 高難易度: 大規模な企画、特別な準備や複数人での実施が必要\n"
            "6. すべての出力は自然なビジネス日本語で書き、かつ実用性を重視すること\n"
            "   - 専門用語は避け、誰でも理解できる表現を使用\n"
            "   - 具体的な数値や時間を明記（例: 「10分間のゲーム実況」）\n\n"
            "出力フォーマットは必ず次のJSONオブジェクト【のみ】とし、余計な文章・説明・コメントは一切出力しないこと：\n"
            "{\n"
            '  \"flow\": [\n'
            '    {\n'
            '      \"time_range\": \"0-10分\",\n'
            '      \"title\": \"オープニング\",\n'
            '      \"content\": \"具体的な内容を200-300文字程度で記述。視聴者への挨拶、本日のテーマ紹介、目的の説明を含める。\"\n'
            '    },\n'
            '    ...\n'
            '  ],\n'
            '  \"preparations\": [\"準備物1\", \"準備物2\", ...]\n'
            "}"
        )

        # Build detailed user prompt
        user_prompt_parts = [
            f"ライブ形式: {request.type}",
            f"ライブタイトル: {request.title}",
            f"予定時間: {request.duration_hours}時間{request.duration_minutes}分（合計{total_minutes}分）",
            f"目的: {', '.join(request.purposes)}",
            f"ターゲット層: {request.target_audience}",
        ]
        
        if request.preferred_time_start and request.preferred_time_end:
            user_prompt_parts.append(
                f"優先時間帯: {request.preferred_time_start} 〜 {request.preferred_time_end} (JST)"
            )
        
        if request.notes:
            user_prompt_parts.append(f"追加メモ: {request.notes}")
        
        if request.difficulty:
            difficulty_map = {"low": "低（易しい）", "medium": "中", "high": "高（大規模）"}
            user_prompt_parts.append(f"希望難易度: {difficulty_map.get(request.difficulty, request.difficulty)}")

        user_prompt_parts.extend([
            "",
            "上記の情報を基に、以下の要件でライブ企画案を作成してください：",
            f"1. 配信時間は合計{total_minutes}分です。時間配分を適切に行い、以下の構成を含めてください：",
            f"   - オープニング: 5-10分（挨拶、テーマ紹介、目的説明）",
            f"   - メインコンテンツ: {int(total_minutes * 0.6)}-{int(total_minutes * 0.7)}分（ライブ形式に応じた具体的な活動）",
            f"   - 視聴者交流: 適宜（コメント返し、質問タイム、参加型企画）",
            f"   - エンディング: 5-10分（まとめ、次回告知、チャンネル登録・高評価のお願い）",
            "2. 各セクションのtime_rangeは「開始分-終了分」の形式で記述してください（例: 0-10分、10-60分）。",
            "   時間は連続しており、前のセクションの終了時間が次のセクションの開始時間になります。",
            "3. 各セクションのcontentは、その時間帯で何をするのかを具体的に200-300文字程度で記述してください。",
            "   以下の要素を含めてください：",
            "   - 具体的な活動内容（何を話すか、何をするか）",
            "   - 視聴者への呼びかけや参加方法",
            "   - 目的を達成するための具体的な施策",
            "4. 準備物は、このライブ形式と目的に必要な具体的なアイテムを5〜10個程度列挙してください。",
            "   必須アイテム（配信環境、告知用素材等）とライブ形式特有のアイテムを含めてください。",
            "5. ターゲット層と目的を意識し、視聴者が楽しめる・参加できる内容を提案してください。",
            f"   特に「{', '.join(request.purposes)}」という目的を達成するための具体的な施策を含めてください。",
        ])

        if request.difficulty == "high":
            user_prompt_parts.append("6. 難易度が高いため、大規模な企画や特別な準備物を含めてください。")
        elif request.difficulty == "low":
            user_prompt_parts.append("6. 難易度が低いため、シンプルで準備が簡単な企画を提案してください。")

        user_content = "\n".join(user_prompt_parts)

        if not self.client:
            raise ValueError("OpenAI client is not initialized")

        try:
            model_name = settings.OPENAI_MODEL or "gpt-4o-mini"
            logger.info(f"Calling OpenAI model '{model_name}' for live plan generation")
            
            # Set timeout to 30 seconds
            response = self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.7,
                max_tokens=2000,
                timeout=30.0,  # 30 seconds timeout
            )

            response_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            plan_data = json.loads(response_text)

            # Build flow items
            flow_items = [
                FlowItem(
                    time_range=item["time_range"],
                    title=item["title"],
                    content=item["content"],
                )
                for item in plan_data["flow"]
            ]

            # Build response
            return LivePlanResponse(
                id=str(uuid.uuid4()),
                type=request.type,
                title=request.title,
                duration_hours=request.duration_hours,
                duration_minutes=request.duration_minutes,
                purposes=request.purposes,
                target_audience=request.target_audience,
                preferred_time_start=request.preferred_time_start,
                preferred_time_end=request.preferred_time_end,
                notes=request.notes,
                difficulty=request.difficulty,
                flow=flow_items,
                preparations=plan_data["preparations"],
                generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

        except json.JSONDecodeError as e:
            logger.error(f"OpenAIレスポンスのJSON解析に失敗しました: {e}\nレスポンス: {response_text}")
            raise ValueError("企画案の生成に失敗しました。レスポンスの解析に失敗しました。")
        except Exception as e:
            logger.error(f"OpenAI API呼び出しエラー: {e}", exc_info=True)
            raise

    # ---------- Rule-based fallback generation ----------

    def _generate_rule_based(self, request: LivePlanRequest) -> LivePlanResponse:
        """Generate plan using rule-based logic (fallback)"""
        total_minutes = request.duration_hours * 60 + request.duration_minutes
        
        # Calculate time distribution
        opening_duration = max(5, min(10, int(total_minutes * 0.1)))
        ending_duration = max(5, min(10, int(total_minutes * 0.1)))
        main_duration = max(30, total_minutes - opening_duration - ending_duration)
        
        # Generate flow based on type
        flow_items = []
        
        # Opening
        flow_items.append(
            FlowItem(
                time_range=f"0-{opening_duration}分",
                title="オープニング",
                content=f"視聴者の皆さん、こんにちは/こんばんは！本日は「{request.title}」をお届けします。{', '.join(request.purposes)}を目的として、{request.target_audience}の皆さんに向けた配信です。今日もよろしくお願いします！",
            )
        )
        
        # Main content sections
        main_sections = self._get_main_sections_for_type(request.type, main_duration)
        current_time = opening_duration
        section_duration = main_duration // len(main_sections)
        
        for i, section_title in enumerate(main_sections):
            start_time = current_time
            end_time = current_time + section_duration
            if i == len(main_sections) - 1:
                end_time = opening_duration + main_duration
            
            flow_items.append(
                FlowItem(
                    time_range=f"{start_time}-{end_time}分",
                    title=section_title,
                    content=f"{section_title}の時間です。{', '.join(request.purposes)}を意識した内容で進めます。視聴者の皆さんと一緒に楽しみましょう！",
                )
            )
            current_time = end_time
        
        # Ending
        flow_items.append(
            FlowItem(
                time_range=f"{total_minutes - ending_duration}-{total_minutes}分",
                title="エンディング",
                content="本日もご視聴ありがとうございました！次回配信の告知と、チャンネル登録・高評価のお願いをします。また次回もお楽しみに！",
            )
        )
        
        # Generate preparations
        preparations = self._get_preparations_for_type(request.type, request.difficulty)
        
        return LivePlanResponse(
            id=str(uuid.uuid4()),
            type=request.type,
            title=request.title,
            duration_hours=request.duration_hours,
            duration_minutes=request.duration_minutes,
            purposes=request.purposes,
            target_audience=request.target_audience,
            preferred_time_start=request.preferred_time_start,
            preferred_time_end=request.preferred_time_end,
            notes=request.notes,
            difficulty=request.difficulty,
            flow=flow_items,
            preparations=preparations,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _get_main_sections_for_type(self, live_type: str, main_duration: int) -> List[str]:
        """Get main section titles based on live type"""
        type_sections = {
            "雑談": ["近況報告", "視聴者との交流", "トークタイム"],
            "ゲーム": ["ゲーム実況", "視聴者参加コーナー", "ハイライト振り返り"],
            "コラボ": ["コラボ相手紹介", "共同企画", "クロストーク"],
            "トーク企画": ["テーマトーク", "視聴者質問コーナー", "ディスカッション"],
            "歌枠": ["アップテンポセット", "リクエストコーナー", "バラードセット"],
            "ASMR": ["ASMR実演", "リラックスタイム", "視聴者との交流"],
            "Q&A": ["質問回答", "追加質問タイム", "まとめ"],
            "特別イベント": ["イベント紹介", "メイン企画", "結果発表"],
        }
        return type_sections.get(live_type, ["メインコンテンツ", "視聴者との交流", "まとめ"])

    def _get_preparations_for_type(self, live_type: str, difficulty: Optional[str]) -> List[str]:
        """Get preparation items based on live type and difficulty"""
        base_preparations = [
            "配信環境の確認",
            "告知用サムネイル・説明文",
            "BGM・音響設定",
            "コメントビューワ準備",
        ]
        
        type_preparations = {
            "雑談": ["トークテーマのメモ", "BGMセット"],
            "ゲーム": ["ゲームソフト・コントローラー", "配信画面レイアウト調整"],
            "コラボ": ["コラボ相手との連絡確認", "共有スライド/素材"],
            "トーク企画": ["トークテーマの資料", "質問リスト"],
            "歌枠": ["音源・マイクチェック", "歌詞カード準備", "飲み物・加湿器"],
            "ASMR": ["ASMR道具", "静かな環境の確保", "マイク設定"],
            "Q&A": ["質問リスト", "回答メモ"],
            "特別イベント": ["イベント企画書", "景品・小道具", "タイマー"],
        }
        
        preparations = base_preparations + type_preparations.get(live_type, [])
        
        if difficulty == "high":
            preparations.extend(["特別な装飾・背景", "追加の機材", "アシスタント配置"])
        elif difficulty == "low":
            preparations = base_preparations[:3]  # 最小限の準備物
        
        return preparations

