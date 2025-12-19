from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import single, batch, status

app = FastAPI(
    title="Document Meta-Tagging API",
    version="1.0.0",
    description="AI-powered document tagging system using OpenRouter"
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


@app.get("/")
def root():
    return {"message": "Document Meta-Tagging API", "version": "1.0.0"}

