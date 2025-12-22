"""
SNS Automation Backend - Main Application
FastAPI application for YouTube and X analytics
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import sys

from app.core.config import settings
from app.api.v1.router import api_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="SNS Automation API",
    description="Backend API for SNS Management Support Tool - YouTube and X Analytics",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
origins = [
    settings.FRONTEND_URL,
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
    "https://floodlike-crysta-nondrying.ngrok-free.dev"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.get("/")
async def root():
    """Root endpoint - API health check"""
    return {
        "message": "SNS Automation API is running",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "sns-automation-backend",
    }


@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    logger.info("Starting SNS Automation Backend...")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"Frontend URL: {settings.FRONTEND_URL}")
    logger.info(f"X Username: @{settings.X_USERNAME}")
    
    # Create database tables
    if settings.DATABASE_URL:
        from app.database import engine, Base
        from app.models import ShortsScript
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event"""
    logger.info("Shutting down SNS Automation Backend...")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

