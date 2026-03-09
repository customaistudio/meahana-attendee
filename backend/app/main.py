from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
from app.routers import bots, reports, webhooks, ngrok, auth
import logging
from pathlib import Path

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
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

if getattr(settings, "frontend_url", None):
    allowed_origins.append(settings.frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(bots.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/meeting")
app.include_router(webhooks.router)
app.include_router(ngrok.router)

# Serve static files (React build)
# Determine the build directory path
build_dir = Path(__file__).parent.parent.parent / "build"

if build_dir.exists():
    # Mount static files
    app.mount("/static", StaticFiles(directory=str(build_dir / "static")), name="static")

    @app.get("/api")
    async def api_root():
        """API root endpoint"""
        return {
            "message": settings.app_name,
            "version": "1.0.0",
            "environment": settings.environment
        }

    # Serve React app for all other routes
    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        """Serve React app"""
        # Check if it's an API route
        if full_path.startswith("api/") or full_path.startswith("meeting/") or full_path.startswith("webhook/"):
            return {"error": "Not found"}

        # Serve index.html for all other routes (SPA routing)
        index_file = build_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"error": "Frontend not built"}
else:
    @app.get("/")
    async def root():
        """Root endpoint (development mode - no frontend build)"""
        return {
            "message": settings.app_name,
            "version": "1.0.0",
            "environment": settings.environment,
            "note": "Frontend not built. Run 'npm run build' to build the frontend."
        }

@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    # Application startup complete
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