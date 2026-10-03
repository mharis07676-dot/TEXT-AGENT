from fastapi import APIRouter

from app.api import messaging

api_router = APIRouter()
api_router.include_router(messaging.router)
