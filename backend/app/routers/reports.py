from fastapi import APIRouter, Depends, HTTPException, status, Header
from app.core.database import get_supabase
from app.schemas.schemas import (
    ScorecardResponse,
    MessageResponse
)
from app.services.analysis_service import AnalysisService
from app.services.auth_service import AuthService
import logging
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reports"])


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
        return user
    except Exception as e:
        logger.error(f"Failed to get current user: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


@router.get("/{meeting_id}/scorecard", response_model=ScorecardResponse)
async def get_meeting_scorecard(
    meeting_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get meeting scorecard/analysis for the current user"""
    try:
        supabase = get_supabase()
        
        # Check if meeting exists and belongs to current user
        result = supabase.table("meetings").select("*").eq("id", meeting_id).eq("user_id", current_user["id"]).single().execute()
        
        if result.error:
            if "No rows found" in str(result.error):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Meeting not found"
                )
            raise Exception(f"Supabase error: {result.error}")
        
        meeting = result.data
        
        # Check if meeting is completed
        if meeting["status"] != "COMPLETED":
            return ScorecardResponse(
                meeting_id=meeting_id,
                status="unavailable",
                message="Meeting is not completed yet"
            )
        
        # Get the latest report for this meeting
        result = supabase.table("reports").select("*").eq("meeting_id", meeting_id).eq("user_id", current_user["id"]).order("created_at", desc=True).limit(1).execute()
        
        if result.error:
            raise Exception(f"Supabase error: {result.error}")
        
        reports = result.data
        
        if not reports:
            return ScorecardResponse(
                meeting_id=meeting_id,
                status="processing",
                message="Analysis is in progress"
            )
        
        report = reports[0]
        
        return ScorecardResponse(
            meeting_id=meeting_id,
            status="available",
            scorecard=report["score"],
            created_at=report["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scorecard for meeting {meeting_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scorecard"
        )


@router.post("/{meeting_id}/trigger-analysis", response_model=MessageResponse)
async def trigger_analysis(
    meeting_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Manually trigger analysis for a meeting for the current user"""
    try:
        supabase = get_supabase()
        
        # Check if meeting exists and belongs to current user
        result = supabase.table("meetings").select("*").eq("id", meeting_id).eq("user_id", current_user["id"]).single().execute()
        
        if result.error:
            if "No rows found" in str(result.error):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Meeting not found"
                )
            raise Exception(f"Supabase error: {result.error}")
        
        meeting = result.data
        
        # Check if meeting is completed
        if meeting["status"] != "COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only analyze completed meetings"
            )
        
        # Trigger analysis
        analysis_service = AnalysisService()
        await analysis_service.trigger_analysis(meeting_id, current_user["id"])
        
        return MessageResponse(message="Analysis triggered successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger analysis for meeting {meeting_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger analysis"
        ) 