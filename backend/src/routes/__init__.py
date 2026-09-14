from fastapi import APIRouter
from src.routes.health import router as health_router
from src.routes.auth import router as auth_router
from src.routes.interview import router as interview_router
from src.routes.planner import router as planner_router
from src.routes.websocket import router as websocket_router
from src.routes.candidate import router as candidate_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(interview_router)
api_router.include_router(planner_router)
api_router.include_router(websocket_router)
api_router.include_router(candidate_router)



