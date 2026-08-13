from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import MatchStatus


class Match(Base):
    """Partido de la Liga BetPlay Dimayor: cubre tanto próximos (SCHEDULED) como jugados
    (FINISHED). Los campos `*_real` quedan NULL hasta que el partido se disputa; el histórico
    post-match (módulo 4b del brief) compara estos valores contra los guardados en `Prediction`.
    """

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True, index=True)
    # True una vez se trajo /fixtures/statistics para este partido (llamada aparte, limitada por
    # el cupo diario de la API — puede haber partidos FINISHED con esto todavía en False).
    stats_synced: Mapped[bool] = mapped_column(Boolean, default=False)

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    referee_id: Mapped[int | None] = mapped_column(ForeignKey("referees.id"), nullable=True)

    matchday: Mapped[int] = mapped_column(Integer)
    kickoff: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus), default=MatchStatus.SCHEDULED)

    # --- Contexto geográfico/climático del día del partido (d) ---
    venue_altitude_m: Mapped[float] = mapped_column(Float, default=0.0)
    temperature_c: Mapped[float] = mapped_column(Float, default=22.0)
    humidity_pct: Mapped[float] = mapped_column(Float, default=60.0)

    # Cansancio acumulado: días de descanso desde el partido anterior de cada equipo.
    home_rest_days: Mapped[int] = mapped_column(Integer, default=7)
    away_rest_days: Mapped[int] = mapped_column(Integer, default=7)
    away_travel_km: Mapped[float] = mapped_column(Float, default=0.0)

    # --- Resultado real (a) — NULL hasta FINISHED ---
    home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)

    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])
    referee: Mapped["Referee | None"] = relationship()

    corner_stats: Mapped[list["MatchCornerStats"]] = relationship(back_populates="match")
    discipline_stats: Mapped[list["MatchDisciplineStats"]] = relationship(back_populates="match")
    player_stats: Mapped[list["PlayerMatchStat"]] = relationship(back_populates="match")
    prediction: Mapped["Prediction | None"] = relationship(back_populates="match", uselist=False)

    @property
    def is_finished(self) -> bool:
        return self.status == MatchStatus.FINISHED

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Match #{self.id} {self.home_team_id} vs {self.away_team_id}>"
