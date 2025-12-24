"""
Storage File Database Models
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from app.database import Base
import enum


class ReportType(str, enum.Enum):
    """レポートタイプ"""
    YOUTUBE_ANALYTICS = "youtube_analytics"
    X_ANALYTICS = "x_analytics"


class FileCategory(str, enum.Enum):
    """ファイルカテゴリ"""
    REPORT = "report"  # レポート
    SCHEDULED_POST = "scheduled_post"  # X投稿登録簿


class StorageFile(Base):
    """ストレージファイル管理用データベースモデル"""
    __tablename__ = "storage_files"

    id = Column(String, primary_key=True, index=True)
    category = Column(SQLEnum(FileCategory), nullable=False, index=True)  # レポート or X投稿登録簿
    report_type = Column(SQLEnum(ReportType), nullable=True, index=True)  # YouTube分析 or X分析 (レポートの場合のみ)
    file_name = Column(String, nullable=False, index=True)  # ファイル名（例: YouTube_Analytics_Report_25-8-17-15-30-45.xlsx）
    file_path = Column(String, nullable=False, unique=True, index=True)  # ストレージ内の相対パス
    file_size = Column(Integer, nullable=False)  # ファイルサイズ（バイト）
    description = Column(Text, nullable=True)  # 説明（任意）
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<StorageFile(id={self.id}, category={self.category}, file_name={self.file_name})>"


class ScheduledPost(Base):
    """X投稿登録簿用データベースモデル"""
    __tablename__ = "scheduled_posts"

    id = Column(String, primary_key=True, index=True)
    content = Column(Text, nullable=False)  # 投稿テキスト
    image_path = Column(String, nullable=True)  # 画像ファイルパス（storage/X投稿登録簿/内の相対パス）
    scheduled_datetime = Column(DateTime(timezone=True), nullable=False, index=True)  # 予約投稿日時
    status = Column(String, nullable=False, default="pending", index=True)  # pending, posted, cancelled
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<ScheduledPost(id={self.id}, scheduled_datetime={self.scheduled_datetime}, status={self.status})>"

