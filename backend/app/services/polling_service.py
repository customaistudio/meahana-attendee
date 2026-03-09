import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict
from app.core.database import get_supabase
from app.services.bot_service import BotService
from app.services.analysis_service import AnalysisService
from app.services.transcript_service import TranscriptService
from app.core.config import settings
import httpx

logger = logging.getLogger(__name__)


class PollingService:
    """Service for polling Attendee API to check meeting status and process transcripts as backup"""
    
    def __init__(self):
        self.is_running = False
        self.polling_interval = settings.polling_interval
        self.max_retries = settings.polling_max_retries
        self.retry_delay = settings.polling_retry_delay
        
    async def start_polling(self):
        """Start the polling service"""
        if self.is_running:
            return
            
        self.is_running = True
        
        while self.is_running:
            try:
                await self._poll_completed_meetings()
                await asyncio.sleep(self.polling_interval)
            except Exception as e:
                logger.error(f"Error in polling service: {e}")
                await asyncio.sleep(self.retry_delay)
    
    async def stop_polling(self):
        """Stop the polling service"""
        self.is_running = False
    
    async def _poll_completed_meetings(self, user_id: str = None):
        """Poll for meetings that should be completed but haven't been processed"""
        try:
            # First check if we have missing critical events that require polling fallback
            from app.services.webhook_delivery_service import webhook_delivery_service
            await webhook_delivery_service.check_critical_event_fallbacks(user_id)
            
            # Only do general polling if no critical events are missing
            pending_meetings = await self._get_pending_meetings(user_id)
            
            if not pending_meetings:
                return
            
            for meeting in pending_meetings:
                try:
                    await self._check_meeting_status(meeting, user_id)
                except Exception as e:
                    logger.error(f"Error checking meeting {meeting['id']}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error in meeting status polling: {e}")
    
    async def _get_pending_meetings(self, user_id: str = None) -> List[Dict]:
        """Get meetings that are in progress and might be completed"""
        try:
            supabase = get_supabase()
            
            # Find meetings that are in progress and haven't been updated recently
            # This helps catch meetings where webhooks failed
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=10)  # Check meetings older than 10 minutes
            
            query = supabase.table("meetings").select("*").in_("status", ["PENDING", "STARTED"]).lt("updated_at", cutoff_time.isoformat())
            
            if user_id:
                query = query.eq("user_id", user_id)
            
            result = query.execute()
            
            if result.error:
                logger.error(f"Supabase error: {result.error}")
                return []
            
            return result.data
            
        except Exception as e:
            logger.error(f"Error getting pending meetings: {e}")
            return []
    
    async def _check_meeting_status(self, meeting: Dict, user_id: str = None):
        """Check the status of a specific meeting via Attendee API"""
        try:
            if not meeting.get("bot_id"):
                logger.warning(f"Meeting {meeting['id']} has no bot_id, skipping status check")
                return
            
            # Use BotService to check status
            bot_service = BotService()
            status_response = await bot_service.poll_bot_status(meeting["id"], user_id or meeting["user_id"])
            
            if status_response.status_updated:
                logger.info(f"Meeting {meeting['id']} status updated to {status_response.new_status}")
                
                # If meeting is completed, trigger analysis
                if status_response.new_status == "COMPLETED":
                    await self._trigger_analysis_for_completed_meeting(meeting["id"], user_id or meeting["user_id"])
                    
        except Exception as e:
            logger.error(f"Error checking meeting {meeting['id']} status: {e}")
    
    async def _trigger_analysis_for_completed_meeting(self, meeting_id: int, user_id: str):
        """Trigger analysis for a completed meeting"""
        try:
            analysis_service = AnalysisService()
            await analysis_service.enqueue_analysis(meeting_id, user_id)
            logger.info(f"Analysis triggered for completed meeting {meeting_id}")
            
        except Exception as e:
            logger.error(f"Error triggering analysis for meeting {meeting_id}: {e}")
    
    async def manual_check_meeting(self, meeting_id: int, user_id: str) -> bool:
        """Manually check a specific meeting for completion status"""
        try:
            supabase = get_supabase()
            
            # Get the meeting
            result = supabase.table("meetings").select("*").eq("id", meeting_id).eq("user_id", user_id).single().execute()
            
            if result.error:
                logger.error(f"Meeting {meeting_id} not found: {result.error}")
                return False
            
            meeting = result.data
            
            # Check the meeting status
            await self._check_meeting_status(meeting, user_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error manually checking meeting {meeting_id}: {e}")
            return False
    
    async def _get_meeting_by_bot_id(self, bot_id: str, user_id: str = None) -> Optional[Dict]:
        """Get meeting by bot_id"""
        try:
            supabase = get_supabase()
            
            query = supabase.table("meetings").select("*").eq("bot_id", bot_id)
            
            if user_id:
                query = query.eq("user_id", user_id)
            
            result = query.single().execute()
            
            if result.error:
                if "No rows found" in str(result.error):
                    return None
                logger.error(f"Supabase error: {result.error}")
                return None
            
            return result.data
            
        except Exception as e:
            logger.error(f"Error getting meeting by bot_id {bot_id}: {e}")
            return None
    
    async def _update_meeting_status(self, meeting_id: int, user_id: str, new_status: str):
        """Update meeting status"""
        try:
            supabase = get_supabase()
            
            result = supabase.table("meetings").update({
                "status": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", meeting_id).eq("user_id", user_id).execute()
            
            if result.error:
                logger.error(f"Failed to update meeting status: {result.error}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating meeting status: {e}")
            return False
    
    async def _get_webhook_events_for_meeting(self, meeting_id: int, user_id: str) -> List[Dict]:
        """Get webhook events for a meeting"""
        try:
            supabase = get_supabase()
            
            result = supabase.table("webhook_events").select("*").eq("meeting_id", meeting_id).eq("user_id", user_id).order("created_at", desc=True).execute()
            
            if result.error:
                logger.error(f"Supabase error: {result.error}")
                return []
            
            return result.data
            
        except Exception as e:
            logger.error(f"Error getting webhook events for meeting {meeting_id}: {e}")
            return []
    
    async def _check_webhook_completion(self, meeting: Dict, user_id: str) -> bool:
        """Check if a meeting has received all expected webhooks"""
        try:
            webhook_events = await self._get_webhook_events_for_meeting(meeting["id"], user_id)
            
            # Check for critical webhook events
            critical_events = ["post_processing_completed", "transcript.completed"]
            
            for critical_event in critical_events:
                if not any(webhook["event_type"] == critical_event for webhook in webhook_events):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking webhook completion for meeting {meeting['id']}: {e}")
            return False
    
    async def _handle_missing_webhooks(self, meeting: Dict, user_id: str):
        """Handle meetings with missing webhooks by triggering polling fallback"""
        try:
            logger.warning(f"Meeting {meeting['id']} has missing webhooks, triggering polling fallback")
            
            # Use BotService to check status directly
            bot_service = BotService()
            await bot_service.poll_bot_status(meeting["id"], user_id)
            
        except Exception as e:
            logger.error(f"Error handling missing webhooks for meeting {meeting['id']}: {e}")
    
    async def _schedule_delayed_check(self, meeting: Dict, delay: int, user_id: str):
        """Schedule a delayed status check for a meeting"""
        try:
            await asyncio.sleep(delay)
            
            # Check if meeting still needs attention
            current_meeting = await self._get_meeting_by_id(meeting["id"], user_id)
            
            if current_meeting and current_meeting["status"] not in ["COMPLETED", "FAILED"]:
                logger.info(f"Meeting {meeting['id']} still needs attention after delay, checking status")
                await self._check_meeting_status(current_meeting, user_id)
                
        except Exception as e:
            logger.error(f"Error in delayed check for meeting {meeting['id']}: {e}")
    
    async def _get_meeting_by_id(self, meeting_id: int, user_id: str) -> Optional[Dict]:
        """Get meeting by ID"""
        try:
            supabase = get_supabase()
            
            result = supabase.table("meetings").select("*").eq("id", meeting_id).eq("user_id", user_id).single().execute()
            
            if result.error:
                if "No rows found" in str(result.error):
                    return None
                logger.error(f"Supabase error: {result.error}")
                return None
            
            return result.data
            
        except Exception as e:
            logger.error(f"Error getting meeting {meeting_id}: {e}")
            return None
    
    async def _log_polling_activity(self, meeting_id: int, user_id: str, action: str, success: bool):
        """Log polling activity for monitoring"""
        try:
            logger.info(f"Polling activity: Meeting {meeting_id}, User {user_id}, Action: {action}, Success: {success}")
            
            # TODO: Add more detailed logging if needed
            
        except Exception as e:
            logger.error(f"Error logging polling activity: {e}")


# Global instance
polling_service = PollingService()
