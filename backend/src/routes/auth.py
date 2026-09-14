from fastapi import APIRouter, status
from src.schemas.user import UserCreate, UserLogin
from src.service.auth import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserCreate):
    """
    Create a new user account (Candidate or Recruiter).
    """
    return auth_service.create_account(user_data)


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(credentials: UserLogin):
    """
    Authenticate user with email and password.
    """
    return auth_service.login(credentials)
