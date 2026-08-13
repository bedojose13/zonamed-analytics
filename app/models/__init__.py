"""Registro central de modelos ORM: importar este paquete garantiza que todas las tablas
queden registradas en `Base.metadata` antes de llamar a `create_all`."""
from app.models.discipline_stats import MatchDisciplineStats, PlayerMatchStat
from app.models.corner_stats import MatchCornerStats
from app.models.enums import MatchStatus, PlayerPosition, TacticalPosture
from app.models.match import Match
from app.models.player import Player
from app.models.prediction import Prediction
from app.models.referee import Referee
from app.models.rivalry import Rivalry
from app.models.team import Team

__all__ = [
    "Team",
    "Player",
    "Referee",
    "Rivalry",
    "Match",
    "MatchCornerStats",
    "MatchDisciplineStats",
    "PlayerMatchStat",
    "Prediction",
    "MatchStatus",
    "PlayerPosition",
    "TacticalPosture",
]
