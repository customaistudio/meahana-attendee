from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import bots, reports, webhooks, ngrok
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Meahana Attendee Integration API",
    version="1.0.0",
)

# Add CORS middleware
allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(bots.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/meeting")
app.include_router(webhooks.router)
app.include_router(ngrok.router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": settings.app_name,
        "version": "1.0.0",
        "environment": settings.environment,
    }


@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    pass


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
    )