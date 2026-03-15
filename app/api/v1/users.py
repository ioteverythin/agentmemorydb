"""User endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserResponse

router = APIRouter()


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    repo = UserRepository(session)
    user = User(name=data.name, email=data.email, external_id=data.external_id)
    user = await repo.create(user)
    return UserResponse.model_validate(user)
