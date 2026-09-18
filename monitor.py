#!/usr/bin/env python3
"""
Monitor de fuentes tributarias y laborales — Póngase al Día
Revisa 16 fuentes colombianas, detecta contenido nuevo, filtra por relevancia,
clasifica por nivel de importancia y envía alertas por Telegram y Gmail.

Ejecutado automáticamente por GitHub Actions (ver .github/workflows/monitor.yml).
"""

import json
import os
import re
import smtplib
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuración general
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
TIMEOUT = 20
REGISTRY_PATH = Path(__file__).parent / "registro.json"

# Palabras clave que determinan relevancia tributaria/laboral (case-insensitive)
KEYWORDS = [
    "tributari", "tributario", "impuesto", "renta", "iva", "retenci",
    "dian", "declaraci", "aduaner", "arancel", "reforma tributaria",
    "calendario tributario", "sancion", "concepto", "oficio", "circular",
    "decreto", "resoluci", "laboral", "trabajo", "seguridad social",
    "pensi", "salario", "ugpp", "prima", "cesant", "eps", "afp", "arl",
    "estabilidad laboral", "despido", "contrato de trabajo", "niif",
    "revisor fiscal", "contable", "auditor", "supersociedades",
]

# Palabras/patrones que elevan una alerta a "alta importancia" (🔴)
HIGH_PRIORITY_PATTERNS = [
    r"\breforma tributaria\b",
    r"\bemergencia econ",
    r"\bdecreto legislativo\b",
    r"\bsu-\d+\b",  # sentencias de unificación
    r"\bc-\d+\b",   # sentencias de constitucionalidad
    r"\bcalendario tributario\b",
    r"\bplazo\b.*\bvence\b",
    r"\bvence\b.*\bplazo\b",
]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
GMAIL_TO = os.environ.get("GMAIL_TO", GMAIL_USER)


@dataclass
class Item:
    fuente: str
    titulo: str
    url: str
    fecha: str  # texto tal como aparece en la fuente
    resumen: str = ""
    nivel: str = "🟢"  # 🔴 🟠 🟡 🟢

    def key(self) -> str:
        return f"{self.fuente}::{self.url}"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def get_soup(url: str, timeout: int = TIMEOUT) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"  [WARN] fallo al descargar {url}: {exc}")
        return None


def is_relevant(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in KEYWORDS)


def classify_level(text: str) -> str:
    t = text.lower()
    for pattern in HIGH_PRIORITY_PATTERNS:
        if re.search(pattern, t):
            return "🔴"
    if any(k in t for k in ["dian", "concepto", "ctcp", "sentencia", "corte constitucional",
                             "consejo de estado", "corte suprema"]):
        return "🟠"
    if any(k in t for k in ["decreto", "resoluci", "circular", "noticia"]):
        return "🟡"
    return "🟢"


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        try:
            return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_registry(registry: dict) -> None:
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Extractores por fuente
# ---------------------------------------------------------------------------

def fetch_by_generic_cards(fuente: str, url: str, min_len: int = 15,
                            href_filter: str | None = None) -> list[Item]:
    """Extractor genérico: busca <h2>/<h3> dentro de <a>, o <a> con texto largo,
    en cualquier contenedor (article o div). Más resiliente a cambios de diseño
    que depender de una sola etiqueta semántica."""
    items = []
    soup = get_soup(url)
    if not soup:
        return items
    seen_urls = set()

    # Caso 1: título en h2/h3 dentro de <a>
    for heading in soup.select("h2, h3"):
        a = heading.find_parent("a", href=True) or heading.find("a", href=True)
        if not a:
            continue
        titulo = heading.get_text(strip=True)
        if not titulo or len(titulo) < min_len:
            continue
        href = urljoin(url, a["href"])
        if href_filter and href_filter not in href:
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)
        items.append(Item(fuente, titulo, href, ""))

    # Caso 2 (fallback): enlaces con texto largo directamente
    if not items:
        for a in soup.select("a[href]"):
            titulo = a.get_text(strip=True)
            if not titulo or len(titulo) < min_len:
                continue
            href = urljoin(url, a["href"])
            if href_filter and href_filter not in href:
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)
            items.append(Item(fuente, titulo, href, ""))

    return items[:30]


def fetch_siemprealdia() -> list[Item]:
    return fetch_by_generic_cards(
        "siemprealdia.co", "https://siemprealdia.co/colombia/impuestos/"
    )


def fetch_incp() -> list[Item]:
    return fetch_by_generic_cards(
        "incp.org.co", "https://incp.org.co/category/publicaciones/"
    )


def fetch_ambitojuridico() -> list[Item]:
    items = []
    for seccion, url in [
        ("tributario", "https://www.ambitojuridico.com/noticias/tributario"),
        ("laboral", "https://www.ambitojuridico.com/noticias/laboral"),
    ]:
        items.extend(
            fetch_by_generic_cards(f"ambitojuridico.com ({seccion})", url, href_filter="ambitojuridico.com")
        )
    return items


def fetch_nexiamya() -> list[Item]:
    # SPA con JS pesado: con requests simple el HTML inicial puede venir casi
    # vacío. Se intenta igual (a veces el listado ya viene server-rendered);
    # si no trae nada, GitHub Actions lo registrará como 0 y no falla el resto.
    return fetch_by_generic_cards(
        "nexiamya.com.co", "https://nexiamya.com.co/articulos/", href_filter="nexiamya.com.co"
    )


def fetch_accounter() -> list[Item]:
    return fetch_by_generic_cards("accounter.co", "https://accounter.co/")


def fetch_gerencie() -> list[Item]:
    return fetch_by_generic_cards("gerencie.com", "https://www.gerencie.com/")


def fetch_jcc() -> list[Item]:
    return fetch_by_generic_cards(
        "jcc.gov.co", "https://www.jcc.gov.co/noticias1", min_len=10
    )


def fetch_dian_normativa() -> list[Item]:
    items = []
    for url in [
        "https://www.dian.gov.co/normatividad/Paginas/Normatividad.aspx",
        "https://www.dian.gov.co/Prensa/Paginas/Noticias.aspx",
    ]:
        items.extend(fetch_by_generic_cards("dian.gov.co", url, min_len=20))
    # Solo lo relevante: esta fuente trae mucho ruido institucional
    return [i for i in items if is_relevant(i.titulo)]


def fetch_valoraanalitik() -> list[Item]:
    return fetch_by_generic_cards(
        "valoraanalitik.com", "https://www.valoraanalitik.com/noticias-financieras/"
    )


def fetch_noticieroficial() -> list[Item]:
    return fetch_by_generic_cards(
        "noticieroficial.com", "https://www.noticieroficial.com/", min_len=20
    )


def fetch_albaluciaorozco() -> list[Item]:
    return fetch_by_generic_cards(
        "albaluciaorozco.com", "https://www.albaluciaorozco.com/", min_len=10
    )


MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def fetch_cijuf() -> list[Item]:
    """cijuf publica un índice por mes; hay que navegar al mes vigente
    antes de poder leer los conceptos/oficios en sí."""
    items = []
    now = datetime.now()
    mes_actual = MESES_ES[now.month - 1]
    year_url = f"https://cijuf.org.co/normatividad/conceptos-y-oficios-dian/{now.year}"
    soup = get_soup(year_url)
    if not soup:
        return items

    target = year_url
    for a in soup.select("a[href]"):
        texto = a.get_text(strip=True).lower()
        if mes_actual in texto:
            target = urljoin(year_url, a["href"])
            break

    return fetch_by_generic_cards("cijuf.org.co", target, min_len=10)


SOURCES = [
    fetch_siemprealdia,
    fetch_incp,
    fetch_ambitojuridico,
    fetch_nexiamya,
    fetch_accounter,
    fetch_gerencie,
    fetch_jcc,
    fetch_dian_normativa,
    fetch_valoraanalitik,
    fetch_noticieroficial,
    fetch_albaluciaorozco,
    fetch_cijuf,
]


# ---------------------------------------------------------------------------
# Envío de alertas
# ---------------------------------------------------------------------------

def format_item_block(item: Item) -> str:
    return (
        f"{item.nivel} *{item.titulo}*\n"
        f"Fuente: {item.fuente}\n"
        f"{item.url}"
    )


def format_report(items: list[Item]) -> str:
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"📋 *Póngase al Día — Monitoreo {hoy}*", ""]
    alertas = [i for i in items if i.nivel == "🔴"]
    if alertas:
        lines.append("🚨 *ALERTA TRIBUTARIA/LABORAL IMPORTANTE*")
        for it in alertas:
            lines.append(format_item_block(it))
            lines.append("")
    resto = [i for i in items if i.nivel != "🔴"]
    if resto:
        lines.append(f"Otras {len(resto)} novedades detectadas:")
        for it in resto:
            lines.append(format_item_block(it))
            lines.append("")
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [INFO] Telegram no configurado (faltan TELEGRAM_TOKEN / TELEGRAM_CHAT_ID)")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Telegram limita ~4096 caracteres por mensaje; se trocea si es necesario
    chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)] or [text]
    for chunk in chunks:
        try:
            resp = requests.post(
                url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": chunk,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=TIMEOUT,
            )
            if resp.status_code != 200:
                print(f"  [WARN] Telegram respondió {resp.status_code}: {resp.text}")
        except Exception as exc:
            print(f"  [WARN] fallo enviando a Telegram: {exc}")
        time.sleep(1)


def send_gmail(subject: str, body: str) -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("  [INFO] Gmail no configurado (faltan GMAIL_USER / GMAIL_APP_PASSWORD)")
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_USER
        msg["To"] = GMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=TIMEOUT) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print("  [OK] Correo enviado")
    except Exception as exc:
        print(f"  [WARN] fallo enviando correo: {exc}")


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"=== Monitor Póngase al Día — {datetime.now().isoformat()} ===")
    registry = load_registry()
    nuevos: list[Item] = []

    for fetch_fn in SOURCES:
        nombre = fetch_fn.__name__
        print(f"[{nombre}] consultando...")
        try:
            found = fetch_fn()
        except Exception as exc:
            print(f"  [ERROR] {nombre} falló por completo: {exc}")
            continue
        print(f"  -> {len(found)} elementos leídos")

        for item in found:
            if not is_relevant(item.titulo):
                continue
            key = item.key()
            if key in registry:
                continue
            item.nivel = classify_level(item.titulo)
            registry[key] = {
                "titulo": item.titulo,
                "fecha_detectado": datetime.now(timezone.utc).isoformat(),
                "nivel": item.nivel,
            }
            nuevos.append(item)

    print(f"\nTotal de novedades relevantes nuevas: {len(nuevos)}")

    if nuevos:
        # Orden: alta prioridad primero
        orden = {"🔴": 0, "🟠": 1, "🟡": 2, "🟢": 3}
        nuevos.sort(key=lambda i: orden.get(i.nivel, 9))
        reporte = format_report(nuevos)
        print("\n--- REPORTE ---\n")
        print(reporte)
        send_telegram(reporte)
        send_gmail(
            subject=f"Póngase al Día — {len(nuevos)} novedades ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
            body=reporte,
        )
    else:
        print("Sin novedades relevantes en esta corrida.")

    save_registry(registry)
    print("Registro actualizado y guardado.")


if __name__ == "__main__":
    sys.exit(main() or 0)
