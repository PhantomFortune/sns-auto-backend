"""
Application configuration using pydantic-settings
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os
from urllib.parse import quote_plus


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    
    # X (Twitter) API Credentials
    X_API_KEY: str = ""
    X_API_KEY_SECRET: str = ""
    X_ACCESS_TOKEN: str = ""
    X_ACCESS_TOKEN_SECRET: str = ""
    X_BEARER_TOKEN: str = ""
    
    # X Account
    X_USERNAME: str = "shelessV"
    
    # YouTube API
    YOUTUBE_API_KEY: str = ""
    YOUTUBE_CHANNEL_ID: str = "UCYPOx7xRlFDKiNSj2n-2Yuw"
    YOUTUBE_CLIENT_SECRET_JSON: Optional[str] = None  # Path to client_secret.json or JSON string
    YOUTUBE_REFRESH_TOKEN: Optional[str] = None  # OAuth2 refresh token (if available)
    YOUTUBE_TOKEN_JSON: Optional[str] = None  # Path to youtube_token.json or JSON string
    
    # Google Calendar API
    GOOGLE_CALENDAR_REDIRECT_URI: Optional[str] = None  # OAuth redirect URI (e.g., https://your-ngrok-url.ngrok-free.app/api/v1/google-calendar/callback)
    GOOGLE_CALENDAR_TOKEN_JSON: Optional[str] = None  # Path to google_calendar_token.json or JSON string
    
    # CORS
    FRONTEND_URL: str = "http://localhost:5173"

    # OpenAI API (for improvement suggestions)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    # Database
    # Note: If password contains @, use URL encoding: @ becomes %40
    # Example: postgresql://postgres:WSXwsx%40321@localhost:5432/youtube_automation
    DATABASE_URL: str = ""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Fix DATABASE_URL if password contains @ symbol
        if self.DATABASE_URL and "://" in self.DATABASE_URL:
            try:
                parts = self.DATABASE_URL.split("://")
                if len(parts) == 2:
                    scheme, rest = parts
                    # Count @ symbols - if more than 1, password likely contains @
                    at_count = rest.count("@")
                    if at_count > 1:
                        # Find the last @ which should be the separator between auth and host
                        last_at_index = rest.rfind("@")
                        auth_part = rest[:last_at_index]
                        host_part = rest[last_at_index + 1:]
                        
                        if ":" in auth_part:
                            user, password = auth_part.split(":", 1)
                            # URL encode the password
                            encoded_password = quote_plus(password)
                            self.DATABASE_URL = f"{scheme}://{user}:{encoded_password}@{host_part}"
            except Exception:
                # If parsing fails, use as-is
                pass
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields like DATABASE_URL if not needed


# Create settings instance
settings = Settings()

