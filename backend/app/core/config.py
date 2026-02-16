from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # Core Configuration
    app_name: str = Field(default="Meahana Attendee", description="Application name")
    environment: str = Field(default="production", description="Environment")
    debug: bool = Field(default=False, description="Debug mode")
    
    # Service API Key (for authenticating requests from Meahana Backend)
    meahana_api_key: str = Field(..., description="API key for service-to-service authentication")
    
    # Supabase Configuration
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_anon_key: str = Field(..., description="Supabase anonymous key")
    supabase_service_role_key: str = Field(..., description="Supabase service role key")
    
    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    
    # Ngrok Configuration
    ngrok_auth_token: Optional[str] = Field(default=None, description="Ngrok authentication token")

    # OpenAI Configuration
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key for AI analysis")
    
    # Attendee API
    attendee_api_key: str = Field(..., description="Attendee API key")
    attendee_api_base_url: str = Field(default="https://app.attendee.dev", description="Attendee API base URL")
    
    # Polling Configuration
    polling_interval: int = Field(default=30, description="Polling interval in seconds")
    polling_max_retries: int = Field(default=3, description="Maximum polling retry attempts")
    polling_retry_delay: int = Field(default=60, description="Delay between polling retries in seconds")
    
    # Webhook Configuration
    webhook_base_url: str = Field(..., description="Base URL for webhook endpoints (set via WEBHOOK_BASE_URL env var)")
    webhook_max_retry_attempts: int = Field(default=3, description="Maximum webhook delivery retry attempts")
    webhook_retry_delays: str = Field(default="5,30,300", description="Comma-separated retry delays in seconds")
    webhook_fallback_timeout: int = Field(default=30, description="Webhook delivery timeout in seconds")
    
    # Outgoing Report Webhook Configuration
    report_webhook_url: Optional[str] = Field(default=None, description="URL to POST reportcards to after analysis completes")
    report_webhook_signing_secret: Optional[str] = Field(default=None, description="HMAC-SHA256 secret for signing outgoing webhook payloads")
    report_webhook_timeout: int = Field(default=10, description="HTTP timeout in seconds for outgoing report webhooks")
    report_webhook_max_retries: int = Field(default=3, description="Maximum retry attempts for outgoing report webhooks")
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment.lower() == "production"
    
    @property
    def should_use_ngrok(self) -> bool:
        """Check if ngrok should be used for webhook URLs"""
        return self.environment.lower() == "development" and not self.webhook_base_url
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings() 