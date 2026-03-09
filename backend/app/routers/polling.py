from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Header
from app.core.database import get_supabase
from app.services.polling_service import polling_service
from app.services.auth_service import AuthService
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/polling", tags=["polling"])


class PollingResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class ManualCheckRequest(BaseModel):
    meeting_id: int


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


@router.post("/start", response_model=PollingResponse)
async def start_polling(background_tasks: BackgroundTasks):
    """Start the polling service in the background"""
    try:
        if polling_service.is_running:
            return PollingResponse(
                success=True,
                message="Polling service already running",
                data={"status": "running"}
            )
        
        # Start polling in background
        background_tasks.add_task(polling_service.start_polling)
        
        return PollingResponse(
            success=True,
            message="Polling service started successfully",
            data={
                "status": "starting",
                "polling_interval": polling_service.polling_interval,
                "max_retries": polling_service.max_retries
            }
        )
        
    except Exception as e:
        logger.error(f"Error starting polling service: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start polling service: {str(e)}"
        )


@router.post("/stop", response_model=PollingResponse)
async def stop_polling():
    """Stop the polling service"""
    try:
        await polling_service.stop_polling()
        
        return PollingResponse(
            success=True,
            message="Polling service stopped successfully",
            data={"status": "stopped"}
        )
        
    except Exception as e:
        logger.error(f"Error stopping polling service: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop polling service: {str(e)}"
        )


@router.get("/status", response_model=PollingResponse)
async def get_polling_status():
    """Get the current status of the polling service"""
    try:
        return PollingResponse(
            success=True,
            message="Polling service status retrieved",
            data={
                "is_running": polling_service.is_running,
                "polling_interval": polling_service.polling_interval,
                "max_retries": polling_service.max_retries,
                "retry_delay": polling_service.retry_delay
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting polling status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get polling status: {str(e)}"
        )


@router.post("/check-meeting", response_model=PollingResponse)
async def manually_check_meeting(
    request: ManualCheckRequest,
    current_user: dict = Depends(get_current_user)
):
    """Manually check a specific meeting for completion status for the current user"""
    try:
        # Verify the meeting belongs to the current user
        supabase = get_supabase()
        result = supabase.table("meetings").select("id").eq("id", request.meeting_id).eq("user_id", current_user["id"]).single().execute()
        
        if result.error:
            if "No rows found" in str(result.error):
                raise HTTPException(
                    status_code=404,
                    detail="Meeting not found"
                )
            raise Exception(f"Supabase error: {result.error}")
        
        success = await polling_service.manual_check_meeting(request.meeting_id, current_user["id"])
        
        if success:
            return PollingResponse(
                success=True,
                message=f"Meeting {request.meeting_id} checked successfully",
                data={"meeting_id": request.meeting_id, "status": "checked"}
            )
        else:
            return PollingResponse(
                success=False,
                message=f"Failed to check meeting {request.meeting_id}",
                data={"meeting_id": request.meeting_id, "status": "failed"}
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error manually checking meeting {request.meeting_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check meeting: {str(e)}"
        )


@router.post("/check-all-pending", response_model=PollingResponse)
async def check_all_pending_meetings(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Manually trigger a check of all pending meetings for the current user"""
    try:
        # Run the polling check in background for the current user
        background_tasks.add_task(polling_service._poll_completed_meetings, current_user["id"])
        
        return PollingResponse(
            success=True,
            message="Manual check of pending meetings initiated",
            data={"status": "checking"}
        )
        
    except Exception as e:
        logger.error(f"Error initiating manual check of pending meetings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate manual check: {str(e)}"
        )


@router.post("/configure", response_model=PollingResponse)
async def configure_polling(
    polling_interval: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_delay: Optional[int] = None
):
    """Configure polling service parameters"""
    try:
        if polling_interval is not None:
            polling_service.polling_interval = max(30, polling_interval)  # Minimum 30 seconds
        
        if max_retries is not None:
            polling_service.max_retries = max(1, max_retries)  # Minimum 1 retry
        
        if retry_delay is not None:
            polling_service.retry_delay = max(10, retry_delay)  # Minimum 10 seconds
        
        return PollingResponse(
            success=True,
            message="Polling service configured successfully",
            data={
                "polling_interval": polling_service.polling_interval,
                "max_retries": polling_service.max_retries,
                "retry_delay": polling_service.retry_delay
            }
        )
        
    except Exception as e:
        logger.error(f"Error configuring polling service: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to configure polling service: {str(e)}"
        )
