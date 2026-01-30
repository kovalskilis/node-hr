from fastapi import APIRouter

from app.api.endpoints.interview import interview_router

api_router = APIRouter()

api_router.include_router(interview_router, prefix="/interview", tags=["interview"])
