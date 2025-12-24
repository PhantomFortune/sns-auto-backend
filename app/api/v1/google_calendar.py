"""
Google Calendar API OAuth Authentication Endpoints
"""
import os
import json
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Request, Body
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings
from app.services.google_calendar_service import GoogleCalendarService

logger = logging.getLogger(__name__)

router = APIRouter()

# Google Calendar API scopes
CALENDAR_SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.readonly'
]

# Token file path
CALENDAR_TOKEN_FILE = 'google_calendar_token.json'


def get_client_config():
    """Get OAuth client configuration from settings"""
    client_config = None
    client_secret_file = 'client_secret.json'
    
    # Try as file path first
    if settings.YOUTUBE_CLIENT_SECRET_JSON and os.path.exists(settings.YOUTUBE_CLIENT_SECRET_JSON):
        with open(settings.YOUTUBE_CLIENT_SECRET_JSON, 'r') as f:
            client_config = json.load(f)
        # Also save to backend directory for OAuth flow
        with open(client_secret_file, 'w') as f:
            json.dump(client_config, f)
        logger.info(f"Loaded client_secret.json from {settings.YOUTUBE_CLIENT_SECRET_JSON}")
    elif settings.YOUTUBE_CLIENT_SECRET_JSON:
        # Try as JSON string
        try:
            client_config = json.loads(settings.YOUTUBE_CLIENT_SECRET_JSON)
            # Save to file for OAuth flow
            with open(client_secret_file, 'w') as f:
                json.dump(client_config, f)
            logger.info("Saved client_secret.json from environment variable")
        except json.JSONDecodeError:
            logger.error("YOUTUBE_CLIENT_SECRET_JSON is not valid JSON")
            return None
    elif os.path.exists(client_secret_file):
        # Try to load from backend directory
        with open(client_secret_file, 'r') as f:
            client_config = json.load(f)
        logger.info("Loaded client_secret.json from backend directory")
    
    return client_config


def get_redirect_uri():
    """Get redirect URI from settings or construct from request"""
    if settings.GOOGLE_CALENDAR_REDIRECT_URI:
        return settings.GOOGLE_CALENDAR_REDIRECT_URI
    
    # Fallback: try to construct from common patterns
    # This should be set explicitly in production
    logger.warning("GOOGLE_CALENDAR_REDIRECT_URI not set. Please set it in environment variables.")
    return None


@router.get("/google-calendar/auth")
async def start_oauth_flow(request: Request):
    """
    Start Google Calendar OAuth authentication flow
    Returns redirect URL to Google OAuth consent screen
    """
    try:
        client_config = get_client_config()
        if not client_config:
            logger.error("client_config is None - client_secret.json not found or invalid")
            raise HTTPException(
                status_code=500,
                detail="OAuth client configuration not found. Please set YOUTUBE_CLIENT_SECRET_JSON."
            )
        
        logger.info(f"Loaded client_config keys: {list(client_config.keys())}")
        
        redirect_uri = get_redirect_uri()
        if not redirect_uri:
            logger.error("GOOGLE_CALENDAR_REDIRECT_URI not set")
            raise HTTPException(
                status_code=500,
                detail="Redirect URI not configured. Please set GOOGLE_CALENDAR_REDIRECT_URI environment variable."
            )
        
        logger.info(f"Using redirect_uri: {redirect_uri}")
        
        # Extract client info from config
        if 'installed' in client_config:
            client_info = client_config['installed']
            logger.info("Using 'installed' client type")
        elif 'web' in client_config:
            client_info = client_config['web']
            logger.info("Using 'web' client type")
        else:
            logger.error(f"Invalid client_config format. Available keys: {list(client_config.keys())}")
            raise HTTPException(
                status_code=500,
                detail="Invalid client_secret.json format. Expected 'installed' or 'web' key."
            )
        
        client_id = client_info.get('client_id')
        client_secret = client_info.get('client_secret')
        redirect_uris = client_info.get('redirect_uris', [])
        
        logger.info(f"Client ID: {client_id[:20]}..." if client_id else "Client ID: None")
        logger.info(f"Client Secret: {'***' if client_secret else 'None'}")
        logger.info(f"Configured redirect_uris in client_secret.json: {redirect_uris}")
        
        if not client_id or not client_secret:
            logger.error(f"Missing client_id or client_secret. client_id: {bool(client_id)}, client_secret: {bool(client_secret)}")
            raise HTTPException(
                status_code=500,
                detail="client_id or client_secret not found in client_secret.json"
            )
        
        # Verify redirect_uri is in the configured list
        if redirect_uris and redirect_uri not in redirect_uris:
            logger.warning(f"Redirect URI {redirect_uri} not in client_secret.json redirect_uris list: {redirect_uris}")
            logger.warning("This may cause OAuth errors. Please add the redirect URI to Google Cloud Console.")
        
        # Create OAuth flow
        try:
            flow = Flow.from_client_config(
                client_config,
                scopes=CALENDAR_SCOPES,
                redirect_uri=redirect_uri
            )
            logger.info("OAuth flow created successfully")
        except Exception as e:
            logger.error(f"Failed to create OAuth flow: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create OAuth flow: {str(e)}"
            )
        
        # Generate authorization URL
        try:
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='select_account consent'  # Show account selection screen, then force consent screen to get refresh token
            )
            
            logger.info(f"Generated OAuth authorization URL: {authorization_url}")
            logger.info(f"State: {state}")
            
            # Return redirect URL
            return {
                "authorization_url": authorization_url,
                "state": state,
                "message": "Please visit the authorization_url to authenticate",
                "client_id": client_id[:20] + "..." if client_id else None,
                "redirect_uri": redirect_uri
            }
        except Exception as e:
            logger.error(f"Failed to generate authorization URL: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate authorization URL: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start OAuth flow: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start OAuth flow: {str(e)}"
        )


@router.get("/google-calendar/callback")
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None)
):
    """
    OAuth callback endpoint
    Receives authorization code from Google and exchanges it for tokens
    """
    try:
        if error:
            logger.error(f"OAuth error: {error}")
            raise HTTPException(
                status_code=400,
                detail=f"OAuth authentication failed: {error}"
            )
        
        if not code:
            raise HTTPException(
                status_code=400,
                detail="Authorization code not provided"
            )
        
        client_config = get_client_config()
        if not client_config:
            raise HTTPException(
                status_code=500,
                detail="OAuth client configuration not found"
            )
        
        redirect_uri = get_redirect_uri()
        if not redirect_uri:
            raise HTTPException(
                status_code=500,
                detail="Redirect URI not configured"
            )
        
        # Create OAuth flow
        flow = Flow.from_client_config(
            client_config,
            scopes=CALENDAR_SCOPES,
            redirect_uri=redirect_uri
        )
        
        # Exchange authorization code for tokens
        flow.fetch_token(code=code)
        
        # Get credentials
        creds = flow.credentials
        
        # Save credentials to file
        token_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }
        
        # Save to file
        token_file = settings.GOOGLE_CALENDAR_TOKEN_JSON or CALENDAR_TOKEN_FILE
        with open(token_file, 'w') as f:
            json.dump(token_data, f, indent=2)
        
        logger.info(f"Saved Google Calendar OAuth token to {token_file}")
        logger.info(f"Token scopes: {creds.scopes}")
        
        # Test access to Calendar API
        try:
            calendar_service = build('calendar', 'v3', credentials=creds)
            calendar_list = calendar_service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            logger.info(f"Successfully accessed Google Calendar API! Found {len(calendars)} calendar(s)")
        except Exception as e:
            logger.warning(f"Token saved but Calendar API test failed: {e}")
        
        # Redirect to frontend success page
        frontend_url = settings.FRONTEND_URL
        return RedirectResponse(
            url=f"{frontend_url}/?calendar_auth=success",
            status_code=302
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle OAuth callback: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete OAuth flow: {str(e)}"
        )


@router.get("/google-calendar/debug")
async def debug_oauth_config():
    """
    Debug endpoint to check OAuth configuration
    Analyzes the exact cause of OAuth errors
    """
    try:
        client_config = get_client_config()
        redirect_uri = get_redirect_uri()
        
        debug_info = {
            "client_config_exists": client_config is not None,
            "redirect_uri": redirect_uri,
            "redirect_uri_set": redirect_uri is not None,
            "analysis": {}
        }
        
        if client_config:
            debug_info["client_config_keys"] = list(client_config.keys())
            
            if 'installed' in client_config:
                client_info = client_config['installed']
                debug_info["client_type"] = "installed"
                client_id = client_info.get('client_id', 'Not found')
                client_secret = client_info.get('client_secret')
                redirect_uris = client_info.get('redirect_uris', [])
                
                debug_info["client_id"] = client_id[:30] + "..." if len(str(client_id)) > 30 else client_id
                debug_info["client_secret_exists"] = bool(client_secret)
                debug_info["redirect_uris_in_config"] = redirect_uris
                debug_info["project_id"] = client_info.get('project_id', 'Not found')
                
            elif 'web' in client_config:
                client_info = client_config['web']
                debug_info["client_type"] = "web"
                client_id = client_info.get('client_id', 'Not found')
                client_secret = client_info.get('client_secret')
                redirect_uris = client_info.get('redirect_uris', [])
                
                debug_info["client_id"] = client_id[:30] + "..." if len(str(client_id)) > 30 else client_id
                debug_info["client_secret_exists"] = bool(client_secret)
                debug_info["redirect_uris_in_config"] = redirect_uris
                debug_info["project_id"] = client_info.get('project_id', 'Not found')
            else:
                debug_info["client_type"] = "unknown"
                debug_info["error"] = f"Expected 'installed' or 'web' key. Found keys: {list(client_config.keys())}"
                return debug_info
        else:
            debug_info["error"] = "client_secret.json not found or invalid"
            debug_info["analysis"]["primary_issue"] = "client_secret.json not found"
            debug_info["analysis"]["solution"] = "Ensure client_secret.json exists in backend directory or set YOUTUBE_CLIENT_SECRET_JSON environment variable"
            return debug_info
        
        # Analyze the configuration
        analysis = {}
        
        # Check 1: Redirect URI configuration
        if not redirect_uri:
            analysis["redirect_uri_issue"] = "GOOGLE_CALENDAR_REDIRECT_URI not set in environment"
            analysis["redirect_uri_solution"] = "Set GOOGLE_CALENDAR_REDIRECT_URI in .env file"
        elif redirect_uris and redirect_uri not in redirect_uris:
            analysis["redirect_uri_issue"] = f"Redirect URI '{redirect_uri}' not in client_secret.json redirect_uris list"
            analysis["redirect_uri_solution"] = f"Add '{redirect_uri}' to Google Cloud Console OAuth client's 'Authorized redirect URIs'"
            analysis["redirect_uri_mismatch"] = True
        else:
            analysis["redirect_uri_status"] = "OK"
            if redirect_uris:
                analysis["redirect_uri_match"] = redirect_uri in redirect_uris
        
        # Check 2: Client ID validity
        if not client_id or client_id == 'Not found':
            analysis["client_id_issue"] = "client_id not found in client_secret.json"
            analysis["client_id_solution"] = "Download a valid client_secret.json from Google Cloud Console"
        else:
            analysis["client_id_status"] = "Found"
        
        # Check 3: Client Secret validity
        if not client_secret:
            analysis["client_secret_issue"] = "client_secret not found in client_secret.json"
            analysis["client_secret_solution"] = "Download a valid client_secret.json from Google Cloud Console"
        else:
            analysis["client_secret_status"] = "Found"
        
        # Error analysis based on "OAuth client was not found" / "invalid_client"
        error_analysis = {
            "error_type": "OAuth client was not found / invalid_client (401)",
            "possible_causes": []
        }
        
        if redirect_uris and redirect_uri not in redirect_uris:
            error_analysis["possible_causes"].append({
                "cause": "Redirect URI not registered in Google Cloud Console",
                "probability": "HIGH",
                "description": "The redirect URI used in the OAuth flow is not in the 'Authorized redirect URIs' list in Google Cloud Console",
                "solution": f"Add '{redirect_uri}' to the OAuth client's 'Authorized redirect URIs' in Google Cloud Console"
            })
        
        error_analysis["possible_causes"].append({
            "cause": "OAuth client belongs to different Google account/project",
            "probability": "HIGH",
            "description": f"The OAuth client (Project: {client_info.get('project_id', 'Unknown')}) belongs to a different Google account. The logged-in account cannot access this OAuth client.",
            "solution": "Either: 1) Login with the account that owns the project, or 2) Create a new OAuth client in your own Google Cloud project"
        })
        
        error_analysis["possible_causes"].append({
            "cause": "OAuth client ID deleted or invalid in Google Cloud Console",
            "probability": "MEDIUM",
            "description": "The client_id in client_secret.json does not match any OAuth client in Google Cloud Console",
            "solution": "Verify the OAuth client exists in Google Cloud Console and download a fresh client_secret.json"
        })
        
        error_analysis["possible_causes"].append({
            "cause": "OAuth client type mismatch",
            "probability": "LOW",
            "description": f"client_secret.json uses '{debug_info.get('client_type')}' type but Google Cloud Console has a different type",
            "solution": "Ensure the OAuth client type in Google Cloud Console matches the client_secret.json structure"
        })
        
        debug_info["analysis"] = analysis
        debug_info["error_analysis"] = error_analysis
        
        # Determine most likely cause
        project_id = debug_info.get('project_id', 'Unknown')
        
        if redirect_uris and redirect_uri not in redirect_uris:
            debug_info["most_likely_cause"] = "Redirect URI not registered in Google Cloud Console"
            debug_info["confidence"] = "HIGH"
        elif not client_id or client_id == 'Not found':
            debug_info["most_likely_cause"] = "Invalid or missing client_id"
            debug_info["confidence"] = "HIGH"
        else:
            debug_info["most_likely_cause"] = f"OAuth client belongs to different Google account/project (Project: {project_id}). The logged-in account cannot access this OAuth client."
            debug_info["confidence"] = "HIGH"
            debug_info["recommended_action"] = "Login with the account that owns the project, or create a new OAuth client in your own Google Cloud project"
        
        return debug_info
    except Exception as e:
        logger.error(f"Debug endpoint error: {e}", exc_info=True)
        return {
            "error": str(e),
            "traceback": str(e.__traceback__) if hasattr(e, '__traceback__') else None
        }


@router.get("/google-calendar/status")
async def get_calendar_status():
    """
    Check Google Calendar API connection status
    """
    try:
        # Load credentials
        creds = None
        token_file = settings.GOOGLE_CALENDAR_TOKEN_JSON or CALENDAR_TOKEN_FILE
        
        if os.path.exists(token_file):
            try:
                creds = Credentials.from_authorized_user_file(token_file)
                logger.info(f"Loaded token from {token_file}")
            except Exception as e:
                logger.warning(f"Failed to load token: {e}")
                return {
                    "connected": False,
                    "error": f"Failed to load token: {str(e)}"
                }
        else:
            return {
                "connected": False,
                "error": "No token file found. Please authenticate first."
            }
        
        # Refresh token if expired
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(GoogleRequest())
                logger.info("Token refreshed successfully")
            except Exception as e:
                return {
                    "connected": False,
                    "error": f"Failed to refresh token: {str(e)}"
                }
        
        # Check scopes
        token_scopes = creds.scopes if hasattr(creds, 'scopes') and creds.scopes else []
        has_calendar_scope = any('calendar' in scope.lower() for scope in token_scopes)
        
        if not has_calendar_scope:
            return {
                "connected": False,
                "error": "Token does not have Google Calendar API scope",
                "current_scopes": token_scopes
            }
        
        # Test Calendar API access
        try:
            calendar_service = build('calendar', 'v3', credentials=creds)
            calendar_list = calendar_service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            
            return {
                "connected": True,
                "scopes": token_scopes,
                "calendars_count": len(calendars),
                "calendars": [
                    {
                        "id": cal.get('id'),
                        "summary": cal.get('summary'),
                        "primary": cal.get('primary', False)
                    }
                    for cal in calendars[:5]  # Return first 5 calendars
                ]
            }
        except HttpError as e:
            error_details = json.loads(e.content.decode('utf-8'))
            error_reason = error_details.get('error', {}).get('errors', [{}])[0].get('reason', 'unknown')
            return {
                "connected": False,
                "error": f"Calendar API access failed: {error_reason}",
                "scopes": token_scopes
            }
        except Exception as e:
            return {
                "connected": False,
                "error": f"Failed to access Calendar API: {str(e)}",
                "scopes": token_scopes
            }
            
    except Exception as e:
        logger.error(f"Failed to check calendar status: {e}", exc_info=True)
        return {
            "connected": False,
            "error": str(e)
        }


# Pydantic models for event operations
class CreateEventRequest(BaseModel):
    title: str
    date: str  # YYYY-MM-DD format
    startTime: str  # HH:mm format
    endTime: str  # HH:mm format
    description: Optional[str] = None
    type: Optional[str] = None  # Schedule type: "YouTubeライブ配信", "X自動投稿", "重要イベント", "その他"
    calendarId: str = "primary"


class UpdateEventRequest(BaseModel):
    title: Optional[str] = None
    date: Optional[str] = None  # YYYY-MM-DD format
    startTime: Optional[str] = None  # HH:mm format
    endTime: Optional[str] = None  # HH:mm format
    description: Optional[str] = None
    type: Optional[str] = None  # Schedule type: "YouTubeライブ配信", "X自動投稿", "重要イベント", "その他"
    calendarId: str = "primary"


# Map schedule types to Google Calendar color IDs
# Google Calendar color IDs: 
# 1=Lavender, 2=Sage, 3=Grape, 4=Flamingo, 5=Banana, 
# 6=Tangerine, 7=Peacock, 8=Graphite, 9=Blueberry, 10=Basil, 11=Tomato
# Frontend colors: YouTube=#fbbf24(yellow), X=#3b82f6(blue), Event=#dc2626(red)
SCHEDULE_TYPE_TO_COLOR_ID = {
    "YouTubeライブ配信": "5",  # Banana (黄色) - matches frontend #fbbf24
    "X自動投稿": "9",  # Blueberry (青) - matches frontend #3b82f6
    "重要イベント": "11",  # Tomato (赤) - matches frontend #dc2626
    "その他": "8",  # Graphite (グレー) - matches frontend #9aa0a6
}


@router.post("/google-calendar/events")
async def create_calendar_event(event_data: CreateEventRequest):
    """
    Create a new event in Google Calendar
    """
    try:
        calendar_service = GoogleCalendarService()
        
        if not calendar_service.is_available():
            raise HTTPException(
                status_code=401,
                detail="Google Calendar not connected. Please authenticate first."
            )
        
        # Parse date and time
        date_str = event_data.date
        start_time_str = event_data.startTime
        end_time_str = event_data.endTime
        
        # Combine date and time
        start_datetime_str = f"{date_str}T{start_time_str}:00"
        end_datetime_str = f"{date_str}T{end_time_str}:00"
        
        # Parse to datetime (assume JST timezone)
        from datetime import timezone, timedelta
        jst = timezone(timedelta(hours=9))
        
        start_datetime = datetime.fromisoformat(start_datetime_str).replace(tzinfo=jst)
        end_datetime = datetime.fromisoformat(end_datetime_str).replace(tzinfo=jst)
        
        # Handle day overflow: if end time is earlier than start time, add 1 day
        # This handles cases like 22:50-1:30 (overnight) or 9:00-7:00 (22 hours)
        if end_datetime <= start_datetime:
            end_datetime = end_datetime + timedelta(days=1)
        
        # Get color ID based on type
        color_id = None
        if event_data.type:
            color_id = SCHEDULE_TYPE_TO_COLOR_ID.get(event_data.type)
        
        # Create event
        created_event = calendar_service.create_event(
            summary=event_data.title,
            start_time=start_datetime,
            end_time=end_datetime,
            description=event_data.description,
            calendar_id=event_data.calendarId,
            color_id=color_id,
            event_type=event_data.type
        )
        
        logger.info(f"Created Google Calendar event: {created_event.get('id')}")
        
        # Notify WebSocket clients about schedule change
        try:
            from app.api.v1.websocket import manager
            await manager.broadcast({
                "type": "schedule_update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.warning(f"Failed to notify WebSocket clients: {e}")
        
        return {
            "success": True,
            "event": {
                "id": created_event.get('id'),
                "title": created_event.get('summary'),
                "start": created_event.get('start'),
                "end": created_event.get('end'),
                "htmlLink": created_event.get('htmlLink')
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to create calendar event: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create calendar event: {str(e)}"
        )


@router.put("/google-calendar/events/{event_id}")
async def update_calendar_event(event_id: str, event_data: UpdateEventRequest):
    """
    Update an existing event in Google Calendar
    """
    try:
        calendar_service = GoogleCalendarService()
        
        if not calendar_service.is_available():
            raise HTTPException(
                status_code=401,
                detail="Google Calendar not connected. Please authenticate first."
            )
        
        # Prepare update parameters
        summary = event_data.title
        description = event_data.description
        start_time = None
        end_time = None
        
        # Parse date and time if provided
        if event_data.date and event_data.startTime:
            from datetime import timezone, timedelta
            jst = timezone(timedelta(hours=9))
            
            start_datetime_str = f"{event_data.date}T{event_data.startTime}:00"
            start_time = datetime.fromisoformat(start_datetime_str).replace(tzinfo=jst)
        
        if event_data.date and event_data.endTime:
            from datetime import timezone, timedelta
            jst = timezone(timedelta(hours=9))
            
            end_datetime_str = f"{event_data.date}T{event_data.endTime}:00"
            end_time = datetime.fromisoformat(end_datetime_str).replace(tzinfo=jst)
            
            # Handle day overflow: if end time is earlier than start time, add 1 day
            # This handles cases like 22:50-1:30 (overnight) or 9:00-7:00 (22 hours)
            if start_time and end_time <= start_time:
                end_time = end_time + timedelta(days=1)
        
        # Get color ID based on type
        color_id = None
        if event_data.type:
            color_id = SCHEDULE_TYPE_TO_COLOR_ID.get(event_data.type)
        
        # Update event
        updated_event = calendar_service.update_event(
            event_id=event_id,
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            calendar_id=event_data.calendarId,
            color_id=color_id,
            event_type=event_data.type
        )
        
        logger.info(f"Updated Google Calendar event: {event_id}")
        
        # Notify WebSocket clients about schedule change
        try:
            from app.api.v1.websocket import manager
            await manager.broadcast({
                "type": "schedule_update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.warning(f"Failed to notify WebSocket clients: {e}")
        
        return {
            "success": True,
            "event": {
                "id": updated_event.get('id'),
                "title": updated_event.get('summary'),
                "start": updated_event.get('start'),
                "end": updated_event.get('end'),
                "htmlLink": updated_event.get('htmlLink')
            }
        }
        
    except HttpError as e:
        if e.resp.status == 404:
            raise HTTPException(
                status_code=404,
                detail="Event not found"
            )
        logger.error(f"Failed to update calendar event: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update calendar event: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to update calendar event: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update calendar event: {str(e)}"
        )


@router.delete("/google-calendar/events/{event_id}")
async def delete_calendar_event(event_id: str, calendar_id: str = Query(default="primary")):
    """
    Delete an event from Google Calendar
    """
    try:
        calendar_service = GoogleCalendarService()
        
        if not calendar_service.is_available():
            raise HTTPException(
                status_code=401,
                detail="Google Calendar not connected. Please authenticate first."
            )
        
        # Delete event
        calendar_service.delete_event(
            event_id=event_id,
            calendar_id=calendar_id
        )
        
        logger.info(f"Deleted Google Calendar event: {event_id}")
        
        # Notify WebSocket clients about schedule change
        try:
            from app.api.v1.websocket import manager
            await manager.broadcast({
                "type": "schedule_update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.warning(f"Failed to notify WebSocket clients: {e}")
        
        return {
            "success": True,
            "message": "Event deleted successfully"
        }
        
    except HttpError as e:
        if e.resp.status == 404:
            raise HTTPException(
                status_code=404,
                detail="Event not found"
            )
        logger.error(f"Failed to delete calendar event: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete calendar event: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to delete calendar event: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete calendar event: {str(e)}"
        )


@router.get("/google-calendar/events")
async def get_calendar_events(
    calendar_id: str = Query(default="primary"),
    time_min: Optional[str] = Query(default=None, description="Start time in ISO format (YYYY-MM-DDTHH:mm:ss)"),
    time_max: Optional[str] = Query(default=None, description="End time in ISO format (YYYY-MM-DDTHH:mm:ss)"),
    max_results: int = Query(default=100, ge=1, le=2500)
):
    """
    Get events from Google Calendar
    """
    try:
        calendar_service = GoogleCalendarService()
        
        if not calendar_service.is_available():
            raise HTTPException(
                status_code=401,
                detail="Google Calendar not connected. Please authenticate first."
            )
        
        # Parse time_min and time_max if provided
        from datetime import timezone, timedelta
        jst = timezone(timedelta(hours=9))
        
        time_min_dt = None
        time_max_dt = None
        
        if time_min:
            try:
                time_min_dt = datetime.fromisoformat(time_min.replace('Z', '+00:00'))
                if time_min_dt.tzinfo is None:
                    time_min_dt = time_min_dt.replace(tzinfo=jst)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid time_min format: {time_min}. Use ISO format (YYYY-MM-DDTHH:mm:ss)"
                )
        
        if time_max:
            try:
                time_max_dt = datetime.fromisoformat(time_max.replace('Z', '+00:00'))
                if time_max_dt.tzinfo is None:
                    time_max_dt = time_max_dt.replace(tzinfo=jst)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid time_max format: {time_max}. Use ISO format (YYYY-MM-DDTHH:mm:ss)"
                )
        
        # Get events
        events = calendar_service.get_events(
            calendar_id=calendar_id,
            time_min=time_min_dt,
            time_max=time_max_dt,
            max_results=max_results
        )
        
        logger.info(f"Retrieved {len(events)} events from Google Calendar")
        
        return {
            "success": True,
            "events": events,
            "count": len(events)
        }
        
    except HttpError as e:
        logger.error(f"Failed to get calendar events: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get calendar events: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to get calendar events: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get calendar events: {str(e)}"
        )

