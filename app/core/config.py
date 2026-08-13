"""Configuración centralizada de la plataforma (12-factor: todo por entorno)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ZONAMED_", env_file=".env", extra="ignore")

    app_name: str = "Zonamed Analytics — BetPlay Dimayor"
    database_url: str = f"sqlite:///{BASE_DIR / 'zonamed.db'}"
    models_dir: Path = BASE_DIR / "artifacts" / "models"

    # Ventanas de forma reciente usadas en el feature engineering
    rolling_window_matches: int = 20
    exponential_half_life_matches: float = 5.0  # partidos hasta que el peso cae a la mitad

    # Simulación Monte Carlo
    monte_carlo_iterations: int = 100_000
    monte_carlo_random_seed: int = 42

    # Líneas de mercado por defecto (se pueden pedir otras vía API)
    default_corner_line: float = 8.5
    default_card_line: float = 3.5

    # Auto-seed/auto-train al arrancar si la base está vacía o faltan modelos (útil en la nube,
    # donde no hay terminal para correr los scripts a mano antes del primer request)
    auto_bootstrap: bool = True

    # Ingesta de datos reales (API-Football — https://www.api-football.com/)
    football_api_key: str = ""
    football_api_base_url: str = "https://v3.football.api-sports.io"
    football_league_id: int = 239   # Colombia - Primera A (Liga BetPlay Dimayor)
    football_season: int = 2024     # el plan free solo cubre 2022-2024, no la temporada en curso
    football_calls_per_run: int = 80   # margen bajo el límite de 100/día del plan gratuito
    admin_sync_token: str = ""      # requerido para llamar POST /admin/sync manualmente

    def ensure_dirs(self) -> None:
        self.models_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
