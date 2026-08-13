# Zonamed Analytics — Liga BetPlay Dimayor

Plataforma de analítica y predicción probabilística multi-mercado (1X2/marcador exacto,
córners, tarjetas/faltas) para la Liga BetPlay Dimayor.

## Arquitectura

```
zonamed-analytics/
├── app/
│   ├── core/            # config (pydantic-settings) y motor de base de datos (SQLAlchemy)
│   ├── models/           # ORM: Team, Player, Referee, Rivalry, Match, MatchCornerStats,
│   │                      MatchDisciplineStats, PlayerMatchStat, Prediction
│   ├── schemas/          # Pydantic: I/O de la API (request/response)
│   ├── services/         # feature engineering: xC, xCards, xGoals, ponderación exponencial,
│   │                      promedios de liga auto-calibrados, riesgo disciplinario por jugador
│   ├── predictive/        # motor: Poisson biparamétrico (Dixon-Coles), XGBoost, Binomial
│   │                      Negativa (córners), GLM (tarjetas), Monte Carlo (100k iteraciones)
│   ├── api/               # FastAPI: routers de los 3 endpoints requeridos
│   └── scripts/           # seed_db.py (datos sintéticos) y train_models.py (entrenamiento)
├── frontend/              # Streamlit: 3 vistas (Próximos, Análisis Detallado, Jugados)
├── artifacts/models/      # modelos entrenados (.joblib) — se genera al entrenar
└── requirements.txt
```

**Flujo de datos:** `seed_db.py` puebla la base (SQLite por defecto) → `train_models.py`
calibra los promedios de liga y entrena XGBoost/Binomial Negativa/GLM sobre el histórico →
la API genera predicciones bajo demanda combinando Poisson biparamétrico + esas correcciones
aprendidas + una simulación Monte Carlo de 100,000 iteraciones, y las cachea en la tabla
`predictions` → el frontend Streamlit consume la API vía HTTP.

## IMPORTANTE: datos sintéticos

`app/scripts/seed_db.py` genera 20 equipos reales de la Dimayor (nombres, ciudades, estadios y
altitudes son de dominio público) pero **resultados, plantillas y estadísticas son 100%
sintéticos**, simulados con parámetros latentes aleatorios para poder demostrar el pipeline
completo sin depender de una licencia de datos. Para producción, sustituye `seed_db.py` por un
conector real (Opta, StatsBomb, Wyscout, API-Football, etc.) que llene las mismas tablas ORM —
el resto del sistema (features, modelos, API, frontend) no necesita cambiar.

## Puesta en marcha

```powershell
# 1. Instalar dependencias (usa tu venv de preferencia)
pip install -r requirements.txt

# 2. Generar datos sintéticos (equipos, árbitros, plantillas, 19 jornadas)
python -m app.scripts.seed_db

# 3. Entrenar / calibrar el ensemble sobre el histórico
python -m app.scripts.train_models

# 4. Levantar la API (puerto 8000, docs interactivas en /docs)
uvicorn app.api.main:app --reload --port 8000

# 5. En otra terminal, levantar el frontend
streamlit run frontend/Home.py
```

Cada vez que se cargan más partidos jugados (nuevo histórico), vuelve a correr
`train_models.py` para recalibrar los promedios de liga, ρ de Dixon-Coles y los modelos.

## Los 3 endpoints requeridos

| Endpoint | Descripción |
|---|---|
| `GET /partidos/proximos` | Próximos partidos con Ganador, córners y tarjetas probables (resumen) |
| `GET /partidos/analisis-detallado/{partido_id}` | Radiografía completa: árbitro, clima/altitud, matriz Monte Carlo íntegra, jugadores de riesgo disciplinario |
| `GET /partidos/jugados` | Histórico: resultado real vs. proyectado, con error absoluto por mercado |

## Lógica matemática — resumen

- **Ponderación exponencial** (`app/services/weighting.py`): la forma reciente pesa más que la
  antigua vía decaimiento por "vida media" (half-life), no una ventana fija equiponderada.
- **Modelo ataque/defensa** (`app/services/rate_model.py`): mismo mecanismo multiplicativo
  (estilo Dixon-Coles) generalizado a goles, córners y faltas — `λ = liga_prom × ataque_i ×
  defensa_j`. Los promedios de liga se recalculan del propio histórico (`league_baseline.py`),
  nunca son constantes fijas en el código.
- **Poisson biparamétrico + Dixon-Coles** (`app/predictive/poisson_1x2.py`): dos Poisson
  independientes (λ_local, λ_visita) corregidos por un factor τ(ρ) que infla/reduce marcadores
  bajos (0-0, 1-0, 0-1, 1-1); ρ se calibra por Máxima Verosimilitud con `scipy.optimize`.
- **XGBoost** (`app/predictive/xgboost_model.py`): corrige el prior Poisson capturando
  interacciones no lineales (altitud × descanso, etc.); el resultado final es un ensemble
  ponderado 55% Poisson / 45% XGBoost.
- **Binomial Negativa para córners** (`app/predictive/corners_model.py`): los córners están
  sobredispersos (varianza > media); NB2 (`statsmodels`) modela esa sobredispersión con un
  parámetro α adicional, evitando subestimar las colas de las líneas Over/Under.
- **GLM para tarjetas** (`app/predictive/cards_model.py`): nivel equipo (Poisson) y nivel
  jugador (logístico) cruzando agresividad de los planteles con la rigurosidad del árbitro.
- **Monte Carlo (100,000 iteraciones)** (`app/predictive/monte_carlo.py`): muestrea escenarios
  de partido completos (marcador vía draw categórico exacto sobre la matriz Dixon-Coles +
  córners y tarjetas vía Binomial Negativa) para devolver la matriz de probabilidades conjunta
  de los 4 mercados sin derivar cada uno por separado a mano.

Cada módulo trae su explicación matemática completa en el docstring del archivo.

## Notas de producción

- Las predicciones se generan on-demand y se cachean en `predictions`; en producción, un job
  programado debería regenerarlas tras cada actualización de alineación/calendario en vez de
  calcularlas en el primer request (ver comentario en `app/api/routers/proximos.py`).
- SQLite es suficiente para esta demo; cambia `ZONAMED_DATABASE_URL` a una URL de Postgres para
  producción (el ORM no requiere cambios).
- Python 3.14 es muy reciente: `requirements.txt` no fija versiones exactas a propósito para
  que `pip` resuelva wheels compatibles con tu intérprete.
