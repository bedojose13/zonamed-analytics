from __future__ import annotations

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Team(Base):
    """Equipo de la Liga BetPlay Dimayor. Incluye el contexto geográfico de su estadio sede,
    determinante para el desgaste físico del rival visitante (altitud/humedad/temperatura)."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    short_name: Mapped[str] = mapped_column(String(10))
    city: Mapped[str] = mapped_column(String(60))
    stadium: Mapped[str] = mapped_column(String(80))

    # --- Contexto geográfico/climático fijo del estadio sede (d) ---
    altitude_m: Mapped[float] = mapped_column(Float, default=0.0)
    avg_temperature_c: Mapped[float] = mapped_column(Float, default=22.0)
    avg_humidity_pct: Mapped[float] = mapped_column(Float, default=60.0)

    players: Mapped[list["Player"]] = relationship(back_populates="team")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Team {self.short_name}>"
