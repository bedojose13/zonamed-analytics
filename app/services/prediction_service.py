"""Capa de persistencia sobre el motor predictivo: genera (si hace falta) y guarda la
`Prediction` de un partido en la base de datos, para no re-simular 100,000 iteraciones en cada
request de lectura. Tanto la API como el script de backfill de históricos usan esta capa."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, Prediction
from app.predictive.ensemble import generate_prediction


def get_or_create_prediction(db: Session, match: Match, *, force_refresh: bool = False) -> Prediction:
    existing = db.execute(select(Prediction).where(Prediction.match_id == match.id)).scalars().first()
    if existing is not None and not force_refresh:
        return existing

    result = generate_prediction(db, match, exclude_this_match=True)
    summary, mc, snapshot = result["summary"], result["monte_carlo"], result["feature_snapshot"]

    if existing is not None:
        prediction = existing
    else:
        prediction = Prediction(match_id=match.id)
        db.add(prediction)

    for field in (
        "model_version", "prob_home_win", "prob_draw", "prob_away_win",
        "expected_home_goals", "expected_away_goals", "most_likely_score",
        "expected_home_corners", "expected_away_corners", "corner_line_used", "prob_over_corner_line",
        "expected_home_cards", "expected_away_cards", "expected_total_fouls",
        "card_line_used", "prob_over_card_line", "prob_red_card_shown",
    ):
        setattr(prediction, field, summary[field])

    prediction.monte_carlo_matrix = mc
    prediction.feature_snapshot = snapshot
    db.flush()
    return prediction
