from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from app.core.database import get_supabase
from app.core.auth import verify_api_key
from app.services.webhook_service import WebhookService
from app.schemas.schemas import WebhookPayload
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])


@router.get("/url")
async def get_webhook_url():
    """Get the current webhook URL for copying to external services"""
    try:
        webhook_url = WebhookService.get_webhook_url()

        if not webhook_url:
            raise HTTPException(status_code=404, detail="No webhook URL configured")

        return {
            "webhook_url": webhook_url,
            "message": "This is the webhook URL configured via WEBHOOK_BASE_URL environment variable",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting webhook URL: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/")
async def handle_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Handle webhook events from Attendee API (no auth -- server-to-server)"""
    try:
        result = await WebhookService.process_webhook(payload, background_tasks)
        return result
    except Exception as e:
        logger.error(f"Error processing Attendee webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/attendee")
async def handle_attendee_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Handle webhook events from Attendee API (no auth -- server-to-server)"""
    try:
        result = await WebhookService.process_webhook(payload, background_tasks)
        return result
    except Exception as e:
        logger.error(f"Error processing Attendee webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/retry-failed", dependencies=[Depends(verify_api_key)])
async def retry_failed_webhooks(
    background_tasks: BackgroundTasks,
    user_id: str = Query(...),
):
    """Retry processing failed webhook events for a user."""
    try:
        supabase = get_supabase()

        result = (
            supabase.table("webhook_events")
            .select("*")
            .eq("user_id", user_id)
            .eq("processed", "false")
            .order("created_at", desc=True)
            .execute()
        )

        failed_webhooks = result.data

        if not failed_webhooks:
            return {"message": "No failed webhooks to retry", "count": 0}

        retry_count = 0
        for webhook in failed_webhooks:
            try:
                supabase.table("webhook_events").update(
                    {"processed": "false", "delivery_status": "pending", "delivery_error": None}
                ).eq("id", webhook["id"]).eq("user_id", user_id).execute()

                payload = WebhookPayload(**webhook["raw_payload"])

                background_tasks.add_task(
                    WebhookService.process_webhook,
                    payload,
                    background_tasks,
                )

                retry_count += 1

            except Exception as e:
                logger.error(f"Error retrying webhook {webhook['id']}: {e}")
                continue

        return {
            "message": f"Retry initiated for {retry_count} failed webhooks",
            "count": retry_count,
        }

    except Exception as e:
        logger.error(f"Error in retry-failed endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retry webhooks: {str(e)}")
