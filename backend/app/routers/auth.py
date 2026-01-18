"""Authentication router for user registration, login, and token management"""

from fastapi import APIRouter, HTTPException, status, Request, Depends

from app.models import (
    RegisterRequest,
    LoginRequest,
    LoginResponse,
    TokenResponse,
    RefreshTokenRequest,
    UserResponse,
    MessageResponse,
)
from app.services.auth_service import AuthService
from app.dependencies.auth import get_current_active_user

router = APIRouter()


def get_client_info(request: Request) -> tuple:
    """Extract client info from request"""
    user_agent = request.headers.get("user-agent", "")
    forwarded_for = request.headers.get("x-forwarded-for")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host
    return user_agent, client_ip


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """Register a new user"""
    auth_service = AuthService()

    try:
        user = await auth_service.register_user(
            email=request.email,
            password=request.password,
            full_name=request.full_name
        )
        return UserResponse(**user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user"
        )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, http_request: Request):
    """Login and get access + refresh tokens"""
    auth_service = AuthService()
    user_agent, client_ip = get_client_info(http_request)

    try:
        result = await auth_service.authenticate_user(
            email=request.email,
            password=request.password,
            device_info=user_agent,
            ip_address=client_ip
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        return LoginResponse(
            user=UserResponse(**result["user"]),
            tokens=TokenResponse(**result["tokens"])
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to login"
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, http_request: Request):
    """Refresh access token using refresh token"""
    auth_service = AuthService()
    user_agent, client_ip = get_client_info(http_request)

    try:
        result = await auth_service.refresh_tokens(
            refresh_token=request.refresh_token,
            device_info=user_agent,
            ip_address=client_ip
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
            )

        return TokenResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh token"
        )


@router.post("/logout", response_model=MessageResponse)
async def logout(request: RefreshTokenRequest):
    """Logout by revoking the refresh token"""
    auth_service = AuthService()

    try:
        success = await auth_service.logout(request.refresh_token)

        if not success:
            return MessageResponse(
                message="Token already revoked or invalid",
                success=True
            )

        return MessageResponse(
            message="Successfully logged out",
            success=True
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to logout"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_active_user)):
    """Get current authenticated user info"""
    return UserResponse(**current_user)
