"""
API v1 Router
Aggregates all v1 API routes
"""
from fastapi import APIRouter

from app.api.v1.analytics import router as analytics_router
from app.api.v1.shorts import router as shorts_router
from app.api.v1.live_plan import router as live_plan_router
from app.api.v1.metadata import router as metadata_router
from app.api.v1.cevio import router as cevio_router
from app.api.v1.google_calendar import router as google_calendar_router
from app.api.v1.auto_post import router as auto_post_router
from app.api.v1.websocket import router as websocket_router
from app.api.v1.storage import router as storage_router

# Main v1 router
api_router = APIRouter(prefix="/api/v1")

# Include sub-routers
api_router.include_router(analytics_router)
api_router.include_router(shorts_router)
api_router.include_router(live_plan_router)
api_router.include_router(metadata_router)
api_router.include_router(cevio_router)
api_router.include_router(google_calendar_router)
api_router.include_router(auto_post_router)
api_router.include_router(websocket_router)
api_router.include_router(storage_router)

