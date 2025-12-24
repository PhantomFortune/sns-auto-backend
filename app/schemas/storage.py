"""
Storage API Schemas
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.storage_file import ReportType, FileCategory


class SaveReportRequest(BaseModel):
    """レポート保存リクエスト"""
    report_type: ReportType  # "youtube_analytics" or "x_analytics"
    analytics_data: dict  # 分析データ（JSON形式）
    improvement_suggestion: dict  # 改善提案データ（JSON形式）
    period: str  # 分析期間（例: "過去1週間"）
    description: Optional[str] = None  # 説明（任意）


class SaveReportResponse(BaseModel):
    """レポート保存レスポンス"""
    success: bool
    file_id: str
    file_name: str
    file_path: str
    file_size: int
    message: str


class StorageFileResponse(BaseModel):
    """ストレージファイル情報レスポンス"""
    id: str
    category: FileCategory
    report_type: Optional[ReportType]
    file_name: str
    file_path: str
    file_size: int
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


class FileListResponse(BaseModel):
    """ファイル一覧レスポンス"""
    success: bool
    files: list[StorageFileResponse]
    total: int


class DeleteFileResponse(BaseModel):
    """ファイル削除レスポンス"""
    success: bool
    message: str


class DownloadFileResponse(BaseModel):
    """ファイルダウンロードレスポンス"""
    success: bool
    file_path: str
    file_name: str
    file_size: int

