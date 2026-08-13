from __future__ import annotations

from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Rivalry(Base):
    """Derbis / rivalidades de alta tensión (c). El `intensity_index` (1.0 = liga promedio)
    escala el xCards vía el ajuste H2H — ver app/services/xcards.py."""

    __tablename__ = "rivalries"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    intensity_index: Mapped[float] = mapped_column(Float, default=1.3)
    label: Mapped[str] = mapped_column(default="")
