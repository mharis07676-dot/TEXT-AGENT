import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.bootstrap import init_db
from app.config import get_settings, validate_required_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    validate_required_settings(settings)
    await init_db()
    logger.info("Text Agent API started env=%s", settings.app_env)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/")
    async def root() -> dict:
        return {
            "service": settings.app_name,
            "status": "ok",
            "docs": "/docs",
            "health": "/health",
            "api": settings.api_prefix,
            "note": "Shared SMS + WhatsApp text agent API.",
        }

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "service": settings.app_name,
            "env": settings.app_env,
            "twilio_configured": settings.twilio_configured,
            "sms_configured": settings.sms_configured,
            "whatsapp_configured": settings.whatsapp_configured,
            "openai_configured": settings.openai_configured,
        }

    return app


app = create_app()
