"""Capa de persistencia sobre el motor predictivo: genera (si hace falta) y guarda la
`Prediction` de un partido en la base de datos, para no re-simular 100,000 iteraciones en cada
request de lectura. Tanto la API como el script de backfill de históricos usan esta capa."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, MatchStatus, Prediction
from app.predictive.ensemble import generate_prediction
from app.services.team_history import HistoryCache


def get_or_create_prediction(db: Session, match: Match, *, force_refresh: bool = False,
                              history: HistoryCache | None = None) -> Prediction:
    existing = db.execute(select(Prediction).where(Prediction.match_id == match.id)).scalars().first()
    if existing is not None and not force_refresh:
        return existing

    result = generate_prediction(db, match, exclude_this_match=True, history=history)
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


def pregenerate_predictions(db: Session, *, recent_played_limit: int = 100) -> int:
    """Genera por adelantado las predicciones que la API sirve más seguido (próximos partidos y
    el histórico reciente de jugados), para que los endpoints de lectura sean siempre lecturas
    rápidas de la tabla `predictions` en vez de disparar una simulación Monte Carlo de 100,000
    iteraciones EN VIVO dentro de un request HTTP.

    Por qué esto importa en producción: generar varias predicciones nuevas de una dentro de un
    solo request (p. ej. /partidos/proximos?limit=30 la primera vez que se piden esos 30
    partidos) es lo bastante pesado en CPU/memoria como para tumbar un servidor con recursos
    limitados (Render free tier) — mejor absorber ese costo aquí, dentro del job de fondo que
    corre sin límite de tiempo de request (ver app/core/bootstrap.py).
    """
    history = HistoryCache(db)

    upcoming = db.execute(select(Match).where(Match.status == MatchStatus.SCHEDULED)).scalars().all()
    recent_played = db.execute(
        select(Match).where(Match.status == MatchStatus.FINISHED)
        .order_by(Match.kickoff.desc()).limit(recent_played_limit)
    ).scalars().all()

    generated = 0
    for i, match in enumerate(upcoming + recent_played, start=1):
        existing = db.execute(select(Prediction).where(Prediction.match_id == match.id)).scalars().first()
        if existing is not None:
            continue
        get_or_create_prediction(db, match, history=history)
        generated += 1
        if i % 10 == 0:
            db.commit()
    db.commit()
    return generated
