from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.core.database import get_supabase
from app.core.auth import verify_api_key
from app.schemas.schemas import ScorecardResponse, MessageResponse
from app.services.analysis_service import AnalysisService
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reports"])


@router.get("/{meeting_id}/scorecard", response_model=ScorecardResponse, dependencies=[Depends(verify_api_key)])
async def get_meeting_scorecard(meeting_id: int, user_id: str = Query(...)):
    """Get meeting scorecard/analysis."""
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
        meeting = result.data

        if meeting["status"] != "COMPLETED":
            return ScorecardResponse(
                meeting_id=meeting_id,
                status="unavailable",
                message="Meeting is not completed yet",
            )

        result = (
            supabase.table("reports")
            .select("*")
            .eq("meeting_id", meeting_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        reports = result.data

        if not reports:
            return ScorecardResponse(
                meeting_id=meeting_id,
                status="processing",
                message="Analysis is in progress",
            )

        report = reports[0]

        return ScorecardResponse(
            meeting_id=meeting_id,
            status="available",
            scorecard=report["score"],
            created_at=report["created_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scorecard for meeting {meeting_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scorecard",
        )


@router.post("/{meeting_id}/trigger-analysis", response_model=MessageResponse, dependencies=[Depends(verify_api_key)])
async def trigger_analysis(meeting_id: int, user_id: str = Query(...)):
    """Manually trigger analysis for a meeting."""
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
        meeting = result.data

        if meeting["status"] != "COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only analyze completed meetings",
            )

        analysis_service = AnalysisService()
        await analysis_service.trigger_analysis(meeting_id, user_id)

        return MessageResponse(message="Analysis triggered successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger analysis for meeting {meeting_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger analysis",
        )
