from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import single, batch, status
from app.routers import auth, history
from app.database import get_database
from app.services import redis_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events"""
    # Startup
    logger.info("Starting up application...")
    db = get_database()
    try:
        await db.connect()
        logger.info("Database connection established")
    except Exception as e:
        logger.warning(f"Database connection failed: {e}. Auth features will be unavailable.")

    # Connect Redis
    try:
        r = await redis_client.get_redis()
        await r.ping()
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Job persistence will be unavailable.")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    try:
        await redis_client.close_redis()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.warning(f"Error closing Redis: {e}")
    try:
        await db.disconnect()
        logger.info("Database connection closed")
    except Exception as e:
        logger.warning(f"Error closing database: {e}")


app = FastAPI(
    title="Document Meta-Tagging API",
    version="2.0.0",
    description="AI-powered document tagging system with authentication",
    lifespan=lifespan
)

# CORS setup for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(single.router, prefix="/api/single", tags=["Single PDF"])
app.include_router(batch.router, prefix="/api/batch", tags=["Batch Processing"])
app.include_router(status.router, prefix="/api", tags=["Status"])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(history.router, prefix="/api/history", tags=["History"])


@app.get("/")
def root():
    return {"message": "Document Meta-Tagging API", "version": "2.0.0"}
