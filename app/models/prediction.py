from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Prediction(Base):
    """Salida congelada del motor predictivo para un partido (una fila por partido).

    Se guarda tanto el resumen escalar (medias esperadas, usado en las vistas de listado)
    como el `monte_carlo_matrix` completo en JSON (distribución de probabilidad discreta por
    marcador, córners y tarjetas) para que la vista de análisis detallado no tenga que
    re-simular en cada request. `model_version` permite auditar qué versión del ensemble
    generó cada predicción cuando se reentrena el modelo.
    """

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), unique=True, index=True)
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    model_version: Mapped[str] = mapped_column(String(20), default="v1")

    # --- 1X2 (resumen) ---
    prob_home_win: Mapped[float] = mapped_column(Float)
    prob_draw: Mapped[float] = mapped_column(Float)
    prob_away_win: Mapped[float] = mapped_column(Float)
    expected_home_goals: Mapped[float] = mapped_column(Float)
    expected_away_goals: Mapped[float] = mapped_column(Float)
    most_likely_score: Mapped[str] = mapped_column(String(10))

    # --- Córners (resumen) ---
    expected_home_corners: Mapped[float] = mapped_column(Float)
    expected_away_corners: Mapped[float] = mapped_column(Float)
    prob_over_corner_line: Mapped[float] = mapped_column(Float)
    corner_line_used: Mapped[float] = mapped_column(Float)

    # --- Tarjetas/faltas (resumen) ---
    expected_home_cards: Mapped[float] = mapped_column(Float)
    expected_away_cards: Mapped[float] = mapped_column(Float)
    expected_total_fouls: Mapped[float] = mapped_column(Float)
    prob_over_card_line: Mapped[float] = mapped_column(Float)
    prob_red_card_shown: Mapped[float] = mapped_column(Float)
    card_line_used: Mapped[float] = mapped_column(Float)

    # Matriz completa de Monte Carlo + metadatos de features usados (auditable, ver schemas.prediction)
    monte_carlo_matrix: Mapped[dict] = mapped_column(JSON)
    feature_snapshot: Mapped[dict] = mapped_column(JSON)

    match: Mapped["Match"] = relationship(back_populates="prediction")
