from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.ai.exceptions import AIServiceError
from app.config import settings
from app.database import engine
from app.routers import ai, auth, projects, reviews, tests


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_auth_configuration()
    yield


app = FastAPI(title=settings.app_name, version="0.5.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(ai.router)
app.include_router(reviews.router)
app.include_router(tests.router)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "devpilot-api"}


@app.get("/api/v1/status", tags=["operations"])
def status() -> dict[str, str | bool]:
    return {
        "application": settings.app_name,
        "environment": settings.environment,
        "llm_configured": bool(settings.openai_api_key),
    }


@app.get("/api/v1/health/database", tags=["operations"])
def database_health() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Database connection failed") from exc
    return {"status": "ok", "database": "connected"}


@app.exception_handler(AIServiceError)
async def ai_service_error_handler(_, exc: AIServiceError):
    return JSONResponse(
        status_code=exc.http_status,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
