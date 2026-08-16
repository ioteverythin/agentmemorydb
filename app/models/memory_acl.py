"""Memory ACL — explicit access grants for ``restricted`` memories."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MemoryACL(Base):
    """A grant that lets a principal read a ``restricted`` memory.

    ``principal_type`` is ``user`` (``principal_id`` = a user UUID string) or
    ``agent`` (``principal_id`` = an agent identifier). Grants are additive:
    a memory is visible to a viewer if any grant matches.
    """

    __tablename__ = "memory_acls"
    __table_args__ = (
        UniqueConstraint(
            "memory_id", "principal_type", "principal_id", name="uq_memory_acl_principal"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    principal_type: Mapped[str] = mapped_column(String(16), nullable=False)  # user | agent
    principal_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
