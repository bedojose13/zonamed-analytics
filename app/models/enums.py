import enum


class MatchStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"       # próximo partido, aún no jugado
    LIVE = "LIVE"                 # en curso (no usado por los endpoints actuales, reservado)
    FINISHED = "FINISHED"         # jugado, con resultado real cargado
    POSTPONED = "POSTPONED"


class PlayerPosition(str, enum.Enum):
    GK = "GK"
    DF = "DF"
    MF = "MF"
    FW = "FW"


class TacticalPosture(str, enum.Enum):
    """Postura táctica dominante de un equipo en un partido: condiciona el xC (juego por bandas
    genera más córners que el juego por el centro) y el xCards (posturas de presión alta generan
    más faltas)."""

    OFENSIVO_BANDAS = "OFENSIVO_BANDAS"
    OFENSIVO_CENTRO = "OFENSIVO_CENTRO"
    EQUILIBRADO = "EQUILIBRADO"
    DEFENSIVO_BLOQUE_BAJO = "DEFENSIVO_BLOQUE_BAJO"
    PRESION_ALTA = "PRESION_ALTA"
