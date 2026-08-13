from __future__ import annotations

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Referee(Base):
    """Historial disciplinario del árbitro (c): la rigurosidad del central es uno de los
    predictores más fuertes de xCards y debe entrar multiplicativamente en el modelo de
    tarjetas (ver app/services/xcards.py)."""

    __tablename__ = "referees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    matches_officiated: Mapped[int] = mapped_column(Integer, default=0)
    avg_yellow_per_match: Mapped[float] = mapped_column(Float, default=3.8)
    avg_red_per_match: Mapped[float] = mapped_column(Float, default=0.15)
    avg_fouls_called_per_match: Mapped[float] = mapped_column(Float, default=22.0)

    # Índice de rigurosidad normalizado (media liga = 1.0). > 1 => más estricto que el promedio.
    strictness_index: Mapped[float] = mapped_column(Float, default=1.0)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Referee {self.name}>"
