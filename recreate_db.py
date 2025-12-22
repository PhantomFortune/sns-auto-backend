"""
Recreate database tables (drop and create)
"""
from app.database import engine, Base
from app.models import ShortsScript
from app.core.config import settings
from sqlalchemy import inspect

if __name__ == "__main__":
    if not settings.DATABASE_URL:
        print("ERROR: DATABASE_URL is not set in .env file")
        exit(1)
    
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    if 'shorts_scripts' in tables:
        print("Dropping existing shorts_scripts table...")
        ShortsScript.__table__.drop(engine)
        print("Table dropped successfully!")
    
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")
    
    # Verify columns
    if 'shorts_scripts' in inspector.get_table_names():
        cols = [c['name'] for c in inspector.get_columns('shorts_scripts')]
        print(f"Table columns: {', '.join(cols)}")

