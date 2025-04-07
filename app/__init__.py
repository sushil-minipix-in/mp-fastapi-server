import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    """
    Application factory pattern to create and configure the FastAPI app
    """
    app = FastAPI(
        title=settings.APP_NAME,
        description="MiniPix FastAPI Server with best practices",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, specify the allowed origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Import and register routers
    from app.routers import user_router, auth_router
    app.include_router(user_router.router)
    app.include_router(auth_router.router)
    
    # Add health check endpoint
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": "1.0.0"}
    
    logger.info(f"Application {settings.APP_NAME} initialized")
    return app

