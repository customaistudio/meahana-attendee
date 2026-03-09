from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Header
from app.core.database import get_supabase
from app.services.webhook_service import WebhookService
from app.schemas.schemas import WebhookPayload
from app.services.auth_service import AuthService
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])


async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current user from authorization header"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header"
        )
    
    token = authorization.replace("Bearer ", "")
    auth_service = AuthService()
    
    try:
        user = await auth_service.get_user(token)
        return user
    except Exception as e:
        logger.error(f"Failed to get current user: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )


@router.get("/url")
async def get_webhook_url():
    """Get the current webhook URL for copying to external services"""
    try:
        from app.services.webhook_service import WebhookService
        
        webhook_url = WebhookService.get_webhook_url()
        
        if not webhook_url:
            raise HTTPException(status_code=404, detail="No webhook URL configured")
        
        return {
            "webhook_url": webhook_url,
            "message": "This is the webhook URL configured via WEBHOOK_BASE_URL environment variable",
            "note": "Bot-level webhooks are automatically created when bots are created via API using the static webhook URL",
            "instructions": [
                "1. Bot-level webhooks are automatically configured using WEBHOOK_BASE_URL",
                "2. Webhooks are created when bots are created via API",
                "3. Triggers: bot.state_change, transcript.update, chat_messages.update, participant_events.join_leave"
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting webhook URL: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/")
async def handle_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Handle webhook events from Attendee API"""
    try:
        result = await WebhookService.process_webhook(payload, background_tasks)
        return result
        
    except Exception as e:
        logger.error(f"Error processing Attendee webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/attendee")
async def handle_attendee_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Handle webhook events from Attendee API"""
    try:
        result = await WebhookService.process_webhook(payload, background_tasks)
        return result
        
    except Exception as e:
        logger.error(f"Error processing Attendee webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/retry-failed")
async def retry_failed_webhooks(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Retry processing failed webhook events for the current user"""
    try:
        supabase = get_supabase()
        
        # Find failed webhooks for the current user
        result = supabase.table("webhook_events").select("*").eq("user_id", current_user["id"]).eq("processed", "false").order("created_at", desc=True).execute()
        
        if result.error:
            raise Exception(f"Supabase error: {result.error}")
        
        failed_webhooks = result.data
        
        if not failed_webhooks:
            return {"message": "No failed webhooks to retry", "count": 0}
        
        retry_count = 0
        for webhook in failed_webhooks:
            try:
                # Reset status for retry
                update_result = supabase.table("webhook_events").update({
                    "processed": "false",
                    "delivery_status": "pending",
                    "delivery_error": None
                }).eq("id", webhook["id"]).eq("user_id", current_user["id"]).execute()
                
                if update_result.error:
                    logger.error(f"Error updating webhook {webhook['id']}: {update_result.error}")
                    continue
                
                # Re-process the webhook
                from app.services.webhook_service import WebhookService
                from app.schemas.schemas import WebhookPayload
                
                # Reconstruct payload from stored data
                payload = WebhookPayload(**webhook["raw_payload"])
                
                # Process in background to avoid blocking
                background_tasks.add_task(
                    WebhookService.process_webhook,
                    payload,
                    background_tasks
                )
                
                retry_count += 1
                # Retrying webhook
                
            except Exception as e:
                logger.error(f"Error retrying webhook {webhook['id']}: {e}")
                continue
        
        return {
            "message": f"Retry initiated for {retry_count} failed webhooks",
            "count": retry_count
        }
        
    except Exception as e:
        logger.error(f"Error in retry-failed endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retry webhooks: {str(e)}")

 
