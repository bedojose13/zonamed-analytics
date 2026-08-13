"""Riesgo disciplinario por jugador para la ficha de un partido concreto (ficha 'Disciplina' del
frontend): combina el `card_proneness_index` histórico del jugador (app/services/player_aggregates.py)
con la rigurosidad del árbitro asignado vía el GLM logístico de app/predictive/cards_model.py."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, Player
from app.predictive.cards_model import predict_player_booking_probability

BASELINE_BOOKING_PROBABILITY = 0.18  # tasa base liga de amonestación por jugador involucrado


def top_discipline_risks(db: Session, match: Match, referee_strictness_index: float, top_n: int = 6) -> list[dict]:
    stmt = select(Player).where(Player.team_id.in_([match.home_team_id, match.away_team_id]))
    players = db.execute(stmt).scalars().all()

    risks = []
    for player in players:
        fallback = BASELINE_BOOKING_PROBABILITY * max(player.card_proneness_index, 0.1)
        prob = predict_player_booking_probability(
            {
                "card_proneness_index": player.card_proneness_index,
                "referee_strictness_index": referee_strictness_index,
            },
            fallback_p=min(fallback, 0.9),
        )
        team_short = match.home_team.short_name if player.team_id == match.home_team_id else match.away_team.short_name
        risks.append({
            "player_id": player.id, "player_name": player.name, "team_short_name": team_short,
            "card_proneness_index": player.card_proneness_index, "prob_booked": round(prob, 3),
        })

    risks.sort(key=lambda r: r["prob_booked"], reverse=True)
    return risks[:top_n]
