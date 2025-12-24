"""
WebSocket endpoints for real-time updates
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Set
from fastapi import WebSocket, WebSocketDisconnect
from app.services.google_calendar_service import GoogleCalendarService

logger = logging.getLogger(__name__)

# 接続されているWebSocketクライアントの管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.last_schedule_hash: str = ""
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending message to WebSocket client: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: dict):
        """すべての接続されているクライアントにメッセージを送信"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket client: {e}")
                disconnected.append(connection)
        
        # 切断された接続を削除
        for connection in disconnected:
            self.disconnect(connection)
    
    def get_schedule_hash(self, schedules: List[dict]) -> str:
        """スケジュールリストのハッシュを生成（変更検出用）"""
        if not schedules:
            return ""
        # スケジュールIDと更新日時でハッシュを生成
        schedule_ids = sorted([s.get('id', '') for s in schedules])
        return str(hash(tuple(schedule_ids)))


# グローバルな接続マネージャー
manager = ConnectionManager()


async def get_x_auto_post_schedules() -> List[dict]:
    """GoogleカレンダーからX自動投稿スケジュールを取得"""
    try:
        calendar_service = GoogleCalendarService()
        
        if not calendar_service.is_available():
            return []
        
        now = datetime.now(timezone.utc)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0)
        time_max = now.replace(year=now.year + 1, hour=23, minute=59, second=59, microsecond=999999)
        
        events = calendar_service.get_events(
            calendar_id='primary',
            time_min=time_min,
            time_max=time_max,
            max_results=2500
        )
        
        # X自動投稿スケジュールをフィルタリング
        x_schedules = []
        for event in events:
            # タイプがX自動投稿か確認
            if event.get('type') == 'X自動投稿':
                x_schedules.append(event)
            else:
                # 説明欄から判定
                description = event.get('description', '')
                description_lower = description.lower()
                type_match = None
                if description:
                    import re
                    type_match = re.search(r'\[種類: (.+?)\]', description)
                
                if type_match and type_match.group(1) == 'X自動投稿':
                    x_schedules.append(event)
                elif 'X' in description and 'youtube' not in description_lower:
                    x_schedules.append(event)
        
        # 未来のスケジュールのみフィルタリング
        future_schedules = []
        for schedule in x_schedules:
            start_str = schedule.get('start')
            if start_str:
                try:
                    start_date = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    # offset-naiveの場合はUTCとして扱う
                    if start_date.tzinfo is None:
                        start_date = start_date.replace(tzinfo=timezone.utc)
                    if start_date >= now:
                        future_schedules.append(schedule)
                except Exception as e:
                    logger.warning(f"Failed to parse schedule date: {e}")
                    continue
        
        # 日時順にソート
        future_schedules.sort(key=lambda x: x.get('start', ''))
        
        return future_schedules
    except Exception as e:
        logger.error(f"Error fetching X auto post schedules: {e}")
        return []


async def get_all_schedules() -> List[dict]:
    """Googleカレンダーから全スケジュール（X自動投稿とYouTubeライブ配信）を取得"""
    try:
        calendar_service = GoogleCalendarService()
        
        if not calendar_service.is_available():
            return []
        
        now = datetime.now(timezone.utc)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0)
        time_max = now.replace(year=now.year + 1, hour=23, minute=59, second=59, microsecond=999999)
        
        events = calendar_service.get_events(
            calendar_id='primary',
            time_min=time_min,
            time_max=time_max,
            max_results=2500
        )
        
        # X自動投稿、YouTubeライブ配信、重要イベント（#重要のみ）のスケジュールをフィルタリング
        relevant_schedules = []
        for event in events:
            event_type = event.get('type')
            description = event.get('description', '')
            description_lower = description.lower()
            
            # 最優先: 説明欄に「#重要」が含まれる場合は必ず重要イベントとして認識
            if '#重要' in description:
                relevant_schedules.append(event)
                continue
            
            # タイプで判定（重要イベントは「#重要」がある場合のみ）
            if event_type in ['X自動投稿', 'YouTubeライブ配信']:
                relevant_schedules.append(event)
            elif event_type == '重要イベント' and '#重要' in description:
                # タイプが重要イベントでも「#重要」がある場合のみ
                relevant_schedules.append(event)
            else:
                # 説明欄から判定
                type_match = None
                if description:
                    import re
                    type_match = re.search(r'\[種類: (.+?)\]', description)
                
                if type_match and type_match.group(1) in ['X自動投稿', 'YouTubeライブ配信']:
                    relevant_schedules.append(event)
                elif 'X' in description and 'youtube' not in description_lower:
                    relevant_schedules.append(event)
                elif 'youtube' in description_lower:
                    relevant_schedules.append(event)
                # 重要イベントは「#重要」がある場合のみ（上記で既にチェック済み）
        
        # 未来のスケジュールのみフィルタリング
        future_schedules = []
        for schedule in relevant_schedules:
            start_str = schedule.get('start')
            if start_str:
                try:
                    start_date = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    # offset-naiveの場合はUTCとして扱う
                    if start_date.tzinfo is None:
                        start_date = start_date.replace(tzinfo=timezone.utc)
                    if start_date >= now:
                        future_schedules.append(schedule)
                except Exception as e:
                    logger.warning(f"Failed to parse schedule date: {e}")
                    continue
        
        # 日時順にソート
        future_schedules.sort(key=lambda x: x.get('start', ''))
        
        return future_schedules
    except Exception as e:
        logger.error(f"Error fetching all schedules: {e}")
        return []


async def check_schedule_changes():
    """定期的にスケジュールをチェックし、変更があれば通知を送信"""
    while True:
        try:
            await asyncio.sleep(30)  # 30秒ごとにチェック
            
            # 全スケジュール（X自動投稿とYouTubeライブ配信）を取得
            schedules = await get_all_schedules()
            current_hash = manager.get_schedule_hash(schedules)
            
            # ハッシュが変更された場合、通知を送信
            if current_hash != manager.last_schedule_hash:
                logger.info(f"Schedule change detected. Count: {len(schedules)}")
                manager.last_schedule_hash = current_hash
                
                # すべての接続されているクライアントに通知
                await manager.broadcast({
                    "type": "schedule_update",
                    "count": len(schedules),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            logger.error(f"Error in schedule check loop: {e}")
            await asyncio.sleep(60)  # エラー時は60秒待機


# バックグラウンドタスクを開始
_schedule_check_task = None


async def start_schedule_check_task():
    """スケジュールチェックタスクを開始"""
    global _schedule_check_task
    if _schedule_check_task is None or _schedule_check_task.done():
        _schedule_check_task = asyncio.create_task(check_schedule_changes())
        logger.info("Schedule check task started")


async def stop_schedule_check_task():
    """スケジュールチェックタスクを停止"""
    global _schedule_check_task
    if _schedule_check_task and not _schedule_check_task.done():
        _schedule_check_task.cancel()
        try:
            await _schedule_check_task
        except asyncio.CancelledError:
            pass
        logger.info("Schedule check task stopped")


# WebSocketエンドポイント
from fastapi import APIRouter

router = APIRouter()


@router.websocket("/schedule-updates")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocketエンドポイント - スケジュール更新通知を受信"""
    await manager.connect(websocket)
    try:
        # 接続時に現在のスケジュール数を送信（全スケジュール）
        schedules = await get_all_schedules()
        await manager.send_personal_message({
            "type": "connected",
            "count": len(schedules),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, websocket)
        
        # クライアントからのメッセージを待機（接続維持用）
        while True:
            try:
                data = await websocket.receive_text()
                # 必要に応じてクライアントからのメッセージを処理
                logger.debug(f"Received message from client: {data}")
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)

