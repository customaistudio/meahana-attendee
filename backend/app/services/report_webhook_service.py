import asyncio
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import settings
from app.core.database import get_supabase
from app.schemas.schemas import ReportScore, ReportWebhookPayload

logger = logging.getLogger(__name__)


class ReportWebhookService:
    """Service for sending outgoing report webhooks after analysis completes."""

    async def send_report_webhook(
        self,
        meeting_id: int,
        user_id: str,
        scorecard: ReportScore,
    ) -> None:
        """
        POST the completed reportcard to the configured webhook URL.

        This is a no-op if REPORT_WEBHOOK_URL is not set.
        """
        if not settings.report_webhook_url:
            logger.debug("REPORT_WEBHOOK_URL not configured, skipping outgoing webhook")
            return

        try:
            # Fetch meeting details for the payload
            meeting = await self._get_meeting(meeting_id, user_id)
            if not meeting:
                logger.error(
                    f"Cannot send report webhook: meeting {meeting_id} not found"
                )
                return

            # Build the payload
            payload = ReportWebhookPayload(
                event="report.completed",
                meeting_id=meeting_id,
                meeting_url=str(meeting.get("meeting_url", "")),
                bot_id=meeting.get("bot_id", ""),
                bot_name=(meeting.get("meeting_metadata") or {}).get("bot_name"),
                scorecard=scorecard,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

            payload_json = payload.model_dump_json()
            delivery_id = str(uuid.uuid4())

            # Build headers
            headers = {
                "Content-Type": "application/json",
                "X-Meahana-Event": "report.completed",
                "X-Meahana-Delivery": delivery_id,
            }

            # Add HMAC signature if signing secret is configured
            if settings.report_webhook_signing_secret:
                signature = self._compute_signature(
                    payload_json, settings.report_webhook_signing_secret
                )
                headers["X-Meahana-Signature"] = f"sha256={signature}"

            # Send with retries
            await self._send_with_retries(
                url=settings.report_webhook_url,
                payload_json=payload_json,
                headers=headers,
                delivery_id=delivery_id,
                meeting_id=meeting_id,
            )

        except Exception as e:
            logger.error(
                f"Unexpected error sending report webhook for meeting {meeting_id}: {e}"
            )

    async def _send_with_retries(
        self,
        url: str,
        payload_json: str,
        headers: dict,
        delivery_id: str,
        meeting_id: int,
    ) -> None:
        """POST the payload with exponential backoff retries."""
        max_retries = settings.report_webhook_max_retries
        timeout = settings.report_webhook_timeout

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        url,
                        content=payload_json,
                        headers=headers,
                    )

                if response.status_code < 300:
                    logger.info(
                        f"Report webhook delivered successfully for meeting {meeting_id} "
                        f"(delivery={delivery_id}, status={response.status_code}, "
                        f"attempt={attempt})"
                    )
                    return

                logger.warning(
                    f"Report webhook received non-success status {response.status_code} "
                    f"for meeting {meeting_id} (delivery={delivery_id}, attempt={attempt})"
                )

            except httpx.TimeoutException:
                logger.warning(
                    f"Report webhook timed out for meeting {meeting_id} "
                    f"(delivery={delivery_id}, attempt={attempt})"
                )
            except httpx.RequestError as e:
                logger.warning(
                    f"Report webhook request error for meeting {meeting_id}: {e} "
                    f"(delivery={delivery_id}, attempt={attempt})"
                )

            # Exponential backoff: 2s, 4s, 8s, ...
            if attempt < max_retries:
                delay = 2 ** attempt
                logger.info(f"Retrying report webhook in {delay}s...")
                await asyncio.sleep(delay)

        logger.error(
            f"Report webhook delivery failed after {max_retries} attempts "
            f"for meeting {meeting_id} (delivery={delivery_id})"
        )

    @staticmethod
    def _compute_signature(payload_json: str, secret: str) -> str:
        """Compute HMAC-SHA256 hex digest of the payload."""
        return hmac.new(
            key=secret.encode("utf-8"),
            msg=payload_json.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

    @staticmethod
    async def _get_meeting(meeting_id: int, user_id: str) -> Optional[dict]:
        """Fetch meeting details from Supabase."""
        try:
            supabase = get_supabase()
            result = (
                supabase.table("meetings")
                .select("*")
                .eq("id", meeting_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            return result.data

        except Exception as e:
            logger.error(f"Error fetching meeting {meeting_id}: {e}")
            return None
