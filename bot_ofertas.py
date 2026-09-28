"""
Bot de ofertas de tecnología: Slickdeals (RSS) -> Discord (webhook).

Uso:
    pip install feedparser requests
    python bot_ofertas.py            # corre en bucle cada INTERVALO_MIN
    python bot_ofertas.py --una-vez  # una sola pasada (para cron / Task Scheduler)
"""

import json
import os
import re
import sys
import time
import html

import feedparser
import requests

# ======================= CONFIGURACIÓN =======================

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "PEGA_AQUI_TU_WEBHOOK")

# Umbrales
PRECIO_MAX = 400          # USD: nada por encima de esto, aunque tenga 50 % off
DESCUENTO_MIN = 30        # % mínimo de descuento (cuando se puede detectar)
EXIGIR_DESCUENTO = False  # True = descarta ofertas sin % detectable
SOLO_AMAZON = False       # True = solo ofertas de Amazon

INTERVALO_MIN = 5         # minutos entre revisiones

# Feeds curados por la comunidad (ya son "buenas" ofertas; aquí solo filtramos)
FEEDS = [
    "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1",
    "https://slickdeals.net/newsearch.php?mode=popdeals&searcharea=deals&searchin=first&rss=1",
    "https://slickdeals.net/newsearch.php?searchin=first&forumchoice%5B%5D=9&rss=1",
]

# Categorías: al menos una palabra debe aparecer en el título
CATEGORIAS = [
    "laptop", "notebook", "chromebook", "macbook", "ultrabook",
    "phone", "smartphone", "iphone", "galaxy s", "galaxy z", "pixel",
    "watch", "smartwatch", "fitbit", "garmin",
    "earbuds", "headphones", "airpods", "buds", "speaker",
    "tablet", "ipad", "kindle", "monitor", "ssd", "power bank",
    "charger", "keyboard", "mouse", "router", "webcam", "drone",
]

# Marcas reconocidas: al menos una debe aparecer en el título
MARCAS = [
    "apple", "iphone", "ipad", "macbook", "airpods", "samsung", "galaxy",
    "google", "pixel", "sony", "bose", "jbl", "anker", "lenovo", "thinkpad",
    "dell", "hp", "asus", "acer", "msi", "microsoft", "surface", "logitech",
    "garmin", "fitbit", "amazfit", "xiaomi", "oneplus", "motorola", "nothing",
    "razer", "corsair", "tp-link", "eero", "kindle", "sandisk", "crucial",
    "western digital", "wd", "lg", "dji", "beats", "sennheiser", "casio",
    "seiko", "citizen",
]

# Palabras que descartan la oferta (accesorios baratos, etc.)
EXCLUIR = ["case", "screen protector", "cover", "strap", "band only", "cable only"]

# Usados / reacondicionados: se aceptan, pero con umbrales más exigentes
ACEPTAR_USADOS = True
PALABRAS_USADO = ["refurbished", "renewed", "used", "pre-owned", "open box",
                  "open-box", "certified refurb", "recertified", "like new"]
PRECIO_MAX_USADO = 300    # USD
DESCUENTO_MIN_USADO = 50  # % (vs. precio nuevo)
EXIGIR_DESCUENTO_USADO = True  # sin descuento confirmado no se sabe si vale la pena

ARCHIVO_VISTOS = "ofertas_vistas.json"

# ================== FIN DE CONFIGURACIÓN =====================

RE_PRECIO = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")
RE_PORCENTAJE = re.compile(r"(\d{1,2})\s?%\s?off", re.I)
RE_ORIGINAL = re.compile(
    r"(?:list(?:\s+price)?|reg(?:ular|\.)?|was|msrp|orig(?:inal|\.)?)\s*:?\s*\$\s?"
    r"(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", re.I)


def a_numero(s):
    return float(s.replace(",", ""))


def contiene(texto, palabras):
    t = f" {texto.lower()} "
    return any(re.search(rf"(?<![a-z]){re.escape(p)}(?![a-z])", t) for p in palabras)


def limpiar_html(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s or ""))


def analizar(entrada):
    """Devuelve dict con precio, precio original y descuento (si se detectan)."""
    titulo = entrada.get("title", "")
    desc = limpiar_html(entrada.get("summary", ""))

    precios = RE_PRECIO.findall(titulo)
    precio = a_numero(precios[0]) if precios else None

    original = None
    m = RE_ORIGINAL.search(desc) or RE_ORIGINAL.search(titulo)
    if m:
        original = a_numero(m.group(1))

    descuento = None
    m = RE_PORCENTAJE.search(titulo) or RE_PORCENTAJE.search(desc)
    if m:
        descuento = int(m.group(1))
    elif precio and original and original > precio:
        descuento = round((1 - precio / original) * 100)

    tienda_amazon = "amazon" in (titulo + " " + desc).lower()
    usado = contiene(titulo, PALABRAS_USADO)
    return {"precio": precio, "original": original, "descuento": descuento,
            "amazon": tienda_amazon, "usado": usado}


def pasa_filtros(entrada, info):
    titulo = entrada.get("title", "")
    if not contiene(titulo, CATEGORIAS):
        return False, "categoría"
    if not contiene(titulo, MARCAS):
        return False, "marca"
    if contiene(titulo, EXCLUIR):
        return False, "excluido"
    if SOLO_AMAZON and not info["amazon"]:
        return False, "no es Amazon"
    if info["precio"] is None:
        return False, "sin precio"

    if info["usado"]:
        if not ACEPTAR_USADOS:
            return False, "usado"
        pmax, dmin, exigir = PRECIO_MAX_USADO, DESCUENTO_MIN_USADO, EXIGIR_DESCUENTO_USADO
    else:
        pmax, dmin, exigir = PRECIO_MAX, DESCUENTO_MIN, EXIGIR_DESCUENTO

    if info["precio"] > pmax:
        return False, f"precio > ${pmax}"
    if info["descuento"] is None:
        if exigir:
            return False, "descuento no detectable"
    elif info["descuento"] < dmin:
        return False, f"descuento < {dmin}%"
    return True, "ok"


def cargar_vistos():
    """Dict {id_oferta: timestamp}. Orden estable para no generar commits vacíos."""
    try:
        with open(ARCHIVO_VISTOS, encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def guardar_vistos(vistos):
    recientes = sorted(vistos.items(), key=lambda kv: kv[1])[-3000:]
    with open(ARCHIVO_VISTOS, "w", encoding="utf-8") as f:
        json.dump(dict(recientes), f, indent=0, sort_keys=True)


def enviar_discord(entrada, info):
    precio = f"${info['precio']:,.2f}"
    if info["original"]:
        precio += f"  ~~${info['original']:,.2f}~~"
    campos = [{"name": "Precio", "value": precio, "inline": True}]
    if info["descuento"] is not None:
        campos.append({"name": "Descuento", "value": f"{info['descuento']}%", "inline": True})
    if info["amazon"]:
        campos.append({"name": "Tienda", "value": "Amazon", "inline": True})
    campos.append({"name": "Estado",
                   "value": "♻️ Usado / reacondicionado" if info["usado"] else "Nuevo",
                   "inline": True})

    payload = {"embeds": [{
        "title": entrada.get("title", "")[:250],
        "url": entrada.get("link"),
        "color": 0xF39C12 if info["usado"] else 0x2ECC71,
        "fields": campos,
        "footer": {"text": "Slickdeals"},
    }]}
    r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=15)
    if r.status_code == 429:  # rate limit de Discord
        time.sleep(r.json().get("retry_after", 2))
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=15)


def revisar(vistos, primera_vez=False):
    nuevas = 0
    for url in FEEDS:
        feed = feedparser.parse(url, agent="Mozilla/5.0 (bot-ofertas)")
        estado = getattr(feed, "status", "?")
        print(f"Feed {estado}: {len(feed.entries)} ofertas <- {url[:70]}...")
        if not feed.entries:
            print("  ⚠ Feed vacío o bloqueado:", feed.get("bozo_exception", ""))
        for e in feed.entries:
            uid = e.get("id") or e.get("link")
            if not uid or uid in vistos:
                continue
            vistos[uid] = int(time.time())
            if primera_vez:
                continue  # no inundar Discord con lo que ya estaba publicado
            info = analizar(e)
            ok, motivo = pasa_filtros(e, info)
            if ok:
                enviar_discord(e, info)
                nuevas += 1
                print(f"[ENVIADA] {e.title}")
                time.sleep(1)
    guardar_vistos(vistos)
    return nuevas


def main():
    if "PEGA_AQUI" in DISCORD_WEBHOOK:
        sys.exit("Configura DISCORD_WEBHOOK (variable de entorno o en el script).")
    vistos = cargar_vistos()
    primera = not vistos
    if primera:
        print("Primera ejecución: registrando ofertas actuales sin notificar.")

    if "--una-vez" in sys.argv:
        revisar(vistos, primera)
        return

    while True:
        try:
            n = revisar(vistos, primera)
            print(f"{time.strftime('%H:%M')} - {n} oferta(s) enviada(s)")
        except Exception as ex:
            print("Error:", ex)
        primera = False
        time.sleep(INTERVALO_MIN * 60)


if __name__ == "__main__":
    main()
