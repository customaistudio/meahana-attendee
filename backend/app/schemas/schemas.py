from enum import Enum
from pydantic import BaseModel, HttpUrl, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class MeetingStatus(str, Enum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Base schemas
class MeetingBase(BaseModel):
    meeting_url: HttpUrl
    bot_name: str
    join_at: Optional[datetime] = None


class MeetingCreate(MeetingBase):
    pass


class MeetingUpdate(BaseModel):
    meeting_url: Optional[HttpUrl] = None
    bot_name: Optional[str] = None
    join_at: Optional[datetime] = None


class MeetingResponse(BaseModel):
    id: int
    meeting_url: HttpUrl
    bot_name: Optional[str] = None  # Will be populated from meeting_metadata
    bot_id: Optional[str] = None
    status: MeetingStatus
    meeting_metadata: Dict[str, Any]
    join_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        
    @field_validator('bot_name', mode='before')
    @classmethod
    def extract_bot_name(cls, v, info):
        """Extract bot_name from meeting_metadata if not directly provided"""
        if v is None and 'meeting_metadata' in info.data:
            return info.data['meeting_metadata'].get('bot_name')
        return v


# Transcript schemas
class TranscriptChunkBase(BaseModel):
    speaker: Optional[str] = None
    text: str
    timestamp: datetime
    confidence: Optional[str] = None


class TranscriptChunkResponse(TranscriptChunkBase):
    id: int
    meeting_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Alias for backward compatibility
TranscriptChunkSchema = TranscriptChunkResponse


# Report schemas
class ReportScore(BaseModel):
    overall_score: float
    sentiment: str
    key_topics: List[str]
    action_items: List[str]
    participants: List[str]
    engagement_score: float
    meeting_effectiveness: float
    summary: str
    insights: List[str]
    recommendations: List[str]


class ReportResponse(BaseModel):
    id: int
    meeting_id: int
    score: ReportScore
    created_at: datetime

    class Config:
        from_attributes = True


# Alias for backward compatibility
ReportSchema = ReportResponse


# Webhook schemas
class WebhookPayload(BaseModel):
    idempotency_key: Optional[str] = None
    bot_id: Optional[str] = None
    bot_metadata: Optional[Dict[str, Any]] = None
    trigger: str
    data: Dict[str, Any]
    
    def get_event_type(self) -> str:
        """Extract event type from payload data"""
        # For bot.state_change trigger, check the data.event_type
        if self.trigger == "bot.state_change":
            return self.data.get("event_type", "bot.state_change")
        
        # For transcript.update trigger
        elif self.trigger == "transcript.update":
            return "transcript.chunk"
        
        # For chat_messages.update trigger
        elif self.trigger == "chat_messages.update":
            return "chat_message"
        
        # For participant_events.join_leave trigger
        elif self.trigger == "participant_events.join_leave":
            return f"participant_events.{self.data.get('event_type', 'unknown')}"
        
        # Default to trigger type
        return self.trigger
    
    def get_bot_id(self) -> Optional[str]:
        """Extract bot ID from payload data"""
        return self.bot_id


# Composite schemas
class MeetingWithReport(BaseModel):
    meeting: MeetingResponse
    report: Optional[ReportResponse] = None

    class Config:
        from_attributes = True


class MeetingWithTranscripts(BaseModel):
    meeting: MeetingResponse
    transcript_chunks: List[TranscriptChunkResponse] = []

    class Config:
        from_attributes = True


class MeetingReportResponse(BaseModel):
    meeting_id: int
    status: str
    message: Optional[str] = None
    scorecard: Optional[ReportScore] = None
    created_at: Optional[datetime] = None


# Scorecard response
class ScorecardResponse(BaseModel):
    meeting_id: int
    status: str
    message: Optional[str] = None
    scorecard: Optional[ReportScore] = None
    created_at: Optional[datetime] = None


# Bot creation response
class BotCreateResponse(BaseModel):
    id: int
    meeting_url: str
    bot_id: str
    status: str
    meeting_metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


# Status polling response
class StatusPollResponse(BaseModel):
    status_updated: bool
    new_status: Optional[str] = None
    message: str


# API responses
class MessageResponse(BaseModel):
    message: str


class ListResponse(BaseModel):
    items: List[Any]
    total: int


# Authentication schemas
class UserSignUp(BaseModel):
    email: str
    password: str


class UserSignIn(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    created_at: datetime
    user_metadata: Optional[Dict[str, Any]] = None


class SessionInfo(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: Optional[datetime] = None


class AuthResponse(BaseModel):
    success: bool
    message: str
    user: Optional[UserResponse] = None
    session: Optional[SessionInfo] = None 