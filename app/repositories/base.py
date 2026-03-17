"""Base repository with common CRUD operations."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Thin data-access layer over an async SQLAlchemy session."""

    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self._model = model
        self._session = session

    async def get_by_id(self, id: uuid.UUID) -> ModelT | None:
        return await self._session.get(self._model, id)

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        stmt = select(self._model).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(self, obj: ModelT) -> ModelT:
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def update_fields(self, id: uuid.UUID, **values: Any) -> ModelT | None:
        stmt = (
            update(self._model)
            .where(self._model.id == id)  # type: ignore[attr-defined]
            .values(**values)
            .returning(self._model)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            await self._session.flush()
        return row

    async def delete(self, id: uuid.UUID) -> bool:
        obj = await self.get_by_id(id)
        if obj is None:
            return False
        await self._session.delete(obj)
        await self._session.flush()
        return True
