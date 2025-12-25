"""
Storage API Routes
Endpoints for file storage management
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import FileResponse
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import logging
import io
import uuid
import base64
import pandas as pd
from pathlib import Path
import shutil
import os
# PIL imports removed - no longer needed since we don't composite images

from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.storage_file import StorageFile, ReportType, FileCategory, ScheduledPost
from app.schemas.storage import (
    SaveReportRequest,
    SaveReportResponse,
    StorageFileResponse,
    FileListResponse,
    DeleteFileResponse,
    SaveScheduledPostRequest,
    ScheduledPostResponse,
    ScheduledPostListResponse,
    UpdateScheduledPostRequest,
)
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storage", tags=["Storage"])


def generate_excel_from_data(
    report_type: str,
    analytics_data: dict,
    improvement_suggestion: dict,
    period: str,
    timestamp: datetime
) -> bytes:
    """
    Excelファイルを生成
    
    Args:
        report_type: "youtube_analytics" or "x_analytics"
        analytics_data: 分析データ
        improvement_suggestion: 改善提案データ
        period: 分析期間
        timestamp: タイムスタンプ
    
    Returns:
        Excelファイルのバイトコンテンツ
    """
    # ExcelWriterを使用してメモリ上にExcelファイルを生成
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if report_type == "youtube_analytics":
            # Sheet 1: KPI Summary
            kpi_data = {
                "指標": [
                    "再生回数",
                    "総再生時間（分）",
                    "平均視聴時間（秒）",
                    "視聴継続率（%）",
                    "登録者増加",
                    "登録者減少",
                    "純増登録者数",
                    "共有数",
                ],
                "値": [
                    analytics_data.get("views", 0),
                    round(analytics_data.get("estimatedMinutesWatched", 0)),
                    round(analytics_data.get("averageViewDuration", 0)),
                    round(analytics_data.get("viewerRetentionRate", 0), 1) if analytics_data.get("viewerRetentionRate") else "-",
                    analytics_data.get("subscribersGained", 0),
                    analytics_data.get("subscribersLost", 0),
                    analytics_data.get("subscribersGained", 0) - analytics_data.get("subscribersLost", 0),
                    analytics_data.get("shares", 0),
                ],
            }
            df_kpi = pd.DataFrame(kpi_data)
            df_kpi.to_excel(writer, sheet_name="KPIサマリー", index=False)
            
            # Sheet 2: Daily Trend Data
            if analytics_data.get("dailyData") and len(analytics_data["dailyData"]) > 0:
                trend_data = []
                for item in analytics_data["dailyData"]:
                    trend_data.append({
                        "日付": item.get("date", ""),
                        "再生回数": item.get("views", 0),
                        "総再生時間（分）": round(item.get("estimatedMinutesWatched", 0)),
                        "純増登録者数": item.get("netSubscribers", 0),
                        "平均視聴時間（秒）": round(item.get("averageViewDuration", 0)),
                    })
                df_trend = pd.DataFrame(trend_data)
                df_trend.to_excel(writer, sheet_name="日次トレンド", index=False)
            
            # Sheet 3: Improvement Suggestions
            suggestions_data = {
                "項目": [],
                "内容": [],
            }
            suggestions_data["項目"].append("サマリー")
            suggestions_data["内容"].append(improvement_suggestion.get("summary", ""))
            suggestions_data["項目"].append("")
            suggestions_data["内容"].append("")
            
            suggestions_data["項目"].append("主要インサイト")
            suggestions_data["内容"].append("")
            for i, insight in enumerate(improvement_suggestion.get("key_insights", []), 1):
                suggestions_data["項目"].append(f"{i}.")
                suggestions_data["内容"].append(insight)
            
            suggestions_data["項目"].append("")
            suggestions_data["内容"].append("")
            suggestions_data["項目"].append("改善推奨事項")
            suggestions_data["内容"].append("")
            for i, rec in enumerate(improvement_suggestion.get("recommendations", []), 1):
                suggestions_data["項目"].append(f"{i}.")
                suggestions_data["内容"].append(rec)
            
            if improvement_suggestion.get("best_posting_time"):
                suggestions_data["項目"].append("")
                suggestions_data["内容"].append("")
                suggestions_data["項目"].append("推奨投稿時間")
                suggestions_data["内容"].append(improvement_suggestion["best_posting_time"])
            
            if improvement_suggestion.get("hashtag_recommendations"):
                suggestions_data["項目"].append("")
                suggestions_data["内容"].append("")
                suggestions_data["項目"].append("推奨ハッシュタグ")
                suggestions_data["内容"].append(", ".join(improvement_suggestion["hashtag_recommendations"]))
            
            df_suggestions = pd.DataFrame(suggestions_data)
            df_suggestions.to_excel(writer, sheet_name="改善提案", index=False)
        
        elif report_type == "x_analytics":
            # Sheet 1: KPI Summary
            kpi_data = {
                "指標": [
                    "いいね数",
                    "リツイート数",
                    "返信数",
                    "インプレッション数",
                    "フォロワー数",
                ],
                "値": [
                    analytics_data.get("likes_count", 0),
                    analytics_data.get("retweets_count", 0),
                    analytics_data.get("replies_count", 0),
                    analytics_data.get("impressions_count", 0),
                    analytics_data.get("followers_count", 0),
                ],
            }
            df_kpi = pd.DataFrame(kpi_data)
            df_kpi.to_excel(writer, sheet_name="KPIサマリー", index=False)
            
            # Sheet 2: Hashtag Analysis
            hashtag_data = {
                "ハッシュタグ": [],
                "いいね数": [],
            }
            for hashtag in analytics_data.get("hashtag_analysis", [])[:3]:
                hashtag_data["ハッシュタグ"].append(f"#{hashtag.get('tag', '')}")
                hashtag_data["いいね数"].append(hashtag.get("likes", 0))
            
            df_hashtag = pd.DataFrame(hashtag_data)
            df_hashtag.to_excel(writer, sheet_name="ハッシュタグ分析", index=False)
            
            # Sheet 3: Trend Data
            trend_data = []
            for item in analytics_data.get("engagement_trend", []):
                trend_data.append({
                    "時間": item.get("time", ""),
                    "エンゲージメント": item.get("engagement", 0),
                    "インプレッション": item.get("impressions", 0),
                })
            df_trend = pd.DataFrame(trend_data)
            df_trend.to_excel(writer, sheet_name="トレンドデータ", index=False)
            
            # Sheet 4: Improvement Suggestions
            suggestions_data = {
                "項目": [],
                "内容": [],
            }
            suggestions_data["項目"].append("サマリー")
            suggestions_data["内容"].append(improvement_suggestion.get("summary", ""))
            suggestions_data["項目"].append("")
            suggestions_data["内容"].append("")
            
            suggestions_data["項目"].append("主要インサイト")
            suggestions_data["内容"].append("")
            for i, insight in enumerate(improvement_suggestion.get("key_insights", []), 1):
                suggestions_data["項目"].append(f"{i}.")
                suggestions_data["内容"].append(insight)
            
            suggestions_data["項目"].append("")
            suggestions_data["内容"].append("")
            suggestions_data["項目"].append("改善推奨事項")
            suggestions_data["内容"].append("")
            for i, rec in enumerate(improvement_suggestion.get("recommendations", []), 1):
                suggestions_data["項目"].append(f"{i}.")
                suggestions_data["内容"].append(rec)
            
            suggestions_data["項目"].append("")
            suggestions_data["内容"].append("")
            suggestions_data["項目"].append("推奨投稿時間")
            suggestions_data["内容"].append(improvement_suggestion.get("best_posting_time", ""))
            
            suggestions_data["項目"].append("")
            suggestions_data["内容"].append("")
            suggestions_data["項目"].append("推奨ハッシュタグ")
            suggestions_data["内容"].append(", ".join(improvement_suggestion.get("hashtag_recommendations", [])))
            
            df_suggestions = pd.DataFrame(suggestions_data)
            df_suggestions.to_excel(writer, sheet_name="改善提案", index=False)
    
    output.seek(0)
    return output.getvalue()


@router.post("/reports", response_model=SaveReportResponse, status_code=status.HTTP_201_CREATED)
async def save_report(
    request: SaveReportRequest,
    db: Session = Depends(get_db)
):
    """
    レポートをストレージに保存
    
    - 分析データと改善提案を含むExcelファイルを生成
    - ストレージに保存
    - データベースにファイル情報を記録
    """
    try:
        timestamp = datetime.now()
        
        # Excelファイルを生成
        excel_content = generate_excel_from_data(
            report_type=request.report_type.value,
            analytics_data=request.analytics_data,
            improvement_suggestion=request.improvement_suggestion,
            period=request.period,
            timestamp=timestamp
        )
        
        # ストレージに保存
        file_path, file_name, file_size = storage_service.save_file(
            file_content=excel_content,
            category="report",
            report_type=request.report_type.value,
            timestamp=timestamp
        )
        
        # データベースに記録
        file_id = str(uuid.uuid4())
        storage_file = StorageFile(
            id=file_id,
            category=FileCategory.REPORT,
            report_type=request.report_type,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            description=request.description
        )
        
        db.add(storage_file)
        db.commit()
        db.refresh(storage_file)
        
        logger.info(f"Report saved: {file_path} (ID: {file_id})")
        
        return SaveReportResponse(
            success=True,
            file_id=file_id,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            message="レポートを保存しました"
        )
    
    except Exception as e:
        logger.error(f"Failed to save report: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"レポートの保存に失敗しました: {str(e)}"
        )


@router.get("/files", response_model=FileListResponse)
async def list_files(
    category: Optional[FileCategory] = Query(None, description="ファイルカテゴリでフィルタ"),
    report_type: Optional[ReportType] = Query(None, description="レポートタイプでフィルタ"),
    db: Session = Depends(get_db)
):
    """
    ストレージ内のファイル一覧を取得
    """
    try:
        query = db.query(StorageFile)
        
        if category:
            query = query.filter(StorageFile.category == category)
        
        if report_type:
            query = query.filter(StorageFile.report_type == report_type)
        
        files = query.order_by(StorageFile.created_at.desc()).all()
        
        return FileListResponse(
            success=True,
            files=[
                StorageFileResponse(
                    id=file.id,
                    category=file.category,
                    report_type=file.report_type,
                    file_name=file.file_name,
                    file_path=file.file_path,
                    file_size=file.file_size,
                    description=file.description,
                    created_at=file.created_at,
                    updated_at=file.updated_at,
                )
                for file in files
            ],
            total=len(files)
        )
    
    except Exception as e:
        logger.error(f"Failed to list files: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ファイル一覧の取得に失敗しました: {str(e)}"
        )


@router.delete("/files/{file_id}", response_model=DeleteFileResponse)
async def delete_file(
    file_id: str,
    db: Session = Depends(get_db)
):
    """
    ファイルを削除
    
    - データベースからファイル情報を削除
    - ストレージからファイルを削除
    """
    try:
        # データベースからファイル情報を取得
        storage_file = db.query(StorageFile).filter(StorageFile.id == file_id).first()
        
        if not storage_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ファイルが見つかりません"
            )
        
        # ストレージからファイルを削除
        deleted = storage_service.delete_file(storage_file.file_path)
        
        if not deleted:
            logger.warning(f"File not found in storage: {storage_file.file_path}")
        
        # データベースから削除
        db.delete(storage_file)
        db.commit()
        
        logger.info(f"File deleted: {file_id}")
        
        return DeleteFileResponse(
            success=True,
            message="ファイルを削除しました"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete file: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ファイルの削除に失敗しました: {str(e)}"
        )


@router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    db: Session = Depends(get_db)
):
    """
    ファイルをダウンロード
    """
    try:
        # データベースからファイル情報を取得
        storage_file = db.query(StorageFile).filter(StorageFile.id == file_id).first()
        
        if not storage_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ファイルが見つかりません"
            )
        
        # ファイルパスを取得
        file_path = storage_service.get_file_path(storage_file.file_path)
        
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ファイルがストレージに見つかりません"
            )
        
        return FileResponse(
            path=str(file_path),
            filename=storage_file.file_name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download file: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ファイルのダウンロードに失敗しました: {str(e)}"
        )


@router.post("/scheduled-posts", response_model=ScheduledPostResponse, status_code=status.HTTP_201_CREATED)
async def save_scheduled_post(
    request: SaveScheduledPostRequest,
    db: Session = Depends(get_db)
):
    """
    予約投稿を保存
    
    - 元の画像をそのままストレージに保存（テキストは画像上に合成しない）
    - データベースに予約投稿情報を記録
    """
    try:
        timestamp = datetime.now(timezone.utc)
        
        # 画像をそのまま保存（合成しない）
        image_path = None
        
        if request.image_base64:
            try:
                # Base64デコード
                image_data = base64.b64decode(request.image_base64.split(',')[-1])
                
                # 元の画像をそのままストレージに保存
                file_path, file_name, file_size = storage_service.save_file(
                    file_content=image_data,
                    category="scheduled_post",
                    filename=storage_service.generate_scheduled_post_filename(timestamp),
                    timestamp=timestamp
                )
                
                image_path = file_path
                
            except Exception as e:
                logger.error(f"Failed to process image: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"画像の処理に失敗しました: {str(e)}"
                )
        
        # データベースに記録
        post_id = str(uuid.uuid4())
        scheduled_post = ScheduledPost(
            id=post_id,
            content=request.content,
            image_path=image_path,
            scheduled_datetime=request.scheduled_datetime,
            status="pending"
        )
        
        db.add(scheduled_post)
        db.commit()
        db.refresh(scheduled_post)
        
        logger.info(f"Scheduled post saved: {post_id}")
        
        return ScheduledPostResponse(
            id=scheduled_post.id,
            content=scheduled_post.content,
            image_path=scheduled_post.image_path,
            scheduled_datetime=scheduled_post.scheduled_datetime,
            status=scheduled_post.status,
            created_at=scheduled_post.created_at,
            updated_at=scheduled_post.updated_at,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save scheduled post: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"予約投稿の保存に失敗しました: {str(e)}"
        )


@router.get("/scheduled-posts", response_model=ScheduledPostListResponse)
async def list_scheduled_posts(
    status_filter: Optional[str] = Query(None, description="ステータスでフィルタ (pending, posted, cancelled)"),
    db: Session = Depends(get_db)
):
    """
    予約投稿一覧を取得
    """
    try:
        query = db.query(ScheduledPost)
        
        if status_filter:
            query = query.filter(ScheduledPost.status == status_filter)
        
        posts = query.order_by(ScheduledPost.scheduled_datetime.asc()).all()
        
        return ScheduledPostListResponse(
            success=True,
            posts=[
                ScheduledPostResponse(
                    id=post.id,
                    content=post.content,
                    image_path=post.image_path,
                    scheduled_datetime=post.scheduled_datetime,
                    status=post.status,
                    created_at=post.created_at,
                    updated_at=post.updated_at,
                )
                for post in posts
            ],
            total=len(posts)
        )
    
    except Exception as e:
        logger.error(f"Failed to list scheduled posts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"予約投稿一覧の取得に失敗しました: {str(e)}"
        )


@router.put("/scheduled-posts/{post_id}", response_model=ScheduledPostResponse)
async def update_scheduled_post(
    post_id: str,
    request: UpdateScheduledPostRequest,
    db: Session = Depends(get_db)
):
    """
    予約投稿を更新
    """
    try:
        # データベースから予約投稿を取得
        scheduled_post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
        
        if not scheduled_post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="予約投稿が見つかりません"
            )
        
        # 更新
        if request.content is not None:
            scheduled_post.content = request.content
        
        if request.scheduled_datetime is not None:
            scheduled_post.scheduled_datetime = request.scheduled_datetime
        
        if request.status is not None:
            scheduled_post.status = request.status
        
        # 画像の更新処理（元の画像をそのまま保存）
        if request.image_base64 is not None:
            if request.image_base64 == "":  # 空文字列の場合は画像を削除
                # 既存の画像を削除
                if scheduled_post.image_path:
                    storage_service.delete_file(scheduled_post.image_path)
                scheduled_post.image_path = None
            else:
                try:
                    # Base64デコード
                    image_data = base64.b64decode(request.image_base64.split(',')[-1])
                    
                    # 既存の画像を削除
                    if scheduled_post.image_path:
                        storage_service.delete_file(scheduled_post.image_path)
                    
                    # 元の画像をそのままストレージに保存（合成しない）
                    timestamp = datetime.now(timezone.utc)
                    file_path, file_name, file_size = storage_service.save_file(
                        file_content=image_data,
                        category="scheduled_post",
                        filename=storage_service.generate_scheduled_post_filename(timestamp),
                        timestamp=timestamp
                    )
                    
                    scheduled_post.image_path = file_path
                    
                except Exception as e:
                    logger.error(f"Failed to process image: {e}", exc_info=True)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"画像の処理に失敗しました: {str(e)}"
                    )
        
        db.commit()
        db.refresh(scheduled_post)
        
        logger.info(f"Scheduled post updated: {post_id}")
        
        return ScheduledPostResponse(
            id=scheduled_post.id,
            content=scheduled_post.content,
            image_path=scheduled_post.image_path,
            scheduled_datetime=scheduled_post.scheduled_datetime,
            status=scheduled_post.status,
            created_at=scheduled_post.created_at,
            updated_at=scheduled_post.updated_at,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update scheduled post: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"予約投稿の更新に失敗しました: {str(e)}"
        )


@router.delete("/scheduled-posts/{post_id}", response_model=DeleteFileResponse)
async def delete_scheduled_post(
    post_id: str,
    db: Session = Depends(get_db)
):
    """
    予約投稿を削除
    
    - データベースから予約投稿情報を削除
    - ストレージから画像ファイルを削除
    """
    try:
        # データベースから予約投稿情報を取得
        scheduled_post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
        
        if not scheduled_post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="予約投稿が見つかりません"
            )
        
        # ストレージから画像ファイルを削除
        if scheduled_post.image_path:
            deleted = storage_service.delete_file(scheduled_post.image_path)
            if not deleted:
                logger.warning(f"Image file not found in storage: {scheduled_post.image_path}")
        
        # データベースから削除
        db.delete(scheduled_post)
        db.commit()
        
        logger.info(f"Scheduled post deleted: {post_id}")
        
        return DeleteFileResponse(
            success=True,
            message="予約投稿を削除しました"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete scheduled post: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"予約投稿の削除に失敗しました: {str(e)}"
        )


@router.get("/scheduled-posts/{post_id}/image")
async def get_scheduled_post_image(
    post_id: str,
    db: Session = Depends(get_db)
):
    """
    予約投稿の画像を取得
    """
    try:
        # データベースから予約投稿情報を取得
        scheduled_post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
        
        if not scheduled_post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="予約投稿が見つかりません"
            )
        
        if not scheduled_post.image_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="画像が存在しません"
            )
        
        # ファイルパスを取得
        file_path = storage_service.get_file_path(scheduled_post.image_path)
        
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="画像ファイルがストレージに見つかりません"
            )
        
        from fastapi.responses import Response
        import os
        
        # 画像ファイルを読み込む
        with open(file_path, "rb") as f:
            image_data = f.read()
        
        # ファイル拡張子からメディアタイプを判定
        ext = file_path.suffix.lower()
        media_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        media_type = media_type_map.get(ext, "image/png")
        
        # キャッシュを無効化するためのヘッダーを設定
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        
        return Response(
            content=image_data,
            media_type=media_type,
            headers=headers
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scheduled post image: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"画像の取得に失敗しました: {str(e)}"
        )


@router.get("/storage-stats")
async def get_storage_stats(db: Session = Depends(get_db)):
    """
    ストレージの使用状況を取得
    - ドライブの総容量
    - 使用可能な容量
    - ストレージディレクトリの使用容量
    """
    try:
        # ストレージディレクトリのパスを取得
        storage_path = storage_service.storage_dir
        
        # ストレージディレクトリがあるドライブの容量を取得
        try:
            total, used, free = shutil.disk_usage(storage_path)
        except Exception as e:
            logger.warning(f"Failed to get disk usage: {e}")
            # フォールバック: デフォルト値を使用
            total = 120 * 1024 * 1024 * 1024  # 120GB
            free = total
            used = 0
        
        # ストレージディレクトリの実際の使用容量を計算
        storage_used = 0
        try:
            for root, dirs, files in os.walk(storage_path):
                for file in files:
                    file_path = Path(root) / file
                    try:
                        storage_used += file_path.stat().st_size
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Failed to calculate storage usage: {e}")
        
        # データベースからファイルサイズの合計を取得（検証用）
        db_total_bytes = db.query(func.sum(StorageFile.file_size)).scalar() or 0
        
        return {
            "success": True,
            "drive": {
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "total_gb": total / (1024 ** 3),
                "used_gb": used / (1024 ** 3),
                "free_gb": free / (1024 ** 3),
            },
            "storage_directory": {
                "used_bytes": storage_used,
                "used_gb": storage_used / (1024 ** 3),
                "path": str(storage_path),
            },
            "database_total_bytes": db_total_bytes,
            "database_total_gb": db_total_bytes / (1024 ** 3),
        }
    
    except Exception as e:
        logger.error(f"Failed to get storage stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ストレージ統計の取得に失敗しました: {str(e)}"
        )
