import logging
from app.core.database import get_supabase
from app.schemas.schemas import WebhookPayload
from app.core.config import settings
from fastapi import BackgroundTasks
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import json

logger = logging.getLogger(__name__)


class WebhookService:
    @staticmethod
    def get_webhook_url() -> Optional[str]:
        """Get the global webhook URL for the application"""
        # This method is mainly used for debugging and documentation purposes
        
        # Production: Use configured webhook base URL if available
        if settings.is_production and settings.webhook_base_url:
            webhook_url = f"{settings.webhook_base_url.rstrip('/')}/webhook/"
            return webhook_url
        
        # Development: Show available options
        if settings.webhook_base_url:
            webhook_url = f"{settings.webhook_base_url.rstrip('/')}/webhook/"
            return webhook_url
        
        return None

    @staticmethod
    async def process_webhook(
        payload: WebhookPayload, 
        background_tasks: BackgroundTasks
    ) -> dict:
        """Process webhook payload - Production-ready version"""
        try:
            supabase = get_supabase()
            
            # Store webhook event
            event_type = payload.get_event_type()
            bot_id = payload.get_bot_id()
            
            # Find meeting by bot_id to get user_id
            meeting = await WebhookService._find_meeting_by_bot_id(bot_id)
            if not meeting:
                logger.error(f"No meeting found for bot {bot_id}. Bot creation may have failed.")
                raise ValueError(f"Webhook event has no associated meeting. Bot creation may have failed.")
            
            user_id = meeting["user_id"]
            
            webhook_event_data = {
                "event_type": event_type,
                "bot_id": bot_id,
                "event_data": payload.data,
                "raw_payload": payload.model_dump(),
                "meeting_id": meeting["id"],
                "user_id": user_id,
                "processed": "false"
            }
            
            # Insert webhook event
            result = supabase.table("webhook_events").insert(webhook_event_data).execute()
            if result.error:
                raise Exception(f"Supabase error: {result.error}")
            
            webhook_event_id = result.data[0]["id"]
            
            # Process webhook delivery tracking
            from app.services.webhook_delivery_service import webhook_delivery_service
            await webhook_delivery_service.process_webhook_delivery(webhook_event_id, user_id)
            
            # Handle different event types
            await WebhookService._process_event_by_type(event_type, payload, user_id, background_tasks)
            
            # Mark webhook as processed
            update_result = supabase.table("webhook_events").update({
                "processed": "true",
                "processed_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", webhook_event_id).execute()
            
            if update_result.error:
                logger.error(f"Failed to mark webhook as processed: {update_result.error}")
            
            return {"status": "processed", "event_type": event_type}
                
        except Exception as e:
            logger.error(f"Error processing webhook event {event_type}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Mark webhook as failed if we have an ID
            if 'webhook_event_id' in locals():
                try:
                    supabase = get_supabase()
                    update_result = supabase.table("webhook_events").update({
                        "processed": "false",
                        "delivery_status": "failed",
                        "delivery_error": str(e)
                    }).eq("id", webhook_event_id).execute()
                    
                    if update_result.error:
                        logger.error(f"Failed to mark webhook as failed: {update_result.error}")
                except Exception as update_error:
                    logger.error(f"Failed to update webhook status: {update_error}")
            
            raise  # Re-raise to trigger the 500 response

    @staticmethod
    def _has_transcript_data(payload: WebhookPayload) -> bool:
        """Check if payload contains transcript data"""
        data = payload.data
        # Check if payload has transcription data
        if data.get("transcription") and data["transcription"].get("transcript"):
            return True
        # Check if payload has direct text field
        if data.get("text"):
            return True
        return False

    @staticmethod
    async def _find_meeting_by_bot_id(bot_id: str):
        """Find meeting by bot_id using Supabase"""
        try:
            supabase = get_supabase()
            
            # Search for meeting with this bot_id
            result = supabase.table("meetings").select("*").eq("bot_id", bot_id).execute()
            
            if result.error:
                logger.error(f"Supabase error finding meeting: {result.error}")
                return None
            
            if not result.data:
                return None
            
            return result.data[0]
            
        except Exception as e:
            logger.error(f"Error finding meeting by bot_id {bot_id}: {e}")
            return None

    @staticmethod
    async def _process_event_by_type(
        event_type: str, 
        payload: WebhookPayload, 
        user_id: str,
        background_tasks: BackgroundTasks
    ):
        """Route webhook events to appropriate handlers based on event type"""
        from app.services.bot_service import BotService
        
        if event_type in ["bot.state_change", "bot.join_requested", "bot.joining", "bot.joined"]:
            await WebhookService._handle_bot_state_change(payload, user_id, background_tasks)
        elif event_type in ["bot.recording", "bot.started_recording"]:
            await WebhookService._handle_bot_recording(payload, user_id)
        elif event_type in ["bot.left", "bot.completed"]:
            await WebhookService._handle_bot_completed(payload, user_id, background_tasks)
        elif event_type in ["bot.failed"]:
            await WebhookService._handle_bot_failed(payload, user_id)
        elif event_type in ["transcript.update", "transcript.chunk"]:
            await WebhookService._handle_transcript_chunk(payload, user_id)
        elif event_type in ["transcript.completed"]:
            await WebhookService._handle_transcript_completed(payload, user_id, background_tasks)
        elif event_type in ["chat_messages.update"]:
            await WebhookService._handle_chat_message(payload, user_id)
        elif event_type in ["participant_events.join_leave"]:
            await WebhookService._handle_participant_event(payload, user_id)
        elif event_type == "post_processing_completed":
            await WebhookService._handle_post_processing_completed(payload, user_id, background_tasks)
        elif event_type == "unknown" and WebhookService._has_transcript_data(payload):
            await WebhookService._handle_transcript_chunk(payload, user_id)
        else:
            logger.warning(f"Unhandled webhook event: {event_type}")

    @staticmethod
    async def _handle_bot_state_change(
        payload: WebhookPayload, 
        user_id: str,
        background_tasks: BackgroundTasks
    ):
        """Handle bot state change events according to Attendee API specification"""
        from app.services.bot_service import BotService
        
        bot_id = payload.get_bot_id()
        data = payload.data
        
        # Extract state change information per Attendee API spec
        new_state = data.get("new_state")
        old_state = data.get("old_state")
        event_type = data.get("event_type")
        event_sub_type = data.get("event_sub_type")
        
        if new_state == "ended" and event_type == "post_processing_completed":
            # Bot has completed post-processing and meeting is ended
            meeting = await BotService.get_meeting_by_bot_id(bot_id, user_id)
            if meeting:
                # Update meeting status to completed
                await BotService.update_meeting_status(meeting["id"], user_id, "completed")
                
                # Trigger analysis in background
                background_tasks.add_task(
                    WebhookService._fetch_transcript_and_analyze,
                    meeting["id"],
                    bot_id,
                    user_id
                )
        elif new_state in ["failed", "error"]:
            # Bot failed
            meeting = await BotService.get_meeting_by_bot_id(bot_id, user_id)
            if meeting:
                await BotService.update_meeting_status(meeting["id"], user_id, "failed")
        elif new_state in ["staged", "join_requested", "joining", "joined_meeting", "joined_recording", "recording_permission_granted"]:
            # Bot is joining or in meeting
            meeting = await BotService.get_meeting_by_bot_id(bot_id, user_id)
            if meeting and meeting["status"] != "started":
                await BotService.update_meeting_status(meeting["id"], user_id, "started")

    @staticmethod
    async def _handle_bot_recording(payload: WebhookPayload, user_id: str):
        """Handle bot recording events"""
        from app.services.bot_service import BotService
        
        bot_id = payload.get_bot_id()
        
        meeting = await BotService.get_meeting_by_bot_id(bot_id, user_id)
        if meeting:
            await BotService.update_meeting_status(meeting["id"], user_id, "started")

    @staticmethod
    async def _handle_bot_completed(
        payload: WebhookPayload, 
        user_id: str,
        background_tasks: BackgroundTasks
    ):
        """Handle bot completion events"""
        from app.services.bot_service import BotService
        
        bot_id = payload.get_bot_id()
        
        meeting = await BotService.get_meeting_by_bot_id(bot_id, user_id)
        if meeting:
            await BotService.update_meeting_status(meeting["id"], user_id, "completed")
            
            # Trigger transcript fetch and analysis in background
            background_tasks.add_task(
                WebhookService._fetch_transcript_and_analyze,
                meeting["id"],
                bot_id,
                user_id
            )
        else:
            logger.warning(f"No meeting found for completed bot {bot_id}")

    @staticmethod
    async def _handle_bot_failed(payload: WebhookPayload, user_id: str):
        """Handle bot failure events"""
        from app.services.bot_service import BotService
        
        bot_id = payload.get_bot_id()
        
        meeting = await BotService.get_meeting_by_bot_id(bot_id, user_id)
        if meeting:
            await BotService.update_meeting_status(meeting["id"], user_id, "failed")

    @staticmethod
    async def _handle_transcript_chunk(payload: WebhookPayload, user_id: str):
        """Handle real-time transcript chunks"""
        from app.services.bot_service import BotService
        
        # Try to get bot_id first
        bot_id = payload.get_bot_id()
        
        # Find meeting using BotService
        meeting = await BotService.get_meeting_by_bot_id(bot_id, user_id)
        
        if not meeting:
            logger.warning(f"Could not find meeting for transcript webhook")
            return
        
        # Extract transcript data
        data = payload.data
        speaker = data.get("speaker") or data.get("speaker_name", "Unknown")
        text = data.get("text") or (data.get("transcription", {}) or {}).get("transcript", "")
        timestamp_ms = data.get("timestamp_ms")
        timestamp_str = data.get("timestamp")
        confidence = data.get("confidence", "medium")
        
        if not text:
            logger.warning("Empty transcript text received")
            return
        
        # Parse timestamp
        try:
            if timestamp_ms:
                timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            elif timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                timestamp = datetime.now(timezone.utc)
        except Exception as e:
            logger.warning(f"Failed to parse timestamp {timestamp_ms} or {timestamp_str}: {e}")
            timestamp = datetime.now(timezone.utc)
        
        # Store transcript chunk in Supabase
        chunk_data = {
            "meeting_id": meeting["id"],
            "user_id": user_id,
            "speaker": speaker,
            "text": text,
            "timestamp": timestamp.isoformat(),
            "confidence": confidence
        }
        
        supabase = get_supabase()
        result = supabase.table("transcript_chunks").insert(chunk_data).execute()
        
        if result.error:
            logger.error(f"Failed to insert transcript chunk: {result.error}")

    @staticmethod
    async def _handle_transcript_completed(
        payload: WebhookPayload, 
        user_id: str,
        background_tasks: BackgroundTasks
    ):
        """Handle transcript completion events"""
        from app.services.bot_service import BotService
        
        bot_id = payload.get_bot_id()
        
        meeting = await BotService.get_meeting_by_bot_id(bot_id, user_id)
        if meeting:
            # Trigger analysis in background
            background_tasks.add_task(
                WebhookService._fetch_transcript_and_analyze,
                meeting["id"],
                bot_id,
                user_id
            )

    @staticmethod
    async def _handle_chat_message(payload: WebhookPayload, user_id: str):
        """Handle chat message events"""
        bot_id = payload.get_bot_id()
        # TODO: Implement chat message storage if needed

    @staticmethod
    async def _handle_participant_event(payload: WebhookPayload, user_id: str):
        """Handle participant join/leave events"""
        bot_id = payload.get_bot_id()
        data = payload.data
        event_type = data.get("event_type", "unknown")
        participant = data.get("participant", {})
        # TODO: Implement participant tracking if needed

    @staticmethod
    async def _handle_post_processing_completed(
        payload: WebhookPayload, 
        user_id: str,
        background_tasks: BackgroundTasks
    ):
        """Handle post-processing completed events"""
        from app.services.bot_service import BotService
        
        bot_id = payload.get_bot_id()
        if not bot_id:
            logger.error("Post-processing completed webhook has no bot_id. Cannot process.")
            raise ValueError("Post-processing completed webhook missing bot_id")
        
        # Production-ready: Find meeting by bot_id or fail
        meeting = await BotService.get_meeting_by_bot_id(bot_id, user_id)
        if not meeting:
            logger.error(f"No meeting found for bot {bot_id}. Bot creation may have failed.")
            raise ValueError(f"Meeting not found for bot {bot_id}")
        
        # Update meeting status to completed
        await BotService.update_meeting_status(meeting["id"], user_id, "completed")
        
        # Trigger analysis in background
        background_tasks.add_task(
            WebhookService._fetch_transcript_and_analyze,
            meeting["id"],
            bot_id,
            user_id
        )

    @staticmethod
    async def _fetch_transcript_and_analyze(meeting_id: int, bot_id: str, user_id: str):
        """Background task to fetch transcript and trigger analysis"""
        try:
            # TODO: Fetch full transcript from Attendee API if needed
            # For now, we rely on real-time transcript chunks
            
            # Trigger analysis
            from app.services.analysis_service import AnalysisService
            analysis_service = AnalysisService()
            await analysis_service.enqueue_analysis(meeting_id, user_id)
            
        except Exception as e:
            logger.error(f"Error in background transcript fetch and analysis: {e}")
            import traceback
            logger.error(f"Background task traceback: {traceback.format_exc()}") 