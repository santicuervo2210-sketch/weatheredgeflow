# WeatherEdgeflow en VPS gratis

## Recomendación

Para correr 24/7 gratis, la opción más razonable es **Oracle Cloud Always Free**. WeatherEdgeflow ya funciona con Docker y SQLite persistente, así que encaja bien en una VM chica.

Render Free no es ideal para este bot porque duerme servicios web inactivos. Fly.io ya no es una opción gratis permanente para workloads always-on.

## Importante

WeatherEdgeflow queda en `PAPER` por defecto. No ejecuta operaciones reales, no guarda claves privadas y no debe usarse para evadir restricciones legales o geográficas.

Antes de cargar dinero real en un venue, verificá:

- elegibilidad de tu país;
- KYC aprobado;
- depósitos y retiros disponibles;
- comisiones;
- reglas del contrato;
- que puedas retirar fondos.

## Pasos

1. Crear una cuenta en Oracle Cloud Free Tier.
2. Crear una VM Ubuntu Always Free.
3. Abrir puerto TCP `8000` en la Security List / Network Security Group de Oracle.
4. Conectarte por SSH.
5. Subir este repo a GitHub privado o público.
6. Ejecutar:

```bash
REPO_URL=https://github.com/TU_USUARIO/weatheredgeflow.git sudo -E bash deploy/oracle_free_tier_setup.sh
```

7. Abrir:

```text
http://IP_DEL_VPS:8000
```

## Comandos útiles

```bash
cd /opt/weatheredgeflow
docker compose ps
docker compose logs -f
docker compose restart
docker compose pull
docker compose up -d --build
```

## Configuración inicial recomendada

```env
VENUE=KALSHI
MODE=PAPER
INITIAL_BANKROLL_USD=10.00
PAPER_BANKROLL_USD=10.00
MIN_NET_EDGE=0.10
MAX_POSITION_USD=1.00
SCAN_INTERVAL_MINUTES=20
```

## Para dejarlo corriendo esta noche

Si ya tenés la VM creada, el script la deja corriendo con `restart: unless-stopped` desde `docker-compose.yml`.

Si todavía no tenés cuenta Oracle, no hay forma segura de que yo la cree por vos: requiere datos personales y método de verificación.
