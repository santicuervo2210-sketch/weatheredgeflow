# WeatherEdgeflow en Northflank Sandbox

Esta guía es para dejar WeatherEdgeflow corriendo en Northflank sin usar tu PC. Northflank es hosting; no es la plataforma donde depositás dinero.

## Estado seguro

Dejar inicialmente:

```env
VENUE=KALSHI
MODE=PAPER
INITIAL_BANKROLL_USD=10.00
PAPER_BANKROLL_USD=10.00
MAX_POSITION_USD=1.00
MIN_NET_EDGE=0.10
SCAN_INTERVAL_MINUTES=20
```

No configures API keys de trading ni claves privadas. Este proyecto no las necesita para `PAPER`.

## Requisitos

- Cuenta Northflank.
- Un repo GitHub/GitLab/Bitbucket con este proyecto.
- Servicio creado desde el `Dockerfile`.
- Volumen persistente montado en `/app/data`.

## Pasos en Northflank

1. Crear `Project`.
2. Crear `Service`.
3. Elegir `Repository` como fuente.
4. Conectar el repo de WeatherEdgeflow.
5. Build option: `Dockerfile`.
6. Dockerfile path: `Dockerfile`.
7. Build context: `/`.
8. Port: `8000` público HTTP.
9. Health check path: `/health`.
10. Agregar volumen persistente:

```text
Mount path: /app/data
Size: mínimo disponible
```

11. Variables de entorno:

```env
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
DATABASE_URL=sqlite:////app/data/weatheredgeflow.sqlite3
LOG_LEVEL=INFO
LOG_FILE=/app/data/weatheredgeflow.log
VENUE=KALSHI
MODE=PAPER
INITIAL_BANKROLL_USD=10.00
PAPER_BANKROLL_USD=10.00
MAX_POSITION_PERCENT=10
MAX_POSITION_USD=1.00
MAX_TOTAL_EXPOSURE_PERCENT=25
MAX_DAILY_LOSS_PERCENT=10
MAX_DRAWDOWN_PERCENT=30
MIN_NET_EDGE=0.10
MIN_CONFIDENCE=55
MAX_SPREAD=0.08
SCAN_INTERVAL_MINUTES=20
USER_TIMEZONE=America/Argentina/Buenos_Aires
SAFETY_MARGIN=0.03
ACTIONABLE_HORIZON_HOURS=24
PREFERRED_HORIZON_HOURS=24
MAX_MARKETS_PER_SCAN=250
KALSHI_BASE_URL=https://external-api.kalshi.com/trade-api/v2
KALSHI_SERIES_TICKERS=KXHIGHNY,KXHIGHCHI,KXHIGHMIA,KXHIGHLAX,KXHIGHDEN
OPENMETEO_FORECAST_BASE_URL=https://api.open-meteo.com/v1
OPENMETEO_GEOCODING_BASE_URL=https://geocoding-api.open-meteo.com/v1
NOAA_BASE_URL=https://api.weather.gov
HTTP_TIMEOUT_SECONDS=12
```

12. Deploy.
13. Abrir la URL pública del servicio.
14. Verificar:

```text
/health
```

Debe mostrar:

```json
{"status":"ONLINE"}
```

## Plataforma donde abrir cuenta para operar manualmente

La plataforma de mercado configurada es **Kalshi**:

```text
https://kalshi.com
```

Depositá sólo desde métodos oficiales dentro de Kalshi, a tu nombre y después de KYC aprobado. No deposites dinero en direcciones o cuentas copiadas desde chats.

## Si Northflank pide upgrade o tarjeta

No actives pagos apurado. Corré el bot local de 13:00 a 17:00 en `PAPER`, o buscá otra opción. Para un bot que necesita scheduler 24/7, las opciones gratis sin tarjeta suelen dormir o tener límites fuertes.
