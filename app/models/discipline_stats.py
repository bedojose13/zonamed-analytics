from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MatchDisciplineStats(Base):
    """Faltas/tarjetas por equipo y partido (b/c). Una fila por (match, team)."""

    __tablename__ = "match_discipline_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    is_home: Mapped[bool] = mapped_column(default=True)

    fouls_committed: Mapped[int] = mapped_column(Integer, default=0)
    fouls_received: Mapped[int] = mapped_column(Integer, default=0)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)
    aggression_index: Mapped[float] = mapped_column(Float, default=1.0)  # tackles+faltas normalizado, media liga=1.0

    match: Mapped["Match"] = relationship(back_populates="discipline_stats")


class PlayerMatchStat(Base):
    """Detalle por jugador y partido: soporta la ficha 'jugador más propenso a recibir tarjeta'."""

    __tablename__ = "player_match_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)

    minutes_played: Mapped[int] = mapped_column(Integer, default=90)
    fouls_committed: Mapped[int] = mapped_column(Integer, default=0)
    fouls_received: Mapped[int] = mapped_column(Integer, default=0)
    yellow_card: Mapped[bool] = mapped_column(default=False)
    red_card: Mapped[bool] = mapped_column(default=False)

    match: Mapped["Match"] = relationship(back_populates="player_stats")
    player: Mapped["Player"] = relationship()
