# Monitor Póngase al Día

Monitorea automáticamente 12 fuentes colombianas de doctrina y noticias tributarias/laborales, detecta contenido nuevo relevante y envía alertas por Telegram y Gmail.

## Fuentes monitoreadas

- siemprealdia.co (impuestos)
- incp.org.co (publicaciones)
- ambitojuridico.com (tributario y laboral)
- nexiamya.com.co (artículos)
- accounter.co
- gerencie.com
- jcc.gov.co (noticias)
- dian.gov.co (normatividad y prensa)
- valoraanalitik.com (noticias financieras)
- noticieroficial.com (portada gratuita)
- albaluciaorozco.com
- cijuf.org.co (conceptos y oficios DIAN)

## Cómo funciona

1. `monitor.py` descarga cada fuente y extrae títulos/enlaces.
2. Filtra por palabras clave tributarias/laborales.
3. Compara contra `registro.json` para detectar solo lo **nuevo**.
4. Clasifica cada novedad por nivel de importancia (🔴🟠🟡🟢).
5. Envía un reporte consolidado por Telegram y por Gmail.
6. Actualiza `registro.json` para no repetir alertas en la próxima corrida.

## Configuración necesaria (GitHub Secrets)

En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Valor |
|---|---|
| `TELEGRAM_TOKEN` | Token del bot de Telegram (desde @BotFather) |
| `TELEGRAM_CHAT_ID` | Chat ID de Oscar en Telegram |
| `GMAIL_USER` | Correo de Gmail que envía las alertas |
| `GMAIL_APP_PASSWORD` | Contraseña de aplicación de Gmail (no la contraseña normal) |
| `GMAIL_TO` | Correo que recibe las alertas (puede ser el mismo GMAIL_USER) |

## Horario

Corre automáticamente 3 veces al día (7am, 1pm, 6pm hora Colombia) vía GitHub Actions.
También se puede ejecutar manualmente desde la pestaña "Actions" del repositorio → "Monitor Póngase al Día" → "Run workflow".
