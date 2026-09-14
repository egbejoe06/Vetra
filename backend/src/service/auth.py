from typing import Any, Dict, Optional
from fastapi import HTTPException, status
from supabase import AuthApiError, AuthError, Client
from config import settings
from src.db.supabase import supabase
from src.schemas.user import UserCreate, UserLogin


class AuthService:
    """Authentication service handling user registration and login via Supabase Auth."""

    def __init__(self, client: Client = supabase):
        self.supabase = client

    def create_account(self, user_data: UserCreate) -> Dict[str, Any]:
        """
        Create a new user account with validated Pydantic model and immediate session generation.
        Email verification is bypassed; users receive their active session immediately upon signup.

        Args:
            user_data: Validated UserCreate Pydantic model.

        Returns:
            Dict containing user object, session, access_token, and refresh_token.
        """
        try:
            response = self.supabase.auth.sign_up({
                "email": user_data.email,
                "password": user_data.password,
                "options": {
                    "data": {
                        "first_name": user_data.first_name,
                        "last_name": user_data.last_name,
                        "full_name": f"{user_data.first_name} {user_data.last_name}".strip(),
                        "role": user_data.role,
                    }
                },
            })

            if not response.user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to create user account."
                )

            return {
                "user": response.user,
                "session": response.session,
                "access_token": response.session.access_token if response.session else None,
                "refresh_token": response.session.refresh_token if response.session else None,
                "token_type": response.session.token_type if response.session else "bearer",
                "message": "Account created successfully.",
            }
        except AuthApiError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred during account creation: {str(e)}"
            )

    def login(self, credentials: UserLogin) -> Dict[str, Any]:
        """
        Authenticate an existing user with validated UserLogin model.

        Args:
            credentials: Validated UserLogin Pydantic model.

        Returns:
            Dict containing user object, session, access_token, refresh_token, and token_type.
        """
        try:
            response = self.supabase.auth.sign_in_with_password({
                "email": credentials.email,
                "password": credentials.password,
            })

            if not response.user or not response.session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password."
                )

            return {
                "user": response.user,
                "session": response.session,
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token,
                "token_type": response.session.token_type,
                "message": "Login successful.",
            }
        except AuthApiError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred during login: {str(e)}"
            )


# Default singleton instance
auth_service = AuthService()


def create_account(user_data: UserCreate) -> Dict[str, Any]:
    """Convenience functional wrapper for create_account."""
    return auth_service.create_account(user_data)


def login(credentials: UserLogin) -> Dict[str, Any]:
    """Convenience functional wrapper for login."""
    return auth_service.login(credentials)

