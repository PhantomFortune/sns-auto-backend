"""
Initialize database tables
"""
from app.database import engine, Base
from app.models import ShortsScript
from app.core.config import settings

if __name__ == "__main__":
    if not settings.DATABASE_URL:
        print("ERROR: DATABASE_URL is not set in .env file")
        exit(1)
    
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

