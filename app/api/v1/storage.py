"""
Storage API Routes
Endpoints for file storage management
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import FileResponse
from typing import Optional, List
from datetime import datetime
import logging
import io
import uuid
import pandas as pd
from pathlib import Path

from app.database import get_db
from sqlalchemy.orm import Session
from app.models.storage_file import StorageFile, ReportType, FileCategory
from app.schemas.storage import (
    SaveReportRequest,
    SaveReportResponse,
    StorageFileResponse,
    FileListResponse,
    DeleteFileResponse,
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
