# WeatherEdgeflow

WeatherEdgeflow analiza mercados meteorológicos abiertos de venues tipo prediction market. Por defecto usa Kalshi (`VENUE=KALSHI`) porque expone market data pública y mercados meteorológicos accesibles desde API oficial. También conserva soporte opcional de Polymarket (`VENUE=POLYMARKET`) para entornos donde sea legal y accesible.

La aplicación compara precios ejecutables del orderbook contra pronósticos públicos, estima probabilidades mediante un motor determinístico y registra señales, descartes y operaciones PAPER en SQLite. Además incluye un módulo auxiliar `Crypto` que analiza carry spot/perp de Binance y barreras de BTC en Kalshi con datos públicos.

La aplicación tiene tres modos:

- `OBSERVE`: analiza y guarda snapshots sin simular posiciones.
- `PAPER`: modo por defecto, simula órdenes, fills, posiciones, PnL y bankroll virtual.
- `LIVE_SIGNAL`: genera recomendaciones manuales `BUY YES`, `BUY NO` o `NO TRADE`; no conecta wallets, no guarda private keys y no envía órdenes.

WeatherEdgeflow existe para buscar valor esperado positivo después de costes, incertidumbre y margen de seguridad. Si los datos no son suficientes, la decisión correcta es `NO TRADE`.

## Arquitectura

- Backend: Python 3.12, FastAPI, SQLAlchemy, APScheduler, httpx.
- Frontend: React + TypeScript + Vite, servido por FastAPI tras el build.
- Base de datos: SQLite en `data/weatheredgeflow.sqlite3`.
- Migraciones: SQL versionado en `backend/app/db/migrations`.
- APIs públicas: Kalshi Trade API, Open-Meteo, NOAA cuando aplica, Binance Spot/USDT-M market data, y soporte opcional para Gamma/CLOB de Polymarket.

Componentes principales:

- `KalshiClient`: descubre mercados meteorológicos, lee orderbooks, bid/ask, spread, fees estimados y market data pública.
- `KalshiWeatherMarketParser` y `WeatherMarketParser`: aceptan sólo temperatura máxima/mínima diaria con ciudad, fecha, unidad, fuente y outcomes interpretables.
- `PolymarketClient`: soporte opcional para Gamma/CLOB cuando `VENUE=POLYMARKET`.
- `OpenMeteoProvider` y `NOAAProvider`: pronóstico, condiciones actuales y observaciones.
- `ForecastEnsemble`: conserva predicciones por modelo.
- `ProbabilityEngine`: distribución probabilística auditable, sin LLM.
- `EdgeCalculator`: resta fees, spread, slippage, incertidumbre y margen.
- `LiquidityFilter`: bloquea orderbooks vacíos, spreads grandes y liquidez insuficiente.
- `RiskManager`: centraliza límites de bankroll y exposición.
- `PaperExecutionEngine`: simula fills sólo contra liquidez disponible.
- `ResolutionEngine`: actualiza PnL PAPER cuando el venue publica resolución.
- `CryptoCarryEngine`: monitorea carry spot/perp en Binance, pero no crea operaciones reales.
- `CryptoBarrierEngine`: estima probabilidades de mercados Kalshi de barreras BTC usando precio spot y volatilidad realizada de Binance.

## Instalación local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Set-Location frontend
npm install
npm run build
Set-Location ..
Copy-Item .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

Dashboard:

```text
http://127.0.0.1:8000
```

Health:

```text
http://127.0.0.1:8000/health
```

## Docker

```powershell
Copy-Item .env.example .env
docker compose up -d
docker compose logs -f
docker compose down
```

SQLite y logs persisten en:

- `data/`
- `logs/`

## GitHub Actions PAPER Scan

El repo incluye `.github/workflows/paper-scan.yml`. Sirve para correr un scan `PAPER` cada 20 minutos en servidores de GitHub y subir un artefacto con:

- `reports/latest_scan.json`
- `reports/latest_scan.md`
- `data/weatheredgeflow-actions.sqlite3`
- `data/weatheredgeflow-actions.log`

Esto no reemplaza un VPS con dashboard 24/7, pero permite recolectar señales sin dejar la PC encendida. No ejecuta operaciones reales.

## Variables de entorno

Valores seguros por defecto:

```text
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
MODE=PAPER
VENUE=KALSHI
KALSHI_SERIES_TICKERS=KXHIGHNY,KXHIGHCHI,KXHIGHMIA,KXHIGHLAX,KXHIGHDEN
BINANCE_SPOT_BASE_URL=https://api.binance.com
BINANCE_FUTURES_BASE_URL=https://fapi.binance.com
CRYPTO_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
KALSHI_CRYPTO_SERIES_TICKERS=KXBTCMAXY,KXBTCMINY
CRYPTO_BARRIER_MIN_NET_EDGE=0.15
CRYPTO_BARRIER_SAFETY_MARGIN=0.08
```

No se requieren credenciales privadas. No configures seed phrases ni private keys: la aplicación no las usa.

## PAPER MODE

`PAPER` usa bankroll virtual independiente. El bot crea órdenes simuladas sólo si:

- hay orderbook ejecutable;
- el stake cumple mínimos;
- la liquidez cubre el tamaño;
- el edge neto supera el mínimo;
- RiskManager aprueba el tamaño;
- no están activos `PAUSE BOT` ni `KILL SWITCH`.

## LIVE SIGNAL MODE

`LIVE_SIGNAL` calcula recomendaciones reales con precios públicos, pero la ejecución es manual en el venue elegido. El botón `ABRIR MERCADO` abre el mercado para que el usuario decida.

La aplicación no firma, no custodia y no envía órdenes.

Antes de cargar fondos reales en cualquier venue, verificá elegibilidad, regulación local, KYC, métodos de retiro y riesgos. WeatherEdgeflow no evita bloqueos legales ni automatiza trading real.

## Dashboard

La cabecera muestra:

- modo;
- estado del sistema;
- último y próximo scan;
- bankroll;
- PnL de hoy;
- PnL total;
- ROI;
- exposición abierta.

Páginas:

- `Oportunidades`: tabla principal y detalle completo por señal.
- `Crypto`: señales auxiliares de carry Binance y barreras BTC Kalshi.
- `Cartera`: bankroll, cash, exposición, PnL, posiciones e historial.
- `Rendimiento`: señales, trades, edge promedio, calibración y buckets.
- `Actividad`: log humano de cada ciclo.
- `Settings`: idioma, modo, bankroll, límites y controles.

## Cambiar bankroll y riesgo

En `Settings`, modificar reglas sensibles pide confirmación. Ningún componente cambia automáticamente:

- `MIN_NET_EDGE`;
- stake máximo;
- exposición máxima;
- límite diario;
- drawdown máximo;
- modelo probabilístico;
- algoritmo de riesgo.

## Detener el bot

- `PAUSE BOT`: no crea nuevas posiciones PAPER; sigue actualizando información y resoluciones.
- `KILL SWITCH`: deshabilita recomendaciones accionables hasta reactivación manual.

## Migración a VPS

La guía rápida para Oracle Cloud Always Free está en `deploy/README_VPS.md`.
La guía específica para Northflank Sandbox está en `deploy/NORTHFLANK.md`.

1. Instalar Docker y Docker Compose.
2. Copiar el proyecto al VPS.
3. Crear `.env` desde `.env.example`.
4. Ejecutar:

```bash
docker compose up -d
```

5. Abrir `http://IP_DEL_VPS:8000`.
6. Revisar `/health` y `docker compose logs -f`.

Para un VPS barato, mantener SQLite con volumen persistente es suficiente para V1. PostgreSQL puede añadirse cambiando `DATABASE_URL` y agregando migraciones equivalentes.

## Troubleshooting

- `DEGRADED`: la app y DB funcionan, pero alguna API externa falló o fue rate-limited.
- `NO TRADE`: decisión esperada cuando no hay edge neto suficiente o faltan datos.
- `BELOW_MIN_ORDER`: el stake configurado es menor que el mínimo del mercado.
- `UNKNOWN_RESOLUTION_SOURCE`: el mercado no tiene reglas/fuente suficientes para V1.
- `NO_ORDERBOOK`: el venue no devolvió libro ejecutable.
- `EDGE_BELOW_THRESHOLD`: la cuota parece interesante, pero después de spread, costes y margen no alcanza.

## English Short Section

WeatherEdgeflow is a public-data-only weather prediction-market scanner. It defaults to Kalshi market data, keeps optional Polymarket support, compares executable orderbook prices with deterministic weather probabilities, records all snapshots in SQLite, and supports `OBSERVE`, `PAPER`, and `LIVE_SIGNAL` modes. `LIVE_SIGNAL` never places trades; it only shows manual recommendations.

Run locally:

```bash
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

Run with Docker:

```bash
docker compose up -d
```
