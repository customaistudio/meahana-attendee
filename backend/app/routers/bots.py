from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.core.database import get_supabase
from app.core.auth import verify_api_key
from app.schemas.schemas import (
    MeetingCreate,
    MeetingResponse,
    BotCreateResponse,
    StatusPollResponse,
    MessageResponse,
    ListResponse,
)
from app.services.bot_service import BotService
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bots"])


@router.post("/bots/", response_model=BotCreateResponse, dependencies=[Depends(verify_api_key)])
async def create_bot(meeting: MeetingCreate):
    """Create a new meeting bot. user_id is passed in the request body."""
    try:
        bot_service = BotService()
        result = await bot_service.create_bot(meeting, meeting.user_id)
        return result
    except Exception as e:
        logger.error(f"Failed to create bot: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create bot",
        )


@router.get("/bots/", response_model=ListResponse, dependencies=[Depends(verify_api_key)])
async def get_bots(user_id: str = Query(..., description="The user ID to list bots for")):
    """Get all bots for the given user_id."""
    try:
        supabase = get_supabase()

        result = (
            supabase.table("meetings")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        meetings = getattr(result, "data", None) or []

        transformed_meetings = []
        for meeting in meetings:
            try:
                if isinstance(meeting.get("created_at"), str):
                    meeting["created_at"] = datetime.fromisoformat(
                        meeting["created_at"].replace("Z", "+00:00")
                    )
                if isinstance(meeting.get("updated_at"), str):
                    meeting["updated_at"] = datetime.fromisoformat(
                        meeting["updated_at"].replace("Z", "+00:00")
                    )
                if meeting.get("status"):
                    meeting["status"] = meeting["status"].upper()
                transformed_meetings.append(meeting)
            except Exception as transform_error:
                logger.warning(f"Failed to transform meeting {meeting.get('id')}: {transform_error}")
                continue

        return ListResponse(
            items=[MeetingResponse.model_validate(m) for m in transformed_meetings],
            total=len(transformed_meetings),
        )
    except Exception as e:
        logger.error(f"Failed to get bots: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get bots",
        )


@router.get("/bots/{bot_id}", response_model=MeetingResponse, dependencies=[Depends(verify_api_key)])
async def get_bot(bot_id: int, user_id: str = Query(...)):
    """Get a specific bot by ID."""
    try:
        supabase = get_supabase()
        result = (
            supabase.table("meetings")
            .select("*")
            .eq("id", bot_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return MeetingResponse.model_validate(result.data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get bot {bot_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get bot",
        )


@router.delete("/bots/{bot_id}", response_model=MessageResponse, dependencies=[Depends(verify_api_key)])
async def delete_bot(bot_id: int, user_id: str = Query(...)):
    """Delete a bot."""
    try:
        supabase = get_supabase()
        result = (
            supabase.table("meetings")
            .delete()
            .eq("id", bot_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not getattr(result, "data", None):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
        return MessageResponse(message="Bot deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete bot {bot_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete bot: {str(e)}",
        )


@router.post("/bots/{bot_id}/poll-status", response_model=StatusPollResponse, dependencies=[Depends(verify_api_key)])
async def poll_bot_status(bot_id: int, user_id: str = Query(...)):
    """Poll for bot status updates."""
    try:
        bot_service = BotService()
        result = await bot_service.poll_bot_status(bot_id, user_id)
        return result
    except Exception as e:
        logger.error(f"Failed to poll bot status for {bot_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to poll bot status",
        )
