from __future__ import annotations

from sqlalchemy import Enum, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import TacticalPosture


class MatchCornerStats(Base):
    """Métricas granulares de córners por equipo y partido (b). Una fila por (match, team):
    dos filas por partido (local/visitante). Estas son las variables crudas que alimentan el
    cálculo de Expected Corners (xC) — ver app/services/xg_corners.py."""

    __tablename__ = "match_corner_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    is_home: Mapped[bool] = mapped_column(default=True)

    corners_won: Mapped[int] = mapped_column(Integer, default=0)
    crosses_completed: Mapped[int] = mapped_column(Integer, default=0)
    crosses_attempted: Mapped[int] = mapped_column(Integer, default=0)
    shots_blocked_by_opponent: Mapped[int] = mapped_column(Integer, default=0)
    wing_play_index: Mapped[float] = mapped_column(Float, default=0.5)  # 0=juego x el centro, 1=100% bandas
    possession_pct: Mapped[float] = mapped_column(Float, default=50.0)
    tactical_posture: Mapped[TacticalPosture] = mapped_column(
        Enum(TacticalPosture), default=TacticalPosture.EQUILIBRADO
    )

    match: Mapped["Match"] = relationship(back_populates="corner_stats")
