# Freqtrade Sidecar para WeatherEdgeflow

Este directorio integra Freqtrade como bot open-source externo en modo `dry-run`. Freqtrade es un proyecto público mantenido por la comunidad: https://github.com/freqtrade/freqtrade

La configuración incluida no opera dinero real:

- `dry_run=true`
- claves de exchange vacías
- spot solamente
- sin apalancamiento
- stake simulado de 10 USDT
- wallet simulado de 100 USDT
- UI enlazada sólo a `127.0.0.1:8081`

## Ejecutar

```powershell
docker compose -f docker-compose.freqtrade.yml pull
docker compose -f docker-compose.freqtrade.yml up -d
docker compose -f docker-compose.freqtrade.yml logs -f
```

UI local:

```text
http://127.0.0.1:8081
```

Usuario local:

```text
weatheredge
```

Password local:

```text
change-this-local-password
```

## Backtest rápido

```powershell
docker compose -f docker-compose.freqtrade.yml run --rm freqtrade-dryrun download-data --config /freqtrade/user_data/config.json --days 30 -t 5m
docker compose -f docker-compose.freqtrade.yml run --rm freqtrade-dryrun backtesting --config /freqtrade/user_data/config.json --strategy WeatherEdgeflowGuardedStrategy -i 5m
```

## Seguridad

No cargues API keys reales en esta configuración. Para operar real se necesita una revisión humana separada, exchange compatible, permisos correctos, cumplimiento de términos y un despliegue propio. Esta integración está diseñada para observación, paper trading y backtesting.
