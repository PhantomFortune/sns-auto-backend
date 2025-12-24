"""
Google Calendar API Service
Handles reading and writing to Google Calendar
"""
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Google Calendar API scopes
CALENDAR_SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.readonly'
]

# Token file path
CALENDAR_TOKEN_FILE = 'google_calendar_token.json'


class GoogleCalendarService:
    """Service for interacting with Google Calendar API"""
    
    def __init__(self):
        self.service = None
        self.credentials = None
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize Google Calendar API service"""
        try:
            # Load credentials
            creds = self._load_credentials()
            
            if not creds:
                logger.warning("Google Calendar credentials not available")
                return
            
            # Refresh token if expired
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Google Calendar token refreshed successfully")
                    # Save refreshed token
                    self._save_credentials(creds)
                except Exception as e:
                    logger.error(f"Failed to refresh Google Calendar token: {e}")
                    return
            
            # Build Calendar service
            self.service = build('calendar', 'v3', credentials=creds)
            self.credentials = creds
            logger.info("Google Calendar API service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Calendar service: {e}")
    
    def _load_credentials(self) -> Optional[Credentials]:
        """Load OAuth credentials from file or environment variable"""
        creds = None
        token_file = settings.GOOGLE_CALENDAR_TOKEN_JSON or CALENDAR_TOKEN_FILE
        
        # Try to load from environment variable first
        if settings.GOOGLE_CALENDAR_TOKEN_JSON:
            try:
                if os.path.exists(settings.GOOGLE_CALENDAR_TOKEN_JSON):
                    creds = Credentials.from_authorized_user_file(settings.GOOGLE_CALENDAR_TOKEN_JSON)
                    logger.info(f"Loaded Google Calendar token from {settings.GOOGLE_CALENDAR_TOKEN_JSON}")
                else:
                    # Try as JSON string
                    token_data = json.loads(settings.GOOGLE_CALENDAR_TOKEN_JSON)
                    creds = Credentials.from_authorized_user_info(token_data)
                    logger.info("Loaded Google Calendar token from environment variable")
            except Exception as e:
                logger.warning(f"Failed to load token from environment variable: {e}")
        
        # Try to load from file if not loaded from environment
        if not creds and os.path.exists(token_file):
            try:
                creds = Credentials.from_authorized_user_file(token_file)
                logger.info(f"Loaded Google Calendar token from {token_file}")
            except Exception as e:
                logger.warning(f"Failed to load token from file: {e}")
        
        return creds
    
    def _save_credentials(self, creds: Credentials):
        """Save credentials to file"""
        try:
            token_file = settings.GOOGLE_CALENDAR_TOKEN_JSON or CALENDAR_TOKEN_FILE
            token_data = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes
            }
            with open(token_file, 'w') as f:
                json.dump(token_data, f, indent=2)
            logger.info(f"Saved Google Calendar token to {token_file}")
        except Exception as e:
            logger.warning(f"Failed to save token: {e}")
    
    def is_available(self) -> bool:
        """Check if Calendar service is available"""
        return self.service is not None
    
    def list_calendars(self) -> List[Dict]:
        """List all calendars"""
        if not self.service:
            raise Exception("Google Calendar service not initialized")
        
        try:
            calendar_list = self.service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            
            result = []
            for calendar in calendars:
                result.append({
                    'id': calendar.get('id'),
                    'summary': calendar.get('summary'),
                    'description': calendar.get('description'),
                    'primary': calendar.get('primary', False),
                    'timeZone': calendar.get('timeZone'),
                    'backgroundColor': calendar.get('backgroundColor'),
                    'foregroundColor': calendar.get('foregroundColor')
                })
            
            return result
        except HttpError as e:
            logger.error(f"Failed to list calendars: {e}")
            raise
    
    def get_events(
        self,
        calendar_id: str = 'primary',
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 100
    ) -> List[Dict]:
        """Get events from a calendar"""
        if not self.service:
            raise Exception("Google Calendar service not initialized")
        
        try:
            # Set default time range if not provided
            if not time_min:
                time_min = datetime.now(timezone.utc)
            if not time_max:
                time_max = time_min + timedelta(days=30)
            
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            result = []
            for event in events:
                start = event.get('start', {}).get('dateTime') or event.get('start', {}).get('date')
                end = event.get('end', {}).get('dateTime') or event.get('end', {}).get('date')
                
                # Extract type from description
                # Rules: 
                # Priority 1: Check for "#重要" hashtag → 重要イベント (highest priority)
                # Priority 2: Check for "youtube" (case-insensitive) → YouTubeライブ配信
                # Priority 3: Check for "X" (uppercase) → X自動投稿
                # Otherwise → 重要イベント
                description = event.get('description', '')
                event_type = None
                
                # First, try to get type from [種類: ...] prefix (if backend added it)
                if description:
                    import re
                    type_match = re.search(r'\[種類: (.+?)\]', description)
                    if type_match:
                        extracted_type = type_match.group(1)
                        if extracted_type in ["YouTubeライブ配信", "X自動投稿", "重要イベント", "その他"]:
                            event_type = extracted_type
                
                # If not found in prefix, check description for keywords
                if not event_type:
                    description_lower = description.lower()
                    # Priority 1: Check for "#重要" hashtag (highest priority)
                    if '#重要' in description:
                        event_type = "重要イベント"
                    elif 'youtube' in description_lower:
                        # Priority 2: Check for "youtube" (case-insensitive)
                        event_type = "YouTubeライブ配信"
                    elif 'X' in description:
                        # Priority 3: Check for "X" (uppercase) in description
                        event_type = "X自動投稿"
                    else:
                        # Otherwise → その他
                        event_type = "その他"
                
                result.append({
                    'id': event.get('id'),
                    'summary': event.get('summary'),
                    'description': description,
                    'start': start,
                    'end': end,
                    'location': event.get('location'),
                    'status': event.get('status'),
                    'htmlLink': event.get('htmlLink'),
                    'creator': event.get('creator'),
                    'organizer': event.get('organizer'),
                    'colorId': event.get('colorId'),
                    'type': event_type
                })
            
            return result
        except HttpError as e:
            logger.error(f"Failed to get events: {e}")
            raise
    
    def create_event(
        self,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str] = None,
        location: Optional[str] = None,
        calendar_id: str = 'primary',
        color_id: Optional[str] = None,
        event_type: Optional[str] = None
    ) -> Dict:
        """Create a new event in the calendar"""
        if not self.service:
            raise Exception("Google Calendar service not initialized")
        
        try:
            # Build description with type information
            full_description = description or ""
            if event_type:
                type_prefix = f"[種類: {event_type}]\n"
                full_description = type_prefix + full_description if full_description else type_prefix
            
            event = {
                'summary': summary,
                'description': full_description,
                'location': location,
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': str(start_time.tzinfo) if start_time.tzinfo else 'UTC'
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': str(end_time.tzinfo) if end_time.tzinfo else 'UTC'
                }
            }
            
            # Set color if provided
            if color_id:
                event['colorId'] = color_id
            
            created_event = self.service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()
            
            logger.info(f"Created event: {created_event.get('id')} with colorId: {color_id}")
            
            return {
                'id': created_event.get('id'),
                'summary': created_event.get('summary'),
                'description': created_event.get('description'),
                'start': created_event.get('start', {}).get('dateTime'),
                'end': created_event.get('end', {}).get('dateTime'),
                'location': created_event.get('location'),
                'htmlLink': created_event.get('htmlLink'),
                'colorId': created_event.get('colorId')
            }
        except HttpError as e:
            logger.error(f"Failed to create event: {e}")
            raise
    
    def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        calendar_id: str = 'primary',
        color_id: Optional[str] = None,
        event_type: Optional[str] = None
    ) -> Dict:
        """Update an existing event"""
        if not self.service:
            raise Exception("Google Calendar service not initialized")
        
        try:
            # Get existing event
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            # Update fields
            if summary:
                event['summary'] = summary
            if description is not None:
                # Preserve type information if it exists
                existing_desc = event.get('description', '')
                if event_type:
                    # Remove old type prefix if exists
                    import re
                    existing_desc = re.sub(r'^\[種類: .+?\]\n?', '', existing_desc)
                    type_prefix = f"[種類: {event_type}]\n"
                    event['description'] = type_prefix + (description if description else existing_desc)
                else:
                    event['description'] = description
            if location is not None:
                event['location'] = location
            if start_time:
                event['start'] = {
                    'dateTime': start_time.isoformat(),
                    'timeZone': str(start_time.tzinfo) if start_time.tzinfo else 'UTC'
                }
            if end_time:
                event['end'] = {
                    'dateTime': end_time.isoformat(),
                    'timeZone': str(end_time.tzinfo) if end_time.tzinfo else 'UTC'
                }
            
            # Update color if provided (always set if color_id is provided, even if None)
            if color_id is not None:
                event['colorId'] = color_id
            elif event_type:
                # If type is provided but color_id is not, determine color from type
                from app.api.v1.google_calendar import SCHEDULE_TYPE_TO_COLOR_ID
                determined_color_id = SCHEDULE_TYPE_TO_COLOR_ID.get(event_type)
                if determined_color_id:
                    event['colorId'] = determined_color_id
            
            # Update event
            updated_event = self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event
            ).execute()
            
            logger.info(f"Updated event: {updated_event.get('id')} with colorId: {color_id}")
            
            return {
                'id': updated_event.get('id'),
                'summary': updated_event.get('summary'),
                'description': updated_event.get('description'),
                'start': updated_event.get('start', {}).get('dateTime'),
                'end': updated_event.get('end', {}).get('dateTime'),
                'location': updated_event.get('location'),
                'htmlLink': updated_event.get('htmlLink'),
                'colorId': updated_event.get('colorId')
            }
        except HttpError as e:
            logger.error(f"Failed to update event: {e}")
            raise
    
    def delete_event(
        self,
        event_id: str,
        calendar_id: str = 'primary'
    ) -> bool:
        """Delete an event"""
        if not self.service:
            raise Exception("Google Calendar service not initialized")
        
        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            logger.info(f"Deleted event: {event_id}")
            return True
        except HttpError as e:
            logger.error(f"Failed to delete event: {e}")
            raise

