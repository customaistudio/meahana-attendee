from fastapi import APIRouter, Depends, HTTPException, status, Header
from app.core.database import get_supabase
from app.schemas.schemas import (
    MeetingCreate, 
    MeetingResponse, 
    BotCreateResponse,
    StatusPollResponse,
    MessageResponse,
    ListResponse
)
from app.services.bot_service import BotService
from app.services.auth_service import AuthService
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bots"])


async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current user from authorization header"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header"
        )
    
    token = authorization.replace("Bearer ", "")
    auth_service = AuthService()
    
    try:
        user = await auth_service.get_user(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get current user: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


@router.post("/bots/", response_model=BotCreateResponse)
async def create_bot(
    meeting: MeetingCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new meeting bot"""
    try:
        bot_service = BotService()
        result = await bot_service.create_bot(meeting, current_user["id"])
        return result
    except Exception as e:
        logger.error(f"Failed to create bot: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create bot"
        )


@router.get("/bots/", response_model=ListResponse)
async def get_bots(current_user: dict = Depends(get_current_user)):
    """Get all bots for the current user"""
    try:
        supabase = get_supabase()
        
        # Get meetings for the current user
        result = supabase.table("meetings").select("*").eq("user_id", current_user["id"]).order("created_at", desc=True).execute()
        
        # Handle Supabase response - newer versions return data directly
        try:
            if hasattr(result, 'data'):
                meetings = result.data or []
            else:
                # Fallback: try to access data directly
                meetings = result or []
        except Exception as e:
            logger.warning(f"Unexpected Supabase response format: {e}")
            meetings = []
        
        # Transform Supabase data to match expected schema
        transformed_meetings = []
        for meeting in meetings:
            try:
                # Convert string dates to datetime objects
                if isinstance(meeting.get("created_at"), str):
                    meeting["created_at"] = datetime.fromisoformat(meeting["created_at"].replace("Z", "+00:00"))
                if isinstance(meeting.get("updated_at"), str):
                    meeting["updated_at"] = datetime.fromisoformat(meeting["updated_at"].replace("Z", "+00:00"))
                
                # Ensure status is a valid MeetingStatus enum value
                if meeting.get("status"):
                    meeting["status"] = meeting["status"].upper()
                
                transformed_meetings.append(meeting)
            except Exception as transform_error:
                logger.warning(f"Failed to transform meeting {meeting.get('id')}: {transform_error}")
                continue
        
        return ListResponse(
            items=[MeetingResponse.model_validate(meeting) for meeting in transformed_meetings],
            total=len(transformed_meetings)
        )
    except Exception as e:
        logger.error(f"Failed to get bots: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get bots"
        )


@router.get("/bots/{bot_id}", response_model=MeetingResponse)
async def get_bot(bot_id: int, current_user: dict = Depends(get_current_user)):
    """Get a specific bot by ID for the current user"""
    try:
        supabase = get_supabase()
        
        # Get meeting for the current user
        result = supabase.table("meetings").select("*").eq("id", bot_id).eq("user_id", current_user["id"]).single().execute()
        
        # Check for errors in the response
        if hasattr(result, 'error') and result.error:
            if "No rows found" in str(result.error):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Bot not found"
                )
            raise Exception(f"Supabase error: {result.error}")
        
        meeting = getattr(result, 'data', None)
        
        return MeetingResponse.model_validate(meeting)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get bot {bot_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get bot"
        )


@router.delete("/bots/{bot_id}", response_model=MessageResponse)
async def delete_bot(bot_id: int, current_user: dict = Depends(get_current_user)):
    """Delete a bot for the current user"""
    try:
        supabase = get_supabase()
        
        # Delete the meeting for the current user (RLS will enforce user access)
        result = supabase.table("meetings").delete().eq("id", bot_id).eq("user_id", current_user["id"]).execute()
        
        # Check for errors in the response
        if hasattr(result, 'error') and result.error:
            raise Exception(f"Supabase error: {result.error}")
        
        if not getattr(result, 'data', None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found"
            )
        
        return MessageResponse(message="Bot deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete bot {bot_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete bot: {str(e)}"
        )


@router.post("/bots/{bot_id}/poll-status", response_model=StatusPollResponse)
async def poll_bot_status(
    bot_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Poll for bot status updates for the current user"""
    try:
        bot_service = BotService()
        result = await bot_service.poll_bot_status(bot_id, current_user["id"])
        return result
    except Exception as e:
        logger.error(f"Failed to poll bot status for {bot_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to poll bot status"
        )
 
