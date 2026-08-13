from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base para schemas que se pueblan directamente desde objetos SQLAlchemy."""

    model_config = ConfigDict(from_attributes=True)


class TeamOut(ORMModel):
    id: int
    name: str
    short_name: str
    city: str
    stadium: str
    altitude_m: float


class RefereeOut(ORMModel):
    id: int
    name: str
    avg_yellow_per_match: float
    avg_red_per_match: float
    strictness_index: float


class WeatherContext(BaseModel):
    venue_altitude_m: float
    temperature_c: float
    humidity_pct: float
    home_rest_days: int
    away_rest_days: int
    away_travel_km: float
