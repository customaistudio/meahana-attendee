import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from app.core.database import get_supabase
from app.services.polling_service import polling_service
from app.core.config import settings
import json

logger = logging.getLogger(__name__)


class WebhookDeliveryService:
    """Service for managing webhook delivery, retries, and fallback logic"""
    
    def __init__(self):
        self.max_retry_attempts = settings.webhook_max_retry_attempts
        self.retry_delays = [int(delay.strip()) for delay in settings.webhook_retry_delays.split(",")]
        self.critical_events = ["post_processing_completed"]
        self.fallback_timeout = settings.webhook_fallback_timeout
        
        # Proactive monitoring settings
        self.proactive_check_interval = 120  # Check every 2 minutes
        self.meeting_timeout_threshold = 600  # 10 minutes without updates
        self.expected_webhook_patterns = {
            "STARTED": ["bot.state_change", "transcript.update"],
            "PENDING": ["bot.state_change"],
            "COMPLETED": ["post_processing_completed", "transcript.completed"]
        }
        
    async def start_proactive_monitoring(self):
        """Start proactive monitoring for webhook failures on Attendee's end"""
        
        while True:
            try:
                await self._proactive_webhook_failure_check()
                await asyncio.sleep(self.proactive_check_interval)
            except Exception as e:
                logger.error(f"Error in proactive webhook failure check: {e}")
                await asyncio.sleep(30)  # Wait 30 seconds before retrying
    
    async def _proactive_webhook_failure_check(self, user_id: str = None):
        """Proactively check for webhook failures on Attendee's end"""
        try:
            # Find meetings that might have missed webhooks
            suspicious_meetings = await self._find_suspicious_meetings(user_id)
            
            if not suspicious_meetings:
                return
            
            # Found meetings with potential webhook failures
            
            for meeting in suspicious_meetings:
                await self._investigate_meeting_webhook_status(meeting, user_id)
                
        except Exception as e:
            logger.error(f"Error in proactive webhook failure check: {e}")
    
    async def _find_suspicious_meetings(self, user_id: str = None) -> List[Dict]:
        """Find meetings that might have missed webhooks"""
        try:
            supabase = get_supabase()
            
            # Find meetings that haven't been updated recently
            timeout_threshold = datetime.now(timezone.utc) - timedelta(seconds=self.meeting_timeout_threshold)
            
            query = supabase.table("meetings").select("*").in_("status", ["STARTED", "PENDING"]).lt("updated_at", timeout_threshold.isoformat())
            
            if user_id:
                query = query.eq("user_id", user_id)
            
            result = query.execute()
            
            if result.error:
                logger.error(f"Supabase error: {result.error}")
                return []
            
            meetings = result.data
            
            suspicious_meetings = []
            
            for meeting in meetings:
                if await self._is_meeting_suspicious(meeting, user_id):
                    suspicious_meetings.append(meeting)
            
            return suspicious_meetings
            
        except Exception as e:
            logger.error(f"Error finding suspicious meetings: {e}")
            return []
    
    async def _is_meeting_suspicious(self, meeting: Dict, user_id: str = None) -> bool:
        """Check if a meeting is suspicious (missing expected webhooks)"""
        try:
            # Get recent webhook events for this meeting/bot
            recent_webhooks = await self._get_recent_webhook_events(meeting, user_id)
            
            # Check if we have the expected webhook pattern for the current status
            expected_events = self.expected_webhook_patterns.get(meeting["status"], [])
            
            # Check if we have all expected events
            for expected_event in expected_events:
                if not any(webhook["event_type"] == expected_event for webhook in recent_webhooks):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if meeting is suspicious: {e}")
            return False
    
    async def _get_recent_webhook_events(self, meeting: Dict, user_id: str = None) -> List[Dict]:
        """Get recent webhook events for a meeting"""
        try:
            supabase = get_supabase()
            
            # Get webhooks from the last hour
            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            
            query = supabase.table("webhook_events").select("*").eq("meeting_id", meeting["id"]).gte("created_at", one_hour_ago.isoformat())
            
            if user_id:
                query = query.eq("user_id", user_id)
            
            result = query.execute()
            
            if result.error:
                logger.error(f"Supabase error: {result.error}")
                return []
            
            return result.data
            
        except Exception as e:
            logger.error(f"Error getting recent webhook events: {e}")
            return []
    
    async def _investigate_meeting_webhook_status(self, meeting: Dict, user_id: str = None):
        """Investigate webhook status for a suspicious meeting"""
        try:
            # Check if we should trigger polling fallback
            if await self._should_trigger_polling_fallback(meeting, user_id):
                logger.info(f"Triggering polling fallback for meeting {meeting['id']}")
                await self._trigger_polling_fallback(meeting, user_id)
                
        except Exception as e:
            logger.error(f"Error investigating meeting webhook status: {e}")
    
    async def _should_trigger_polling_fallback(self, meeting: Dict, user_id: str = None) -> bool:
        """Determine if we should trigger polling fallback"""
        try:
            # Check if meeting has been in current status for too long
            status_duration = datetime.now(timezone.utc) - datetime.fromisoformat(meeting["updated_at"].replace('Z', '+00:00'))
            
            if status_duration.total_seconds() > self.fallback_timeout:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if should trigger polling fallback: {e}")
            return False
    
    async def _trigger_polling_fallback(self, meeting: Dict, user_id: str = None):
        """Trigger polling fallback for a meeting"""
        try:
            # Use polling service to check meeting status
            if user_id:
                await polling_service.manual_check_meeting(meeting["id"], user_id)
            else:
                # For system-wide checks, we need to find the user_id
                supabase = get_supabase()
                result = supabase.table("meetings").select("user_id").eq("id", meeting["id"]).single().execute()
                
                if result.error:
                    logger.error(f"Supabase error: {result.error}")
                    return
                
                user_id = result.data["user_id"]
                await polling_service.manual_check_meeting(meeting["id"], user_id)
                
        except Exception as e:
            logger.error(f"Error triggering polling fallback: {e}")
    
    async def process_webhook_delivery(self, webhook_event_id: int, user_id: str):
        """Process webhook delivery tracking"""
        try:
            supabase = get_supabase()
            
            # Update webhook event with delivery status
            update_result = supabase.table("webhook_events").update({
                "delivery_status": "delivered",
                "delivered_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", webhook_event_id).eq("user_id", user_id).execute()
            
            if update_result.error:
                logger.error(f"Failed to update webhook delivery status: {update_result.error}")
                
        except Exception as e:
            logger.error(f"Error processing webhook delivery: {e}")
    
    async def retry_failed_webhooks(self, user_id: str = None):
        """Retry failed webhook deliveries"""
        try:
            supabase = get_supabase()
            
            # Find failed webhooks
            query = supabase.table("webhook_events").select("*").eq("delivery_status", "failed")
            
            if user_id:
                query = query.eq("user_id", user_id)
            
            result = query.execute()
            
            if result.error:
                logger.error(f"Supabase error: {result.error}")
                return
            
            failed_webhooks = result.data
            
            for webhook in failed_webhooks:
                await self._retry_webhook_delivery(webhook, user_id)
                
        except Exception as e:
            logger.error(f"Error retrying failed webhooks: {e}")
    
    async def _retry_webhook_delivery(self, webhook: Dict, user_id: str = None):
        """Retry delivery of a failed webhook"""
        try:
            supabase = get_supabase()
            
            # Reset status for retry
            update_result = supabase.table("webhook_events").update({
                "delivery_status": "pending",
                "delivery_error": None,
                "retry_count": (webhook.get("retry_count", 0) + 1)
            }).eq("id", webhook["id"])
            
            if user_id:
                update_result = update_result.eq("user_id", user_id)
            
            result = update_result.execute()
            
            if result.error:
                logger.error(f"Failed to update webhook for retry: {result.error}")
                return
            
            # TODO: Implement actual webhook retry logic
            logger.info(f"Webhook {webhook['id']} marked for retry")
            
        except Exception as e:
            logger.error(f"Error retrying webhook delivery: {e}")
    
    async def check_critical_event_fallbacks(self, user_id: str = None):
        """Check for missing critical events and trigger polling fallback"""
        try:
            supabase = get_supabase()
            
            # Find meetings that should have critical events but don't
            query = supabase.table("meetings").select("*").in_("status", ["STARTED", "PENDING"])
            
            if user_id:
                query = query.eq("user_id", user_id)
            
            result = query.execute()
            
            if result.error:
                logger.error(f"Supabase error: {result.error}")
                return
            
            meetings = result.data
            
            for meeting in meetings:
                if await self._is_missing_critical_events(meeting, user_id):
                    await self._trigger_polling_fallback(meeting, user_id)
                    
        except Exception as e:
            logger.error(f"Error checking critical event fallbacks: {e}")
    
    async def _is_missing_critical_events(self, meeting: Dict, user_id: str = None) -> bool:
        """Check if a meeting is missing critical events"""
        try:
            # Check if we have the expected critical events for this meeting
            expected_events = self.expected_webhook_patterns.get(meeting["status"], [])
            
            recent_webhooks = await self._get_recent_webhook_events(meeting, user_id)
            
            for expected_event in expected_events:
                if not any(webhook["event_type"] == expected_event for webhook in recent_webhooks):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if missing critical events: {e}")
            return False
    
    async def get_webhook_delivery_stats(self, user_id: str = None) -> Dict[str, Any]:
        """Get webhook delivery statistics"""
        try:
            supabase = get_supabase()
            
            # Get total webhooks
            query = supabase.table("webhook_events").select("*", count="exact")
            
            if user_id:
                query = query.eq("user_id", user_id)
            
            result = query.execute()
            
            if result.error:
                logger.error(f"Supabase error: {result.error}")
                return {}
            
            total_webhooks = result.count or 0
            
            # Get status counts
            status_counts = {}
            for status in ["delivered", "failed", "pending", "permanently_failed"]:
                status_query = supabase.table("webhook_events").select("*", count="exact").eq("delivery_status", status)
                
                if user_id:
                    status_query = status_query.eq("user_id", user_id)
                
                status_result = status_query.execute()
                
                if not status_result.error:
                    status_counts[status] = status_result.count or 0
                else:
                    status_counts[status] = 0
            
            # Calculate success rate
            delivered = status_counts.get("delivered", 0)
            total = total_webhooks
            
            if total > 0:
                delivery_success_rate = (delivered / total) * 100
            else:
                delivery_success_rate = 0
            
            return {
                "total_webhooks": total,
                "status_counts": status_counts,
                "delivery_success_rate": round(delivery_success_rate, 2)
            }
            
        except Exception as e:
            logger.error(f"Error getting webhook delivery stats: {e}")
            return {}


# Global instance
webhook_delivery_service = WebhookDeliveryService()
