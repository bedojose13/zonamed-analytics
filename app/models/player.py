from __future__ import annotations

from sqlalchemy import Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import PlayerPosition


class Player(Base):
    """Métricas disciplinarias agregadas por jugador (b/c): usadas para identificar al jugador
    más propenso a recibir tarjeta en un partido dado (feature: card_proneness)."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    position: Mapped[PlayerPosition] = mapped_column(Enum(PlayerPosition))

    # Promedios históricos de temporada (recalculados por el pipeline de feature engineering;
    # aquí se guarda el último valor consolidado para lecturas rápidas desde la API).
    avg_fouls_committed: Mapped[float] = mapped_column(Float, default=0.0)
    avg_fouls_received: Mapped[float] = mapped_column(Float, default=0.0)
    avg_yellow_cards: Mapped[float] = mapped_column(Float, default=0.0)
    avg_red_cards: Mapped[float] = mapped_column(Float, default=0.0)
    card_proneness_index: Mapped[float] = mapped_column(Float, default=0.0)

    team: Mapped["Team"] = relationship(back_populates="players")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Player {self.name}>"
