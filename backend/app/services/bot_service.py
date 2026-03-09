import httpx
import logging
from datetime import datetime
from app.core.config import settings
from app.core.database import get_supabase
from app.schemas.schemas import MeetingCreate, BotCreateResponse, StatusPollResponse, MeetingStatus
from typing import Optional

logger = logging.getLogger(__name__)


class BotService:
    def __init__(self):
        self.api_key = settings.attendee_api_key
        self.base_url = settings.attendee_api_base_url
        self.supabase = get_supabase()
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=30.0
        )
    
    async def create_bot(self, meeting: MeetingCreate, user_id: str) -> BotCreateResponse:
        """Create a new meeting bot"""
        try:
            # Create meeting record in Supabase
            meeting_data = {
                "meeting_url": str(meeting.meeting_url),
                "status": "pending",
                "user_id": user_id,
                "meeting_metadata": {
                    "bot_name": meeting.bot_name,
                    "join_at": meeting.join_at.isoformat() if meeting.join_at else None
                }
            }
            
            # Insert into Supabase
            result = self.supabase.table("meetings").insert(meeting_data).execute()
            
            if not result.data:
                raise Exception("Failed to create meeting record")
            
            db_meeting = result.data[0]
            
            # Call Attendee API to create bot
            bot_data = await self._create_attendee_bot(meeting)
            
            # Update meeting with bot_id and status
            update_data = {
                "bot_id": bot_data["id"],
                "status": "started"
            }
            
            result = self.supabase.table("meetings").update(update_data).eq("id", db_meeting["id"]).execute()
            
            if not result.data:
                raise Exception("Failed to update meeting with bot_id")
            
            updated_meeting = result.data[0]
            
            return BotCreateResponse(
                id=updated_meeting["id"],
                meeting_url=updated_meeting["meeting_url"],
                bot_id=updated_meeting["bot_id"],
                status=updated_meeting["status"],
                meeting_metadata=updated_meeting["meeting_metadata"],
                created_at=datetime.fromisoformat(updated_meeting["created_at"]),
                updated_at=datetime.fromisoformat(updated_meeting["updated_at"])
            )
            
        except Exception as e:
            logger.error(f"Failed to create bot: {e}")
            raise
    
    async def poll_bot_status(self, bot_id: int, user_id: str) -> StatusPollResponse:
        """Poll for bot status updates"""
        try:
            supabase = get_supabase()
            
            # Get meeting for the current user
            result = supabase.table("meetings").select("*").eq("id", bot_id).eq("user_id", user_id).single().execute()
            
            if result.error:
                if "No rows found" in str(result.error):
                    return StatusPollResponse(
                        status_updated=False,
                        message="Meeting not found"
                    )
                raise Exception(f"Supabase error: {result.error}")
            
            meeting = result.data
            
            if not meeting.get("bot_id"):
                return StatusPollResponse(
                    status_updated=False,
                    message="Bot ID not found for meeting"
                )
            
            # Poll Attendee API
            status_data = await self._get_bot_status(meeting["bot_id"])
            
            # Map status
            attendee_state = status_data.get("state", "unknown")
            new_status = self._map_attendee_status(attendee_state, status_data)
            
            # If new_status is None, no status change needed
            if new_status is None:
                return StatusPollResponse(
                    status_updated=False,
                    message=f"No status change needed for state: {attendee_state}"
                )
            
            # Check if status changed
            status_updated = new_status != meeting["status"]
            
            if status_updated:
                # Update meeting status in Supabase
                update_result = supabase.table("meetings").update({
                    "status": new_status.value
                }).eq("id", bot_id).eq("user_id", user_id).execute()
                
                if update_result.error:
                    raise Exception(f"Supabase error: {update_result.error}")
                
                return StatusPollResponse(
                    status_updated=True,
                    new_status=new_status.value,
                    message=f"Status updated from {meeting['status']} to {new_status.value}"
                )
            
            return StatusPollResponse(
                status_updated=False,
                message="No status change"
            )
            
        except Exception as e:
            logger.error(f"Failed to poll bot status: {e}")
            raise
    
    async def _create_attendee_bot(self, meeting: MeetingCreate) -> dict:
        """Create bot via Attendee API"""
        payload = {
            "meeting_url": str(meeting.meeting_url),
            "bot_name": meeting.bot_name
        }
        
        if meeting.join_at:
            payload["join_at"] = meeting.join_at.isoformat()
        
        # Add webhooks configuration - REQUIRED for bot-level webhooks to work
        webhook_url = f"{settings.webhook_base_url.rstrip('/')}/webhook/"
        payload["webhooks"] = [
            {
                "url": webhook_url,
                "triggers": [
                    "bot.state_change",
                    "transcript.update",
                    "chat_messages.update", 
                    "participant_events.join_leave"
                ]
            }
        ]
        
        response = await self.client.post(
            f"{self.base_url}/api/v1/bots",
            json=payload
        )
        response.raise_for_status()
        
        return response.json()
    
    async def _get_bot_status(self, attendee_bot_id: str) -> dict:
        """Get bot status from Attendee API"""
        response = await self.client.get(
            f"{self.base_url}/api/v1/bots/{attendee_bot_id}"
        )
        response.raise_for_status()
        
        return response.json()
    
    def _map_attendee_status(self, attendee_state: str, status_data: dict) -> MeetingStatus:
        """Map Attendee API state to our MeetingStatus enum"""
        if attendee_state == "ended":
            # Only set FAILED if there's a genuine error
            if (status_data.get("transcription_state") == "complete" and 
                status_data.get("recording_state") == "complete"):
                return MeetingStatus.COMPLETED
            elif (status_data.get("transcription_state") == "error" or 
                  status_data.get("recording_state") == "error"):
                return MeetingStatus.FAILED
            else:
                # Meeting ended but processing might still be ongoing
                return MeetingStatus.COMPLETED
        elif attendee_state == "started":
            return MeetingStatus.STARTED
        elif attendee_state == "pending":
            return MeetingStatus.PENDING
        elif attendee_state == "joining":
            return MeetingStatus.STARTED
        elif attendee_state == "recording":
            return MeetingStatus.STARTED
        elif attendee_state == "transcribing":
            return MeetingStatus.STARTED
        else:
            # Don't default to FAILED for unknown states - keep current status
            return None  # Return None to indicate no status change
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    @staticmethod
    async def update_meeting_status(meeting_id: int, user_id: str, status: str):
        """Update meeting status"""
        from app.schemas.schemas import MeetingStatus
        
        try:
            supabase = get_supabase()
            
            # Convert string status to enum if needed
            if isinstance(status, str):
                status = MeetingStatus(status.upper())
            
            # Update meeting status in Supabase
            result = supabase.table("meetings").update({
                "status": status.value
            }).eq("id", meeting_id).eq("user_id", user_id).execute()
            
            if result.error:
                raise Exception(f"Supabase error: {result.error}")
            
        except Exception as e:
            logger.error(f"Failed to update meeting {meeting_id} status to {status}: {e}")
            raise
    
    @staticmethod
    async def get_meeting_by_bot_id(bot_id: str, user_id: str):
        """Get meeting by bot_id for the current user"""
        try:
            supabase = get_supabase()
            
            result = supabase.table("meetings").select("*").eq("bot_id", bot_id).eq("user_id", user_id).single().execute()
            
            if result.error:
                if "No rows found" in str(result.error):
                    return None
                raise Exception(f"Supabase error: {result.error}")
            
            return result.data
            
        except Exception as e:
            logger.error(f"Failed to get meeting by bot_id {bot_id}: {e}")
            return None 