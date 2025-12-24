"""
Storage Service
Handles file storage operations for reports and scheduled posts
"""
import os
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class StorageService:
    """ストレージサービス - ファイル保存と管理"""
    
    def __init__(self):
        # Get base directory (backend folder)
        self.base_dir = Path(__file__).parent.parent.parent
        self.storage_dir = self.base_dir / "storage"
        
        # Storage subdirectories
        self.report_dir = self.storage_dir / "レポート登録簿"
        self.youtube_report_dir = self.report_dir / "YouTube分析レポート登録簿"
        self.x_report_dir = self.report_dir / "X分析レポート登録簿"
        self.scheduled_post_dir = self.storage_dir / "X投稿登録簿"
    
    def generate_report_filename(self, report_type: str, timestamp: Optional[datetime] = None) -> str:
        """
        レポートファイル名を生成
        形式: {ReportType}_Analytics_Report_YY-M-D-H-M-S.xlsx
        例: YouTube_Analytics_Report_25-8-17-15-30-45.xlsx
        
        Args:
            report_type: "youtube_analytics" or "x_analytics"
            timestamp: タイムスタンプ（Noneの場合は現在時刻）
        
        Returns:
            ファイル名（拡張子付き）
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # ファイル名のプレフィックス
        if report_type == "youtube_analytics":
            prefix = "YouTube_Analytics_Report"
        elif report_type == "x_analytics":
            prefix = "X_Analytics_Report"
        else:
            prefix = "Report"
        
        # 日時をフォーマット: YY-M-D-H-M-S（秒単位まで）
        year = timestamp.year % 100  # 2桁の年
        month = timestamp.month
        day = timestamp.day
        hour = timestamp.hour
        minute = timestamp.minute
        second = timestamp.second
        
        # 一意性を確保するため、マイクロ秒も考慮（同じ秒内で複数回生成される可能性があるため）
        microsecond = timestamp.microsecond
        
        # ファイル名: {prefix}_YY-M-D-H-M-S-{microsecond}.xlsx
        # マイクロ秒の下3桁を使用（ミリ秒相当）
        filename = f"{prefix}_{year}-{month}-{day}-{hour}-{minute}-{second}-{microsecond // 1000:03d}.xlsx"
        
        return filename
    
    def get_storage_path(self, category: str, report_type: Optional[str] = None) -> Path:
        """
        ストレージパスを取得
        
        Args:
            category: "report" or "scheduled_post"
            report_type: "youtube_analytics" or "x_analytics" (categoryが"report"の場合のみ)
        
        Returns:
            ストレージディレクトリのPath
        """
        if category == "report":
            if report_type == "youtube_analytics":
                return self.youtube_report_dir
            elif report_type == "x_analytics":
                return self.x_report_dir
            else:
                return self.report_dir
        elif category == "scheduled_post":
            return self.scheduled_post_dir
        else:
            return self.storage_dir
    
    def save_file(
        self,
        file_content: bytes,
        category: str,
        report_type: Optional[str] = None,
        filename: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> Tuple[str, str, int]:
        """
        ファイルをストレージに保存
        
        Args:
            file_content: ファイルのバイトコンテンツ
            category: "report" or "scheduled_post"
            report_type: "youtube_analytics" or "x_analytics" (categoryが"report"の場合のみ)
            filename: ファイル名（Noneの場合は自動生成）
            timestamp: タイムスタンプ（ファイル名生成用）
        
        Returns:
            (file_path, file_name, file_size) のタプル
            file_path: ストレージ内の相対パス（データベース保存用）
            file_name: ファイル名
            file_size: ファイルサイズ（バイト）
        """
        # ストレージディレクトリを取得
        storage_path = self.get_storage_path(category, report_type)
        
        # ディレクトリが存在しない場合は作成
        storage_path.mkdir(parents=True, exist_ok=True)
        
        # ファイル名を生成
        if filename is None:
            if category == "report" and report_type:
                filename = self.generate_report_filename(report_type, timestamp)
            else:
                # デフォルトファイル名
                if timestamp is None:
                    timestamp = datetime.now()
                year = timestamp.year % 100
                month = timestamp.month
                day = timestamp.day
                hour = timestamp.hour
                minute = timestamp.minute
                second = timestamp.second
                microsecond = timestamp.microsecond
                filename = f"file_{year}-{month}-{day}-{hour}-{minute}-{second}-{microsecond // 1000:03d}.xlsx"
        
        # ファイルパス
        file_path = storage_path / filename
        
        # ファイルが既に存在する場合は、一意なファイル名を生成
        if file_path.exists():
            # ファイル名にUUIDを追加して一意性を確保
            name_part = file_path.stem
            ext_part = file_path.suffix
            unique_id = str(uuid.uuid4())[:8]
            filename = f"{name_part}_{unique_id}{ext_part}"
            file_path = storage_path / filename
        
        # ファイルを保存
        try:
            with open(file_path, 'wb') as f:
                f.write(file_content)
            
            file_size = len(file_content)
            
            # 相対パスを取得（storage/から始まるパス）
            relative_path = file_path.relative_to(self.storage_dir)
            relative_path_str = str(relative_path).replace('\\', '/')  # Windowsパスを統一
            
            logger.info(f"File saved: {relative_path_str} ({file_size} bytes)")
            
            return relative_path_str, filename, file_size
        
        except Exception as e:
            logger.error(f"Failed to save file: {e}")
            raise
    
    def get_file_path(self, relative_path: str) -> Path:
        """
        相対パスから絶対パスを取得
        
        Args:
            relative_path: ストレージ内の相対パス
        
        Returns:
            絶対パスのPath
        """
        return self.storage_dir / relative_path
    
    def delete_file(self, relative_path: str) -> bool:
        """
        ファイルを削除
        
        Args:
            relative_path: ストレージ内の相対パス
        
        Returns:
            削除成功したかどうか
        """
        try:
            file_path = self.get_file_path(relative_path)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"File deleted: {relative_path}")
                return True
            else:
                logger.warning(f"File not found: {relative_path}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            return False
    
    def file_exists(self, relative_path: str) -> bool:
        """
        ファイルが存在するか確認
        
        Args:
            relative_path: ストレージ内の相対パス
        
        Returns:
            ファイルが存在するかどうか
        """
        file_path = self.get_file_path(relative_path)
        return file_path.exists()


# シングルトンインスタンス
storage_service = StorageService()

