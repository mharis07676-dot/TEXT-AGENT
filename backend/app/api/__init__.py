from fastapi import APIRouter

from app.api import auth, messaging

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(messaging.router)
